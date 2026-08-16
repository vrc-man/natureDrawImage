"""从 animadex.net 下载角色缩略图，导入本地 AI 助手角色库。

背景：AI 助手角色库（ai_chat_data.db，danbooru_tag）需要本地缩略图。
AnimaDex 的 characters.csv 的 `character` 列 = danbooru slug（与角色库同源），
缩略图为高质量 WebP。

流程：
  1. 用 export token 调 animadex.net/api/export/manifest 拿 R2 下载地址；
  2. 下载 characters.csv；
  3. 只下载「角色库中存在」的角色缩略图，按 {danbooru_tag}.webp 重命名
     写入 character_thumbnails/；
  4. 生成 index.json（与后端 _load_local_thumbs 兼容）。

用法（token 申请：animadex.net 登录 → Account → Offline dataset export）：
    python scripts/animadex_import_thumbs.py --token YOUR_TOKEN [--dry-run] [--limit N]
    python scripts/animadex_import_thumbs.py --token YOUR_TOKEN --only hatsune_miku,cirno
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

import httpx

SITE = "https://animadex.net"
USER_AGENT = "animadex-import/1"

_client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120,
                       follow_redirects=True, limits=httpx.Limits(max_connections=8))

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DB_PATH = _WEB_DIR / "features" / "ai_chat" / "config" / "ai_chat_data.db"
THUMB_DIR = _WEB_DIR / "features" / "ai_chat" / "skills" / "search_characters" / "character_thumbnails"
INDEX_JSON = THUMB_DIR / "index.json"

ILLEGAL_FS_CHARS = '<>:"/\\|?*'


def sanitize_filename(name: str) -> str:
    cleaned = "".join("_" if c in ILLEGAL_FS_CHARS else c for c in name)
    return cleaned.rstrip(" .") or "unnamed"


def log(msg: str):
    line = time.strftime("%H:%M:%S") + "  " + msg
    print(line, flush=True)
    try:
        with open(THUMB_DIR / "animadex_import.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _get(url, headers=None, timeout=120, retries=4, retry_429=True):
    """GET 返回 (status, bytes)。429 退避重试；retry_429=False 时直接抛 HTTPError。"""
    last = None
    for attempt in range(retries):
        try:
            r = _client.get(url, headers=headers or {}, timeout=timeout)
            if r.status_code == 429:
                if not retry_429:
                    raise urllib.error.HTTPError(url, 429, "Too Many Requests", r.headers, None)
                wait = 2 ** attempt
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        wait = float(ra)
                    except Exception:
                        pass
                time.sleep(min(wait, 30))
                last = urllib.error.HTTPError(url, 429, "Too Many Requests", r.headers, None)
                continue
            r.raise_for_status()
            return r.status_code, r.content
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429:
                if not retry_429:
                    raise urllib.error.HTTPError(url, 429, "Too Many Requests", e.response.headers, None)
                last = urllib.error.HTTPError(url, 429, "Too Many Requests", e.response.headers, None)
                time.sleep(min(2 ** attempt, 30))
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    if last:
        raise last
    raise RuntimeError("_get failed")


def fetch_manifest(token, want_full=True):
    base = SITE + "/api/export/manifest"
    try:
        url = base + ("?full=1" if want_full else "")
        _, body = _get(url, {"X-Export-Token": token}, retry_429=False)
        return json.loads(body.decode("utf-8")), want_full
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # full 被 48h 锁：降级 delta
            print("  ! Full download locked (48h rate limit). Falling back to delta.")
            _, body = _get(base, {"X-Export-Token": token}, retry_429=False)
            return json.loads(body.decode("utf-8")), False
        if e.code == 401:
            sys.exit("Token rejected. Regenerate at animadex.net/account.")
        if e.code == 503:
            sys.exit("Catalogue export not published yet. Try later.")
        raise


def load_local_tags() -> set:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return {str(t) for (t,) in conn.execute("SELECT danbooru_tag FROM character") if t}
    finally:
        conn.close()


def load_existing() -> set:
    existing = set()
    if INDEX_JSON.is_file():
        try:
            data = json.load(open(INDEX_JSON, encoding="utf-8"))
            existing = {str(k) for k, v in (data.get("thumbs") or {}).items() if v}
        except Exception:
            pass
    for p in THUMB_DIR.glob("*.webp"):
        existing.add(p.stem)
    return existing


def download(url, dest: Path, retries=6):
    """用 httpx 下载（连接复用）到临时文件后原子改名。429 按 Retry-After 等待重试。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err = None
    for attempt in range(retries):
        try:
            r = _client.get(url, timeout=120)
            if r.status_code == 429:
                wait = 2 ** attempt
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        wait = float(ra)
                    except Exception:
                        pass
                time.sleep(min(wait, 30))
                last_err = urllib.error.HTTPError(url, 429, "Too Many Requests", r.headers, None)
                continue
            r.raise_for_status()
            tmp.write_bytes(r.content)
            os.replace(tmp, dest)
            return
        except httpx.HTTPStatusError as e:
            last_err = urllib.error.HTTPError(url, e.response.status_code, str(e), e.response.headers, None)
            if e.response.status_code == 429:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise last_err
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise last_err if last_err else RuntimeError("download failed")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--token", required=True, help="animadex.net export token")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不下载")
    ap.add_argument("--limit", type=int, default=None, help="最多下载 N 个（调试）")
    ap.add_argument("--only", type=str, default="", help="逗号分隔指定 tag，只下载这些")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args(argv)

    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    for p in THUMB_DIR.glob("*.part"):
        try:
            p.unlink()
        except Exception:
            pass
    local_tags = load_local_tags()
    existing = load_existing()
    log(f"角色库 tag 总数: {len(local_tags)}，已导入: {len(existing)}")

    only = {t.strip() for t in args.only.split(",") if t.strip()} if args.only else None

    log("联系 %s ..." % SITE)
    man, did_full = fetch_manifest(args.token)
    r2 = man["r2_base"].rstrip("/")
    pref = {k: f"{r2}/{v}" for k, v in man["prefixes"].items()}
    log(f"Catalogue version {man.get('version')} · mode: {'FULL' if did_full else 'delta'}")

    # 下载 characters.csv（缓存：已有且非空则复用，避免重复下载）
    csv_url = man["csv"]["characters"]
    csv_path = THUMB_DIR / "_characters.csv"
    if csv_path.is_file() and csv_path.stat().st_size > 100000:
        log("复用缓存的 characters.csv")
    else:
        log("下载 characters.csv ...")
        download(csv_url, csv_path)
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    log(f"characters.csv 行数: {len(rows)}")

    # 规划下载（只挑角色库存在的）
    jobs = []
    for row in rows:
        slug = (row.get("character") or "").strip()
        if not slug or slug not in local_tags:
            continue
        if only and slug not in only:
            continue
        if slug in existing:
            continue
        thumbname = (row.get("thumbname") or "").strip()
        if not thumbname:
            thumbname = sanitize_filename(row.get("trigger") or slug) + ".webp"
        dest = THUMB_DIR / (sanitize_filename(slug) + ".webp")
        if dest.exists():
            existing.add(slug)
            continue
        jobs.append((f"{pref['char_thumb']}/{quote(thumbname, safe='()')}", slug, dest))

    log(f"待下载: {len(jobs)} 个（角色库匹配且本地缺失）")
    if args.limit:
        jobs = jobs[:args.limit]
        log(f"  --limit 截断为 {len(jobs)} 个")
    if not jobs:
        log("无待下载项，结束。")
        return
    if args.dry_run:
        log("  [dry-run] 示例下载项:")
        for u, slug, d in jobs[:5]:
            log(f"    {slug}  <-  {u}")
        return

    # 并发下载（429 限流任务自动重排队，最多 3 轮）
    ok = fail = 0
    downloaded = {}
    retry_batch = jobs
    for round_no in range(4):
        if not retry_batch:
            break
        pending = []
        if round_no > 0:
            log(f"  第 {round_no + 1} 轮重试 {len(retry_batch)} 个（限流）")
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(download, u, d): (u, slug, d) for u, slug, d in retry_batch}
            for i, fut in enumerate(as_completed(futs), 1):
                u, slug, d = futs[fut]
                try:
                    fut.result()
                    ok += 1
                    downloaded[slug] = sanitize_filename(slug) + ".webp"
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        pending.append((u, slug, d))  # 下轮重试
                        continue
                    fail += 1
                    if e.code != 404:
                        log(f"  ! {slug} -> HTTP {e.code}")
                except Exception as e:
                    fail += 1
                    log(f"  ! {slug} -> {e}")
                if i % 200 == 0 or i == len(futs):
                    log(f"  下载 {i}/{len(futs)}（累计成功 {ok} 失败 {fail}）")
        retry_batch = pending
    if retry_batch:
        log(f"  仍有 {len(retry_batch)} 个持续限流未完成")

    # 写 index.json（与已有合并）
    idx = {}
    if INDEX_JSON.is_file():
        try:
            idx = json.load(open(INDEX_JSON, encoding="utf-8")).get("thumbs") or {}
        except Exception:
            idx = {}
    idx.update(downloaded)
    data = {"version": 1, "updated_at": int(time.time()), "total": len(idx), "thumbs": idx}
    tmp = INDEX_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(INDEX_JSON)
    log(f"index.json 更新完成，累计 {len(idx)} 张。成功 {ok} 失败 {fail}")
    try:
        csv_path.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()


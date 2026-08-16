"""批量翻译角色库 danbooru_tag → 中文名，写入 name_cn 列。

用 ai_chat.json 的 active_llm（deepseek）批量翻译。支持断点续传（跳过已有中文名）、
批内重试、进度显示。用法：

    python scripts/translate_char_cn.py [--limit N] [--batch 20] [--only tag1,tag2]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
CFG_PATH = WEB_DIR / "features" / "ai_chat" / "config" / "ai_chat.json"
DB_PATH = WEB_DIR / "features" / "ai_chat" / "config" / "ai_chat_data.db"


def load_env():
    """从 .env 加载 LLM_ENCRYPTION_KEY（若未在环境变量）。"""
    if os.environ.get("LLM_ENCRYPTION_KEY"):
        return
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("LLM_ENCRYPTION_KEY="):
                os.environ["LLM_ENCRYPTION_KEY"] = line.split("=", 1)[1].strip()


def decrypt_key(cipher: str) -> str:
    if not cipher or not cipher.startswith("fernet:"):
        return cipher
    env_key = os.environ.get("LLM_ENCRYPTION_KEY", "")
    if not env_key:
        return cipher
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"llm-api-key-v2")
    key = base64.urlsafe_b64encode(hkdf.derive(env_key.encode()))
    try:
        return Fernet(key).decrypt(cipher[7:].encode()).decode()
    except Exception:
        return cipher


def get_llm():
    cfg = json.load(open(CFG_PATH, encoding="utf-8"))
    llms = cfg.get("llms") or []
    active = cfg.get("active_llm_id", "")
    llm = next((x for x in llms if x.get("id") == active), llms[0] if llms else None)
    if not llm:
        raise SystemExit("未配置 LLM")
    return {
        "endpoint": str(llm.get("endpoint", "")).rstrip("/"),
        "model": str(llm.get("model", "")),
        "api_key": decrypt_key(str(llm.get("api_key", "") or "").strip()),
    }


PROMPT_TMPL = (
    "把下面这些英文 Danbooru 动漫/游戏角色标签翻译成对应的中文常用名。\n"
    "规则：1) 知名角色用官方中文名（如 hatsune_miku → 初音未来，asuka_langley_sohryu → 明日香）；\n"
    "2) 括号内的作品后缀不翻译、保留原样；\n"
    "3) 不确定的保留英文或给音译；\n"
    "4) 每行一个，严格按输入顺序，格式：`标签 → 中文名`，只输出这一列，不要解释。\n"
    "{tags}"
)


def translate_batch(client: httpx.Client, llm: dict, tags: list[str]) -> dict:
    """翻译一批 tag，返回 {tag: 中文名}。失败抛异常（外层重试）。"""
    url = llm["endpoint"] + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if llm["api_key"] and llm["api_key"].lower() != "none":
        headers["Authorization"] = f"Bearer {llm['api_key']}"
    body = {
        "model": llm["model"],
        "messages": [{"role": "user", "content": PROMPT_TMPL.format(tags="\n".join(tags))}],
        "max_tokens": 40000,
        "stream": False,
        "temperature": 0.1,
        "thinking": {"type": "disabled"},
    }
    r = client.post(url, json=body, headers=headers, timeout=60)
    r.raise_for_status()
    d = r.json()
    content = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    # 解析 "tag → 中文名"
    result = {}
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r"^([^→]+)\s*→\s*(.+)$", line)
        if m:
            tag = m.group(1).strip()
            cn = m.group(2).strip()
            if tag in tags and cn and cn.lower() != "n/a":
                result[tag] = cn
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="最多翻译 N 个（调试）")
    ap.add_argument("--batch", type=int, default=400)
    ap.add_argument("--only", type=str, default="", help="逗号分隔指定 tag")
    ap.add_argument("--retry", type=int, default=2)
    args = ap.parse_args(argv)

    load_env()
    llm = get_llm()
    print(f"LLM: {llm['model']} ({llm['endpoint']})")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    if args.only:
        tags = [t.strip() for t in args.only.split(",") if t.strip()]
    else:
        tags = [r[0] for r in conn.execute(
            "SELECT danbooru_tag FROM character "
            "WHERE danbooru_tag IS NOT NULL AND danbooru_tag != '' "
            "AND (name_cn IS NULL OR name_cn = '') ORDER BY post_count DESC")]
    if args.limit:
        tags = tags[:args.limit]
    total = len(tags)
    print(f"待翻译: {total} 个")
    if not total:
        conn.close()
        return

    client = httpx.Client(timeout=60, limits=httpx.Limits(max_connections=1))
    done = 0
    updated = 0
    failed = []
    try:
        for i in range(0, total, args.batch):
            batch = tags[i:i + args.batch]
            ok = {}
            for attempt in range(args.retry + 1):
                try:
                    ok = translate_batch(client, llm, batch)
                    break
                except Exception as e:
                    if attempt >= args.retry:
                        failed.extend(batch)
                        print(f"  ! 批失败 {i//args.batch}: {type(e).__name__}: {e}")
                        break
                    time.sleep(3 * (attempt + 1))
            # 更新 DB
            for tag, cn in ok.items():
                conn.execute("UPDATE character SET name_cn = ? WHERE danbooru_tag = ?", (cn, tag))
            conn.commit()
            done += len(batch)
            updated += len(ok)
            if len(ok) < len(batch):
                missed = [t for t in batch if t not in ok]
                print(f"  [批 {i//args.batch}] 翻译 {len(ok)}/{len(batch)}，未识别: {missed[:3]}")
            if (i + len(batch)) % 200 == 0 or i + len(batch) >= total:
                print(f"进度 {i + len(batch)}/{total}，已更新 {updated}，耗时 {int((time.time() - _t0))}s", flush=True)
    finally:
        conn.close()
        client.close()
    print(f"完成。更新 {updated}/{total}，失败 {len(failed)}")


_t0 = time.time()

if __name__ == "__main__":
    main()

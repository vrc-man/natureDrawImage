"""AI 助手角色库缩略图本地化工具（Tkinter 界面）。

把 ai_chat_data.db 角色库的 Zerochan 外链缩略图批量转存为本地 WebP 缓存
（最短边 512px 等比缩放），写入 web/features/ai_chat/skills/search_characters/character_thumbnails/，
并维护 index.json 清单。后端 api_search_characters 会「本地优先、代理兜底」。

功能：
  1. 代理池管理：从 GitHub 免费代理列表拉取 → 存活检测 → 过滤 → 手动更新
  2. 批量爬取：并发下载 + 转 WebP + 断点续传 + 失败重试 + 失败清单落盘
  3. index.json 维护：分批写入（每批/结束）

线程模型（复用 sync_gui 思路）：
  - 主线程     : tkinter 事件 + 定时轮询队列（100ms）
  - 日志/状态  : 后台线程入队，主线程刷新
  - 长任务     : 拉取代理 / 爬取全部在 daemon 线程
"""
from __future__ import annotations

import io
import json
import os
import queue
import random
import sqlite3
import threading
import time
from pathlib import Path
from tkinter import END, DISABLED, NORMAL, Button, Frame, Label, Scrollbar, Text, Tk, messagebox

PROXY_LIST_SOURCES = [
    # GitHub 免费代理列表 raw 地址（每行一个 ip:port 或 ip:port:user:pass）
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/proxy4parsers/proxy-list/main/http.txt",
]

# 角色库 DB（相对 web/ 解析，与后端 ai_chat.json 的 character_db 一致）
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DB_PATH = _WEB_DIR / "features" / "ai_chat" / "config" / "ai_chat_data.db"
# 缩略图缓存目录（与后端 CHAR_THUMB_LOCAL_DIR 一致）
THUMB_DIR = _WEB_DIR / "features" / "ai_chat" / "skills" / "search_characters" / "character_thumbnails"
INDEX_JSON = THUMB_DIR / "index.json"
FAILED_JSON = THUMB_DIR / "failed.json"

THUMB_MIN_EDGE = 512      # 最短边像素
CONCURRENCY = 20           # 并发下载数
BATCH_WRITE = 100          # 每 N 张写一次 index.json
RETRY = 2                  # 每张失败重试次数
TIMEOUT = 20               # 单请求超时秒
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
REFERER = "https://www.zerochan.net/"

PROXY_URLS = [
    # 默认内置几个公共代理（手动「更新代理池」后替换）
]


class CharThumbTool:
    def __init__(self, root: Tk):
        self.root = root
        root.title("角色库缩略图本地化工具")
        root.geometry("760x620")
        root.resizable(True, True)

        self._log_queue: queue.Queue = queue.Queue()
        self._state_queue: queue.Queue = queue.Queue()

        self._running = False
        self._stop_flag = threading.Event()
        self._thread = None

        self._build_ui()

        # 定时轮询队列
        self._poll()

    # ── UI ──
    def _build_ui(self):
        # 顶部：统计 + 按钮
        top = Frame(self.root, padx=10, pady=8)
        top.pack(fill="x")
        Label(top, text="代理池状态：").pack(side="left")
        self.lb_proxy = Label(top, text="未拉取", fg="#888")
        self.lb_proxy.pack(side="left", padx=(4, 12))
        self.btn_update_proxy = Button(top, text="🔄 更新代理池", command=self.update_proxy, bg="#e0e7ff", fg="#3730a3")
        self.btn_update_proxy.pack(side="left")
        self.btn_fetch = Button(top, text="▶ 开始爬取", command=self.start_fetch, bg="#86efac", fg="#14532d")
        self.btn_fetch.pack(side="left", padx=(8, 4))
        self.btn_stop = Button(top, text="⏹ 停止", command=self.stop_fetch, state=DISABLED, bg="#fecaca", fg="#991b1b")
        self.btn_stop.pack(side="left")

        # 进度
        mid = Frame(self.root, padx=10)
        mid.pack(fill="x")
        self.lb_progress = Label(mid, text="本地 0 张 / 待爬 0 张 / 失败 0 张", fg="#555")
        self.lb_progress.pack(anchor="w")

        # 日志
        body = Frame(self.root, padx=10, pady=6)
        body.pack(fill="both", expand=True)
        self.txt_log = Text(body, height=20, font=("Consolas", 9), state=DISABLED, wrap="word")
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb = Scrollbar(body, command=self.txt_log.yview)
        sb.pack(side="right", fill="y")
        self.txt_log.configure(yscrollcommand=sb.set)

        self._log("角色库: %s" % DB_PATH)
        self._log("缓存目录: %s" % THUMB_DIR)
        self._log("每张最短边 %dpx WebP，并发 %d，失败重试 %d 次" % (THUMB_MIN_EDGE, CONCURRENCY, RETRY))
        self._log("提示：爬取完成后，到管理面板 AI 聊天 → 「🎭 角色库缩略图缓存」点「更新缩略图缓存」即可生效。")

    def _log(self, msg: str):
        self._log_queue.put(time.strftime("%H:%M:%S") + "  " + msg)

    def _poll(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                self.txt_log.configure(state=NORMAL)
                self.txt_log.insert(END, line + "\n")
                self.txt_log.see(END)
                self.txt_log.configure(state=DISABLED)
        except queue.Empty:
            pass
        try:
            while True:
                key, val = self._state_queue.get_nowait()
                if key == "proxy":
                    self.lb_proxy.configure(text=val)
                elif key == "progress":
                    self.lb_progress.configure(text=val)
                elif key == "done":
                    self._running = False
                    self.btn_fetch.configure(state=NORMAL, text="▶ 开始爬取")
                    self.btn_stop.configure(state=DISABLED)
                    self._log("完成。")
                elif key == "stop":
                    self._running = False
                    self.btn_fetch.configure(state=NORMAL, text="▶ 开始爬取")
                    self.btn_stop.configure(state=DISABLED)
                    self._log("已停止。")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # ── 代理池 ──
    def update_proxy(self):
        if self._running:
            messagebox.showinfo("提示", "爬取进行中，请先停止。")
            return
        self._log("开始更新代理池…")
        self._log("来源: %s" % " | ".join(PROXY_LIST_SOURCES))
        t = threading.Thread(target=self._update_proxy_worker, daemon=True)
        t.start()

    def _update_proxy_worker(self):
        global PROXY_URLS
        import httpx
        candidates: list[str] = []
        for url in PROXY_LIST_SOURCES:
            try:
                r = httpx.get(url, timeout=15)
                if r.status_code != 200:
                    continue
                for line in r.text.splitlines():
                    line = line.strip()
                    if line and ":" in line:
                        candidates.append(line)
            except Exception as e:
                self._log("拉取失败 %s : %s" % (url.split("/")[-1], e))
        self._log("共获取候选代理 %d 个，开始存活检测…" % len(candidates))

        alive: list[str] = []
        test_url = "http://www.zerochan.net/"
        # 逐个检测（用 concurrent 也行，但代理互不可靠，串行检测更准；取前 60 个做样本）
        sample = candidates[:60]
        for i, proxy in enumerate(sample):
            if i % 10 == 0 and i:
                self._state_queue.put(("proxy", "检测中 %d/%d" % (i, len(sample))))
            try:
                with httpx.Client(proxy="http://" + proxy, timeout=6) as c:
                    r = c.get(test_url, headers={"User-Agent": UA, "Referer": REFERER})
                    if r.status_code == 200:
                        alive.append(proxy)
            except Exception:
                pass
        self._state_queue.put(("proxy", "可用 %d 个" % len(alive)))
        if alive:
            PROXY_URLS = alive
        self._log("存活检测完成，可用代理 %d 个" % len(alive))
        self._log("示例: %s" % ", ".join(alive[:5]))
        if not alive:
            self._log("没有可用代理，将用直连爬取。")

    # ── 爬取 ──
    def start_fetch(self):
        if self._running:
            return
        self._running = True
        self._stop_flag.clear()
        self.btn_fetch.configure(state=DISABLED, text="爬取中…")
        self.btn_stop.configure(state=NORMAL)
        self._log("开始爬取…")
        t = threading.Thread(target=self._fetch_worker, daemon=True)
        t.start()

    def stop_fetch(self):
        self._stop_flag.set()
        self._log("正在停止（等待当前批次完成）…")

    def _fetch_worker(self):
        try:
            self._fetch_all()
        except Exception as e:
            self._log("爬取异常: %s" % e)
        if self._stop_flag.is_set():
            self._state_queue.put(("stop", None))
        else:
            self._state_queue.put(("done", None))

    def _load_characters(self):
        """读角色库：返回 [(tag, image_url)]，tag 为空或本地已存在则跳过。"""
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        existing = set()
        if INDEX_JSON.is_file():
            try:
                data = json.load(open(INDEX_JSON, encoding="utf-8"))
                existing = {str(k) for k, v in (data.get("thumbs") or {}).items() if v}
            except Exception:
                pass
        for p in THUMB_DIR.glob("*.webp"):
            existing.add(p.stem)

        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("SELECT danbooru_tag, image FROM character")
            items = []
            for tag, img in rows:
                tag = (tag or "").strip()
                if not tag or tag in existing or not (img or "").strip():
                    continue
                items.append((tag, img.strip()))
        finally:
            conn.close()
        return items

    def _fetch_all(self):
        items = self._load_characters()
        total = len(items)
        self._log("待爬取 %d 个角色（本地已有已跳过）" % total)
        if not total:
            self._state_queue.put(("progress", "本地 0 张 / 待爬 0 张 / 失败 0 张"))
            return

        import httpx
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA, "Referer": REFERER}) as client:
            ok = fail = 0
            failed: list[tuple[str, str]] = []
            thumbs: dict[str, str] = {}
            batch_pending: dict[str, str] = {}

            def _write_index(force=False):
                if not (force or len(batch_pending) >= BATCH_WRITE):
                    return
                data = {
                    "version": 1,
                    "updated_at": int(time.time()),
                    "total": len(thumbs),
                    "thumbs": dict(thumbs),
                }
                tmp = INDEX_JSON.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(INDEX_JSON)
                batch_pending.clear()
                self._log("已写 index.json（累计 %d 张）" % len(thumbs))

            def _do_one(idx: tuple[int, tuple[str, str]]):
                i, (tag, img) = idx
                if self._stop_flag.is_set():
                    return None
                url = img if img.startswith(("http://", "https://")) else ("https://www.zerochan.net/" + img.lstrip("/"))
                for attempt in range(RETRY + 1):
                    if self._stop_flag.is_set():
                        return None
                    try:
                        proxy = None
                        if PROXY_URLS:
                            proxy = "http://" + random.choice(PROXY_URLS)
                        if proxy:
                            # 代理不稳定：按请求创建 client 走该代理
                            with httpx.Client(proxy=proxy, timeout=TIMEOUT,
                                               headers={"User-Agent": UA, "Referer": REFERER}) as pc:
                                r = pc.get(url)
                        else:
                            r = client.get(url, headers={"User-Agent": UA, "Referer": REFERER})
                        if r.status_code != 200:
                            raise RuntimeError("HTTP %d" % r.status_code)
                        data = r.content
                        if len(data) < 200:
                            raise RuntimeError("too small")
                        out = self._to_webp(data)
                        if out is None:
                            raise RuntimeError("decode fail")
                        dest = THUMB_DIR / f"{tag}.webp"
                        tmpf = THUMB_DIR / f".{tag}.{os.getpid()}.tmp"
                        tmpf.write_bytes(out)
                        tmpf.replace(dest)
                        return (tag, img)
                    except Exception as e:
                        if attempt >= RETRY:
                            self._log("失败 %s (%s) : %s" % (tag, url[:80], e))
                            return ("FAIL", (tag, img, str(e)))
                        time.sleep(1.5)
                return None

            # 简单并发：分批跑线程池
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
                futures = {pool.submit(_do_one, (i, it)): i for i, it in enumerate(items)}
                done = 0
                for fut in as_completed(futures):
                    if self._stop_flag.is_set():
                        pool.shutdown(wait=False, cancel_futures=True)
                        break
                    res = fut.result()
                    done += 1
                    if isinstance(res, tuple) and res[0] == "FAIL":
                        tag, img, err = res[1]
                        failed.append((tag, img))
                        fail += 1
                    elif res:
                        tag, img = res
                        thumbs[tag] = tag + ".webp"
                        batch_pending[tag] = tag + ".webp"
                        ok += 1
                        _write_index()
                    self._state_queue.put(("progress", "本地 %d 张 / 待爬 %d 张 / 失败 %d 张" % (len(thumbs), total - ok - fail, fail)))
                self._state_queue.put(("progress", "本地 %d 张 / 待爬 %d 张 / 失败 %d 张" % (len(thumbs), max(0, total - ok - fail), fail)))

            _write_index(force=True)

        # 失败清单落盘
        if failed:
            try:
                FAILED_JSON.write_text(json.dumps({"updated_at": int(time.time()), "failed": failed}, ensure_ascii=False, indent=1), encoding="utf-8")
                self._log("失败清单已写入 %s（%d 条）" % (FAILED_JSON, len(failed)))
            except Exception as e:
                self._log("失败清单写入失败: %s" % e)
        self._log("完成：成功 %d，失败 %d" % (ok, fail))

    def _to_webp(self, data: bytes) -> bytes | None:
        """转 WebP（最短边 512 等比）。失败返回 None。"""
        from PIL import Image, ImageOps
        try:
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            w, h = img.size
            if w < 1 or h < 1:
                return None
            scale = THUMB_MIN_EDGE / min(w, h)
            if scale < 1:
                nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
                img = img.resize((nw, nh), Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=80, method=4)
            return out.getvalue()
        except Exception:
            return None


def main():
    root = Tk()
    CharThumbTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()

"""
外挂功能：AI 聊天/反推助手（支持图片识别）。

额度 token 单独管理，不依赖 access_keys。
系统提示词和 temperature 管理员可配置，用户也可自定义。
"""

import time
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from features._deps import require_admin, ctx

CONFIG_DIR = Path(__file__).resolve().parent / "config"
JSON_PATH = CONFIG_DIR / "ai_chat.json"

_lock = threading.Lock()

router = APIRouter(tags=["ai-chat"])


# ── API Key 加密存储（复用 app.py 的 Fernet 方案，密钥 LLM_ENCRYPTION_KEY）──

def _derive_encryption_key() -> Optional[bytes]:
    env_key = os.environ.get("LLM_ENCRYPTION_KEY", "")
    if not env_key:
        return None
    try:
        import base64 as _b64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError:
        return None
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"llm-api-key-v2")
    return _b64.urlsafe_b64encode(hkdf.derive(env_key.encode()))


def _encrypt_api_value(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    key = _derive_encryption_key()
    if not key:
        return plaintext
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return plaintext
    return "fernet:" + Fernet(key).encrypt(plaintext.encode()).decode()


def _decrypt_api_value(ciphertext: str) -> str:
    if not ciphertext:
        return ciphertext
    if ciphertext.startswith("fernet:"):
        key = _derive_encryption_key()
        if not key:
            return ciphertext
        try:
            from cryptography.fernet import Fernet, InvalidToken
        except ImportError:
            return ciphertext
        try:
            return Fernet(key).decrypt(ciphertext[7:].encode()).decode()
        except InvalidToken:
            return ciphertext
    return ciphertext


# ── JSON 读写 ──

def _load() -> dict:
    if not JSON_PATH.exists():
        return {"tokens": [], "system_prompt": "", "temperature": 0.7}
    try:
        with JSON_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {"tokens": [], "system_prompt": "", "temperature": 0.7}
    except Exception:
        raise RuntimeError("ai_chat.json 解析失败，已停止写入以防丢失")


def _save_atomic(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JSON_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, JSON_PATH)


# ── Token 管理 ──

def _verify_token(token: str) -> Optional[dict]:
    """校验 token 并返回 entry，次数用满或不存在返回 None。"""
    with _lock:
        data = _load()
        for t in data.get("tokens", []):
            if t["token"] == token:
                if t.get("max_uses", 0) > 0 and t.get("used", 0) >= t["max_uses"]:
                    return None
                return t
    return None


def _consume_token(token: str) -> bool:
    """扣减一次额度，成功返回 True。"""
    with _lock:
        data = _load()
        for t in data["tokens"]:
            if t["token"] == token:
                if t.get("max_uses", 0) > 0 and t.get("used", 0) >= t["max_uses"]:
                    return False
                t["used"] = t.get("used", 0) + 1
                _save_atomic(data)
                return True
    return False


# ── LLM 调用 ──

def _get_active_llm(cfg: dict) -> Optional[dict]:
    """返回当前启用的 LLM 配置。优先 llms 列表按 active_llm_id 选择，兼容旧字段。"""
    llms = cfg.get("llms") or []
    active_id = cfg.get("active_llm_id", "")
    if llms:
        for l in llms:
            if l.get("id") == active_id:
                return l
        return llms[0]
    # 旧字段兼容
    if cfg.get("llm_endpoint"):
        return {
            "id": "default",
            "name": "默认",
            "endpoint": cfg.get("llm_endpoint", ""),
            "model": cfg.get("llm_model", ""),
            "api_key": cfg.get("llm_api_key", ""),
            "max_tokens": cfg.get("llm_max_tokens", 2048),
            "stream": cfg.get("llm_stream", True),
        }
    return None


def _llm_request_info(messages: List[dict], temperature: float, max_tokens: int, extra: dict | None = None) -> tuple:
    """读取 ai_chat.json 配置，返回 (url, headers, body)。未配置抛异常。"""
    with _lock:
        aichat_cfg = _load()
    llm = _get_active_llm(aichat_cfg)
    if not llm:
        raise RuntimeError("AI 助手尚未配置，请联系管理员")
    llm_endpoint = str(llm.get("endpoint", "")).strip()
    llm_model = str(llm.get("model", "")).strip()
    llm_api_key = _decrypt_api_value(str(llm.get("api_key", "")))
    llm_max_tokens = int(llm.get("max_tokens", 2048) or 2048)

    if not llm_endpoint:
        raise RuntimeError("AI 助手尚未配置，请联系管理员")

    base = llm_endpoint.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"

    body: dict = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens if 0 < max_tokens <= 50000 else llm_max_tokens,
    }
    # 采样参数透传（top_p/top_k/frequency_penalty/presence_penalty/min_p）
    if extra:
        for k, v in extra.items():
            if v is not None:
                body[k] = v
    if llm_model:
        body["model"] = llm_model
    return url, headers, body


async def _call_llm(messages: List[dict], temperature: float, max_tokens: int = 0, extra: dict | None = None) -> str:
    """调用 LLM（OpenAI 兼容格式），支持多模态 content 数组。非流式返回完整文本。"""
    url, headers, body = _llm_request_info(messages, temperature, max_tokens, extra)
    body["stream"] = False
    client = await ctx("get_http_client")()
    r = await client.post(url, json=body, headers=headers, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"LLM 返回错误 {r.status_code}: {r.text[:200]}")
    resp = r.json()
    msg = ((resp.get("choices") or [{}])[0].get("message") or {})
    content = msg.get("content") or msg.get("reasoning_content") or ""
    return content.strip()


async def _call_llm_stream(messages: List[dict], temperature: float, max_tokens: int = 0, extra: dict | None = None):
    """流式调用 LLM，逐块 yield (kind, text)，kind 为 'reasoning' 或 'content'。"""
    url, headers, body = _llm_request_info(messages, temperature, max_tokens, extra)
    body["stream"] = True
    client = await ctx("get_http_client")()
    async with client.stream("POST", url, json=body, headers=headers, timeout=120) as r:
        if r.status_code >= 400:
            raw = (await r.aread())[:200].decode("utf-8", "replace")
            raise RuntimeError(f"LLM 返回错误 {r.status_code}: {raw}")
        async for line in r.aiter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except Exception:
                continue
            d = ((data.get("choices") or [{}])[0].get("delta") or {})
            reasoning = d.get("reasoning_content")
            content = d.get("content")
            if reasoning:
                yield ("reasoning", reasoning)
            if content:
                yield ("content", content)


# ── 联网搜索 ──

async def _web_search(query: str) -> str:
    """调 SearXNG 搜索，返回前 5 条结果的格式化文本。失败返回空字符串。"""
    with _lock:
        cfg_data = _load()
    searxng_url = str(cfg_data.get("searxng_url", "")).strip().rstrip("/")
    searxng_key = str(cfg_data.get("searxng_key", "")).strip()
    if not searxng_url or not cfg_data.get("web_search_enabled"):
        return ""
    # 只允许 http/https，防任意协议
    if not searxng_url.startswith(("http://", "https://")):
        return ""
    try:
        client = await ctx("get_http_client")()
        headers = {}
        if searxng_key:
            headers["Authorization"] = f"Bearer {searxng_key}"
        r = await client.get(
            f"{searxng_url}/search",
            params={"q": query[:200], "format": "json", "safesearch": "0"},
            headers=headers,
            timeout=15,
        )
        if r.status_code >= 400:
            return ""
        data = r.json()
        results = data.get("results", [])[:5]
        if not results:
            return "（搜索无结果）"
        lines = ["联网搜索结果："]
        for i, item in enumerate(results, 1):
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("content", "")).strip()
            lines.append(f"{i}. {title}")
            if url:
                lines.append(f"   链接: {url}")
            if snippet:
                lines.append(f"   摘要: {snippet}")
        return "\n".join(lines)
    except Exception:
        return ""


# ── 网页抓取 ──

def _validate_public_url(url: str) -> str:
    """校验 URL 必须 HTTPS 且非内网，返回规范化 URL。失败抛 HTTPException。"""
    import urllib.parse, ipaddress as _ipaddr, socket as _sock
    if not url:
        raise HTTPException(400, "url required")
    if not url.lower().startswith("https://"):
        raise HTTPException(403, "仅允许 HTTPS 地址")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(400, "无效地址")
    try:
        try:
            addr = _ipaddr.ip_address(host)
        except ValueError:
            resolved = _sock.getaddrinfo(host, None)
            addr = _ipaddr.ip_address(resolved[0][4][0])
        _deny = [_ipaddr.ip_network(n) for n in (
            "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
            "169.254.0.0/16", "0.0.0.0/8", "224.0.0.0/4", "240.0.0.0/4",
            "::1/128", "fe80::/10", "fc00::/7",
        )]
        if any(addr in n for n in _deny):
            raise HTTPException(403, "不允许访问内网/私网地址")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(403, "地址解析失败")
    return parsed._replace(fragment="").geturl()


def _html_to_text(html: str) -> str:
    """简单提取 HTML 正文文本。"""
    import re
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


async def _fetch_webpage(url: str, max_chars: int | None = None, force_render: bool = False) -> dict:
    """抓取网页并提取文本。返回 {url, title, text}。

    优先 httpx 快抓；force_render=True 或提取文本过短（JS 渲染页）时，
    用无头浏览器（Playwright）渲染后提取完整内容。
    max_chars 为 None 时读取后台配置 web_fetch_max_chars（默认 6000）。
    """
    if max_chars is None:
        with _lock:
            _c = _load()
        try:
            max_chars = int(_c.get("web_fetch_max_chars", 6000) or 6000)
        except (TypeError, ValueError):
            max_chars = 6000
    safe_url = _validate_public_url(url)
    client = await ctx("get_http_client")()
    html = ""
    title = ""
    try:
        r = await client.get(
            safe_url,
            follow_redirects=True,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"网页返回 HTTP {r.status_code}")
        html = r.text
    except RuntimeError:
        raise
    except Exception:
        html = ""  # 网络异常走降级

    text = ""
    if html:
        import re as _re
        mt = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.S | _re.I)
        if mt:
            title = _re.sub(r"\s+", " ", mt.group(1)).strip()
        text = _html_to_text(html)

    # JS 渲染页：显式 URL 抓取或文本不足时用无头浏览器补抓
    if force_render or len(text) < 200:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            if not text:
                raise RuntimeError("未能提取到页面文字内容")
        try:
            pw = await async_playwright().start()
            try:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                    locale="zh-CN",
                )
                try:
                    await page.goto(safe_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(3000)  # 等 JS 渲染
                except Exception:
                    pass
                rendered = await page.evaluate("document.body ? document.body.innerText : ''")
                if not rendered:
                    rendered = await page.evaluate("document.documentElement ? document.documentElement.innerText : ''")
                if rendered:
                    text = _re.sub(r"\s+", " ", rendered)
                if not title:
                    t = await page.title()
                    if t:
                        title = t
            finally:
                await browser.close()
                await pw.stop()
        except Exception:
            pass

    if not text or not text.strip():
        raise RuntimeError("未能提取到页面文字内容")
    return {"url": safe_url, "title": title, "text": text.strip()[:max_chars]}


# ── 统一联网收集（搜索 + 抓正文）──

async def _rewrite_query(question: str) -> str:
    """用 LLM 把口语问题改写为搜索词。失败返回原句。"""
    try:
        url, headers, body = _llm_request_info(
            [{"role": "user", "content": f"把下面的问题改写成一个适合搜索引擎的中文搜索关键词，只输出关键词本身，不要解释、不要引号、不要换行：\n{question}"}],
            0.2, 64,
        )
        body["stream"] = False
        body["max_tokens"] = 64
        client = await ctx("get_http_client")()
        r = await client.post(url, json=body, headers=headers, timeout=30)
        if r.status_code >= 400:
            return question
        resp = r.json()
        kw = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        kw = kw.strip().strip('"\'“”').split("\n")[0].strip()
        return kw[:80] or question
    except Exception:
        return question


async def _web_gather(query: str, max_pages: int = 3, rewrite: bool = True) -> dict:
    """统一联网：改写→搜索→并发抓正文。返回 {"query", "sources", "text"}。"""
    with _lock:
        cfg_data = _load()
    searxng_url = str(cfg_data.get("searxng_url", "")).strip().rstrip("/")
    try:
        grab_max = int(cfg_data.get("web_fetch_max_chars", 6000) or 6000)
    except (TypeError, ValueError):
        grab_max = 6000
    if not searxng_url or not cfg_data.get("web_search_enabled"):
        return {"query": query, "sources": [], "text": ""}

    search_q = query
    if rewrite:
        search_q = await _rewrite_query(query)
    if not search_q:
        search_q = query

    search_text = await _web_search(search_q)
    if not search_text or search_text == "（搜索无结果）":
        return {"query": search_q, "sources": [], "text": search_text}

    # 从搜索结果文本提取 title/url/摘要 列表
    import re as _re
    sources = []
    lines = search_text.split("\n")
    i = 0
    while i < len(lines):
        mt = _re.match(r"^(\d+)\. (.*)$", lines[i])
        if mt:
            title = mt.group(2).strip()
            url = ""
            snippet = ""
            j = i + 1
            while j < len(lines) and j <= i + 2:
                if lines[j].startswith("   链接: "):
                    url = lines[j][len("   链接: "):].strip()
                elif lines[j].startswith("   摘要: "):
                    snippet = lines[j][len("   摘要: "):].strip()
                j += 1
            sources.append({"title": title, "url": url, "snippet": snippet})
            i = j
        else:
            i += 1

    # 并发抓正文（最多 max_pages 个）
    pages = sources[:max_pages]
    texts: list = [None] * len(pages)
    client = await ctx("get_http_client")()

    async def _grab(idx: int, item: dict):
        try:
            safe = _validate_public_url(item["url"]) if item.get("url") else None
            if not safe:
                return
            r = await client.get(
                safe,
                follow_redirects=True,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 Chrome/124", "Accept-Language": "zh-CN,zh;q=0.9"},
            )
            if r.status_code >= 400:
                return
            t = _html_to_text(r.text)[:grab_max]
            if t:
                texts[idx] = t
        except Exception:
            texts[idx] = None

    import asyncio
    await asyncio.gather(*[_grab(i, p) for i, p in enumerate(pages)])

    # 组装资料文本
    parts = ["以下是从网页获取到的资料，请基于这些内容回答用户问题："]
    for idx, item in enumerate(pages):
        if texts[idx]:
            parts.append(f"\n【资料 {idx+1}】{item['title']}")
            parts.append(f"链接: {item['url']}")
            parts.append(texts[idx][:2000])
    parts.append(f"\n用户问题：{query}")
    return {"query": search_q, "sources": sources, "text": "\n".join(parts)}


# ── API ──

@router.post("/api/features/ai-chat/fetch")
async def api_ai_chat_fetch(request: Request):
    """抓取网页，返回 JSON 文本内容（供 LLM 总结用）。显式 URL 抓取走无头浏览器渲染。"""
    body = await request.json()
    url = str(body.get("url", "")).strip()
    try:
        data = await _fetch_webpage(url, force_render=True)
        return {"ok": True, "url": data["url"], "title": data["title"], "text": data["text"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"抓取失败: {type(e).__name__}: {e}")


@router.post("/api/features/ai-chat/send")
async def api_ai_chat_send(request: Request):
    """聊天发送（额度模式）。传 token + message + 可选 image(base64)。"""
    body = await request.json()
    token = str(body.get("token", "")).strip()
    message = str(body.get("message", "")).strip()
    image = str(body.get("image", "")).strip()
    user_prompt = str(body.get("system_prompt", "")).strip()
    temperature = float(body.get("temperature", 0))
    do_search = bool(body.get("search", False))
    max_tokens = int(body.get("max_tokens", 0) or 0)
    history = body.get("history") or []
    user_stream = body.get("stream")  # 前端用户自定义，None=用管理员默认
    # 采样参数
    sampling: dict = {}
    for k, default in (("top_p", 1.0), ("top_k", 0), ("frequency_penalty", 0.0),
                       ("presence_penalty", 0.0), ("min_p", 0.0)):
        v = body.get(k)
        if v is not None:
            try:
                sampling[k] = float(v)
            except (TypeError, ValueError):
                pass

    if not token:
        raise HTTPException(400, "token required")
    if not message and not image:
        raise HTTPException(400, "message or image required")

    # 校验 token 并扣减
    entry = _verify_token(token)
    if not entry:
        raise HTTPException(403, "token 无效或次数已用完")
    if not _consume_token(token):
        raise HTTPException(403, "token 次数已用完")

    # 读取系统配置
    with _lock:
        cfg_data = _load()
        sys_prompt = cfg_data.get("system_prompt", "")
        sys_temp = cfg_data.get("temperature", 0.7)
        active_llm = _get_active_llm(cfg_data)
        llm_stream = bool(active_llm.get("stream", True)) if active_llm else bool(cfg_data.get("llm_stream", True))
        search_max_pages = int(cfg_data.get("web_search_max_pages", 3) or 3)
        search_rewrite = bool(cfg_data.get("web_search_query_rewrite", True))

    # 前端用户自定义流式开关：传入则覆盖管理员默认
    if user_stream is not None:
        llm_stream = bool(user_stream)

    # 用户自定义覆盖
    # 显式传了 system_prompt（含空字符串）→ 用传的值；没传 → 用后台默认
    if "system_prompt" in body:
        user_prompt = str(body.get("system_prompt", "")).strip()
    else:
        user_prompt = sys_prompt
    if temperature <= 0:
        temperature = sys_temp

    try:
        # 统一联网：改写→搜索→抓正文
        sources = []
        search_text = ""
        if do_search:
            gather = await _web_gather(message, max_pages=search_max_pages, rewrite=search_rewrite)
            sources = gather.get("sources", [])
            search_text = gather.get("text", "")
        # 构建 messages
        content_parts: list = []
        if search_text:
            content_parts.append({"type": "text", "text": search_text})
        elif message:
            content_parts.append({"type": "text", "text": message})
        if image:
            content_parts.append({"type": "image_url", "image_url": {"url": image}})

        messages: list = []
        if user_prompt:
            messages.append({"role": "system", "content": user_prompt})
        # 插入历史上下文（仅 user/assistant 文本，避免污染；限量 200 条）
        if isinstance(history, list):
            for h in history[:200]:
                if not isinstance(h, dict):
                    continue
                role = h.get("role")
                if role not in ("user", "assistant"):
                    continue
                htext = str(h.get("text", "")).strip()
                if not htext:
                    continue
                himg = str(h.get("image", "") or "").strip()
                if himg:
                    messages.append({"role": role, "content": [
                        {"type": "text", "text": htext},
                        {"type": "image_url", "image_url": {"url": himg}},
                    ]})
                else:
                    messages.append({"role": role, "content": htext})
        messages.append({"role": "user", "content": content_parts})

        if llm_stream:
            async def _gen():
                got_content = False
                try:
                    async for kind, delta in _call_llm_stream(messages, temperature, max_tokens, sampling):
                        got_content = True
                        yield f"data: {json.dumps({'delta': delta, 'kind': kind}, ensure_ascii=False)}\n\n"
                    if not got_content:
                        # LLM 未产出任何内容，退还次数
                        with _lock:
                            data = _load()
                            for t in data["tokens"]:
                                if t["token"] == token:
                                    t["used"] = max(0, t.get("used", 0) - 1)
                                    _save_atomic(data)
                                    break
                        yield f"data: {json.dumps({'error': 'LLM 返回为空'}, ensure_ascii=False)}\n\n"
                        return
                    if sources:
                        yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    # 扣了次数但 LLM 失败，退还
                    with _lock:
                        data = _load()
                        for t in data["tokens"]:
                            if t["token"] == token:
                                t["used"] = max(0, t.get("used", 0) - 1)
                                _save_atomic(data)
                                break
                    yield f"data: {json.dumps({'error': f'{type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        reply = await _call_llm(messages, temperature, max_tokens, sampling)
        if not reply:
            # LLM 返回空内容，退还次数
            with _lock:
                data = _load()
                for t in data["tokens"]:
                    if t["token"] == token:
                        t["used"] = max(0, t.get("used", 0) - 1)
                        _save_atomic(data)
                        break
            raise HTTPException(500, "LLM 返回为空")
        resp = {"reply": reply}
        if sources:
            resp["sources"] = sources
        return resp
    except Exception as e:
        # 扣了次数但 LLM 失败，退还会员
        with _lock:
            data = _load()
            for t in data["tokens"]:
                if t["token"] == token:
                    t["used"] = max(0, t.get("used", 0) - 1)
                    _save_atomic(data)
                    break
        raise HTTPException(500, f"LLM 调用失败: {type(e).__name__}: {e}")


@router.post("/api/features/ai-chat/proxy")
async def api_ai_chat_proxy(request: Request):
    """代理：前端自用 Key 模式下绕过 CORS，转发请求到用户指定的 API。"""
    body = await request.json()
    method = str(body.get("method", "GET")).upper()
    url = str(body.get("url", "")).strip()
    api_key = str(body.get("api_key", "")).strip()
    json_body = body.get("body")

    if not url:
        raise HTTPException(400, "url required")
    if method not in ("GET", "POST"):
        raise HTTPException(400, "method 仅支持 GET/POST")
    # 强制 HTTPS
    if not url.lower().startswith("https://"):
        raise HTTPException(403, "仅允许 HTTPS 地址")
    # SSRF 防护：禁止访问任何内网/私网/云元数据地址
    import urllib.parse, ipaddress as _ipaddr, socket as _sock
    try:
        _parsed = urllib.parse.urlparse(url)
        _host = _parsed.hostname or ""
        if not _host:
            raise HTTPException(400, "无效地址")
        # 检查是否内网 IP（域名也解析后检查）
        try:
            _addr = _ipaddr.ip_address(_host)
        except ValueError:
            _resolved = _sock.getaddrinfo(_host, None)
            _addr = _ipaddr.ip_address(_resolved[0][4][0])
        _deny = [_ipaddr.ip_network(n) for n in (
            "127.0.0.0/8",      # loopback
            "10.0.0.0/8",       # 私有 A 类
            "172.16.0.0/12",    # 私有 B 类
            "192.168.0.0/16",   # 私有 C 类
            "169.254.0.0/16",   # link-local / 云元数据
            "0.0.0.0/8",        # 本网络
            "224.0.0.0/4",      # multicast
            "240.0.0.0/4",      # reserved
            "::1/128",          # IPv6 loopback
            "fe80::/10",        # IPv6 link-local
            "fc00::/7",         # IPv6 唯一本地
        )]
        if any(_addr in n for n in _deny):
            raise HTTPException(403, "不允许访问内网/私网地址")
    except HTTPException: raise
    except Exception:
        raise HTTPException(403, "地址解析失败")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # 流式透传：POST 且 body.stream=true 时，把上游 SSE 原样转发给前端
    want_stream = (
        method == "POST"
        and isinstance(json_body, dict)
        and bool(json_body.get("stream", False))
    )

    client = await ctx("get_http_client")()
    try:
        if want_stream:
            async def _proxy_gen():
                async with client.stream("POST", url, json=json_body, headers=headers, timeout=120) as r:
                    if r.status_code >= 400:
                        raw = (await r.aread())[:300].decode("utf-8", "replace")
                        yield f"data: {json.dumps({'error': f'HTTP {r.status_code}: {raw}'}, ensure_ascii=False)}\n\n"
                        return
                    async for line in r.aiter_lines():
                        yield line + "\n"
            return StreamingResponse(
                _proxy_gen(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        if method == "GET":
            r = await client.get(url, headers=headers, timeout=30)
        else:
            r = await client.post(url, json=json_body, headers=headers, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    except Exception as e:
        raise HTTPException(502, f"代理请求失败: {type(e).__name__}: {e}")


@router.get("/api/features/ai-chat/profile")
async def api_ai_chat_profile(request: Request, token: str = ""):
    """查 token 剩余次数。"""
    if not token:
        raise HTTPException(400, "token required")
    entry = _verify_token(token)
    if not entry:
        return {"valid": False, "message": "无效或已用完"}
    return {
        "valid": True,
        "max_uses": entry.get("max_uses", 0),
        "used": entry.get("used", 0),
        "remaining": max(0, entry.get("max_uses", 0) - entry.get("used", 0)),
    }


@router.get("/api/features/ai-chat/default-config")
async def api_ai_chat_default_config():
    """获取默认系统提示词和温度（用户端用）。"""
    with _lock:
        data = _load()
    return {
        "system_prompt": data.get("system_prompt", ""),
        "temperature": data.get("temperature", 0.7),
    }


# ── 管理员接口 ──

@router.post("/api/admin/features/ai-chat/llm-probe")
async def admin_llm_probe(request: Request):
    """探测模型列表。入参 {endpoint, api_key?}。"""
    require_admin(request)
    body = await request.json()
    endpoint = str(body.get("endpoint", "")).strip()
    api_key = str(body.get("api_key", "")).strip()
    if not endpoint:
        raise HTTPException(400, "endpoint required")
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/models"
    else:
        url = base + "/v1/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    client = await ctx("get_http_client")()
    try:
        r = await client.get(url, headers=headers, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        models = []
        for m in (data.get("data") or []):
            mid = str(m.get("id", "")).strip()
            if mid:
                models.append(mid)
        if not models:
            raise RuntimeError("未获取到模型列表")
        return {"models": models}
    except Exception as e:
        raise HTTPException(502, f"探测失败: {type(e).__name__}: {e}")


@router.post("/api/admin/features/ai-chat/llm-test")
async def admin_llm_test(request: Request):
    """测试 LLM 连通性。入参 {endpoint, api_key?, model?}。"""
    require_admin(request)
    body = await request.json()
    endpoint = str(body.get("endpoint", "")).strip()
    api_key = str(body.get("api_key", "")).strip()
    model = str(body.get("model", "")).strip()
    if not endpoint:
        raise HTTPException(400, "endpoint required")
    base = endpoint.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict = {
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 200,
        "stream": False,
    }
    client = await ctx("get_http_client")()
    if model:
        payload["model"] = model
    else:
        # 未指定模型时自动探测并取第一个，避免 400
        try:
            if base.endswith("/v1"):
                murl = base + "/models"
            else:
                murl = base + "/v1/models"
            mr = await client.get(murl, headers=headers, timeout=30)
            if mr.status_code < 400:
                mlist = [str(m.get("id", "")).strip() for m in (mr.json().get("data") or []) if m.get("id")]
                if mlist:
                    payload["model"] = mlist[0]
        except Exception:
            pass
    try:
        r = await client.post(url, json=payload, headers=headers, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        resp = r.json()
        msg = ((resp.get("choices") or [{}])[0].get("message") or {})
        content = msg.get("content") or msg.get("reasoning_content") or ""
        if not content:
            raise RuntimeError("LLM 返回为空")
        return {"ok": True, "reply": content[:200]}
    except Exception as e:
        import traceback
        print(f"[ai-chat llm-test 失败] endpoint={endpoint} model={model!r} key_set={bool(api_key)} url={url} payload_model={payload.get('model')!r} err={type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        raise HTTPException(502, f"测试失败: {type(e).__name__}: {e}")


@router.post("/api/admin/features/ai-chat/search-test")
async def admin_search_test(request: Request):
    """测试 SearXNG 搜索连通性。入参 {url, key?}。"""
    require_admin(request)
    body = await request.json()
    searxng_url = str(body.get("url", "")).strip().rstrip("/")
    searxng_key = str(body.get("key", "")).strip()
    if not searxng_url:
        raise HTTPException(400, "url required")
    if not searxng_url.startswith(("http://", "https://")):
        raise HTTPException(400, "地址需以 http:// 或 https:// 开头")
    headers = {}
    if searxng_key:
        headers["Authorization"] = f"Bearer {searxng_key}"
    client = await ctx("get_http_client")()
    try:
        r = await client.get(
            f"{searxng_url}/search",
            params={"q": "测试", "format": "json"},
            headers=headers,
            timeout=20,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        results = data.get("results") or []
        if not results:
            raise RuntimeError("搜索无结果")
        return {"ok": True, "results": len(results), "first_title": results[0].get("title", "")[:50]}
    except Exception as e:
        raise HTTPException(502, f"测试失败: {type(e).__name__}: {e}")


@router.get("/api/admin/features/ai-chat/tokens")
async def admin_list_tokens(request: Request):
    require_admin(request)
    with _lock:
        data = _load()
        items = []
        for t in data.get("tokens", []):
            items.append({
                "token": t["token"],
                "max_uses": t.get("max_uses", 0),
                "used": t.get("used", 0),
                "created_by": t.get("created_by", ""),
                "created_at": t.get("created_at", 0),
            })
        return {"items": items, "total": len(items)}


@router.post("/api/admin/features/ai-chat/tokens/generate")
async def admin_generate_token(request: Request):
    require_admin(request)
    body = await request.json()
    max_uses = int(body.get("max_uses", 0))
    if max_uses < 0 or max_uses > 999999:
        raise HTTPException(400, "max_uses 范围 0-999999，0=不限")
    import secrets
    token = "ai_chat_" + secrets.token_hex(16)
    user = ctx("get_user")(request)
    created_by = str(user.get("login", "")) if user else ""
    with _lock:
        data = _load()
        data.setdefault("tokens", []).append({
            "token": token,
            "max_uses": max_uses,
            "used": 0,
            "created_by": created_by,
            "created_at": time.time(),
        })
        _save_atomic(data)
    return {"token": token, "max_uses": max_uses}


@router.post("/api/admin/features/ai-chat/tokens/delete")
async def admin_delete_token(request: Request):
    require_admin(request)
    body = await request.json()
    token = str(body.get("token", "")).strip()
    if not token:
        raise HTTPException(400, "token required")
    with _lock:
        data = _load()
        data["tokens"] = [t for t in data["tokens"] if t["token"] != token]
        _save_atomic(data)
    return {"ok": True}


@router.get("/api/admin/features/ai-chat/config")
async def admin_get_config(request: Request):
    require_admin(request)
    with _lock:
        data = _load()
    llms = data.get("llms") or []
    llm_list = []
    for l in llms:
        llm_list.append({
            "id": l.get("id", ""),
            "name": l.get("name", ""),
            "endpoint": l.get("endpoint", ""),
            "model": l.get("model", ""),
            "api_key": _decrypt_api_value(str(l.get("api_key", ""))),
            "max_tokens": l.get("max_tokens", 2048),
            "stream": l.get("stream", True),
        })
    return {
        "system_prompt": data.get("system_prompt", ""),
        "temperature": data.get("temperature", 0.7),
        "searxng_url": data.get("searxng_url", ""),
        "searxng_key": data.get("searxng_key", ""),
        "web_search_enabled": data.get("web_search_enabled", False),
        "llms": llm_list,
        "active_llm_id": data.get("active_llm_id", ""),
        "llm_endpoint": data.get("llm_endpoint", ""),
        "llm_model": data.get("llm_model", ""),
        "llm_api_key": _decrypt_api_value(str(data.get("llm_api_key", ""))),
        "llm_max_tokens": data.get("llm_max_tokens", 2048),
        "llm_stream": data.get("llm_stream", True),
        "web_search_max_pages": data.get("web_search_max_pages", 3),
        "web_search_query_rewrite": data.get("web_search_query_rewrite", True),
        "web_fetch_max_chars": data.get("web_fetch_max_chars", 6000),
    }


@router.post("/api/admin/features/ai-chat/config")
async def admin_set_config(request: Request):
    require_admin(request)
    body = await request.json()
    with _lock:
        data = _load()
        if "system_prompt" in body:
            data["system_prompt"] = str(body["system_prompt"])
        if "temperature" in body:
            data["temperature"] = float(body["temperature"])
        if "searxng_url" in body:
            data["searxng_url"] = str(body["searxng_url"]).strip()
        if "searxng_key" in body:
            data["searxng_key"] = str(body["searxng_key"]).strip()
        if "web_search_enabled" in body:
            data["web_search_enabled"] = bool(body["web_search_enabled"])
        if "llms" in body:
            new_llms = []
            for l in body["llms"]:
                if not isinstance(l, dict):
                    continue
                lid = str(l.get("id", "")).strip() or ("llm_" + __import__("secrets").token_hex(8))
                item = {
                    "id": lid,
                    "name": str(l.get("name", "")).strip(),
                    "endpoint": str(l.get("endpoint", "")).strip(),
                    "model": str(l.get("model", "")).strip(),
                    "api_key": str(l.get("api_key", "")).strip(),
                    "max_tokens": max(1, min(65536, int(l.get("max_tokens", 2048)))),
                    "stream": bool(l.get("stream", True)),
                }
                new_llms.append(item)
            data["llms"] = new_llms
            if not data.get("active_llm_id") or not any(x["id"] == data.get("active_llm_id") for x in new_llms):
                if new_llms:
                    data["active_llm_id"] = new_llms[0]["id"]
                else:
                    data["active_llm_id"] = ""
        if "active_llm_id" in body:
            data["active_llm_id"] = str(body["active_llm_id"]).strip()
        # 兼容旧字段
        if "llm_endpoint" in body:
            data["llm_endpoint"] = str(body["llm_endpoint"]).strip()
        if "llm_model" in body:
            data["llm_model"] = str(body["llm_model"]).strip()
        if "llm_api_key" in body:
            data["llm_api_key"] = _encrypt_api_value(str(body["llm_api_key"]).strip())
        if "llm_max_tokens" in body:
            data["llm_max_tokens"] = max(1, min(65536, int(body["llm_max_tokens"])))
        if "llm_stream" in body:
            data["llm_stream"] = bool(body["llm_stream"])
        if "web_search_max_pages" in body:
            data["web_search_max_pages"] = max(0, min(5, int(body["web_search_max_pages"])))
        if "web_search_query_rewrite" in body:
            data["web_search_query_rewrite"] = bool(body["web_search_query_rewrite"])
        if "web_fetch_max_chars" in body:
            data["web_fetch_max_chars"] = max(1000, min(50000, int(body["web_fetch_max_chars"])))
        _save_atomic(data)
    return {"ok": True}

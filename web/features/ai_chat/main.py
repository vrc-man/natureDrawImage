"""
外挂功能：AI 聊天/反推助手（支持图片识别）。

额度 token 单独管理，不依赖 access_keys。
系统提示词和 temperature 管理员可配置，用户也可自定义。
"""

import time
import json
import os
import sys
import asyncio
import inspect
import importlib.util
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml as _yaml
except ImportError:  # yaml 可选，缺失时 skill.yaml 无法加载（skill.json 仍可用）
    _yaml = None

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response

from features._deps import require_admin, ctx

# 目录化后 main.py 位于 web/features/ai_chat/，上溯 3 级定位 web/（角色库/画风库/工作流元数据所在）
_WEB_DIR = Path(__file__).resolve().parent.parent.parent
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


def _llm_request_info(messages: List[dict], temperature: float, max_tokens: int, extra: dict | None = None, tools: Optional[list] = None) -> tuple:
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
    # function calling 工具列表
    if tools:
        body["tools"] = tools
    if llm_model:
        body["model"] = llm_model
    return url, headers, body


async def _call_llm(messages: List[dict], temperature: float, max_tokens: int = 0, extra: dict | None = None, tools: Optional[list] = None) -> tuple:
    """调用 LLM（OpenAI 兼容格式）。返回 (content, tool_calls, reasoning)。非流式。

    reasoning 为模型的思考过程（reasoning_content），content 为最终正文。两者分离。
    """
    url, headers, body = _llm_request_info(messages, temperature, max_tokens, extra, tools)
    body["stream"] = False
    client = await ctx("get_http_client")()
    r = await client.post(url, json=body, headers=headers, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"LLM 返回错误 {r.status_code}: {r.text[:200]}")
    resp = r.json()
    msg = ((resp.get("choices") or [{}])[0].get("message") or {})
    content = (msg.get("content") or "").strip()
    reasoning = (msg.get("reasoning_content") or "").strip()
    tool_calls = msg.get("tool_calls")
    return content, tool_calls, reasoning


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


# ── 多轮决策（function calling）──

SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索网页，获取与关键词相关的信息列表。适合查询实时信息、查找资料、了解某事物。搜索后返回标题、链接、摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "访问一个网址并抓取其正文内容。适合查看搜索结果中某个链接的详情、网页正文、文档规范。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要访问的网址"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "当用户需求模糊、信息不足、或需要在多个选项中做选择时，必须调用本工具向用户提问澄清，让用户从选项中选择或自由回答。注意：不要用普通文字反问，必须调用本工具，这样前端才能显示选项按钮。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要向用户提出的问题"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选的选项列表（可为空数组，表示让用户自由回答）",
                    },
                },
                "required": ["question"],
            },
        },
    },
]

# ── 技能目录加载器（仿 ComfyUI custom_nodes / opencode skills）──
# 每个技能 = skills/<name>/ 目录，含 skill.json（说明书+schema+入口）+ 若干 py + data/
# 加技能 = 新建目录放 skill.json，重启即自动发现，无需改主文件。

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class SkillContext:
    """传给技能 execute(args, ctx) 的运行上下文。

    - data_dir: 技能私有数据目录（绝对路径）
    - shared: skill.json 里声明的共享文件（绝对路径）
    - ai_config: ai_chat.json 配置全文
    - data: ai_chat.json 里 skill_data 段的数据源路径（相对路径已解析为绝对）
    - get_http_client: async callable，技能可调 LLM（await ctx.get_http_client()）
    """

    def __init__(self, name: str, data_dir: str, shared: dict, ai_config: dict, get_http_client=None):
        self.name = name
        self.data_dir = data_dir
        self.shared = shared
        self.ai_config = ai_config
        self.get_http_client = get_http_client
        self.data: Dict[str, Any] = {}
        try:
            sd = (ai_config or {}).get("skill_data") or {}
            web_dir = _WEB_DIR
            for k, v in sd.items():
                if isinstance(v, str) and v.strip():
                    p = Path(v.strip())
                    if not p.is_absolute():
                        p = web_dir / p
                    self.data[k] = str(p.resolve())
                else:
                    self.data[k] = v
        except Exception:
            self.data = {}


def _resolve_shared(shared: dict) -> dict:
    """把 skill.json 的 shared 相对路径（相对 web/）解析为绝对路径。"""
    web_dir = _WEB_DIR
    out = {}
    for k, v in (shared or {}).items():
        p = str(v or "")
        if p:
            try:
                out[k] = str((web_dir / p).resolve())
            except Exception:
                out[k] = p
    return out


def _discover_skills() -> dict:
    """扫描 skills/，返回 {name: meta}。"""
    skills: dict = {}
    if not SKILLS_DIR.is_dir():
        return skills
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        if d.name in ("skill_template", "__pycache__") or d.name.startswith(".") or d.name.startswith("_"):
            continue
        jf = d / "skill.json"
        yf = d / "skill.yaml"
        if not (jf.is_file() or yf.is_file()):
            continue
        try:
            if yf.is_file() and _yaml is not None:
                meta = _yaml.safe_load(yf.read_text(encoding="utf-8"))
            else:
                meta = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = str(meta.get("name", "")).strip()
        entry = str(meta.get("entry", "")).strip()
        if not name or not entry:
            continue
        module_name, _, fn_name = entry.partition(":")
        skills[name] = {
            "schema": meta,
            "module": str(module_name),
            "entry": fn_name or "execute",
            "data_dir": str((d / str(meta.get("data_dir", "data"))).resolve()),
            "shared": _resolve_shared(meta.get("shared")),
            "dir": d,
        }
    return skills


_SKILLS = _discover_skills()


def _skill_schema(name: str, meta: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": str(meta["schema"].get("description", "")),
            "parameters": meta["schema"].get("parameters", {"type": "object", "properties": {}}),
        },
    }


def _get_skill_executor(name: str):
    meta = _SKILLS.get(name)
    if not meta:
        return None
    # 防路径穿越：入口模块必须位于技能目录内
    try:
        mod_path = (meta["dir"] / meta["module"]).resolve()
        skill_root = meta["dir"].resolve()
        if not str(mod_path).startswith(str(skill_root) + os.sep) and mod_path != skill_root:
            print(f"[ai-chat skill] 拒绝加载 {name}：入口 {meta['module']} 越出技能目录", flush=True)
            return None
    except Exception:
        return None
    key = "ai_chat_skill_" + name
    mod = sys.modules.get(key)
    if mod is None:
        try:
            spec = importlib.util.spec_from_file_location(key, str(mod_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sys.modules[key] = mod
        except Exception as e:
            print(f"[ai-chat skill] 加载 {name} 失败: {type(e).__name__}: {e}", flush=True)
            return None
    return getattr(mod, meta["entry"], None)


def _skill_context(name: str, ai_config: dict) -> SkillContext:
    meta = _SKILLS.get(name)
    return SkillContext(
        name=name,
        data_dir=meta["data_dir"] if meta else str(SKILLS_DIR / name / "data"),
        shared=meta["shared"] if meta else {},
        ai_config=ai_config or {},
        get_http_client=lambda: ctx("get_http_client"),
    )


def _build_workflow_cache() -> None:
    """每次重启时扫描工作流目录，缓存最新清单到 search_workflows 技能 data/workflows.json。

    技能搜索时直接读缓存，避免每次调用都扫目录。重启即刷新。
    缓存文件属 ai_chat.py 独立管理（*.json 已被 .gitignore 忽略）。
    """
    try:
        with _lock:
            cfg = _load()
        sd = (cfg or {}).get("skill_data") or {}
        root = str(sd.get("workflows_dir", "") or "").strip()
        if not root:
            return
        base = Path(root)
        if not base.is_dir():
            print(f"[ai-chat skill] 工作流目录不存在: {root}", flush=True)
            return
        # 可选：从 workflow_meta.json 补充分类（若配置了则用它）
        cats: dict = {}
        try:
            meta_p = sd.get("workflow_meta_file") or str(_WEB_DIR / "workflow_meta.json")
            if os.path.isfile(meta_p):
                d = json.load(open(meta_p, encoding="utf-8"))
                if isinstance(d, list):
                    for w in d:
                        if isinstance(w, dict) and w.get("workflow"):
                            cats[str(w["workflow"]).replace("\\", "/")] = str(w.get("category", "") or "未分类")
        except Exception:
            cats = {}
        out: list = []
        for sub in ("文生图", ""):
            d = base / sub if sub else base
            if not d.is_dir():
                continue
            for f in sorted(d.rglob("*.json")):
                rel = f.relative_to(base).as_posix()
                if not rel.startswith("文生图/"):
                    rel = "文生图/" + rel
                out.append({"path": rel, "name": f.stem, "category": cats.get(rel, "未分类")})
            if out:
                break
        cache_dir = SKILLS_DIR / "search_workflows" / "data"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "workflows.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"[ai-chat skill] 工作流清单已缓存: {len(out)} 条（重启刷新）", flush=True)
    except Exception as e:
        print(f"[ai-chat skill] 工作流缓存生成失败: {type(e).__name__}: {e}", flush=True)


# 每次重启缓存一份最新工作流清单（技能 search_workflows 读缓存）
_build_workflow_cache()

# ── 角色库内存缓存（启动时加载，查询/缩略图走内存，更快）──
_CHAR_MEM: List[Dict[str, Any]] = []
_ALIAS_MEM: Dict[str, str] = {}
# 中文→英文 danbooru tag 翻译缓存（避免重复调 LLM）
_TRANS_CACHE: Dict[str, str] = {}


def _load_char_mem() -> None:
    """每次重启把角色库 + 别名表加载到内存。"""
    global _CHAR_MEM, _ALIAS_MEM
    _CHAR_MEM = []
    _ALIAS_MEM = {}
    try:
        with _lock:
            cfg = _load()
        sd = (cfg or {}).get("skill_data") or {}
        db = str(sd.get("character_db", "") or "").strip()
        if db and not os.path.isabs(db):
            db = str((_WEB_DIR / db).resolve())
        if not db or not os.path.isfile(db):
            return
        import sqlite3
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute("SELECT danbooru_tag, franchise, name_cn, tags, post_count, image FROM character")
            for r in rows:
                tag, franchise, name_cn, tags = (r[0] or ""), (r[1] or ""), (r[2] or ""), (r[3] or "")
                _CHAR_MEM.append({
                    "danbooru_tag": tag, "franchise": franchise, "name_cn": name_cn,
                    "tags": tags, "post_count": r[4] or 0, "image": r[5] or "",
                    "lc": f"{tag} {franchise} {name_cn} {tags}".lower(),
                })
            for (alias, tag) in conn.execute("SELECT alias, tag FROM tag_alias"):
                _ALIAS_MEM[str(alias)] = str(tag)
        finally:
            conn.close()
        print(f"[ai-chat] 角色库已加载到内存: {len(_CHAR_MEM)} 角色 / {len(_ALIAS_MEM)} 别名", flush=True)
    except Exception as e:
        print(f"[ai-chat] 角色库内存加载失败: {type(e).__name__}: {e}", flush=True)


_load_char_mem()


# 生图助手工具集 = 技能目录里发现的所有工具（仿 2x.nz：AI 自主搜角色/画风/尺寸）
GEN_TOOLS = [_skill_schema(n, m) for n, m in _SKILLS.items()]


async def _exec_search_tool(call: dict, sources: list) -> str:
    """执行工具调用，返回结果文本。复用现有 _web_search / _fetch_webpage。"""
    fn = (call.get("function") or {})
    name = fn.get("name", "")
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except Exception:
        args = {}
    if name == "web_search":
        return await _web_search(str(args.get("query", "")))
    if name == "fetch_page":
        try:
            d = await _fetch_webpage(str(args.get("url", "")))
            sources.append({"title": d.get("title", ""), "url": d.get("url", "")})
            return d.get("text", "") or "（该页面无文字内容）"
        except Exception as e:
            return f"（抓取失败: {type(e).__name__}）"
    # ── 技能目录分发（生图工具等，仿 ComfyUI 插件）──
    if name in _SKILLS:
        executor = _get_skill_executor(name)
        if executor is not None:
            try:
                with _lock:
                    ai_cfg = _load()
                ctx = _skill_context(name, ai_cfg)
                result = executor(args, ctx)
                if inspect.isawaitable(result):
                    # 超时兜底：防 async 技能网络卡死拖住 agent 回复
                    result = await asyncio.wait_for(result, timeout=30)
                return str(result or "")
            except asyncio.TimeoutError:
                print(f"[ai-chat skill] 执行 {name} 超时（30s）", flush=True)
                return f"（技能 {name} 执行超时）"
            except Exception as e:
                print(f"[ai-chat skill] 执行 {name} 异常: {type(e).__name__}: {e}", flush=True)
                return f"（技能 {name} 执行失败: {type(e).__name__}）"
        return f"（技能 {name} 加载失败）"
    if name == "trigger_generation":
        return "生图参数已接收，请直接向用户输出最终生图卡片。"
    return "（未知工具）"


# ── 生图助手工具集（仿 2x.nz：AI 自主搜角色/画风/尺寸 → 生成生图卡片）──

def _gen_load_chars() -> list:
    try:
        import json as _j, os as _os
        p = str(_WEB_DIR / "characters.json")
        d = _j.load(open(p, encoding="utf-8"))
        return [c for c in d if isinstance(c, dict) and str(c.get("name", "")).strip()]
    except Exception:
        return []


def _gen_load_styles() -> list:
    try:
        import json as _j, os as _os
        p = str(_WEB_DIR / "styles.json")
        d = _j.load(open(p, encoding="utf-8"))
        return [s for s in d if isinstance(s, dict) and str(s.get("name", "")).strip()]
    except Exception:
        return []


def _gen_load_workflows() -> list:
    """加载工作流库（web/workflow_meta.json：工作流路径 + 分类）。"""
    try:
        import json as _j, os as _os
        p = str(_WEB_DIR / "workflow_meta.json")
        d = _j.load(open(p, encoding="utf-8"))
        out = []
        if isinstance(d, list):
            for w in d:
                if isinstance(w, dict) and str(w.get("workflow", "")).strip():
                    out.append({"path": w.get("workflow"), "name": str(w.get("workflow", "")).split("/")[-1].replace(".json", ""), "category": w.get("category", "") or "未分类"})
        elif isinstance(d, dict):
            for path, meta in d.items():
                if isinstance(meta, dict):
                    out.append({"path": path, "name": str(path).split("/")[-1].replace(".json", ""), "category": meta.get("category", "") or "未分类"})
        return out
    except Exception:
        return []


# ── 工作流 → 提示词规则映射 ──
# 按工作流文件名关键词匹配规则（优先匹配靠前的规则）；支持 ai_chat.json skill_data.workflow_rules 精确覆盖：
#   {"workflow_rules": {"▶▶Z-Anime-漫画.json": "anima"}}
# 规则名：anima / wai / zimage / krea / flux
_MODEL_RULE_KEYWORDS = [
    ("anima",  ("anima", "anime", "z-anime")),
    ("wai",    ("wai", "noobai", "illustrious", "icattower", "matureritual", "miaomiao", "oneobsession", "vil-gembyte")),
    ("zimage", ("z-image", "zimage", "wan", "qwen-edit")),
    ("krea",   ("krea",)),
    ("flux",   ("flux", "klein")),
]


def _workflow_rule_name(workflow_path: str) -> str:
    """返回工作流对应的提示词规则名。精确文件名覆盖表优先，其次关键词匹配。"""
    name = (workflow_path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not name:
        return ""
    try:
        with _lock:
            cfg = _load()
        wm = ((cfg or {}).get("skill_data") or {}).get("workflow_rules") or {}
        if isinstance(wm, dict):
            over = str(wm.get(name, "") or "").strip().lower()
            if over:
                return over
    except Exception:
        pass
    for rule, kws in _MODEL_RULE_KEYWORDS:
        if any(k in name for k in kws):
            return rule
    return ""


def _prompt_style_for_workflow(workflow_path: str) -> str:
    """按工作流名称关键词返回对应模型的提示词写法规范（供 AI 生图决策使用）。

    不同模型（FLUX/Wan/Z-image/Illustrious/SDXL 等）对正向提示词的结构和写法要求不同：
    FLUX/Wan/Z-image 适合自然语言短句，SDXL/Illustrious/NoobAIXL/WAI 适合 Danbooru 标签。
    """
    name = (workflow_path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    rule = _workflow_rule_name(workflow_path)

    if rule == "flux":
        return (
            "【当前工作流是 FLUX 系列模型（Flux2-klein / klein 写实 cos 等）】提示词写法（官方建议）：\n"
            "- 正向提示词：使用通顺的英文自然语言短句（1-3 句），像给人类描述画面一样，包含主体、动作、环境、光线、氛围；不要用 Danbooru 标签堆砌。\n"
            "- 括号权重允许但强度不要超过 1.2（如 (red dress:1.1)），尽量优先用自然语言表达强调。\n"
            "- 反向提示词：'blurry, low quality, watermark, text, extra limbs' 这类精简负面词。"
        )
    if rule == "krea":
        return (
            "【当前工作流是 Krea-2 模型】提示词写法（官方 prompting 规范）：\n"
            "- 正向提示词：使用详细的中文或英文自然语言句子（支持中英混合），像给人描述画面一样写清楚主体、动作、环境、光线、氛围、构图；长而详细的提示词效果最好。\n"
            "- 禁止使用 SD 式权重语法（如 (tag:1.2)、[tag]、tag1+tag2），Krea 不识别这种语法。\n"
            "- 若需要渲染画面中的文字，把要渲染的文字用英文引号括起来，如 \"NEON\"。\n"
            "- 反向提示词：'blurry, low quality, watermark, text, extra limbs' 这类精简负面词。"
        )
    if rule == "zimage":
        if "turbo" in name:
            return (
                "【当前工作流是 Z-Image-Turbo 模型】提示词写法（官方规范）：\n"
                "- 正向提示词：使用中文或英文的自然语言句子（支持中英双语文本渲染），写清楚主体、场景、动作、光线、细节。\n"
                "- 重要：Z-Image-Turbo 原生完全忽略 Negative Prompt（CFG=0），所有约束都必须写进正向提示词，例如避免解剖错误写 'well-proportioned anatomy'、无水印写 'no watermark, no text'。\n"
                "- 反向提示词字段应留空或极简（写了也不生效）。"
            )
        return (
            "【当前工作流是 Z-Image/Wan/Qwen-Edit 系模型】提示词写法（官方规范）：\n"
            "- 正向提示词：使用中文或英文的自然语言句子（支持双语），写清楚主体、场景、动作、光线、细节；禁止解剖/画质词堆砌成 Danbooru 标签。\n"
            "- 反向提示词：可正常使用，写清不希望出现的内容（基础模型支持 negative prompt）。"
        )
    if rule == "wai":
        if "noobai" in name:
            return (
                "【当前工作流是 NoobAIXL 模型】提示词写法：\n"
                "- 正向提示词：Danbooru 标签风格，逗号分隔，按重要性排序（主体→细节→场景），固定加画质词 'masterpiece, best quality, absurdres, highres, extremely detailed'。\n"
                "- 反向提示词：'lowres, bad anatomy, bad hands, text, error, missing finger, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry'。"
            )
        return (
            "【当前工作流是 WAI/Illustrious 动漫模型（含角色/画风 Lora）】提示词写法：\n"
            "- 正向提示词：Danbooru 标签风格，逗号分隔。若模型绑定角色 Lora，先写角色名及触发词，再写 '1girl, (角色特征), 动作/表情/服饰/场景', 固定加画质词 'masterpiece, best quality'。\n"
            "- 反向提示词：'lowres, bad anatomy, bad hands, text, error, worst quality, low quality, jpeg artifacts, signature, watermark, username, blurry'。"
        )
    if rule == "anima":
        return (
            "【当前工作流是 Anima 二次元 DiT 模型（含角色 Lora）】提示词写法（官方规范）：\n"
            "- 正向提示词：Danbooru 标签风格，逗号分隔，固定加质量词 'masterpiece, best quality, solo' 开头。先写角色名及 Lora 触发词（若有），再写人物特征/动作/服饰/场景。\n"
            "- 支持 @画师 触发词语法（如 '@某某画师'）指定特定画师风格；权重用法类似 SD 的 (tag:1.1)。\n"
            "- 反向提示词：仅用 'worst quality, low quality'（极简，屏蔽低清晰度低质量）。本地模型支持宽松内容，不要添加内容限制类负面词。"
        )
    # SDXL 通用绘画（IcatTowerCknV12 / VIL-Gembyte / matureritual 等未匹配关键词时）及默认
    return (
        "【当前工作流是 SDXL 通用二次元绘画模型】提示词写法：\n"
        "- 正向提示词：Danbooru 标签风格，逗号分隔，按重要性排序（主体→细节→场景），固定加画质词 'masterpiece, best quality, highres'。\n"
        "- 反向提示词：'lowres, bad anatomy, bad hands, text, error, worst quality, low quality, jpeg artifacts, signature, watermark, username, blurry'。"
    )


# ── 提示词扩写指令库（按工作流模型类型选对应扩写指令）──
# 指令文件放在 config/prompt_instructions/（*.txt 已被 .gitignore 忽略，指令私有不进 git）

_INSTRUCTION_DIR = CONFIG_DIR / "prompt_instructions"
_instruction_cache: Dict[str, str] = {}


def _load_instruction(filename: str) -> str:
    """读取指令文件内容（进程内缓存，读一次）。"""
    if filename in _instruction_cache:
        return _instruction_cache[filename]
    p = _INSTRUCTION_DIR / filename
    if not p.is_file():
        return ""
    try:
        text = p.read_text(encoding="utf-8")
        _instruction_cache[filename] = text
        return text
    except Exception:
        return ""


# ── 补充提示词（可为空）：AI 聊天生图的可选系统提示词前缀，默认开启（配置在 gitignore 的 json，不进仓库）──
_AI_CHAT_EXTRA_FILE = CONFIG_DIR / "ai_chat_extra_prompt.json"
_aichat_extra_cache: Optional[Dict[str, Any]] = None


def _load_ai_chat_extra_prompt() -> Dict[str, Any]:
    """读取补充提示词配置。默认 {enabled:true, prompt:默认模板}；首次运行自动生成配置文件。"""
    global _aichat_extra_cache
    if _aichat_extra_cache is not None:
        return _aichat_extra_cache
    default = {
        "enabled": True,
        "prompt": "",
    }
    try:
        if _AI_CHAT_EXTRA_FILE.is_file():
            d = json.loads(_AI_CHAT_EXTRA_FILE.read_text(encoding="utf-8"))
            _aichat_extra_cache = {
                "enabled": bool(d.get("enabled", True)),
                "prompt": str(d.get("prompt", "") or ""),
            }
        else:
            _AI_CHAT_EXTRA_FILE.parent.mkdir(parents=True, exist_ok=True)
            _AI_CHAT_EXTRA_FILE.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
            _aichat_extra_cache = dict(default)
    except Exception:
        _aichat_extra_cache = {"enabled": False, "prompt": ""}
    return _aichat_extra_cache


def _prompt_instruction_for_workflow(workflow_path: str) -> str:
    """按工作流名关键词匹配扩写指令。无匹配返回空（调用方用默认）。

    规则 → 指令：anima→anima3模板-精简、wai→wai_noobai、zimage→z-image、
    krea→krea2、flux→动漫转真人。规则由 _workflow_rule_name 决定（含精确覆盖表）。
    """
    rule = _workflow_rule_name(workflow_path)
    if rule == "krea":
        return _load_instruction("Krea2扩写改写指令.txt")
    if rule == "zimage":
        return _load_instruction("Z-Image扩写改写指令.txt")
    if rule == "flux":
        return _load_instruction("Flux2-klein扩写指令.txt")
    if rule == "wai":
        return _load_instruction("WAI扩写改写指令.txt")
    if rule == "anima":
        return _load_instruction("Anima扩写改写指令.txt")
    return ""


def _prompt_style_by_keyword(text: str) -> str:
    """检测用户消息里提到的模型/工作流关键词，返回对应提示词规范。

    解决用户只在消息里说"用 Krea2/FLUX/Anima"但顶部工作流未切换时，
    AI 仍然按顶部工作流写提示词的问题。
    """
    t = (text or "").lower()
    for kw, fake in (
        ("krea", "krea.json"),
        ("flux", "flux.json"),
        ("z-image", "z-image.json"), ("zimage", "z-image.json"),
        ("wan", "wan.json"),
        ("noobai", "noobai.json"),
        ("wai", "wai.json"), ("illustrious", "wai.json"),
        ("anima", "anima.json"), ("anime", "anima.json"),
    ):
        if kw in t:
            return _prompt_style_for_workflow(fake)
    return ""


def _gen_builtin_assets(workflow_path: str) -> str:
    """按工作流名称关键词匹配其内置的角色/画风 Lora（触发词），供 AI 生成提示词时使用。

    同名画风/角色可能存在于多个分类（如"鬼针草画风"既有 SD 版也有 Anima 版），
    这里按工作流名称推断分类倾向，并把分类信息告诉 AI，让它只选一个最匹配的。
    """
    name = (workflow_path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not name:
        return ""
    # 按规则名推断分类倾向（与扩写规则一致）；zimage 规则兼容 "z-image"/"zimage" 两种分类写法
    pref = _workflow_rule_name(workflow_path)

    def _pref_hit(cat: str) -> bool:
        if not pref:
            return False
        c = (cat or "").lower()
        if pref == "zimage":
            return "z-image" in c or "zimage" in c
        return pref in c

    parts = []
    for c in _gen_load_chars():
        ckey = str(c.get("name", "")).split("（")[0].split("(")[0].replace("角色", "").strip().lower()
        if ckey and (ckey in name or name in ckey):
            cat = str(c.get("category", "")).strip()
            mark = "★当前工作流分类优先" if _pref_hit(cat) else ""
            parts.append(f"角色 Lora：{c.get('name')}（分类：{cat or '未分类'}{('，' + mark) if mark else ''}；触发词 {c.get('tags', '')[:120]}）")
    for s in _gen_load_styles():
        skey = str(s.get("name", "")).split("（")[0].split("(")[0].replace("画风", "").strip().lower()
        if skey and (skey in name or name in skey):
            cat = str(s.get("category", "")).strip()
            mark = "★当前工作流分类优先" if _pref_hit(cat) else ""
            parts.append(f"画风 Lora：{s.get('name')}（分类：{cat or '未分类'}{('，' + mark) if mark else ''}；触发词 {s.get('tags', '')[:120]}）")
    if not parts:
        return ""
    return ("【当前工作流内置 Lora】" + "；".join(parts)
            + "。**重要：同名画风/角色可能分属不同分类（如 SD 版和 Anima 版），请选择标注了 ★当前工作流分类优先 的那个；若没有标注★则根据工作流名推断。只选一个最匹配的画风/角色，不要混用多个同名的。**"
            + "生成提示词时必须包含所选内置 Lora 的触发词；若用户需求与之冲突则以用户指定为准。")


def _gen_assets_catalog() -> str:
    """内置角色/画风库名称清单，让 AI 知道可选资源（可再调 search 获取详情）。"""
    cn = [c.get("name", "") for c in _gen_load_chars()]
    sn = [s.get("name", "") for s in _gen_load_styles()]
    parts = []
    if cn:
        parts.append("内置角色库：" + "、".join(cn))
    if sn:
        parts.append("内置画风库：" + "、".join(sn))
    return "\n".join(parts) if parts else ""


def _decision_summary(messages: list, gen_card: dict | None = None) -> str:
    """生成 AI 决策摘要（需求 + 结论），补进思考过程，弥补短思考模型（如 DeepSeek Flash）。"""
    parts: list = []
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, list):
            for item in c:
                if item.get("type") == "text" and str(item.get("text", "")).strip():
                    parts.append("需求：" + str(item["text"]).strip().replace("\n", " ")[:100])
                    break
        elif isinstance(c, str) and c.strip():
            parts.append("需求：" + c.strip().replace("\n", " ")[:100])
        break
    if gen_card:
        parts.append("结论：生图参数已定（角色=" + str(gen_card.get("character") or "未指定")
                     + "；画风=" + str(gen_card.get("style") or "未指定")
                     + f"；尺寸={gen_card.get('width')}x{gen_card.get('height')}）")
    return "【决策摘要】" + "；".join(parts) if parts else ""


async def _agentic_search(messages: List[dict], temperature: float, max_tokens: int = 0, sampling: dict | None = None, max_rounds: int = 8, tools: Optional[list] = None, sys_guide: str = "") -> tuple:
    """多轮决策循环：LLM 自主调用工具，直到给出最终答案。

    返回 (final_text, sources, question, gen_card)。
    - question 非空表示需要用户回答（AI 反问）。
    - gen_card 非空表示 AI 生成了生图卡片（prompt/negative_prompt/width/height/character/style）。
    - 否则 final_text 是最终回答，sources 是访问过的来源。
    """
    if tools is None:
        tools = SEARCH_TOOLS
    sources: list = []
    gen_card = None
    reasoning_parts: list = []
    if not sys_guide:
        sys_guide = (
            "你可以使用工具获取信息。决策原则：\n"
            "1. 遇到需要实时信息/资料/不熟悉的话题，先调用工具。\n"
            "2. 若用户需求模糊、信息不足、或需要在多个选项中做选择，必须调用 ask_user 工具向用户提问澄清（前端会显示选项按钮）。绝对不要用普通文字反问。\n"
            "3. 信息足够后直接输出最终回答，不要调用工具。\n"
            "4. 如果你正在生成生图卡片，先搜索角色/画风/尺寸，最后调用 trigger_generation 提交，然后输出卡片。"
        )
    # 把决策指令附加到当前 user 消息后（避免污染历史）
    work_messages = list(messages)
    if work_messages and work_messages[-1].get("role") == "user":
        content = work_messages[-1].get("content")
        if isinstance(content, str):
            work_messages[-1]["content"] = content + "\n\n" + sys_guide
        elif isinstance(content, list):
            work_messages[-1]["content"] = content + [{"type": "text", "text": "\n\n" + sys_guide}]

    for _ in range(max_rounds):
        content, tool_calls, reasoning = await _call_llm(work_messages, temperature, max_tokens, sampling, tools=tools)
        print(f"[ai-chat agent] round={_+1} tool_calls={json.dumps(tool_calls, ensure_ascii=False)[:200] if tool_calls else 'NONE'}", flush=True)
        if not tool_calls:
            content = content or reasoning
            _sum = _decision_summary(messages, gen_card)
            _reasoning = "\n".join(reasoning_parts) + ("\n" + _sum if _sum else "")
            return content, sources, None, gen_card, _reasoning
        # 有工具调用：reasoning 是模型思考（reasoning_content 字段），content 常为正式说明（不混入思考过程）
        if reasoning and reasoning.strip():
            reasoning_parts.append(reasoning.strip())
        # 记录工具调用轨迹（模型无思考文本时也能看到决策过程）
        tool_trace = []
        for call in tool_calls:
            fn = (call.get("function") or {})
            nm = fn.get("name", "")
            if nm == "trigger_generation":
                tool_trace.append("trigger_generation(提交生图参数)")
            elif nm == "ask_user":
                tool_trace.append("ask_user(询问用户)")
            else:
                try:
                    ar = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    ar = {}
                vs = ",".join([str(v)[:40] for v in list(ar.values())[:2]])
                tool_trace.append(f"{nm}({vs})")
        if tool_trace:
            reasoning_parts.append("调用工具：" + "；".join(tool_trace))

        # 1. 先追加 assistant 消息（含 tool_calls）——tool 结果必须跟在 assistant 后
        asst_content = content or None if tool_calls else content
        work_messages.append({"role": "assistant", "content": asst_content, "tool_calls": tool_calls})

        # 2. 优先处理 ask_user（反问），其余执行工具
        ask = None
        for call in tool_calls:
            fn = (call.get("function") or {})
            if fn.get("name") == "ask_user":
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                ask = {
                    "question": str(args.get("question", "")),
                    "options": args.get("options") or [],
                }
                break
        if ask:
            _sum = _decision_summary(messages, gen_card)
            _reasoning = "\n".join(reasoning_parts) + ("\n" + _sum if _sum else "")
            return content, sources, ask, gen_card, _reasoning

        # 3. 执行工具，结果回填；捕获 trigger_generation 参数
        for call in tool_calls:
            fn = (call.get("function") or {})
            if fn.get("name") == "ask_user":
                continue
            if fn.get("name") == "trigger_generation":
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                gen_card = {
                    "prompt": str(args.get("prompt", "")).strip(),
                    "negative_prompt": str(args.get("negative_prompt", "")).strip(),
                    "width": int(args.get("width", 896) or 896),
                    "height": int(args.get("height", 1152) or 1152),
                    "character": str(args.get("character", "")).strip(),
                    "style": str(args.get("style", "")).strip(),
                    "workflow_path": str(args.get("workflow_path", "")).strip(),
                }
                work_messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": "生图参数已接收。",
                })
                continue
            result = await _exec_search_tool(call, sources)
            work_messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": result,
            })

    # 超过轮次：强制让 LLM 基于已有信息总结
    content, _, reasoning = await _call_llm(work_messages, temperature, max_tokens, sampling)
    content = content or reasoning
    _sum = _decision_summary(messages, gen_card)
    _reasoning = "\n".join(reasoning_parts) + ("\n" + _sum if _sum else "")
    return content, sources, None, gen_card, _reasoning



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
    gen_mode = bool(body.get("gen_mode", False))
    workflow_path = str(body.get("workflow_path", "")).strip()
    selected_characters = str(body.get("selected_characters", "")).strip()
    selected_style = str(body.get("selected_style", "")).strip()
    # 高级面板预设分辨率（前端 genConfig.width/height），AI 生成卡片时优先采用
    user_width = int(body.get("width", 0) or 0)
    user_height = int(body.get("height", 0) or 0)
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
        # 多轮决策搜索（function calling）：AI 自主搜索/访问/反问
        agent_result = None  # (content, sources, question)
        sources = []  # 非 agent 路径的来源（保持兼容）
        # 先构建完整 messages（含 history），供 agent 决策
        content_parts: list = []
        if message:
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
                hreason = str(h.get("reasoning", "") or "").strip()
                if hreason and role == "assistant":
                    htext = htext + "\n\n（我之前决策时的思考过程，供参考保持思路连贯，不要重复输出：\n" + hreason[:600] + "\n）"
                if himg:
                    messages.append({"role": role, "content": [
                        {"type": "text", "text": htext},
                        {"type": "image_url", "image_url": {"url": himg}},
                    ]})
                else:
                    messages.append({"role": role, "content": htext})
        messages.append({"role": "user", "content": content_parts})

        if do_search or gen_mode:
            gen_sys_guide = None
            if gen_mode:
                gen_sys_guide = (
                    "你是 AI 生图助手，根据用户需求生成生图参数卡片。决策原则：\n"
                    "0. 【提示词形式三选一】根据顶部工作流模型类型 + 用户描述语言自动选择提示词写法：\n"
                    "   - 动漫标签模型（工作流名含 Anima/anime/WAI/Illustrious/NoobAI 或 SDXL 系）→ 用英文 Danbooru 标签（逗号分隔，质量词打头）。\n"
                    "   - 自然语言模型（工作流名含 Krea/FLUX/Flux/Z-Image/Zimage/Wan）→ 用通顺的英文句子描述画面。\n"
                    "   - 若用户用中文详细描述需求且所选工作流是自然语言模型 → 可直接用中文自然语言扩写或中英混合；标签模型则始终用英文标签。\n"
                    "1. 用户提到角色时，先调用 search_characters 搜索（可多次搜索不同角色，支持多角色组合）。搜到多个版本时，用 ask_user 让用户选择版本。\n"
                    "2. 用户提到画风时，调用 search_styles 搜索；找不到就用自然语言描述画风。用户指定了分类（如'anima 分类的鬼针草画风'）时，把分类写进搜索关键词并优先选用该分类下的画风。\n"
                    "3. 用户明确要求切换模型/工作流（如'用 anima 工作流''用 Krea2 生图'）时，先调用 search_workflows 搜索匹配的工作流，并在 trigger_generation 时带上所选 workflow_path；若用户只说了模型家族（anima/krea/flux）则选该家族下合适的工作流。\n"
                    "3.5. **真人写实/写实摄影/动漫转真人/真人 cos 需求**：Anima 等动漫 DiT 模型无法生成真人写实图，必须调用 search_workflows 搜索写实工作流，并在 trigger_generation 时**必须传入 workflow_path**（优先选择 Krea2 系列写实工作流，如 ▶▷Krea2-文生图 / ▶▷Krea2-文生图东方等；其次 Klein/Flux2 写实）。否则确认生成会用顶部动漫模型导致效果错误。\n"
                    "4. 用户提到画幅/横竖屏时，调用 get_recommended_dimensions 获取尺寸；未提则默认竖屏 3:4。\n"
                    "5. 用户没选角色/画风时，可根据上下文自由创作（原创角色）或沿用之前的角色/画风。\n"
                    "6. 需求清晰后，立即调用 trigger_generation 提交生图参数。**生成的 prompt 必须是融合了角色/画风/需求/质量词/场景的完整最终提示词**：按工作流提示词结构组织（标签模型如 Anima/WAI 用 Danbooru：质量词打头 → 角色名与触发词 → 人物细节 → 服装 → 动作 → 场景 → 画风触发词 → 光线画质；自然语言模型如 Krea/FLUX 用通顺句子）。选中的角色触发词和画风触发词必须融合进 prompt 的正确位置，不要遗漏。character/style 字段可填对应名称作参考，但不要依赖它们单独拼接。\n"
                    "6.5. **反斜杠转义必须原样保留**：角色/画风库中的 tags 可能含反斜杠转义（如 `ganyu \\(genshin impact\\)`、`\\(masterpiece:1.2\\)`），这些 `\\(` `\\)` 是给生图模型的权重转义（防止括号被解析为权重语法），生成 prompt 时**必须一字不差地保留反斜杠**，绝对不要删除 `\\` 或把 `\\(` 改成 `(`。写 prompt 时原样粘贴搜索到的 tags。\n"
                    "7. 如果用户是在上一张卡片基础上微调（说'改成/加上/再画一个'），必须保留原卡片的角色/画风/关键元素，只修改用户要求的部分。\n"
                    "7.5. **修改服装/发色/配饰/姿态时**：\n"
                    "   - 改某特征 → **先移除原 prompt 中对应的旧 tags**，再补新 tags（如 bodystocking 改丝袜：删 bodystocking 加 pantyhose 或 thighhighs；黑发改红发：删 black hair 加 red hair），**绝不叠加冲突**。\n"
                    "   - 新增配饰 → 补标准 Danbooru 标签（穿丝袜=pantyhose/thighhighs；戴帽=hat；围巾=scarf），并检查互斥（穿丝袜不能 barefoot、换了发色不能保留旧发色 tag）。\n"
                    "   - 角色识别核心（角色名/作品/角/瞳色/非修改部位）必须保留。\n"
                    "8. 当用户表达确认/确定（如'确定、确认、就这样、可以、生成吧、开始吧、OK、好的'）且之前已有讨论好的需求时，立即调用 trigger_generation 基于之前讨论的内容提交生图参数并输出卡片，不要再追问或继续讨论。\n"
                    "10. **生成卡片必须通过 trigger_generation 工具调用，禁止只输出文本代替**：\n"
                    "   - 只要用户要求出图/生成卡片（或生图模式下需求已明确），**第一轮就必须调用 trigger_generation 工具**提交正/负提示词、尺寸、角色、画风参数，由系统渲染成审核卡片。\n"
                    "   - **可以**在调用工具前后输出简短文字说明/方案/建议（文本说明 + 卡片可共存，系统会把卡片渲染在回复下方）。\n"
                    "   - **绝对禁止**只输出 markdown 表格/文本卡片而不调用工具——那样前端收不到卡片，用户无法直接确认生成。\n"
                    "   - 调用工具后，工具会返回『生图参数已接收』。**建议在回复里展示改动后的完整「正向提示词」和「负面提示词」**，方便用户确认本次调整（如：本次修改了发色/服装，请把调整后的完整正向提示词、负面提示词用简洁段落列出，不要省略），同时系统会把卡片渲染在下方。\n"
                    "   - 区分：**展示提示词**（把完整正向/负面提示词用文字列出，帮助用户确认）可以；**用『| 参数项 | 内容 |』表格拼一张假卡片代替工具调用**不行——必须调用 trigger_generation。\n"
                    "   - 如果你发现自己想输出『| 参数项 | 内容 |』这种表格来呈现卡片，立刻改成调用 trigger_generation 工具。\n"
                    "9. **负面提示词以固定标准模板为基座，再根据本次提示词内容微调**：\n"
                    "   - 基础模板（动漫标签模型 Anima/WAI/Illustrious/NoobAI/SDXL 系）：`worst quality, low quality, bad anatomy, bad hands, missing fingers, extra digits, text, watermark, signature, blurry`\n"
                    "   - 基础模板（自然语言模型 Krea/FLUX/Z-Image/Wan）：`blurry, low quality, watermark, text, extra limbs, distorted`\n"
                    "   - **微调规则**：以对应基础模板为底，再按本次正向提示词的内容做针对性调整——① 若提示词主要画人物：确保含手部/解剖类负面词（bad hands、extra fingers、deformed hands），画风不写实则去掉过度写实类要求；② 若提示词是风景/场景/产品：手部负面词可去掉，改加透视/构图/材质类（warped perspective、distorted proportions、cheap plastic）；③ 若提示词含文字/海报需求：不要加 text/watermark 负面词（会压制画面文字），改为 no misspelled text、blurry text；④ 若用户明确说了不要某元素（如'不要眼镜''不要文字'），追加对应负面词。微调是增删个别词，不要推翻基础模板。"
                )
                # 判断当前工作流是标签模型还是自然语言模型（决定角色/画风触发词的使用方式）
                _wf_rule = _workflow_rule_name(workflow_path) if workflow_path else ""
                _is_natural_lang = _wf_rule in ("flux", "krea", "zimage")
                if selected_characters:
                    if _is_natural_lang:
                        gen_sys_guide += f"\n\n【用户已在顶部选择角色】{selected_characters}。注意：当前工作流是**自然语言模型**（不识别 Danbooru 标签，反斜杠转义也无意义）。不要把｜后面的标签整串原样贴进 prompt，而是**把该角色的外貌特征转化为通顺的自然语言描述**（主体+发型发色+瞳色+服装+气质），融合进画面描述；角色名/作品可保留（如 a girl resembling Ganyu from Genshin Impact）。不要用 multiple girls 这类标签，改用 two girls 等自然描述。"
                    else:
                        gen_sys_guide += f"\n\n【用户已在顶部选择角色】{selected_characters}。格式为「角色名（分类）｜触发词」：触发词是可直接使用的 Danbooru 标签，生成 prompt 时**直接原样使用｜后面的触发词**（反斜杠转义如 `\\(` `\\)` **必须一字不差保留，绝对不能删除**），不要丢弃、不要改写、不要再用 search_characters 重复搜索；多角色用 multiple girls 等组合（多角色用 multiple girls / 多个角色标签）。"
                if selected_style:
                    if _is_natural_lang:
                        gen_sys_guide += f"\n\n【用户已在顶部选择画风】{selected_style}。注意：当前工作流是**自然语言模型**（不识别 Danbooru 标签）。不要把｜后面的标签原样贴进 prompt，而是**用自然语言描述该画风的效果**（如：精致厚涂质感、细腻光影、柔和色彩），并把画风名/分类名保留在自然描述中。"
                    else:
                        gen_sys_guide += f"\n\n【用户已在顶部选择画风】{selected_style}。格式为「画风名（分类）｜触发词」：触发词是可直接使用的标签，生成 prompt 时**直接原样使用｜后面的触发词**（反斜杠转义如 `\\(` `\\)` **必须一字不差保留，绝对不能删除**），不要丢弃、不要改写、不要再用 search_styles 重复搜索。"
                    # 画风 ↔ 工作流关联：顶部同时选了画风和工作流时，声明其匹配关系（用户可能已选用对应画风 lora 的工作流）
                    if workflow_path:
                        _wf_style = str(workflow_path).replace("\\", "/").rsplit("/", 1)[-1].replace(".json", "")
                        _wf_cat = ""
                        try:
                            for _w in _gen_load_workflows():
                                if str(_w.get("path", "")).replace("\\", "/") == str(workflow_path).replace("\\", "/"):
                                    _wf_cat = str(_w.get("category", "") or "").strip()
                                    break
                        except Exception:
                            _wf_cat = ""
                        gen_sys_guide += f"\n\n【画风与工作流匹配】用户已在顶部选择画风「{selected_style.split('｜')[0].strip()}」，并已选用匹配该画风的当前工作流「{_wf_style}」{f'（类别：{_wf_cat}）' if _wf_cat else ''}。生成时必须**以该画风的触发词为准**，不要沿用旧卡片上的画风；除非用户明确要求更换画风/工作流。"
                # 高级面板预设分辨率：优先采用；用户消息里明确要求其他画幅/比例时再调整
                if user_width >= 512 and user_height >= 512:
                    gen_sys_guide += f"\n\n【用户已设置分辨率 {user_width}x{user_height}】trigger_generation 时优先使用该尺寸；若用户明确要求其他画幅（横竖/比例）再调整。"
                style_guide = _prompt_style_for_workflow(workflow_path)
                if style_guide:
                    gen_sys_guide += "\n\n" + style_guide
                # 锁定当前工作流：顶部已选时禁止 AI 擅自更换（除非用户明确要求切换）
                if workflow_path:
                    _wf_name = workflow_path.replace("\\", "/").rsplit("/", 1)[-1].replace(".json", "")
                    gen_sys_guide += f"\n\n【当前工作流（顶部已选）】{_wf_name}。trigger_generation 时必须沿用该 workflow_path；除非用户明确要求切换工作流/模型（如'换成 Krea2''用 anima 工作流'），否则禁止调用 search_workflows 或更换工作流。"
                # 当前工作流完整扩写/改写指令（扩写和改写规则都在里面），生图时同样遵循
                instruction = _prompt_instruction_for_workflow(workflow_path)
                if instruction:
                    gen_sys_guide += "\n\n【当前工作流扩写/改写指令】" + instruction
                # 用户消息中提到特定模型时，按其规范书写（即使顶部工作流未切换）
                keyword_guide = _prompt_style_by_keyword(message)
                if keyword_guide and keyword_guide != style_guide:
                    gen_sys_guide += "\n\n【用户消息中明确提到该模型】" + keyword_guide + "\n提示：用户指定了该模型，请优先按其规范书写提示词（如顶部工作流与其不一致，以用户消息指定的模型为准）。"
                builtin = _gen_builtin_assets(workflow_path)
                if builtin:
                    gen_sys_guide += "\n\n" + builtin
                catalog = _gen_assets_catalog()
                if catalog:
                    gen_sys_guide += "\n\n【系统内置资源库】以下是系统内置的画风/角色（可用 search_characters / search_styles 搜索获取详细触发词 tags）：\n" + catalog
                # 补充提示词（可为空）：管理员配置，启用且非空时前置到生图系统引导
                _aichat_extra = _load_ai_chat_extra_prompt()
                if _aichat_extra.get("enabled") and str(_aichat_extra.get("prompt", "") or "").strip():
                    gen_sys_guide = str(_aichat_extra["prompt"]).strip() + "\n\n" + gen_sys_guide
            agent_result = await _agentic_search(
                messages, temperature, max_tokens, sampling,
                tools=GEN_TOOLS if gen_mode else SEARCH_TOOLS,
                sys_guide=gen_sys_guide,
            )

        if llm_stream:
            async def _gen():
                got_content = False
                try:
                    if agent_result:
                        # 多轮决策结果：question 或最终 content / gen_card / reasoning
                        _, agent_sources, agent_question, agent_gen_card, agent_reasoning = agent_result
                        if agent_question:
                            yield f"data: {json.dumps({'question': agent_question}, ensure_ascii=False)}\n\n"
                            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                            return
                        agent_content = agent_result[0]
                        if agent_reasoning:
                            yield f"data: {json.dumps({'kind': 'reasoning', 'delta': agent_reasoning}, ensure_ascii=False)}\n\n"
                        if agent_content:
                            # 模拟流式逐块输出（约 40 字符/块）
                            for i in range(0, len(agent_content), 40):
                                yield f"data: {json.dumps({'delta': agent_content[i:i+40], 'kind': 'content'}, ensure_ascii=False)}\n\n"
                            got_content = True
                        if agent_sources:
                            yield f"data: {json.dumps({'sources': agent_sources}, ensure_ascii=False)}\n\n"
                        if agent_gen_card:
                            yield f"data: {json.dumps({'gen_card': agent_gen_card}, ensure_ascii=False)}\n\n"
                        if not got_content:
                            with _lock:
                                data = _load()
                                for t in data["tokens"]:
                                    if t["token"] == token:
                                        t["used"] = max(0, t.get("used", 0) - 1)
                                        _save_atomic(data)
                                        break
                            yield f"data: {json.dumps({'error': 'LLM 返回为空'}, ensure_ascii=False)}\n\n"
                            return
                        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                        return
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

        if agent_result:
            _, agent_sources, agent_question, agent_gen_card, agent_reasoning = agent_result
            if agent_question:
                return {"question": agent_question}
            reply = agent_result[0]
            if not reply and not agent_gen_card:
                # LLM 返回空内容，退还次数
                with _lock:
                    data = _load()
                    for t in data["tokens"]:
                        if t["token"] == token:
                            t["used"] = max(0, t.get("used", 0) - 1)
                            _save_atomic(data)
                            break
                raise HTTPException(500, "LLM 返回为空")
            resp: Dict[str, Any] = {}
            if agent_reasoning:
                resp["reasoning"] = agent_reasoning
            if reply:
                resp["reply"] = reply
            if agent_sources:
                resp["sources"] = agent_sources
            if agent_gen_card:
                resp["gen_card"] = agent_gen_card
            return resp

        reply, _, reply_reasoning = await _call_llm(messages, temperature, max_tokens, sampling)
        if not reply:
            reply = reply_reasoning
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


# 默认扩写优化指令（后端兜底，无匹配工作流指令时用）
_DEFAULT_OPTIMIZE_SYSTEM = """你是顶级 AI 绘画提示词优化专家。根据用户提供的画面描述/反推结果/角色/画风，生成符合主流文生图模型的提示词。

【主流模型提示词结构规则】
1. SDXL/Illustrious/NoobAI 系：用 Danbooru 标签（逗号分隔），质量词打头（masterpiece, best quality, amazing quality），再排主体（1girl, solo）、人物细节、动作、场景、光影、镜头。
2. Flux/Krea2 系：自然语言描述为主，句式"主体+动作/状态+环境+风格+光照+镜头"。
3. 权重语法：SD 系用 (tag:1.2) 强调；Flux/Krea 一般不用括号权重，用自然语言强调。
4. 反斜杠转义（如 \\(xxx\\)）必须原样保留，不要去掉反斜杠。

【输出格式】必须严格输出两行，不要任何其他内容：
POSITIVE: 优化的正向提示词
NEGATIVE: 优化的负面提示词"""


@router.post("/api/features/ai-chat/optimize")
async def api_ai_chat_optimize(request: Request):
    """提示词扩写/优化：按工作流模型类型选扩写指令，调 LLM 返回 POSITIVE/NEGATIVE。"""
    body = await request.json()
    token = str(body.get("token", "")).strip()
    workflow_path = str(body.get("workflow_path", "")).strip()
    prompt = str(body.get("prompt", "")).strip()
    negative = str(body.get("negative", "")).strip()
    character = str(body.get("character", "")).strip()
    style = str(body.get("style", "")).strip()
    userReq = str(body.get("userReq", "")).strip()
    width = str(body.get("width", "") or "").strip()
    height = str(body.get("height", "") or "").strip()
    # 思考模式开关：默认关（快）；前端可传 thinking=true 启用（质量更高）
    thinking = bool(body.get("thinking", False))

    if not token:
        raise HTTPException(400, "token required")
    entry = _verify_token(token)
    if not entry:
        raise HTTPException(403, "token 无效或次数已用完")
    if not _consume_token(token):
        raise HTTPException(403, "token 次数已用完")

    # 按工作流选扩写指令；无匹配用默认
    instruction = _prompt_instruction_for_workflow(workflow_path)
    if not instruction:
        instruction = _DEFAULT_OPTIMIZE_SYSTEM
    # 补充提示词（可为空）：与生图同源，启用且非空时前置到优化指令（AI 优化同样享受）
    _opt_extra_prompt = _load_ai_chat_extra_prompt()
    if _opt_extra_prompt.get("enabled") and str(_opt_extra_prompt.get("prompt", "") or "").strip():
        instruction = str(_opt_extra_prompt["prompt"]).strip() + "\n\n" + instruction
    # 保护：指令过长会超模型 context，截断保留规则框架并提示
    MAX_INSTRUCTION_CHARS = 60000
    if len(instruction) > MAX_INSTRUCTION_CHARS:
        instruction = instruction[:MAX_INSTRUCTION_CHARS] + "\n\n（注意：原指令模板过长已被截断。请按以上规则和已提供的标签库内容生成提示词，必要时补充合理标签。）"

    parts = []
    wf_name = (workflow_path or "").replace("\\", "/").rsplit("/", 1)[-1]
    if wf_name:
        parts.append(f"当前工作流：{wf_name}（提示词结构必须按该模型规则）")
    if character:
        parts.append(f"角色：{character}")
    if style:
        parts.append(f"画风：{style}")
    if width and height:
        parts.append(f"分辨率：{width}x{height}")
    if prompt:
        parts.append(f"当前提示词：{prompt}")
    if negative:
        parts.append(f"当前负面提示词：{negative}")
    if userReq:
        parts.append(f"用户需求：{userReq}")
    if not parts:
        parts.append("请生成一张图的提示词")
    user_msg = "\n".join(parts)

    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": user_msg},
    ]
    try:
        # 非思考模式（默认）+ 限 max_tokens：扩写优化只需直接输出，跳过推理显著提速；可传 thinking=true 启用推理
        _opt_extra = {}
        if not thinking:
            _opt_extra["thinking"] = {"type": "disabled"}
        reply, _, _ = await _call_llm(messages, 0.6, 1024, _opt_extra)
        if not reply:
            raise RuntimeError("LLM 返回为空")
    except Exception as e:
        with _lock:
            data = _load()
            for t in data["tokens"]:
                if t["token"] == token:
                    t["used"] = max(0, t.get("used", 0) - 1)
                    _save_atomic(data)
                    break
        raise HTTPException(500, f"LLM 调用失败: {type(e).__name__}: {e}")

    positive = reply
    negative_out = negative
    import re as _re
    pm = _re.search(r"POSITIVE:\s*([\s\S]*?)(?=NEGATIVE:|$)", reply)
    nm = _re.search(r"NEGATIVE:\s*([\s\S]*)", reply)
    if pm and pm.group(1).strip():
        positive = pm.group(1).strip()
    if nm and nm.group(1).strip():
        negative_out = nm.group(1).strip()
    return {"reply": reply, "positive": positive, "negative": negative_out}


@router.get("/api/features/ai-chat/search-characters")
async def api_search_characters(request: Request, q: str = ""):
    """搜索 AI 聊天角色库（SQLite 44000+ 角色，含别名映射）。供前端角色弹窗补全内置库。
    中文查询 LIKE 无结果时，先用 active_llm 翻译成 danbooru 英文 tag 再搜。
    """
    q = (q or "").strip().lower()
    if not q:
        return {"characters": []}

    def _has_cn(t: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in t)

    async def _translate(t: str) -> str:
        cached = _TRANS_CACHE.get(t)
        if cached:
            return cached
        try:
            with _lock:
                cfg = _load()
            llms = (cfg or {}).get("llms") or []
            active_id = (cfg or {}).get("active_llm_id", "")
            llm = next((x for x in llms if x.get("id") == active_id), llms[0] if llms else None)
            if not llm:
                return ""
            endpoint = str(llm.get("endpoint", "")).rstrip("/")
            model = str(llm.get("model", ""))
            if not endpoint or not model:
                return ""
            # 与 _llm_request_info 一致的 URL 拼接：endpoint 可能带/不带 /v1
            base = endpoint.rstrip("/")
            if base.endswith("/v1"):
                url = base + "/chat/completions"
            else:
                url = base + "/v1/chat/completions"
            client = await ctx("get_http_client")()
            headers = {"Content-Type": "application/json"}
            key = _decrypt_api_value(str(llm.get("api_key", "") or "").strip())
            if key and key.lower() != "none":
                headers["Authorization"] = f"Bearer {key}"
            body = {
                "model": model,
                "messages": [{"role": "user", "content": (
                    "把下面的中文动漫/游戏角色名翻译成对应的英文 danbooru 标签。"
                    "已知映射示例：甘雨→ganyu_(genshin_impact)，花火→sparkle_(honkai_star_rail)，"
                    "初音未来→hatsune_miku，雷电将军→raiden_shogun，纳西妲→nahida_(genshin_impact)。"
                    "如果输入是知名动漫/游戏角色，输出其官方 danbooru 英文名（含作品后缀）；"
                    "否则直接输出该中文的拼音或常用英文名。只输出一个英文结果，不要解释、不要标点。"
                    "输入：" + t
                )}],
                "max_tokens": 200,
                "stream": False,
                "temperature": 0.1,
            }
            # 超时 8s：DeepSeek 不可达时中文搜索快速降级，不卡死接口
            r = await client.post(url, json=body, headers=headers, timeout=8)
            if r.status_code >= 400:
                return ""
            d = r.json()
            result = str(((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip().strip("。，, ")
            if result:
                _TRANS_CACHE[t] = result  # 只缓存成功结果
            return result
        except Exception as e:
            print(f"[ai-chat] 角色翻译异常: {type(e).__name__}: {e}", flush=True)
            return f"ERR:{type(e).__name__}:{e}"

    async def _zerochan_thumb(tag: str) -> str:
        """从 zerochan 拉角色缩略图 URL（零成本预览，转主词标题化查询）。失败返回空。"""
        try:
            main = tag.split("_(")[0]
            qname = " ".join(w.capitalize() for w in main.replace("_", " ").split())
            if not qname:
                return ""
            client = await ctx("get_http_client")()
            r = await client.get(
                "https://www.zerochan.net/" + urllib.parse.quote(qname) + "?json",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=12,
            )
            if r.status_code >= 400:
                return ""
            d = r.json()
            items = d.get("items") or []
            return str(items[0].get("thumbnail", "") or "") if items else ""
        except Exception:
            return ""

    def _query_mem(term: str, limit: int = 30) -> list:
        """内存 LIKE 查询角色库（启动时已加载 _CHAR_MEM，用预小写组合字段一次 contains）。"""
        t = (term or "").lower()
        hits = [c for c in _CHAR_MEM if t in c["lc"]]
        hits.sort(key=lambda x: -int(x["post_count"]))
        out = hits[:limit * 2]
        # 别名映射补角色
        seen = {c["danbooru_tag"] for c in out}
        for alias, tag in _ALIAS_MEM.items():
            if t in alias.lower() and tag and tag not in seen:
                for c in _CHAR_MEM:
                    if c["danbooru_tag"] == tag:
                        out.append(c)
                        seen.add(tag)
                        break
        return out[:limit]

    def _ensure_image(c: dict) -> str:
        """返回角色缩略图；内存无则标记待拉取。"""
        return c.get("image") or ""

    def _save_image_mem(db_path: str, tag: str, img: str) -> None:
        """缩略图更新内存 + 落盘。"""
        for c in _CHAR_MEM:
            if c["danbooru_tag"] == tag:
                c["image"] = img
                break
        try:
            import sqlite3 as _sqlite3
            _conn = _sqlite3.connect(db_path)
            try:
                _conn.execute("UPDATE character SET image = ? WHERE danbooru_tag = ?", (img, tag))
                _conn.commit()
            finally:
                _conn.close()
        except Exception:
            pass

    try:
        with _lock:
            cfg = _load()
        sd = (cfg or {}).get("skill_data") or {}
        db = str(sd.get("character_db", "") or "").strip()
        if db and not os.path.isabs(db):
            db = str((_WEB_DIR / db).resolve())
        if not db or not os.path.isfile(db):
            return {"characters": []}
        if not _CHAR_MEM:
            _load_char_mem()
        rows = _query_mem(q)
        if not rows and _has_cn(q):
            en = await _translate(q)
            if en and not en.startswith("ERR:"):
                rows = _query_mem(en.split("_")[0])  # 取主词匹配

        # 为缺失缩略图的角色后台补图（不阻塞搜索返回，前端先显示占位，下次搜索出图）
        pending = [c for c in rows if c["danbooru_tag"] and not c.get("image")]
        if pending:
            async def _fill_thumb():
                results = await asyncio.gather(*(_zerochan_thumb(c["danbooru_tag"]) for c in pending), return_exceptions=True)
                for c, res in zip(pending, results):
                    if isinstance(res, str) and res:
                        _save_image_mem(db, c["danbooru_tag"], res)
            try:
                asyncio.create_task(_fill_thumb())
            except Exception:
                pass

        chars = []
        for c in rows:
            name = c["name_cn"] or c["danbooru_tag"] or "?"
            img = c.get("image") or ""
            # zerochan 外链有防盗链（Referer 检查），浏览器直连会 403；
            # 统一走本地代理端点转发，规避防盗链并支持缓存。
            if img.startswith("http"):
                img = f"/api/features/ai-chat/char-thumb?u={urllib.parse.quote(img, safe='')}"
            chars.append({"name": name, "franchise": c["franchise"], "tags": c["tags"] or c["danbooru_tag"], "image": img})
        return {"characters": chars}
    except Exception as e:
        print(f"[ai-chat] 角色搜索接口异常: {type(e).__name__}: {e}", flush=True)
        return {"characters": []}


@router.get("/api/features/ai-chat/char-thumb")
async def api_ai_chat_char_thumb(request: Request, u: str = ""):
    """AI 聊天角色缩略图代理：转发 zerochan 外链图片，规避防盗链。带缓存。"""
    from urllib.parse import urlparse
    if not u or not u.startswith(("https://", "http://")):
        raise HTTPException(400, "invalid url")
    host = urlparse(u).netloc.lower()
    if "zerochan.net" not in host:
        raise HTTPException(400, "仅允许 zerochan.net 图片")
    import hashlib as _hashlib
    # ETag 缓存
    etag = f'"{_hashlib.md5(u.encode()).hexdigest()[:16]}"'
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=86400"})
    try:
        client = await ctx("get_http_client")()
        r = await client.get(u, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.zerochan.net/"}, timeout=15)
        if r.status_code >= 400:
            raise HTTPException(502, "图片拉取失败")
        ctype = r.headers.get("content-type", "image/avif")
        return Response(content=r.content, media_type=ctype, headers={
            "ETag": etag, "Cache-Control": "public, max-age=86400",
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ai-chat] 缩略图代理失败 u={u}: {e}", flush=True)
        raise HTTPException(502, "图片代理失败")


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


@router.post("/api/admin/features/ai-chat/workflows-refresh")
async def admin_workflows_refresh(request: Request):
    """刷新工作流清单缓存（免重启）。返回本次扫描到的数量。"""
    require_admin(request)
    cache_file = SKILLS_DIR / "search_workflows" / "data" / "workflows.json"
    before = 0
    try:
        if cache_file.is_file():
            before = len(json.load(open(cache_file, encoding="utf-8")))
    except Exception:
        before = 0
    _build_workflow_cache()
    after = 0
    try:
        if cache_file.is_file():
            after = len(json.load(open(cache_file, encoding="utf-8")))
    except Exception:
        after = 0
    return {"ok": True, "before": before, "count": after, "updated": before != after}


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


@router.get("/api/admin/features/ai-chat/extra-prompt")
async def admin_aichat_extra_prompt_get(request: Request):
    require_admin(request)
    return _load_ai_chat_extra_prompt()


@router.post("/api/admin/features/ai-chat/extra-prompt")
async def admin_aichat_extra_prompt_set(request: Request):
    require_admin(request)
    global _aichat_extra_cache
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "payload must be object")
    data = {
        "enabled": bool(body.get("enabled", True)),
        "prompt": str(body.get("prompt", "") or "").strip(),
    }
    try:
        _AI_CHAT_EXTRA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _AI_CHAT_EXTRA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _aichat_extra_cache = data
        return {"ok": True, **data}
    except Exception as e:
        raise HTTPException(500, f"写入失败: {type(e).__name__}: {e}")


@router.post("/api/admin/features/ai-chat/tokens/cleanup")
async def admin_cleanup_tokens(request: Request):
    """清理失效 Token（已用完：max_uses>0 且 used>=max_uses）。返回清理数量。"""
    require_admin(request)
    with _lock:
        data = _load()
        before = len(data.get("tokens", []))
        keep = []
        for t in data.get("tokens", []):
            mx = int(t.get("max_uses", 0) or 0)
            used = int(t.get("used", 0) or 0)
            if mx > 0 and used >= mx:
                continue  # 失效，删除
            keep.append(t)
        data["tokens"] = keep
        _save_atomic(data)
        removed = before - len(keep)
    return {"ok": True, "removed": removed, "remaining": len(keep)}


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
                raw_key = str(l.get("api_key", "")).strip()
                if raw_key and not raw_key.startswith("fernet:"):
                    raw_key = _encrypt_api_value(raw_key)  # 明文密钥加密存储
                item = {
                    "id": lid,
                    "name": str(l.get("name", "")).strip(),
                    "endpoint": str(l.get("endpoint", "")).strip(),
                    "model": str(l.get("model", "")).strip(),
                    "api_key": raw_key,
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

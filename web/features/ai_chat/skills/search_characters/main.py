"""search_characters 技能：查 SQLite 角色库（44000+ 角色 + 别名映射 + 中文查询 LLM 翻译）。

- 中文查询（如"花火"）：先用本机 LLM 翻译成 danbooru 英文 tag（如 sparkle），再查库。
- 检索：1) 直接 LIKE 角色名/作品/中文名/特征标签；2) 别名表映射。
"""
import json
import os
import re
import sqlite3

# 中文→英文 tag 翻译缓存（避免重复调 LLM）
_TRANS_CACHE: dict = {}


def _db_path(ctx) -> str:
    return ctx.data.get("character_db") or ""


def _has_cn(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _decrypt_api_value(ciphertext: str) -> str:
    """解密 ai_chat.json 里 fernet 加密的 api_key（复用后端方案）。"""
    import base64 as _b64
    import os as _os
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.fernet import Fernet
    if not ciphertext or not ciphertext.startswith("fernet:"):
        return ciphertext
    env_key = _os.environ.get("LLM_ENCRYPTION_KEY", "")
    if not env_key:
        return ciphertext
    try:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"llm-api-key-v2")
        key = _b64.urlsafe_b64encode(hkdf.derive(env_key.encode()))
        return Fernet(key).decrypt(ciphertext[7:].encode()).decode()
    except Exception:
        return ciphertext


async def _translate_cn(q: str, ctx) -> str:
    """用 ai_chat.json 的 active_llm 把中文查询翻译成英文角色名/danbooru tag。"""
    if q in _TRANS_CACHE:
        return _TRANS_CACHE[q]
    cfg = ctx.ai_config or {}
    llms = cfg.get("llms") or []
    active_id = cfg.get("active_llm_id", "")
    llm = next((x for x in llms if x.get("id") == active_id), llms[0] if llms else None)
    if not llm:
        return ""
    endpoint = str(llm.get("endpoint", "")).rstrip("/")
    model = str(llm.get("model", ""))
    if not endpoint or not model or ctx.get_http_client is None:
        return ""
    try:
        client = await ctx.get_http_client()()
        headers = {"Content-Type": "application/json"}
        key = _decrypt_api_value(str(llm.get("api_key", "") or "").strip())
        if key and key.lower() != "none":
            headers["Authorization"] = f"Bearer {key}"
        # 与后端一致的 URL 拼接：endpoint 可能带/不带 /v1
        base = endpoint.rstrip("/")
        if base.endswith("/v1"):
            url = base + "/chat/completions"
        else:
            url = base + "/v1/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": (
                "把下面的中文动漫/游戏角色名翻译成对应的英文 danbooru 标签。"
                "已知映射示例：甘雨→ganyu_(genshin_impact)，花火→sparkle_(honkai_star_rail)，"
                "初音未来→hatsune_miku，雷电将军→raiden_shogun，纳西妲→nahida_(genshin_impact)。"
                "如果输入是知名动漫/游戏角色，输出其官方 danbooru 英文名（含作品后缀）；"
                "否则直接输出该中文的拼音或常用英文名。只输出一个英文结果，不要解释、不要标点。"
                "输入：" + q
            )}],
            "max_tokens": 200,
            "stream": False,
            "temperature": 0.1,
        }
        r = await client.post(url, json=body, headers=headers, timeout=8)
        if r.status_code >= 400:
            return ""
        d = r.json()
        out = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        result = str(out).strip().strip("。，, ")
        if result:
            _TRANS_CACHE[q] = result  # 只缓存成功结果
        return result
    except Exception:
        return ""


def _search_db(db_path: str, q: str, limit: int = 10) -> list:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        like = f"%{q}%"
        rows = cur.execute(
            """SELECT DISTINCT danbooru_tag, franchise, name_cn, tags FROM character
               WHERE danbooru_tag LIKE ? OR franchise LIKE ? OR name_cn LIKE ? OR tags LIKE ?
               ORDER BY post_count DESC LIMIT ?""",
            (like, like, like, like, limit * 2),
        ).fetchall()
        out = [dict(zip(("danbooru_tag", "franchise", "name_cn", "tags"), r)) for r in rows]
        seen = {r["danbooru_tag"] for r in out}
        for (tag,) in cur.execute("SELECT DISTINCT tag FROM tag_alias WHERE alias LIKE ? LIMIT 30", (like,)):
            if not tag or tag in seen:
                continue
            r = cur.execute(
                "SELECT danbooru_tag, franchise, name_cn, tags FROM character WHERE danbooru_tag = ? LIMIT 1", (tag,)
            ).fetchone()
            if r:
                out.append(dict(zip(("danbooru_tag", "franchise", "name_cn", "tags"), r)))
                seen.add(tag)
        return out[:limit]
    finally:
        conn.close()


async def execute(args: dict, ctx) -> str:
    q = str(args.get("query", "")).strip().lower()
    db = _db_path(ctx)
    if not q:
        return "（参数为空）"
    if not db or not os.path.isfile(db):
        return "（角色库数据库未找到，请确认 skill_data.character_db 配置）"

    try:
        # 先中文/原始词直接查库；命中不足时才 LLM 翻译补充（避免中文命中仍浪费翻译）
        hits = _search_db(db, q)
        if len(hits) < 5 and _has_cn(q):
            extra_q = await _translate_cn(q, ctx)
            if extra_q:
                extra_q = extra_q.split("_")[0]  # 取主词匹配
                extra = _search_db(db, extra_q, limit=5)
                if extra:
                    seen = {h["danbooru_tag"] for h in hits}
                    for h in extra:
                        if h["danbooru_tag"] not in seen:
                            hits.append(h)
    except Exception as e:
        return f"（角色库查询失败: {type(e).__name__}）"
    if not hits:
        return "（未找到匹配角色，可用自然语言绘制原创角色）"
    lines = []
    for h in hits:
        name = h["name_cn"] or h["danbooru_tag"] or "?"
        franchise = h["franchise"] or "未分类"
        tags = h["tags"] or h["danbooru_tag"]
        lines.append(f"- {name}（{franchise}）：{tags[:1000]}")
    return "角色候选：\n" + "\n".join(lines)

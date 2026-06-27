"""
外挂功能：访问密钥管理（从 app.py 迁出，行为 100% 保持原样）。

设计（中间人模式）：
  - 本模块**不** import app、**不** import db，所有数据库读写都走 app.py
    通过 features._deps.set_app_ctx() 注入的同一批函数（db / 锁 / session）。
  - 单一数据入口、共享锁，不会出现多模块争抢数据库读写。
  - API 路径、请求体、返回结构与原 app.py 完全一致，前端无需改动。

迁出的接口：
  GET  /api/admin/access-keys
  POST /api/admin/access-keys/generate
  POST /api/admin/access-keys/delete
  POST /api/admin/access-keys/cleanup
  POST /api/admin/access-keys/enable
  POST /api/admin/access-keys/remove
  POST /api/admin/access-keys/reveal
"""

import secrets
import time as _time
from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException

from features import _deps


def _require_admin(request: Request) -> None:
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(403)


router = APIRouter(tags=["access-keys"])


@router.get("/api/admin/access-keys")
async def api_admin_access_keys(request: Request, limit: int = 50, offset: int = 0):
    """分页列出访问密钥及使用状态。"""
    _require_admin(request)
    db = _deps.ctx("db")
    load_users = _deps.ctx("load_users")
    now = _time.time()
    data = db.load_access_keys()
    keys = data.get("keys", {})
    items = []
    users = load_users()
    for key, entry in keys.items():
        used_by = entry.get("used_by", "")
        login = ""
        if used_by:
            u = users.get(used_by, {})
            login = u.get("login", used_by)
        expires_at = entry.get("expires_at", 0)
        disabled_at = entry.get("disabled_at", 0)
        disabling = disabled_at and now <= disabled_at + 2
        items.append({
            "key_preview": key[:8] + "..." + key[-4:],
            "used_by": used_by,
            "login": login,
            "created_at": entry.get("created_at", 0),
            "expires_at": expires_at,
            "expired": expires_at > 0 and now > expires_at + 60,
            "disabled_at": disabled_at,
            "disabling": disabling,
            "max_uses": entry.get("max_uses", 0),
            "used_count": entry.get("used_count", 0),
        })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    total = len(items)
    offset = max(0, offset)
    limit = max(1, min(limit, 200))
    items = items[offset:offset + limit]
    return {"items": items, "total": total}


@router.post("/api/admin/access-keys/generate")
async def api_admin_access_keys_generate(request: Request, payload: Dict[str, Any] = {}):
    """生成新访问密钥。入参 {count, type: "time"|"count"|"both", days, hours, mins, max_uses}。"""
    _require_admin(request)
    db = _deps.ctx("db")
    count = max(1, min(int((payload or {}).get("count", 1)), 50))
    key_type = str((payload or {}).get("type", "time")).strip()
    if key_type not in ("time", "count", "both"):
        raise HTTPException(400, "type must be time, count, or both")
    days = max(0, min(int((payload or {}).get("days", 7)), 365))
    hours = max(0, min(int((payload or {}).get("hours", 0)), 23))
    mins = max(0, min(int((payload or {}).get("mins", 0)), 59))
    max_uses = max(0, min(int((payload or {}).get("max_uses", 50)), 9999))
    if key_type == "count" and max_uses <= 0:
        raise HTTPException(400, "次数模式需设置 max_uses >= 1")
    if key_type in ("time", "both") and days == 0 and hours == 0 and mins == 0:
        raise HTTPException(400, "时间模式需设置有效期")
    now = _time.time()
    if key_type in ("time", "both"):
        expires_at = now + days * 86400 + hours * 3600 + mins * 60
        if expires_at <= now:
            expires_at = now + 3600
    else:
        expires_at = 0
    new_keys = []
    for _ in range(count):
        k = secrets.token_urlsafe(32)
        db.add_access_key(
            key=k, used_by="", created_at=now,
            disabled_at=0, expires_at=expires_at,
            max_uses=max_uses if key_type in ("count", "both") else 0,
            used_count=0)
        new_keys.append(k)
    return {"ok": True, "keys": new_keys}


@router.post("/api/admin/access-keys/delete")
async def api_admin_access_keys_delete(request: Request, payload: Dict[str, Any]):
    """禁用/删除访问密钥。入参 {key: "abc123"} 或 {key_preview: "abc12345...xyz9"}。
    设置 disabled_at 后 2 秒正式失效，给用户短暂的缓冲时间。"""
    _require_admin(request)
    db = _deps.ctx("db")
    raw = str((payload or {}).get("key") or (payload or {}).get("key_preview") or "").strip()
    if not raw:
        raise HTTPException(400, "key required")
    now = _time.time()
    # 清理 disabled_at 超过 2 秒的密钥，并同步清理 session 引用
    stale = db.cleanup_disabled_access_keys(now)
    if stale:
        db.clear_session_claimed_keys_for_keys(stale)
    # 查找目标 key
    target_key = raw if db.get_access_key(raw) else None
    if not target_key and "..." in raw:
        parts = raw.split("...")
        if len(parts) == 2 and parts[0] and parts[1]:
            prefix, suffix = parts[0], parts[1]
            for k, v in db.load_access_keys().get("keys", {}).items():
                if k.startswith(prefix) and k.endswith(suffix):
                    target_key = k
                    break
    if target_key is None:
        raise HTTPException(404, "操作失败")
    entry = db.get_access_key(target_key)
    if entry.get("disabled_at", 0):
        raise HTTPException(400, "操作失败")
    db.disable_access_key(target_key, now)
    return {"ok": True}


@router.post("/api/admin/access-keys/cleanup")
async def api_admin_access_keys_cleanup(request: Request):
    """清理所有失效的访问密钥（过期/耗尽/禁用已过缓冲期）。"""
    _require_admin(request)
    db = _deps.ctx("db")
    now = _time.time()
    stale = db.cleanup_expired_access_keys(now)
    return {"ok": True, "cleaned": len(stale)}


@router.post("/api/admin/access-keys/enable")
async def api_admin_access_keys_enable(request: Request, payload: Dict[str, Any]):
    """重新启用被禁用的密钥。入参 {key: "abc123"} 或 {key_preview: "abc12345...xyz9"}。"""
    _require_admin(request)
    db = _deps.ctx("db")
    raw = str((payload or {}).get("key") or (payload or {}).get("key_preview") or "").strip()
    if not raw:
        raise HTTPException(400, "key required")
    target_key = raw if db.get_access_key(raw) else None
    if not target_key and "..." in raw:
        parts = raw.split("...")
        if len(parts) == 2 and parts[0] and parts[1]:
            prefix, suffix = parts[0], parts[1]
            for k, v in db.load_access_keys().get("keys", {}).items():
                if k.startswith(prefix) and k.endswith(suffix):
                    target_key = k
                    break
    if target_key is None:
        raise HTTPException(404, "密钥不存在")
    entry = db.get_access_key(target_key)
    if not entry.get("disabled_at", 0):
        raise HTTPException(400, "该密钥未被禁用")
    db.enable_access_key(target_key)
    return {"ok": True}


@router.post("/api/admin/access-keys/remove")
async def api_admin_access_keys_remove(request: Request, payload: Dict[str, Any]):
    """彻底删除访问密钥（物理删除，不可恢复）。"""
    _require_admin(request)
    db = _deps.ctx("db")
    raw = str((payload or {}).get("key") or (payload or {}).get("key_preview") or "").strip()
    if not raw:
        raise HTTPException(400, "key required")
    target_key = raw if db.get_access_key(raw) else None
    if not target_key and "..." in raw:
        parts = raw.split("...")
        if len(parts) == 2 and parts[0] and parts[1]:
            prefix, suffix = parts[0], parts[1]
            for k, v in db.load_access_keys().get("keys", {}).items():
                if k.startswith(prefix) and k.endswith(suffix):
                    target_key = k
                    break
    if target_key is None:
        raise HTTPException(404, "密钥不存在")
    db.delete_access_key(target_key)
    return {"ok": True}


@router.post("/api/admin/access-keys/reveal")
async def api_admin_access_keys_reveal(request: Request, payload: Dict[str, Any]):
    """根据 key_preview 返回完整密钥（仅管理员）。入参 {key_preview: "abc12345...xyz9"}。
    每次调用记录审计日志，且仅支持前缀+后缀双因子匹配（拒绝单因子前缀匹配）。"""
    _require_admin(request)
    db = _deps.ctx("db")
    get_user = _deps.ctx("get_user")
    client_ip = _deps.ctx("client_ip")
    user = get_user(request)
    admin_login = user.get("login", "?") if user else "?"
    raw = str((payload or {}).get("key_preview") or "").strip()
    if not raw:
        raise HTTPException(400, "key_preview required")
    # 拒绝单因子匹配（仅前缀或仅后缀）
    if "..." not in raw:
        raise HTTPException(400, "key_preview 格式无效（需包含 ...）")
    data = db.load_access_keys()
    keys = data.get("keys", {})
    target_key = None
    parts = raw.split("...")
    if len(parts) == 2 and parts[0] and parts[1]:
        prefix, suffix = parts[0], parts[1]
        if len(prefix) < 4 or len(suffix) < 4:
            raise HTTPException(400, "key_preview 前缀/后缀长度不足")
        for k in keys:
            if k.startswith(prefix) and k.endswith(suffix):
                target_key = k
                break
    if target_key is None:
        print(f"[AUDIT] 密钥查看失败 admin={admin_login} preview={raw} ip={client_ip(request)}")
        raise HTTPException(404, "密钥不存在")
    print(f"[AUDIT] 密钥已查看 admin={admin_login} key_preview={raw} ip={client_ip(request)}")
    return {"ok": True, "key": target_key}

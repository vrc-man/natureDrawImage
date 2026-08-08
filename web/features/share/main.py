"""
外挂功能：图片分享链接（内存存储，服务器重启后失效）。
"""

import time
import secrets
import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse

from features._deps import (
    require_admin, validate_rel_path, resolve_output_path, OUTPUT_IMAGE_EXTS, ctx,
)

router = APIRouter(tags=["share"])

_share_links: Dict[str, Dict[str, Any]] = {}
_share_links_lock = asyncio.Lock()
_share_rate: Dict[str, list] = {}
_share_rate_lock = asyncio.Lock()
_SHARE_RATE_CLEANUP_INTERVAL = 300  # 5分钟清理一次过期限流记录
_last_rate_cleanup = time.time()


def _helper_load_deleted_paths() -> set:
    """获取已删除图片路径集合。"""
    dp_all = ctx("load_deleted_images")()
    dp_set: set = set()
    for dpv in dp_all.values():
        for dp in dpv:
            dp_set.add(dp.replace("\\", "/"))
    return dp_set


def _helper_check_permission(user: dict, path: str) -> None:
    """非管理员检查图片是否为自己作品或精选。"""
    if user.get("role") != "admin":
        uid = str(user.get("github_id", ""))
        user_images = ctx("load_user_images")().get(uid, [])
        owned = {i.get("path", "").replace("\\", "/") for i in user_images}
        if path.replace("\\", "/") not in owned:
            featured = set(ctx("read_featured")())
            if path.replace("\\", "/") not in featured:
                raise HTTPException(404, "找不到图片？请核对正确地址后重试！")


@router.post("/api/output/share")
async def api_output_share(request: Request):
    """生成分享链接（支持时间+次数限制，服务器重启后失效）。"""
    user = ctx("get_user")(request)
    if not user:
        raise HTTPException(401)
    uid = str(user.get("github_id", ""))
    ip = ctx("client_ip")(request)
    limit_key = f"share:{uid or ip}"
    async with _share_rate_lock:
        bucket = _share_rate.get(limit_key) or []
        now_r = time.time()
        bucket[:] = [t for t in bucket if now_r - t < 60]
        if len(bucket) >= 20:
            raise HTTPException(429, "请求过于频繁，请稍后再试")
        bucket.append(now_r)
        _share_rate[limit_key] = bucket
        global _last_rate_cleanup
        if now_r - _last_rate_cleanup > _SHARE_RATE_CLEANUP_INTERVAL:
            cutoff = now_r - 120
            stale = [k for k, v in _share_rate.items() if v and max(v) < cutoff]
            for k in stale:
                del _share_rate[k]
            _last_rate_cleanup = now_r
    body = await request.json()
    path = str(body.get("path", "")).strip()
    max_downloads = int(body.get("max_downloads", 0))
    expires_hours = float(body.get("expires_hours", 0))
    if not path:
        raise HTTPException(400, "path required")
    if max_downloads < 0 or max_downloads > 100:
        raise HTTPException(400, "max_downloads 范围 0-100，0=不限")
    if expires_hours < 0 or expires_hours > 720:
        raise HTTPException(400, "expires_hours 范围 0-720（小时），支持小数（如 0.5=30分钟），0=不限（服务器重启后失效）")
    _helper_check_permission(user, path)
    deleted_paths = _helper_load_deleted_paths()
    if path.replace("\\", "/") in deleted_paths:
        raise HTTPException(404, "not found")
    if not validate_rel_path(path):
        raise HTTPException(400, "无效路径")
    p = resolve_output_path(path)
    if not p or not p.is_file():
        raise HTTPException(404, "not found")
    if p.suffix.lower() not in OUTPUT_IMAGE_EXTS:
        raise HTTPException(400, "not an image")
    now_s = time.time()
    expires_at = int(now_s + expires_hours * 3600) if expires_hours > 0 else 0
    token = secrets.token_hex(16)
    async with _share_links_lock:
        # 在同一个锁内检查+插入，避免竞态
        if user.get("role") != "admin":
            total_active = sum(
                1 for e in _share_links.values()
                if (e.get("expires_at", 0) == 0 or e.get("expires_at", 0) > now_s)
                and (e.get("max_downloads", 0) == 0 or e.get("downloads", 0) < e.get("max_downloads", 0))
            )
            if total_active >= 20:
                raise HTTPException(429, "有效分享链接总数已达上限（最多 20 个），请等待过期或消耗完成后重试")
        if len(_share_links) >= 500:
            oldest = min(_share_links, key=lambda k: _share_links[k]["created_at"])
            _share_links.pop(oldest, None)
        _share_links[token] = {
            "path": path,
            "max_downloads": max_downloads,
            "downloads": 0,
            "created_at": now_s,
            "expires_at": expires_at,
            "created_by": uid,
            "created_login": str(user.get("login", "")),
        }
    print(f"[share] 创建分享链接 token={token[:8]}... path={path} expires_hours={expires_hours} max_downloads={max_downloads} user={uid}")
    return {
        "token": token,
        "url": f"/api/output/share/{token}",
        "max_downloads": max_downloads,
        "expires_hours": expires_hours,
    }


@router.get("/api/output/share/links")
async def api_output_share_links(request: Request):
    """获取当前用户的分享链接列表（仅自己的）。"""
    user = ctx("get_user")(request)
    if not user:
        raise HTTPException(401)
    uid = str(user.get("github_id", ""))
    now_s = time.time()
    async with _share_links_lock:
        items = []
        for token, entry in _share_links.items():
            if str(entry.get("created_by", "")) != uid:
                continue
            expires_at = entry.get("expires_at", 0)
            if expires_at > 0 and now_s > expires_at:
                continue
            if entry["max_downloads"] > 0 and entry["downloads"] >= entry["max_downloads"]:
                continue
            items.append({
                "token": token,
                "path": entry["path"],
                "max_downloads": entry["max_downloads"],
                "downloads": entry["downloads"],
                "created_at": entry["created_at"],
                "expires_at": expires_at,
                "url": f"/api/output/share/{token}",
            })
    return {"items": items, "total": len(items)}


@router.post("/api/output/share/revoke")
async def api_output_share_revoke(request: Request):
    """撤销自己的一个分享链接。"""
    user = ctx("get_user")(request)
    if not user:
        raise HTTPException(401)
    uid = str(user.get("github_id", ""))
    body = await request.json()
    token = str(body.get("token", "")).strip()
    if not token:
        raise HTTPException(400, "token required")
    async with _share_links_lock:
        entry = _share_links.get(token)
        if not entry:
            raise HTTPException(404, "分享链接不存在")
        if str(entry.get("created_by", "")) != uid:
            raise HTTPException(403, "只能撤销自己的分享链接")
        _share_links.pop(token, None)
    print(f"[share] 用户撤销分享链接 token={token[:8]}... user={uid}")
    return {"ok": True}


@router.post("/api/output/share/update")
async def api_output_share_update(request: Request):
    """更新自己的分享链接（续次数/续时间）。"""
    user = ctx("get_user")(request)
    if not user:
        raise HTTPException(401)
    uid = str(user.get("github_id", ""))
    body = await request.json()
    token = str(body.get("token", "")).strip()
    add_downloads = int(body.get("add_downloads", 0))
    add_hours = float(body.get("add_hours", 0))
    if not token:
        raise HTTPException(400, "token required")
    if add_downloads < 0 or add_downloads > 100:
        raise HTTPException(400, "add_downloads 范围 0-100")
    if add_hours < 0 or add_hours > 720:
        raise HTTPException(400, "add_hours 范围 0-720")
    async with _share_links_lock:
        entry = _share_links.get(token)
        if not entry:
            raise HTTPException(404, "分享链接不存在")
        if str(entry.get("created_by", "")) != uid:
            raise HTTPException(403, "只能修改自己的分享链接")
        if add_downloads > 0:
            old = entry.get("max_downloads", 0)
            entry["max_downloads"] = (old + add_downloads) if old > 0 else old
        if add_hours > 0:
            old_exp = entry.get("expires_at", 0)
            new_exp = int(time.time() + add_hours * 3600)
            entry["expires_at"] = new_exp if old_exp == 0 else old_exp + int(add_hours * 3600)
    print(f"[share] 用户更新分享链接 token={token[:8]}... add_downloads={add_downloads} add_hours={add_hours} user={uid}")
    return {"ok": True}


@router.get("/api/admin/features/share/links")
async def api_admin_share_links(request: Request):
    """管理员查看所有分享链接。"""
    require_admin(request)
    now_s = time.time()
    async with _share_links_lock:
        items = []
        for token, entry in _share_links.items():
            expires_at = entry.get("expires_at", 0)
            if expires_at > 0 and now_s > expires_at:
                continue
            if entry["max_downloads"] > 0 and entry["downloads"] >= entry["max_downloads"]:
                continue
            items.append({
                "token": token,
                "path": entry["path"],
                "max_downloads": entry["max_downloads"],
                "downloads": entry["downloads"],
                "created_at": entry["created_at"],
                "expires_at": expires_at,
                "created_by": entry.get("created_by", ""),
                "created_login": entry.get("created_login", ""),
                "url": f"/api/output/share/{token}",
            })
    return {"items": items, "total": len(items)}


@router.post("/api/admin/features/share/revoke")
async def api_admin_share_revoke(request: Request):
    """管理员撤销任意分享链接。"""
    require_admin(request)
    body = await request.json()
    token = str(body.get("token", "")).strip()
    if not token:
        raise HTTPException(400, "token required")
    async with _share_links_lock:
        entry = _share_links.get(token)
        if not entry:
            raise HTTPException(404, "分享链接不存在")
        _share_links.pop(token, None)
    print(f"[share] 管理员撤销分享链接 token={token[:8]}... path={entry['path']}")
    return {"ok": True}


@router.get("/api/output/share/{token}")
async def api_output_share_get(token: str):
    """通过分享链接获取文件（验证时间+次数限制）。"""
    async with _share_links_lock:
        entry = _share_links.get(token)
        if not entry:
            raise HTTPException(404, "分享链接不存在或已过期")
        expires_at = entry.get("expires_at", 0)
        if expires_at > 0 and time.time() > expires_at:
            _share_links.pop(token, None)
            raise HTTPException(410, "分享链接已过期（超过有效期）")
        if entry["max_downloads"] > 0 and entry["downloads"] >= entry["max_downloads"]:
            raise HTTPException(410, "分享链接下载次数已用完")
        entry["downloads"] += 1
        path = entry["path"]
        remaining = entry["max_downloads"] - entry["downloads"] if entry["max_downloads"] > 0 else None
    if not validate_rel_path(path):
        async with _share_links_lock: _share_links.pop(token, None)
        raise HTTPException(400, "无效路径")
    deleted_paths = _helper_load_deleted_paths()
    if path.replace("\\", "/") in deleted_paths:
        async with _share_links_lock: _share_links.pop(token, None)
        raise HTTPException(404, "not found")
    p = resolve_output_path(path)
    if not p or not p.is_file():
        async with _share_links_lock: _share_links.pop(token, None)
        raise HTTPException(404, "not found")
    if p.suffix.lower() not in OUTPUT_IMAGE_EXTS:
        async with _share_links_lock: _share_links.pop(token, None)
        raise HTTPException(400, "not an image")
    ext = p.suffix.lower().lstrip(".")
    media = {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, f"image/{ext}")
    fname = p.name
    ascii_name = fname.encode("ascii", "ignore").decode("ascii")
    if not ascii_name:
        ascii_name = f"image.{ext}"
    elif "." not in ascii_name:
        ascii_name = f"{ascii_name}.{ext}"
    from urllib.parse import quote as _q
    return FileResponse(str(p), media_type=media, headers={
        "X-Remaining-Downloads": str(remaining) if remaining is not None else "unlimited",
        "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{_q(fname)}',
    })

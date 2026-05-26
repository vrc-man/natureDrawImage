"""
邮箱注册/登录 + 邀请码 + TOTP 双因素认证 + Turnstile + 限流
(SQLite 版 - 使用统一的 natureDrawImage.db)

用法: 在 app.py 末尾 import:
    from email_auth import init_email_auth
    init_email_auth()
"""
import os
import time
import secrets
import hashlib
import base64
import hmac as _hmac
import struct as _struct
import asyncio
from typing import Dict, Any, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from db.schema import get_db, config_get, config_set

# ═══ 固定配置（env 覆盖） ═══
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SITE_NAME = os.environ.get("SITE_NAME", "二次元绘梦")
SITE_URL = os.environ.get("SITE_URL", "")
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

SESSION_MAX_AGE_SEC = 30 * 86400

_invite_lock = asyncio.Lock()
_email_users_lock = asyncio.Lock()

# ═══ 动态配置（config 表 + env 默认） ═══
def _get_email_config(key: str, default: str = "") -> str:
    val = config_get("email", key, None)
    if val is not None:
        return str(val)
    return os.environ.get(key, default)

def _set_email_config(key: str, value: str):
    config_set("email", key, value)

def _get_email_config_int(key: str, default: int = 0) -> int:
    try:
        return int(_get_email_config(key, str(default)))
    except ValueError:
        return default

# ═══ 工具函数 ═══
def _load_invite_codes() -> dict:
    rows = get_db().execute("SELECT * FROM invite_codes").fetchall()
    return {r["code"]: {"used_count": r["used_count"], "max_uses": r["max_uses"], "created_at": r["created_at"]} for r in rows}

def _save_invite_codes(data: dict):
    db = get_db()
    db.execute("DELETE FROM invite_codes")
    for k, v in data.items():
        db.execute("INSERT INTO invite_codes VALUES (?,?,?,?)",
                   (k, v.get("used_count", 0), v.get("max_uses", 1), v.get("created_at", 0)))
    db.commit()

def _load_email_users() -> dict:
    rows = get_db().execute("SELECT * FROM email_users").fetchall()
    return {r["email"]: dict(r) for r in rows}

def _save_email_users(data: dict):
    db = get_db()
    for email, eu in data.items():
        db.execute("""INSERT OR REPLACE INTO email_users VALUES (?,?,?,?,?,?,?,?,?,?)""",
                   (email, eu.get("password_hash", ""), eu.get("role", "user"),
                    eu.get("banned", 0), eu.get("banned_reason", ""), eu.get("created_at", 0),
                    eu.get("verified", 0), eu.get("verify_token", ""),
                    eu.get("totp_secret", ""), eu.get("totp_enabled", 0)))
    db.commit()

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000)
    return salt + ":" + h.hex()

def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":", 1)
        return h == hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
    except Exception:
        return False

def _generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def _verify_totp(secret: str, code: str) -> bool:
    try:
        key = base64.b32decode(secret.upper() + "=" * (8 - len(secret) % 8))
        now = int(time.time()) // 30
        for offset in (-1, 0, 1):
            msg = _struct.pack(">Q", now + offset)
            h = _hmac.new(key, msg, "sha1").digest()
            o = h[-1] & 0x0F
            token = (_struct.unpack(">I", h[o:o+4])[0] & 0x7FFFFFFF) % 1000000
            if f"{token:06d}" == code:
                return True
    except Exception:
        pass
    return False

def get_email_user(session_uid: str) -> Optional[dict]:
    """从 session 的 github_id 还原邮箱用户"""
    if not session_uid or not session_uid.startswith("email:"):
        return None
    email = session_uid[6:]
    users = _load_email_users()
    eu = users.get(email)
    if not eu:
        return None
    return {
        "github_id": session_uid,
        "login": email.split("@")[0],
        "email": email,
        "avatar_url": "",
        "role": eu.get("role", "user"),
        "banned": bool(eu.get("banned", False)),
        "banned_reason": eu.get("banned_reason", ""),
    }

# ═══ 限流 & Turnstile ═══
_email_rate_ip: Dict[str, list] = {}
_email_rate_addr: Dict[str, list] = {}

def _check_rate_limit(ip: str, email: str) -> Optional[str]:
    now = time.time()
    hourly_limit = _get_email_config_int("REG_HOURLY_LIMIT_PER_IP", 3)
    times_hour = [t for t in _email_rate_ip.get(ip, []) if t > now - 3600]
    if len(times_hour) >= hourly_limit:
        return f"IP 注册次数已达每小时上限({hourly_limit})"
    daily_ip = _get_email_config_int("REG_DAILY_LIMIT_PER_IP", 10)
    times_day = [t for t in _email_rate_ip.get(ip, []) if t > now - 86400]
    if len(times_day) >= daily_ip:
        return f"IP 注册次数已达每日上限({daily_ip})"
    daily_email = _get_email_config_int("REG_DAILY_LIMIT_PER_EMAIL", 3)
    times_email = [t for t in _email_rate_addr.get(email, []) if t > now - 86400]
    if len(times_email) >= daily_email:
        return f"该邮箱注册次数已达每日上限({daily_email})"
    return None

def _record_rate_limit(ip: str, email: str):
    now = time.time()
    _email_rate_ip.setdefault(ip, []).append(now)
    _email_rate_addr.setdefault(email, []).append(now)

async def _verify_turnstile(token: str, remote_ip: str = "") -> bool:
    if not TURNSTILE_SECRET_KEY:
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data={
                "secret": TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": remote_ip,
            })
            result = r.json()
            if not result.get("success"):
                print(f'[turnstile] verify failed: {result}')
            return result.get("success", False)
    except Exception as e:
        print(f'[turnstile] error: {e}')
        return False


# ═══ 注册路由 ═══

def init_email_auth():
    """注册 email auth 路由（在 app 创建后调用）"""
    from web.app import app as _app_obj
    app = _app_obj

    @app.get("/api/admin/invite-codes")
    async def api_admin_invite_codes(request: Request):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        codes = _load_invite_codes()
        items = [{"code": k, **v} for k, v in codes.items()]
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {"items": items, "total": len(items)}

    @app.post("/api/admin/invite-codes/generate")
    async def api_admin_invite_codes_generate(request: Request, payload: Dict[str, Any] = {}):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        count = max(1, min(int(payload.get("count", 1)), 20))
        max_uses = int(payload.get("max_uses", 1))
        async with _invite_lock:
            codes = _load_invite_codes()
            generated = []
            for _ in range(count):
                c = secrets.token_hex(6).upper()[:12]
                codes[c] = {"used_count": 0, "max_uses": max_uses, "created_at": time.time()}
                generated.append(c)
            _save_invite_codes(codes)
        return {"ok": True, "codes": generated}

    @app.post("/api/admin/invite-codes/delete")
    async def api_admin_invite_codes_delete(request: Request, payload: Dict[str, Any]):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        code = str(payload.get("code", "")).strip()
        async with _invite_lock:
            codes = _load_invite_codes()
            codes.pop(code, None)
            _save_invite_codes(codes)
        return {"ok": True}

    @app.post("/api/auth/register-email")
    async def api_register_email(request: Request, payload: Dict[str, Any]):
        try:
            email = str(payload.get("email", "")).strip().lower()
            password = str(payload.get("password", "")).strip()
            invite_code = str(payload.get("invite_code", "")).strip().upper()
            turnstile_token = str(payload.get("turnstile_token", "")).strip()
            if not email or "@" not in email or len(password) < 6:
                raise HTTPException(400, "Invalid input")
            from web.app import _client_ip_from_request
            client_ip = _client_ip_from_request(request)
            if not await _verify_turnstile(turnstile_token, client_ip):
                raise HTTPException(400, "人机验证失败，请重试")
            limit_msg = _check_rate_limit(client_ip, email)
            if limit_msg:
                raise HTTPException(429, limit_msg)
            has_invite = False
            if invite_code:
                async with _invite_lock:
                    codes = _load_invite_codes()
                    entry = codes.get(invite_code)
                    if entry and entry["used_count"] < entry.get("max_uses", 1):
                        entry["used_count"] += 1
                        _save_invite_codes(codes)
                        has_invite = True
                    elif entry:
                        raise HTTPException(400, "邀请码已被用完")
                    else:
                        raise HTTPException(400, "无效邀请码")
            async with _email_users_lock:
                email_users = _load_email_users()
                if email in email_users:
                    raise HTTPException(400, "邮箱已注册")
                verify_token = "" if has_invite else secrets.token_urlsafe(32)
                email_users[email] = {
                    "password_hash": _hash_password(password),
                    "role": "user", "banned": False, "banned_reason": "",
                    "created_at": time.time(), "verified": has_invite,
                    "verify_token": verify_token, "totp_secret": "", "totp_enabled": False,
                }
                _save_email_users(email_users)
            _record_rate_limit(client_ip, email)
            if has_invite:
                return {"ok": True, "message": "注册成功！请返回登录。"}
            else:
                vu = f"{SITE_URL}/api/auth/verify-email?token={verify_token}&email={email}"
                mail_ok = await _send_email(email, f"[{SITE_NAME}] 验证邮箱",
                    f"<p>感谢注册！请点击以下链接验证邮箱：</p><p><a href='{vu}'>{vu}</a></p>")
                if mail_ok:
                    return {"ok": True, "message": "注册成功！请查收验证邮件并点击链接激活账号。"}
                else:
                    return {"ok": True, "message": "注册成功！验证邮件发送失败，手动验证链接: " + vu}
        except HTTPException:
            raise
        except Exception as _e:
            import traceback as _tb
            _tb.print_exc()
            print(f'[register-email] {type(_e).__name__}: {_e}')
            raise HTTPException(500, f"服务器内部错误: {type(_e).__name__}")


    @app.get("/api/auth/verify-email")
    async def api_verify_email(token: str = "", email: str = ""):
        if not token or not email:
            return Response("<h3>链接无效</h3>", media_type="text/html")
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email.lower())
            if not eu or eu.get("verify_token") != token:
                return Response("<h3>链接无效或已过期</h3>", media_type="text/html")
            eu["verified"] = True
            eu["verify_token"] = ""
            _save_email_users(email_users)
        return Response("<h3>邮箱验证成功！<a href='/'>返回首页登录</a></h3>", media_type="text/html")


    @app.post("/api/auth/login-email")
    async def api_login_email(request: Request, payload: Dict[str, Any]):
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", "")).strip()
        totp_code = str(payload.get("totp_code", "")).strip()
        if not email or not password:
            raise HTTPException(400, "Email and password required")
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email)
        if not eu or not _verify_password(password, eu["password_hash"]):
            raise HTTPException(401, "Invalid credentials")
        if not eu.get("verified"):
            raise HTTPException(401, "Email not verified")
        if eu.get("banned"):
            raise HTTPException(403, "Banned")
        if eu.get("totp_enabled"):
            if not totp_code or not _verify_totp(eu["totp_secret"], totp_code):
                raise HTTPException(401, "Invalid TOTP code")
        token = secrets.token_urlsafe(32)
        now = time.time()
        from web.app import _load_sessions, _save_sessions, _sessions_lock
        async with _sessions_lock:
            sessions = _load_sessions()
            sessions[token] = {
                "github_id": "email:" + email,
                "expires_at": now + SESSION_MAX_AGE_SEC,
                "access_granted": False,
                "claimed_key": "",
            }
            await _save_sessions(sessions)
        resp = JSONResponse({"ok": True, "login": email.split("@")[0], "is_admin": eu.get("role") == "admin"})
        resp.set_cookie("session", token, httponly=True, max_age=SESSION_MAX_AGE_SEC,
                         samesite="lax", secure=SITE_URL.startswith("https"))
        return resp

    @app.post("/api/auth/totp-setup")
    async def api_totp_setup(request: Request):
        from web.app import _get_user_from_session
        user = _get_user_from_session(request)
        if not user:
            raise HTTPException(401)
        email = user.get("github_id", "").replace("email:", "")
        if not email:
            raise HTTPException(400, "Email users only")
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email)
            if not eu:
                raise HTTPException(400)
            eu["totp_secret"] = _generate_totp_secret()
            eu["totp_enabled"] = False
            _save_email_users(email_users)
        return {"ok": True, "secret": eu["totp_secret"]}

    @app.get("/api/auth/totp-status")
    async def api_totp_status(request: Request):
        from web.app import _get_user_from_session
        user = _get_user_from_session(request)
        if not user:
            raise HTTPException(401)
        email = user.get("github_id", "").replace("email:", "")
        if not email:
            return {"totp_enabled": False}
        email_users = _load_email_users()
        eu = email_users.get(email)
        if not eu:
            return {"totp_enabled": False}
        return {"totp_enabled": bool(eu.get("totp_enabled"))}

    @app.post("/api/auth/totp-enable")
    async def api_totp_enable(request: Request, payload: Dict[str, Any]):
        from web.app import _get_user_from_session
        user = _get_user_from_session(request)
        if not user:
            raise HTTPException(401)
        email = user.get("github_id", "").replace("email:", "")
        if not email:
            raise HTTPException(400)
        code = str(payload.get("code", "")).strip()
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email)
            if not eu or not _verify_totp(eu.get("totp_secret", ""), code):
                raise HTTPException(400, "Invalid code")
            eu["totp_enabled"] = True
            _save_email_users(email_users)
        return {"ok": True}

    @app.post("/api/auth/totp-disable")
    async def api_totp_disable(request: Request):
        from web.app import _get_user_from_session
        user = _get_user_from_session(request)
        if not user:
            raise HTTPException(401)
        email = user.get("github_id", "").replace("email:", "")
        if not email:
            raise HTTPException(400)
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email)
            if eu:
                eu["totp_enabled"] = False
                eu["totp_secret"] = ""
                _save_email_users(email_users)
        return {"ok": True}

    # ── 管理员：限流配置 ──

    @app.get("/api/admin/email-config")
    async def api_admin_email_config(request: Request):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        return {
            "reg_hourly_limit_per_ip": _get_email_config_int("REG_HOURLY_LIMIT_PER_IP", 3),
            "reg_daily_limit_per_ip": _get_email_config_int("REG_DAILY_LIMIT_PER_IP", 10),
            "reg_daily_limit_per_email": _get_email_config_int("REG_DAILY_LIMIT_PER_EMAIL", 3),
        }

    @app.post("/api/admin/email-config")
    async def api_admin_email_config_save(request: Request, payload: Dict[str, Any] = {}):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        for key in ("REG_HOURLY_LIMIT_PER_IP", "REG_DAILY_LIMIT_PER_IP", "REG_DAILY_LIMIT_PER_EMAIL"):
            if key in payload:
                _set_email_config(key, str(int(payload[key])))
        return {"ok": True}

    # ── 管理员：邮箱用户管理 ──

    @app.get("/api/admin/email-users")
    async def api_admin_email_users(request: Request):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        users = _load_email_users()
        items = []
        for email, eu in users.items():
            items.append({
                "github_id": "email:" + email,
                "login": email.split("@")[0],
                "email": email,
                "avatar_url": "",
                "role": eu.get("role", "user"),
                "banned": bool(eu.get("banned", False)),
                "banned_reason": eu.get("banned_reason", ""),
                "created_at": eu.get("created_at", 0),
            })
        items.sort(key=lambda u: u.get("created_at", 0))
        return {"users": items}

    @app.post("/api/admin/email-users/ban")
    async def api_admin_email_user_ban(request: Request, payload: Dict[str, Any] = {}):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        github_id = str(payload.get("github_id", "")).strip()
        if not github_id or not github_id.startswith("email:"):
            raise HTTPException(400, "github_id required (email: prefix)")
        email = github_id[6:]
        reason = str(payload.get("reason", ""))[:200]
        async with _email_users_lock:
            users = _load_email_users()
            eu = users.get(email)
            if not eu:
                raise HTTPException(404, "用户不存在")
            eu["banned"] = True
            eu["banned_reason"] = reason
            _save_email_users(users)
        return {"ok": True}

    @app.post("/api/admin/email-users/unban")
    async def api_admin_email_user_unban(request: Request, payload: Dict[str, Any] = {}):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        github_id = str(payload.get("github_id", "")).strip()
        if not github_id or not github_id.startswith("email:"):
            raise HTTPException(400, "github_id required (email: prefix)")
        email = github_id[6:]
        async with _email_users_lock:
            users = _load_email_users()
            eu = users.get(email)
            if not eu:
                raise HTTPException(404, "用户不存在")
            eu["banned"] = False
            eu["banned_reason"] = ""
            _save_email_users(users)
        return {"ok": True}

    # Monkey-patch _get_user_from_session to support email users
    from web.app import _get_user_from_session as _orig_get_user

    def _patched_get_user(request):
        user = _orig_get_user(request)
        if user:
            return user
        token = request.cookies.get("session") or ""
        if not token:
            return None
        from web.app import _load_sessions
        sessions = _load_sessions()
        sess = sessions.get(token)
        if not sess:
            return None
        now = time.time()
        if now > sess.get("expires_at", 0):
            return None
        uid = str(sess.get("github_id", ""))
        print(f'[email_auth] session uid={uid}')
        if uid.startswith("email:"):
            eu = get_email_user(uid)
            print(f'[email_auth] email user found: {eu is not None}')
            return eu
        return None

    import web.app as _app_mod
    _app_mod._get_user_from_session = _patched_get_user

    print("[email_auth] Routes registered (SQLite)")

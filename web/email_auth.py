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
import smtplib
from typing import Dict, Any, Optional
from email.mime.text import MIMEText

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
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", SMTP_USER)

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

def _smtp_send(msg):
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

async def _send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        return False
    # 全局每日发信上限
    now = time.time()
    global _email_sent_today
    _email_sent_today = [t for t in _email_sent_today if t > now - 86400]
    if len(_email_sent_today) >= EMAIL_GLOBAL_DAILY_LIMIT:
        print(f'[email] 全局发信已达每日上限({EMAIL_GLOBAL_DAILY_LIMIT})')
        return False
    recent = [t for t in _email_sent_today if t > now - 60]
    if len(recent) >= EMAIL_GLOBAL_MINUTE_LIMIT:
        print(f'[email] 全局发信已达每分钟上限({EMAIL_GLOBAL_MINUTE_LIMIT})')
        return False
    msg = MIMEText(body, "html", "utf-8")
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _smtp_send(msg))
        _email_sent_today.append(time.time())
        return True
    except Exception as e:
        print(f"[email] {e}")
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
EMAIL_GLOBAL_DAILY_LIMIT = int(os.environ.get('EMAIL_GLOBAL_DAILY_LIMIT', '250'))
EMAIL_GLOBAL_MINUTE_LIMIT = int(os.environ.get('EMAIL_GLOBAL_MINUTE_LIMIT', '10'))
_email_sent_today: list = []  # 全局发信时间戳

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


# ═══ 验证邮件重试队列 ═══
_verify_retry: Dict[str, dict] = {}
_verify_abuse_ips: set = set()
MAX_VERIFY_RETRIES = 3
VERIFY_ABUSE_THRESHOLD = 3

async def _retry_verify_loop():
    while True:
        await asyncio.sleep(60)
        try:
            now = time.time()
            for email, info in list(_verify_retry.items()):
                if info["retry_count"] >= MAX_VERIFY_RETRIES:
                    _verify_retry.pop(email, None)
                    continue
                if now < info.get("next_retry_at", 0):
                    continue
                ip = info.get("ip", "")
                if ip in _verify_abuse_ips:
                    _verify_retry.pop(email, None)
                    continue
                email_users = _load_email_users()
                eu = email_users.get(email)
                if not eu or eu.get("verified") or not eu.get("verify_token"):
                    _verify_retry.pop(email, None)
                    continue
                vu = f"{SITE_URL}/api/auth/verify-email?token={eu['verify_token']}&email={email}"
                ok = await _send_email(email, f"[{SITE_NAME}] 验证邮箱",
                    _email_html("邮箱验证", "<p style='font-size:14px;line-height:1.8'>感谢注册！</p><div style='text-align:center;margin:20px 0'><a href='" + vu + "' style='display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#f472b6,#fb7185);color:#fff;text-decoration:none;border-radius:12px;font-weight:600'>验证邮箱</a></div><p style='font-size:12px;color:#9ca3af'>24小时内有效，非本人操作请忽略。</p>"))
                if ok:
                    _verify_retry.pop(email, None)
                else:
                    info["retry_count"] += 1
                    if info["retry_count"] >= MAX_VERIFY_RETRIES:
                        _verify_retry.pop(email, None)
                    else:
                        intervals = [120, 300, 600]
                        info["next_retry_at"] = now + intervals[min(info["retry_count"], 2)]
        except Exception:
            pass


def _email_html(title: str, body: str) -> str:
    top = "<div style='max-width:480px;margin:0 auto;font-family:sans-serif;color:#374151'><div style='background:linear-gradient(135deg,#f472b6,#fb7185);padding:24px;text-align:center;border-radius:16px 16px 0 0'><h1 style='color:#fff;font-size:20px;margin:0'>" + SITE_NAME + "</h1><p style='color:rgba(255,255,255,.85);font-size:13px;margin:6px 0 0'>" + title + "</p></div>"
    mid = "<div style='background:#fff;padding:24px;border:1px solid #fce7f3;border-top:0;border-radius:0 0 16px 16px'>" + body + "</div>"
    end = "<div style='text-align:center;padding:16px;font-size:11px;color:#9ca3af'><p>系统自动发送，请勿回复</p></div></div>"
    return top + mid + end

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
                c = secrets.token_hex(16).upper()[:16]
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
            # 同步写入 users 表（sessions 表有外键约束）
            db2 = get_db()
            db2.execute("""INSERT OR IGNORE INTO users (github_id, login, email, avatar_url, role, banned, banned_reason, created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                ("email:" + email, email.split("@")[0], email, "", "user", 0, "", time.time()))
            db2.commit()
            _record_rate_limit(client_ip, email)
            if has_invite:
                return {"ok": True, "message": "注册成功！请返回登录。"}
            else:
                vu = f"{SITE_URL}/api/auth/verify-email?token={verify_token}&email={email}"
                mail_ok = await _send_email(email, f"[{SITE_NAME}] 验证邮箱",
                    _email_html("邮箱验证", "<p style='font-size:14px;line-height:1.8'>感谢注册！</p><div style='text-align:center;margin:20px 0'><a href='" + vu + "' style='display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#f472b6,#fb7185);color:#fff;text-decoration:none;border-radius:12px;font-weight:600'>验证邮箱</a></div><p style='font-size:12px;color:#9ca3af'>24小时内有效，非本人操作请忽略。</p>"))
                if mail_ok:
                    return {"ok": True, "message": "注册成功！请查收验证邮件并点击链接激活账号。"}
                else:
                    
                    _verify_retry[email] = {"retry_count": 0, "next_retry_at": time.time() + 120, "ip": client_ip}
                    if client_ip in _verify_abuse_ips:
                        return {"ok": True, "message": "检测到恶意行为，已拒绝提供验证服务。如有疑问请联系 " + CONTACT_EMAIL}
                    ip_count = sum(1 for v in _verify_retry.values() if v.get("ip") == client_ip)
                    if ip_count >= VERIFY_ABUSE_THRESHOLD:
                        _verify_abuse_ips.add(client_ip)
                        return {"ok": True, "message": "检测到恶意行为，已拒绝提供验证服务。如有疑问请联系 " + CONTACT_EMAIL}
                    return {"ok": True, "message": "注册成功！验证邮件发送拥堵，系统将自动重试，请耐心等待收件"}
            
        except HTTPException:
            raise
        except Exception as _e:
            import traceback as _tb
            _tb.print_exc()
            print(f'[register-email] {type(_e).__name__}: {_e}')
            raise HTTPException(500, "服务器内部错误，请稍后重试")


    @app.get("/api/auth/verify-email")
    async def api_verify_email(token: str = "", email: str = ""):
        if not token or not email:
            return Response("<h3>链接无效</h3>", media_type="text/html")
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email.lower())
            if not eu or eu.get("verify_token") != token:
                return Response("<h3>链接无效或已过期</h3>", media_type="text/html")
            # 检查验证令牌是否超过24小时（created_at + 86400）
            if time.time() - eu.get("created_at", 0) > 86400:
                return Response("<h3>验证链接已过期，请重新注册</h3>", media_type="text/html")
            eu["verified"] = True
            eu["verify_token"] = ""
            _save_email_users(email_users)
        return Response("<h3>邮箱验证成功！<a href='/'>返回首页登录</a></h3>", media_type="text/html")


    # ── 忘记密码 ──
    RESET_EXPIRE_SEC = 1800

    @app.post("/api/auth/forgot-password")
    async def api_forgot_password(request: Request, payload: Dict[str, Any] = {}):
        email = str(payload.get("email", "")).strip().lower()
        if not email or "@" not in email:
            return {"ok": True, "message": "如果邮箱已注册，重置链接将发送到您的邮箱"}
        # 限流：每邮箱5分钟内只能请求一次重置
        now = time.time()
        fg_key = f"fg:{email}"
        attempts = [t for t in _email_rate_addr.get(fg_key, []) if t > now - 300]
        if attempts:
            return {"ok": True, "message": "如果邮箱已注册，重置链接将发送到您的邮箱"}
        email_users = _load_email_users()
        if email not in email_users:
            return {"ok": True, "message": "如果邮箱已注册，重置链接将发送到您的邮箱"}
        token = secrets.token_urlsafe(32)
        db = get_db()
        db.execute("INSERT OR REPLACE INTO password_resets VALUES (?,?,?)",
                   (email, token, time.time() + RESET_EXPIRE_SEC))
        db.commit()
        _email_rate_addr.setdefault(fg_key, []).append(now)
        link = f"{SITE_URL}/api/auth/reset-password?token={token}&email={email}"
        await _send_email(email, f"[{SITE_NAME}] 重置密码",
            _email_html("密码重置", "<p style='font-size:14px;line-height:1.8'>您请求重置密码。</p><div style='text-align:center;margin:20px 0'><a href='" + link + "' style='display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#f472b6,#fb7185);color:#fff;text-decoration:none;border-radius:12px;font-weight:600'>重置密码</a></div><p style='font-size:12px;color:#9ca3af'>30分钟内有效，非本人操作请忽略。</p>"))
        return {"ok": True, "message": "如果邮箱已注册，重置链接将发送到您的邮箱"}

    @app.get("/api/auth/reset-password")
    async def api_reset_password_form(token: str = "", email: str = ""):
        if not token or not email:
            return Response("<h3>链接无效</h3>", media_type="text/html")
        db = get_db()
        row = db.execute("SELECT * FROM password_resets WHERE email=? AND token=?", (email.lower(), token)).fetchone()
        if not row or row["expires_at"] < time.time():
            return Response("<h3>链接已过期或无效</h3>", media_type="text/html")
        # Simple inline HTML form
        form_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>重置密码</title>
<meta name="referrer" content="no-referrer" />
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#fef2f4,#fdf2f8,#faf5ff,#fff1f2);font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:20px}
.card{background:rgba(255,255,255,0.95);border:1px solid rgba(244,114,182,0.12);border-radius:24px;box-shadow:0 4px 30px rgba(244,114,182,0.15);max-width:400px;width:100%;padding:32px 24px}
h2{text-align:center;color:#1f2937;margin-bottom:16px}
input{width:100%;padding:10px 14px;border:1px solid #fce7f3;border-radius:14px;font-size:14px;margin-bottom:10px;outline:none}
input:focus{border-color:#f472b6;box-shadow:0 0 0 3px rgba(244,114,182,0.1)}
.btn{width:100%;padding:11px;border:0;border-radius:14px;font-size:15px;font-weight:600;cursor:pointer;color:#fff;background:linear-gradient(135deg,#f472b6,#fb7185);box-shadow:0 4px 20px rgba(244,114,182,0.3)}
.status{font-size:12px;text-align:center;display:block;margin-top:6px;min-height:18px}
</style></head>
<body><div class="card">
<h2>🔑 重置密码</h2>
<p style="text-align:center;color:#6b7280;font-size:13px;margin-bottom:16px">为 <b>""" + email + """</b> 设置新密码</p>
<input id="new-pwd" type="password" placeholder="新密码（至少6位）" minlength="6" />
<input id="confirm-pwd" type="password" placeholder="确认密码" minlength="6" />
<button class="btn" id="btn-reset">重置密码</button>
<span id="status" class="status"></span>
<p style="text-align:center;margin-top:12px;font-size:12px;color:#9ca3af"><a href="/auth/email-login">← 返回登录</a></p>
</div>
<script>
document.getElementById('btn-reset').addEventListener('click', async function() {
  var s = document.getElementById('status');
  var p1 = document.getElementById('new-pwd').value;
  var p2 = document.getElementById('confirm-pwd').value;
  if (p1.length < 6) { s.textContent = '密码至少6位'; s.style.color = '#ef4444'; return; }
  if (p1 !== p2) { s.textContent = '两次密码不一致'; s.style.color = '#ef4444'; return; }
  s.textContent = '...';
  try {
    var r = await fetch('/api/auth/reset-password', {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:'""" + token + """',email:'""" + email + """',password:p1})
    });
    var d = await r.json();
    if (r.ok) {
      s.textContent = d.message;
      s.style.color = '#16a34a';
      setTimeout(function(){ location.href = '/auth/email-login'; }, 2000);
    } else {
      s.textContent = d.detail || '失败';
      s.style.color = '#ef4444';
    }
  } catch(e) { s.textContent = e.message; s.style.color = '#ef4444'; }
});
</script></body></html>"""
        return Response(form_html, media_type="text/html")

    @app.post("/api/auth/reset-password")
    async def api_reset_password(request: Request, payload: Dict[str, Any] = {}):
        email = str(payload.get("email", "")).strip().lower()
        token = str(payload.get("token", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not email or not token or len(password) < 6:
            raise HTTPException(400, "参数无效")
        db = get_db()
        row = db.execute("SELECT * FROM password_resets WHERE email=? AND token=?", (email, token)).fetchone()
        if not row or row["expires_at"] < time.time():
            raise HTTPException(400, "链接已过期或无效")
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email)
            if not eu:
                raise HTTPException(404, "用户不存在")
            eu["password_hash"] = _hash_password(password)
            _save_email_users(email_users)
            db.execute("DELETE FROM password_resets WHERE email=?", (email,))
            db.commit()
        return {"ok": True, "message": "密码重置成功！即将跳转到登录页"}


    @app.post("/api/auth/login-email")
    async def api_login_email(request: Request, payload: Dict[str, Any]):
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", "")).strip()
        totp_code = str(payload.get("totp_code", "")).strip()
        if not email or not password:
            raise HTTPException(400, "Email and password required")
        # 登录限流：每IP每分钟5次，每邮箱每分钟3次
        from web.app import _client_ip_from_request
        client_ip = _client_ip_from_request(request)
        now = time.time()
        login_key_ip = f"login_ip:{client_ip}"
        login_key_em = f"login_em:{email}"
        attempts_ip = [t for t in _email_rate_ip.get(login_key_ip, []) if t > now - 60]
        attempts_em = [t for t in _email_rate_addr.get(login_key_em, []) if t > now - 60]
        if len(attempts_ip) >= 5:
            raise HTTPException(429, "登录尝试过于频繁，请稍后再试")
        if len(attempts_em) >= 3:
            raise HTTPException(429, "该邮箱登录尝试过于频繁，请稍后再试")
        _email_rate_ip.setdefault(login_key_ip, []).append(now)
        _email_rate_addr.setdefault(login_key_em, []).append(now)
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
            # 清理过期和同用户旧会话
            uid = "email:" + email
            sessions = {k: v for k, v in sessions.items() if v.get("expires_at", 0) > now}
            sessions = {k: v for k, v in sessions.items() if str(v.get("github_id", "")) != uid}
            sessions[token] = {
                "github_id": uid,
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

    # ── 管理员：恶意IP管理 ──

    @app.get("/api/admin/email-abuse-ips")
    async def api_admin_abuse_ips(request: Request):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        return {"ips": list(_verify_abuse_ips)}

    @app.post("/api/admin/email-abuse-ips/clear")
    async def api_admin_abuse_ips_clear(request: Request, payload: Dict[str, Any] = {}):
        if not getattr(request.state, "is_admin", False):
            raise HTTPException(403)
        ip = str(payload.get("ip", "")).strip()
        if ip:
            _verify_abuse_ips.discard(ip)
            return {"ok": True, "message": f"已移除 {ip}"}
        _verify_abuse_ips.clear()
        return {"ok": True, "message": "已清空全部恶意IP"}


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

    @app.post("/api/admin/email-users/resend-verify")
    async def api_admin_resend_verify(request: Request, payload: Dict[str, Any] = {}):
        if not getattr(request.state, "is_admin", False):
           raise HTTPException(403)
        github_id = str(payload.get("github_id", "")).strip()
        if not github_id or not github_id.startswith("email:"):
            raise HTTPException(400, "Invalid github_id")
        email = github_id[6:]
        async with _email_users_lock:
            email_users = _load_email_users()
            eu = email_users.get(email)
            if not eu:
                raise HTTPException(404, "用户不存在")
            if eu.get("verified"):
                raise HTTPException(400, "邮箱已验证，无需重新发送")
            eu["verify_token"] = secrets.token_urlsafe(32)
            _save_email_users(email_users)
        vu = f"{SITE_URL}/api/auth/verify-email?token={eu['verify_token']}&email={email}"
        mail_ok = await _send_email(email, f"[{SITE_NAME}] 验证邮箱",
            _email_html("邮箱验证", "<p style='font-size:14px;line-height:1.8'>管理员为您重新发送了验证邮件。</p><div style='text-align:center;margin:20px 0'><a href='" + vu + "' style='display:inline-block;padding:12px 32px;background:linear-gradient(135deg,#f472b6,#fb7185);color:#fff;text-decoration:none;border-radius:12px;font-weight:600'>验证邮箱</a></div><p style='font-size:12px;color:#9ca3af'>24小时内有效，非本人操作请忽略。</p>"))
        if mail_ok:
            return {"ok": True, "message": "验证邮件已重新发送"}
        else:
            return {"ok": True, "message": "发送拥堵，请稍后重试。手动验证: " + vu}


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
        if uid.startswith("email:"):
            eu = get_email_user(uid)
            return eu
        return None

    import web.app as _app_mod
    _app_mod._get_user_from_session = _patched_get_user

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_retry_verify_loop())
        print("[email_auth] 验证重试队列已启动")
    except Exception:
        pass
    print("[email_auth] Routes registered (SQLite)")

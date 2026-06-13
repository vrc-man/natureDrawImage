"""
SQLite 数据操作层 (Data Access Layer)

替代 app.py 中所有 _load_json / _save_json 调用。
每个函数签名与原有 JSON 版本兼容，内部改为 SQLite 操作。

所有写入操作自动 commit，读取操作即时查询。
"""

import json
import time as _time_module
import secrets
from typing import Dict, Any, List, Optional, Tuple

from db.schema import get_db, config_get, config_set, config_get_section

_db = get_db  # 函数别名

# ── 写穿透缓存（内存 dict + TTL 兜底） ──
_CACHE_TTL = 60
_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}


def _cache_get(key: str) -> Any:
    ts = _cache_ts.get(key)
    if ts is not None and _time_module.time() - ts < _CACHE_TTL:
        return _cache.get(key)
    return None


def _cache_set(key: str, value: Any):
    _cache[key] = value
    _cache_ts[key] = _time_module.time()


def _cache_del(key: str):
    _cache.pop(key, None)
    _cache_ts.pop(key, None)


def invalidate_users_cache():
    _cache_del("users")


def invalidate_sessions_cache():
    _cache_del("sessions")


# ═══════════════════════════════════════════
# 用户
# ═══════════════════════════════════════════

def load_users() -> Dict[str, Dict]:
    cached = _cache_get("users")
    if cached is not None:
        return cached
    rows = _db().execute("SELECT * FROM users").fetchall()
    data = {r["github_id"]: dict(r) for r in rows}
    _cache_set("users", data)
    return data


def save_user(github_id: str, login: str = "", email: str = "",
              avatar_url: str = "", role: str = "user") -> None:
    _db().execute("""
        INSERT INTO users (github_id, login, email, avatar_url, role, created_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(github_id) DO UPDATE SET
            login=excluded.login, email=excluded.email,
            avatar_url=excluded.avatar_url
    """, (github_id, login, email, avatar_url, role, _time_module.time()))
    _db().commit()
    invalidate_users_cache()


def update_user_role(github_id: str, role: str) -> None:
    _db().execute("UPDATE users SET role=? WHERE github_id=?", (role, github_id))
    _db().commit()
    invalidate_users_cache()


def ban_user(github_id: str, reason: str = "") -> None:
    _db().execute("UPDATE users SET banned=1, banned_reason=? WHERE github_id=?", (reason, github_id))
    _db().commit()
    invalidate_users_cache()


def unban_user(github_id: str) -> None:
    _db().execute("UPDATE users SET banned=0, banned_reason='' WHERE github_id=?", (github_id,))
    _db().commit()
    invalidate_users_cache()


# ═══════════════════════════════════════════
# 会话
# ═══════════════════════════════════════════

def load_sessions() -> Dict[str, Dict]:
    cached = _cache_get("sessions")
    if cached is not None:
        return cached
    rows = _db().execute("SELECT * FROM sessions").fetchall()
    data = {r["token"]: dict(r) for r in rows}
    _cache_set("sessions", data)
    return data


def save_session(token: str, github_id: str, expires_at: float = 0,
                 access_granted: int = 0, claimed_key: str = "") -> None:
    _db().execute("""
        INSERT INTO sessions VALUES (?,?,?,?,?)
        ON CONFLICT(token) DO UPDATE SET
            github_id=excluded.github_id, expires_at=excluded.expires_at,
            access_granted=excluded.access_granted, claimed_key=excluded.claimed_key
    """, (token, github_id, expires_at, access_granted, claimed_key))
    _db().commit()
    invalidate_sessions_cache()


def delete_session(token: str) -> None:
    _db().execute("DELETE FROM sessions WHERE token=?", (token,))
    _db().commit()
    invalidate_sessions_cache()


def cleanup_expired_sessions(now: float) -> int:
    r = _db().execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    _db().commit()
    invalidate_sessions_cache()
    return r.rowcount


def update_session_access(token: str, access_granted: bool, claimed_key: str = "") -> None:
    _db().execute("UPDATE sessions SET access_granted=?, claimed_key=? WHERE token=?",
                  (1 if access_granted else 0, claimed_key, token))
    _db().commit()
    invalidate_sessions_cache()


def clear_session_claimed_keys_for_keys(stale_keys: List[str]) -> None:
    if stale_keys:
        placeholders = ",".join(["?"] * len(stale_keys))
        _db().execute(f"UPDATE sessions SET access_granted=0, claimed_key='' WHERE claimed_key IN ({placeholders})",
                      stale_keys)
        _db().commit()
        invalidate_sessions_cache()


# ═══════════════════════════════════════════
# 访问密钥
# ═══════════════════════════════════════════

def load_access_keys() -> Dict[str, Any]:
    rows = _db().execute("SELECT * FROM access_keys").fetchall()
    keys = {r["key"]: dict(r) for r in rows}
    return {"keys": keys}


def save_access_keys(data: Dict[str, Any]) -> None:
    keys = data.get("keys", {})
    for k, v in keys.items():
        _db().execute("""
            INSERT OR REPLACE INTO access_keys VALUES (?,?,?,?,?,?,?)
        """, (k, v.get("used_by", ""), v.get("created_at", 0),
              v.get("disabled_at", 0), v.get("expires_at", 0),
              v.get("max_uses", 0), v.get("used_count", 0)))
    _db().commit()


def increment_key_usage(key: str) -> None:
    _db().execute("UPDATE access_keys SET used_count = used_count + 1 WHERE key=?", (key,))
    _db().commit()


def cleanup_expired_access_keys(now: float) -> List[str]:
    rows = _db().execute(
        "SELECT key FROM access_keys WHERE (expires_at > 0 AND expires_at+60 < ?) OR (max_uses > 0 AND used_count >= max_uses)",
        (now,)).fetchall()
    stale = [r["key"] for r in rows]
    if stale:
        placeholders = ",".join(["?"] * len(stale))
        _db().execute(f"DELETE FROM access_keys WHERE key IN ({placeholders})", stale)
        _db().commit()
    return stale


def add_access_key(key: str, used_by: str, created_at: float,
                   disabled_at: int, expires_at: float,
                   max_uses: int, used_count: int) -> None:
    _db().execute(
        "INSERT OR REPLACE INTO access_keys VALUES (?,?,?,?,?,?,?)",
        (key, used_by, created_at, disabled_at, expires_at, max_uses, used_count))
    _db().commit()


def delete_access_key(key: str) -> None:
    _db().execute("DELETE FROM access_keys WHERE key=?", (key,))
    _db().commit()


def disable_access_key(key: str, now: float) -> None:
    _db().execute("UPDATE access_keys SET disabled_at=? WHERE key=?", (now, key))
    _db().commit()


def enable_access_key(key: str) -> None:
    _db().execute("UPDATE access_keys SET disabled_at=NULL WHERE key=?", (key,))
    _db().commit()


def unclaim_access_key(github_id: str) -> None:
    _db().execute(
        "UPDATE access_keys SET used_by='' WHERE used_by=? AND disabled_at=0",
        (github_id,))
    _db().commit()


def claim_access_key(key: str, github_id: str) -> bool:
    cur = _db().execute(
        "UPDATE access_keys SET used_by=? WHERE key=? AND (used_by='' OR used_by=?)",
        (github_id, key, github_id))
    _db().commit()
    return cur.rowcount > 0


def get_access_key(key: str) -> Optional[Dict]:
    r = _db().execute("SELECT * FROM access_keys WHERE key=?", (key,)).fetchone()
    return dict(r) if r else None


# ═══════════════════════════════════════════
# 用户图片
# ═══════════════════════════════════════════

def load_user_images() -> Dict[str, List[Dict]]:
    rows = _db().execute("SELECT * FROM user_images ORDER BY time DESC").fetchall()
    result: Dict[str, List[Dict]] = {}
    for r in rows:
        gid = r["github_id"]
        result.setdefault(gid, []).append(
            {"path": r["path"], "prompt": r["prompt"], "time": r["time"]})
    return result


def save_user_image(github_id: str, path: str, prompt: str) -> None:
    _db().execute(
        "INSERT INTO user_images (github_id, path, prompt, time) VALUES (?,?,?,?)",
        (github_id, path, prompt[:100], _time_module.time()))
    # 每人最多 10000 条
    count = _db().execute(
        "SELECT COUNT(*) as c FROM user_images WHERE github_id=?", (github_id,)).fetchone()["c"]
    if count > 10000:
        oldest = _db().execute(
            "SELECT id FROM user_images WHERE github_id=? ORDER BY time ASC LIMIT ?",
            (github_id, count - 10000)).fetchall()
        for o in oldest:
            _db().execute("DELETE FROM user_images WHERE id=?", (o["id"],))
    _db().commit()


def remove_user_image(github_id: str, path: str) -> None:
    _db().execute("DELETE FROM user_images WHERE github_id=? AND path=?", (github_id, path))
    _db().commit()


def remove_user_image_by_path(path: str) -> int:
    """删除所有该路径的 user_images 记录，返回删除数。"""
    r = _db().execute("DELETE FROM user_images WHERE path=?", (path,))
    _db().commit()
    return r.rowcount


def remove_user_images_by_paths(paths: set) -> int:
    """批量删除 user_images 记录，返回删除数。"""
    if not paths:
        return 0
    placeholders = ",".join("?" * len(paths))
    r = _db().execute(
        f"DELETE FROM user_images WHERE path IN ({placeholders})",
        list(paths))
    _db().commit()
    return r.rowcount


def cleanup_stale_user_images(existing_paths_fn) -> int:
    """删除文件已不存在的 user_images 记录，返回删除数。"""
    rows = _db().execute("SELECT id, path FROM user_images").fetchall()
    removed = 0
    for r in rows:
        if not existing_paths_fn(r["path"]):
            _db().execute("DELETE FROM user_images WHERE id=?", (r["id"],))
            removed += 1
    if removed:
        _db().commit()
    return removed


def backfill_user_images_from_gen_logs() -> int:
    """从 gen_logs.file_paths 回填 user_images 缺失的数据，返回新增条数。"""
    import json as _json
    added = 0
    existing = set(
        r["path"] for r in _db().execute("SELECT path FROM user_images").fetchall()
    )
    rows = _db().execute(
        "SELECT github_id, prompt, file_paths, created_at FROM gen_logs WHERE file_paths != '[]'"
    ).fetchall()
    for r in rows:
        gid = r["github_id"]
        prompt = (r["prompt"] or "")[:100]
        ts = r["created_at"] or _time_module.time()
        try:
            fps = _json.loads(r["file_paths"])
        except Exception:
            continue
        for fp in (fps if isinstance(fps, list) else []):
            fp = str(fp).replace("\\", "/")
            if fp and fp not in existing:
                _db().execute(
                    "INSERT INTO user_images (github_id, path, prompt, time) VALUES (?,?,?,?)",
                    (gid, fp, prompt, ts))
                existing.add(fp)
                added += 1
    _db().commit()
    if added:
        print(f"[backfill] user_images 从 gen_logs 回填 {added} 条")
    return added


def cleanup_stale_user_images(existing_paths_fn) -> int:
    """使用回调检查路径有效性。"""
    rows = _db().execute("SELECT id, path FROM user_images").fetchall()
    removed = 0
    for r in rows:
        if not existing_paths_fn(r["path"]):
            _db().execute("DELETE FROM user_images WHERE id=?", (r["id"],))
            removed += 1
    if removed:
        _db().commit()
    return removed


# ═══════════════════════════════════════════
# 删除标记
# ═══════════════════════════════════════════

def load_deleted_images() -> Dict[str, List[str]]:
    rows = _db().execute("SELECT * FROM deleted_images").fetchall()
    result: Dict[str, List[str]] = {}
    for r in rows:
        result.setdefault(r["github_id"], []).append(r["path"])
    return result


def add_deleted_image(github_id: str, path: str) -> None:
    _db().execute(
        "INSERT OR IGNORE INTO deleted_images (github_id, path, marked_at) VALUES (?,?,?)",
        (github_id, path, _time_module.time()))
    _db().commit()


def remove_deleted_image(github_id: str, path: str) -> None:
    _db().execute("DELETE FROM deleted_images WHERE github_id=? AND path=?", (github_id, path))
    _db().commit()


def save_deleted_images(data: Dict[str, List[str]]) -> None:
    """全量写入（仅迁移/启动清理等批量场景使用，有事务保护）。"""
    _db().execute("BEGIN IMMEDIATE")
    try:
        _db().execute("DELETE FROM deleted_images")
        for gid, paths in data.items():
            for p in paths:
                _db().execute(
                    "INSERT INTO deleted_images (github_id, path) VALUES (?,?)", (gid, p))
        _db().commit()
    except Exception:
        _db().execute("ROLLBACK")
        raise


# ═══════════════════════════════════════════
# 生图日志
# ═══════════════════════════════════════════

_GEN_LOG_MAX = 100000  # 最大条数


def load_gen_logs() -> Dict[str, Dict]:
    rows = _db().execute("SELECT * FROM gen_logs ORDER BY created_at DESC").fetchall()
    return {r["log_id"]: dict(r) for r in rows}


def save_gen_log(github_id: str, login: str, prompt: str, workflow: str,
                 count: int, status: str, client_ip: str,
                 negative_prompt: str = "", file_paths: list = None) -> None:
    log_id = f"{int(_time_module.time() * 1000)}_{secrets.token_hex(4)}"
    fps = json.dumps([p.replace("\\", "/") for p in (file_paths or [])])
    _db().execute(
        "INSERT INTO gen_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (log_id, github_id, login or github_id,
         prompt[:25000], negative_prompt[:25000] if negative_prompt else "",
         workflow or "", count, status, client_ip, _time_module.time(), fps))
    # 超出上限删最旧
    total = _db().execute("SELECT COUNT(*) as c FROM gen_logs").fetchone()["c"]
    if total > _GEN_LOG_MAX:
        excess = total - _GEN_LOG_MAX
        _db().execute(
            "DELETE FROM gen_logs WHERE log_id IN (SELECT log_id FROM gen_logs ORDER BY created_at ASC LIMIT ?)",
            (excess,))
    _db().commit()


def load_gen_logs_raw():
    """Return all gen_logs rows as list of dicts (for fallback lookups)."""
    return [dict(r) for r in _db().execute("SELECT * FROM gen_logs ORDER BY created_at DESC").fetchall()]

def clean_gen_logs_by_file_paths(deleted_paths: set) -> int:
    """删除所有 file_paths 已全部被删的日志。"""
    all_logs = _db().execute("SELECT log_id, file_paths FROM gen_logs").fetchall()
    removed = 0
    for r in all_logs:
        try:
            fps = set(json.loads(r["file_paths"] or "[]"))
        except Exception:
            fps = set()
        if fps and fps.issubset(deleted_paths):
            _db().execute("DELETE FROM gen_logs WHERE log_id=?", (r["log_id"],))
            removed += 1
    if removed:
        _db().commit()
    return removed


def query_gen_logs(login: str = "", date_from: float = 0, date_to: float = 0,
                   limit: int = 20, offset: int = 0) -> Tuple[List[Dict], int]:
    conditions = []
    params = []
    if login:
        conditions.append("login LIKE ?")
        params.append(f"%{login}%")
    if date_from:
        conditions.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total = _db().execute(f"SELECT COUNT(*) as c FROM gen_logs{where}", params).fetchone()["c"]
    rows = _db().execute(
        f"SELECT * FROM gen_logs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [max(1, min(limit, 200)), max(0, offset)]).fetchall()
    return [dict(r) for r in rows], total


def delete_gen_logs_by_ids(log_ids: list) -> int:
    if not log_ids:
        return 0
    placeholders = ",".join(["?"] * len(log_ids))
    cur = _db().execute(f"DELETE FROM gen_logs WHERE log_id IN ({placeholders})", log_ids)
    _db().commit()
    return cur.rowcount


def clear_gen_logs(date_from: float = 0, date_to: float = 0, *, unlink_all: bool = False) -> int:
    if unlink_all:
        removed = _db().execute("SELECT COUNT(*) as c FROM gen_logs").fetchone()["c"]
        _db().execute("DELETE FROM gen_logs")
    else:
        conditions = []
        params = []
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        removed = _db().execute(f"SELECT COUNT(*) as c FROM gen_logs{where}", params).fetchone()["c"]
        _db().execute(f"DELETE FROM gen_logs{where}", params)
    _db().commit()
    return removed


# ═══════════════════════════════════════════
# 删除日志（回收站）
# ═══════════════════════════════════════════

_DELETION_LOG_MAX = 100000


def load_deletion_log() -> List[Dict]:
    rows = _db().execute("SELECT * FROM deletion_logs ORDER BY deleted_at DESC").fetchall()
    return [dict(r) for r in rows]


def add_deletion_log_entry(entry: Dict) -> None:
    _db().execute(
        "INSERT INTO deletion_logs (path, thumb_file, deleted_by_gid, deleted_by_login, deleted_at, creator_ip, creator_gid, creator_login) VALUES (?,?,?,?,?,?,?,?)",
        (entry.get("path", ""), entry.get("thumb_file", ""),
         entry.get("deleted_by_github_id", ""), entry.get("deleted_by_login", ""),
         entry.get("deleted_at", _time_module.time()),
         entry.get("creator_ip", ""), entry.get("creator_github_id", ""), entry.get("creator_login", "")))
    # 超上限
    total = _db().execute("SELECT COUNT(*) as c FROM deletion_logs").fetchone()["c"]
    if total > _DELETION_LOG_MAX:
        excess = total - _DELETION_LOG_MAX
        _db().execute(
            "DELETE FROM deletion_logs WHERE id IN (SELECT id FROM deletion_logs ORDER BY deleted_at ASC LIMIT ?)",
            (excess,))
    _db().commit()


def clear_deletion_logs_by_path(path: str) -> int:
    r = _db().execute("DELETE FROM deletion_logs WHERE path=?", (path,))
    _db().commit()
    return r.rowcount


def clear_deletion_logs_by_date(date_from: float, date_to: float) -> int:
    conditions = []
    params = []
    if date_from:
        conditions.append("deleted_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("deleted_at <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions)
    r = _db().execute(f"DELETE FROM deletion_logs{where}", params)
    _db().commit()
    return r.rowcount


def clear_all_deletion_logs() -> int:
    r = _db().execute("DELETE FROM deletion_logs")
    _db().commit()
    return r.rowcount


def query_deletion_log(search: str = "", date_from: float = 0, date_to: float = 0,
                       limit: int = 60, offset: int = 0) -> Tuple[List[Dict], int]:
    conditions = []
    params = []
    if search:
        conditions.append("(deleted_by_login LIKE ? OR creator_login LIKE ? OR path LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s])
    if date_from:
        conditions.append("deleted_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("deleted_at <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    total = _db().execute(f"SELECT COUNT(*) as c FROM deletion_logs{where}", params).fetchone()["c"]
    rows = _db().execute(
        f"SELECT * FROM deletion_logs{where} ORDER BY deleted_at DESC LIMIT ? OFFSET ?",
        params + [max(1, min(limit, 200)), max(0, offset)]).fetchall()
    return [dict(r) for r in rows], total


# ═══════════════════════════════════════════
# 队列
# ═══════════════════════════════════════════

def load_queue() -> List[Dict]:
    rows = _db().execute("SELECT * FROM queue_items ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_queue_item(github_id: str, login: str, workflow: str,
                   client_ip: str, status: str = "waiting") -> int:
    c = _db().execute("INSERT INTO queue_items (github_id, login, workflow, client_ip, status, created_at) VALUES (?,?,?,?,?,?)",
                      (github_id, login, workflow, client_ip, status, _time_module.time()))
    _db().commit()
    return c.lastrowid or 0


def update_queue_item_status(item_id: int, status: str) -> None:
    _db().execute("UPDATE queue_items SET status=? WHERE id=?", (status, item_id))
    _db().commit()


def remove_queue_item(item_id: int) -> None:
    _db().execute("DELETE FROM queue_items WHERE id=?", (item_id,))
    _db().commit()


def clear_completed_queue(max_age: float = 7200) -> None:
    cutoff = _time_module.time() - max_age
    _db().execute(
        "DELETE FROM queue_items WHERE status IN ('done','failed','cancelled') AND created_at < ?",
        (cutoff,))
    _db().commit()


# ═══════════════════════════════════════════
# 举报
# ═══════════════════════════════════════════

def load_reports() -> List[Dict]:
    rows = _db().execute("SELECT * FROM reports").fetchall()
    return [dict(r) for r in rows]


def save_report(report: Dict) -> None:
    _db().execute(
        "INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?,?)",
        (report.get("id", ""), report.get("image_path", ""),
         report.get("reporter_gid", ""), report.get("reporter_login", ""),
         report.get("reason", ""), report.get("status", "pending"),
         report.get("timestamp", 0), report.get("resolved_action", ""),
         report.get("reporter_ip", "")))
    _db().commit()


def resolve_report(report_id: str, action: str) -> None:
    _db().execute(
        "UPDATE reports SET status='resolved', resolved_action=? WHERE id=? AND status='pending'",
        (action, report_id))
    _db().commit()


def dismiss_reports_for_image(image_path: str) -> int:
    cur = _db().execute(
        "UPDATE reports SET status='resolved', resolved_action='dismiss' WHERE status='pending' AND image_path=?",
        (image_path,))
    _db().commit()
    return cur.rowcount


def dismiss_reports_for_image_paths(image_paths: set) -> int:
    """批量忽略多张图的所有待处理举报（事务保护）。"""
    if not image_paths:
        return 0
    placeholders = ",".join("?" * len(image_paths))
    cur = _db().execute(
        f"UPDATE reports SET status='resolved', resolved_action='dismiss' WHERE status='pending' AND image_path IN ({placeholders})",
        list(image_paths))
    _db().commit()
    return cur.rowcount


def dismiss_reports_by_reporter_ip(reporter_ip: str, exclude_id: str = "") -> int:
    if exclude_id:
        cur = _db().execute(
            "UPDATE reports SET status='resolved', resolved_action='dismiss' WHERE status='pending' AND reporter_ip=? AND id!=?",
            (reporter_ip, exclude_id))
    else:
        cur = _db().execute(
            "UPDATE reports SET status='resolved', resolved_action='dismiss' WHERE status='pending' AND reporter_ip=?",
            (reporter_ip,))
    _db().commit()
    return cur.rowcount


# ═══════════════════════════════════════════
# 精选
# ═══════════════════════════════════════════

def load_featured() -> List[str]:
    rows = _db().execute("SELECT path FROM featured ORDER BY sort_order").fetchall()
    return [r["path"] for r in rows]


def save_featured(paths: List[str]) -> None:
    old = {r["path"] for r in _db().execute("SELECT path FROM featured").fetchall()}
    new_set = set(paths)
    for p in old:
        if p not in new_set:
            _db().execute("DELETE FROM featured WHERE path=?", (p,))
    for i, p in enumerate(paths):
        _db().execute("INSERT OR REPLACE INTO featured (path, sort_order) VALUES (?,?)", (p, i))


# ═══════════════════════════════════════════
# 封禁 IP
# ═══════════════════════════════════════════

def load_banned_ips() -> List[str]:
    rows = _db().execute("SELECT ip FROM banned_ips").fetchall()
    return [r["ip"] for r in rows]


def save_banned_ips(ips: List[str]) -> None:
    old = {r["ip"] for r in _db().execute("SELECT ip FROM banned_ips").fetchall()}
    new_set = set(ips)
    for ip in old:
        if ip not in new_set:
            _db().execute("DELETE FROM banned_ips WHERE ip=?", (ip,))
    for ip in ips:
        if ip not in old:
            _db().execute("INSERT OR IGNORE INTO banned_ips VALUES (?)", (ip,))


# ═══════════════════════════════════════════
# 生图者 IP
# ═══════════════════════════════════════════

def load_creator_map() -> Dict[str, str]:
    rows = _db().execute("SELECT * FROM creator_ips").fetchall()
    return {r["path"]: r["ip"] for r in rows}


def set_creator_ip(path: str, ip: str) -> None:
    _db().execute("INSERT OR REPLACE INTO creator_ips VALUES (?,?)", (path, ip))
    _db().commit()


def remove_creator_ip(path: str) -> None:
    _db().execute("DELETE FROM creator_ips WHERE path=?", (path,))
    _db().commit()


def lookup_creator_ip(path: str) -> Optional[str]:
    r = _db().execute("SELECT ip FROM creator_ips WHERE path=?", (path,)).fetchone()
    return r["ip"] if r else None


# ═══════════════════════════════════════════
# 画风 / 角色 / 分辨率 / 工作流元数据
# ═══════════════════════════════════════════

def load_styles() -> List[Dict]:
    rows = _db().execute("SELECT * FROM styles ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def save_styles(styles: List[Dict]) -> None:
    _db().execute("BEGIN IMMEDIATE")
    try:
        _db().execute("DELETE FROM styles")
        for i, s in enumerate(styles):
            _db().execute(
                "INSERT INTO styles (name, tags, alias, thumbnail, sort_order) VALUES (?,?,?,?,?)",
                (s.get("name", ""), s.get("tags", ""), s.get("alias", ""), s.get("thumbnail", ""), i))
        _db().commit()
    except Exception:
        _db().execute("ROLLBACK")
        raise


def load_characters() -> List[Dict]:
    rows = _db().execute("SELECT * FROM characters ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def save_characters(characters: List[Dict]) -> None:
    _db().execute("BEGIN IMMEDIATE")
    try:
        _db().execute("DELETE FROM characters")
        for i, c in enumerate(characters):
            _db().execute(
                "INSERT INTO characters (name, tags, alias, thumbnail, sort_order) VALUES (?,?,?,?,?)",
                (c.get("name", ""), c.get("tags", ""), c.get("alias", ""), c.get("thumbnail", ""), i))
        _db().commit()
    except Exception:
        _db().execute("ROLLBACK")
        raise


def load_resolutions() -> Dict[str, Any]:
    rows = _db().execute("SELECT * FROM resolutions ORDER BY sort_order").fetchall()
    return {"presets": [{"w": r["w"], "h": r["h"], "label": r["label"]} for r in rows]}


def save_resolutions(presets: List[Dict]) -> None:
    _db().execute("BEGIN IMMEDIATE")
    try:
        _db().execute("DELETE FROM resolutions")
        for i, r in enumerate(presets):
            _db().execute(
                "INSERT INTO resolutions (w, h, label, sort_order) VALUES (?,?,?,?)",
                (r.get("w", 0), r.get("h", 0), r.get("label", ""), i))
        _db().commit()
    except Exception:
        _db().execute("ROLLBACK")
        raise


def load_workflow_meta() -> List[Dict]:
    rows = _db().execute("SELECT * FROM workflow_meta ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def save_workflow_meta(meta: List[Dict]) -> None:
    _db().execute("BEGIN IMMEDIATE")
    try:
        _db().execute("DELETE FROM workflow_meta")
        for i, m in enumerate(meta):
            _db().execute(
                "INSERT INTO workflow_meta (workflow, thumbnail, lora_link, display_name, sort_order) VALUES (?,?,?,?,?)",
                (m.get("workflow", ""), m.get("thumbnail", ""), m.get("lora_link", ""), m.get("display_name", ""), i))
        _db().commit()
    except Exception:
        _db().execute("ROLLBACK")
        raise


# ═══════════════════════════════════════════
# KV 状态 (替代 state.json)
# ═══════════════════════════════════════════

def state_get(key: str, default: Any = None) -> Any:
    r = _db().execute("SELECT value FROM kv_state WHERE key=?", (key,)).fetchone()
    if r is None:
        return default
    try:
        return json.loads(r["value"])
    except Exception:
        return r["value"]


def state_set(key: str, value: Any) -> None:
    v = json.dumps(value) if not isinstance(value, str) else value
    _db().execute("INSERT OR REPLACE INTO kv_state VALUES (?,?)", (key, v))
    _db().commit()


# ═══════════════════════════════════════════
# GC 日志
# ═══════════════════════════════════════════

def add_gc_log(timestamp: float, duration: float, cleaned: dict, backup_dir: str = "") -> None:
    _db().execute(
        "INSERT INTO gc_logs (timestamp, duration, cleaned, backup_dir) VALUES (?,?,?,?)",
        (timestamp, duration, json.dumps(cleaned), backup_dir))
    _db().commit()


def load_gc_logs(limit: int = 20, offset: int = 0, min_time: float = 0, max_time: float = 0) -> list:
    where = []
    params = []
    if min_time > 0:
        where.append("timestamp >= ?")
        params.append(min_time)
    if max_time > 0:
        where.append("timestamp <= ?")
        params.append(max_time)
    sql = "SELECT * FROM gc_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = _db().execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["cleaned"] = json.loads(d["cleaned"])
        except Exception:
            d["cleaned"] = {}
        result.append(d)
    return result


def clear_gc_logs() -> None:
    _db().execute("DELETE FROM gc_logs")
    _db().commit()


def count_gc_logs(min_time: float = 0, max_time: float = 0) -> int:
    where = []
    params = []
    if min_time > 0:
        where.append("timestamp >= ?")
        params.append(min_time)
    if max_time > 0:
        where.append("timestamp <= ?")
        params.append(max_time)
    sql = "SELECT COUNT(*) as cnt FROM gc_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    r = _db().execute(sql, params).fetchone()
    return r["cnt"] if r else 0


# ═══════════════════════════════════════════
# 通知
# ═══════════════════════════════════════════

def add_notification(github_id: str, message: str) -> None:
    _db().execute(
        "INSERT INTO notifications (github_id, message, created_at) VALUES (?,?,?)",
        (github_id, message, __import__("time").time()))
    _db().commit()


def get_unread_notifications(github_id: str) -> list:
    rows = _db().execute(
        "SELECT * FROM notifications WHERE github_id=? AND read=0 ORDER BY created_at DESC LIMIT 20",
        (github_id,)).fetchall()
    return [dict(r) for r in rows]


def mark_notifications_read(github_id: str) -> None:
    _db().execute("UPDATE notifications SET read=1 WHERE github_id=? AND read=0", (github_id,))
    _db().commit()

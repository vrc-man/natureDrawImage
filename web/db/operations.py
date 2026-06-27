"""
SQLite 数据操作层 (Data Access Layer)

替代 app.py 中所有 _load_json / _save_json 调用。
每个函数签名与原有 JSON 版本兼容，内部改为 SQLite 操作。

所有写入操作自动 commit，读取操作即时查询。
"""

import json
import sqlite3
import time as _time_module
import secrets
import hashlib as _hashlib
from typing import Dict, Any, List, Optional, Tuple

from db.schema import get_db, config_get, config_set, config_get_section, db_lock, transaction

_db = get_db  # 函数别名


def backup_database(dst_path: str) -> None:
    """使用 SQLite 在线备份 API 生成事务一致快照，包含 WAL 中的最新数据。"""
    dst = sqlite3.connect(dst_path)
    try:
        with db_lock():
            _db().backup(dst)
    finally:
        dst.close()

# ── 写穿透缓存（内存 dict + TTL 兜底） ──
_CACHE_TTL = 60

# ── 日志表上限（超出时自动清理最旧记录） ──
_GEN_LOG_MAX = 500000       # 生图日志最多保留 50 万条
_DELETION_LOG_MAX = 500000  # 删除日志最多保留 50 万条
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


def update_user_info(github_id: str, login: str = "", email: str = "", avatar_url: str = "") -> None:
    """更新用户非角色信息，原子单行。"""
    if not login and not email and not avatar_url:
        return
    parts = []
    params = []
    if login:
        parts.append("login=?")
        params.append(login)
    if email:
        parts.append("email=?")
        params.append(email)
    if avatar_url:
        parts.append("avatar_url=?")
        params.append(avatar_url)
    params.append(github_id)
    _db().execute(f"UPDATE users SET {','.join(parts)} WHERE github_id=?", params)
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
    data = {}
    migrated = False
    for r in rows:
        token = r["token"]
        if len(token) != 64:  # old-style raw token, migrate to sha256
            hashed = _hashlib.sha256(token.encode()).hexdigest()
            if hashed not in data:
                _db().execute("UPDATE sessions SET token=? WHERE token=?", (hashed, token))
                migrated = True
            else:
                _db().execute("DELETE FROM sessions WHERE token=?", (token,))
            token = hashed
        data[token] = dict(r)
    if migrated:
        _db().commit()
        invalidate_sessions_cache()
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


def clear_sessions_for_user(github_id: str) -> None:
    """清除指定用户的所有会话。"""
    _db().execute("DELETE FROM sessions WHERE github_id=?", (github_id,))
    _db().commit()
    invalidate_sessions_cache()


def revoke_user_sessions(github_id: str, as_admin: bool = False) -> None:
    """撤销/恢复用户的所有会话（原子单行，修改 access_granted 并清空 claimed_key）。"""
    _db().execute(
        "UPDATE sessions SET access_granted=?, claimed_key='' WHERE github_id=?",
        (1 if as_admin else 0, github_id))
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


def decrement_key_usage(key: str) -> None:
    _db().execute("UPDATE access_keys SET used_count = MAX(0, used_count - 1) WHERE key=?", (key,))
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


def cleanup_disabled_access_keys(now: float) -> List[str]:
    """删除禁用缓冲期已结束的密钥，返回被删除的 key。"""
    rows = _db().execute(
        "SELECT key FROM access_keys WHERE disabled_at > 0 AND disabled_at+2 < ?",
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
    _db().execute("UPDATE access_keys SET disabled_at=0 WHERE key=?", (key,))
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
    # 每人最多 100000 条，放到 GC 里统一清理
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
    with transaction() as conn:
        for r in rows:
            if not existing_paths_fn(r["path"]):
                conn.execute("DELETE FROM user_images WHERE id=?", (r["id"],))
                removed += 1
    return removed


def backfill_user_images_from_gen_logs(exists_fn=None) -> int:
    """从 gen_logs.file_paths 回填 user_images 缺失的数据，返回新增条数。
    exists_fn(path) 可选，只回填文件仍存在的记录。
    """
    import json as _json
    added = 0
    existing = set(
        r["path"] for r in _db().execute("SELECT path FROM user_images").fetchall()
    )
    rows = _db().execute(
        "SELECT github_id, prompt, file_paths, created_at FROM gen_logs WHERE file_paths != '[]'"
    ).fetchall()
    with transaction() as conn:
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
                    if exists_fn and not exists_fn(fp):
                        continue
                    conn.execute(
                        "INSERT INTO user_images (github_id, path, prompt, time) VALUES (?,?,?,?)",
                        (gid, fp, prompt, ts))
                    existing.add(fp)
                    added += 1
    return added

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
    with transaction(immediate=True) as conn:
        conn.execute("DELETE FROM deleted_images")
        for gid, paths in data.items():
            for p in paths:
                conn.execute(
                    "INSERT INTO deleted_images (github_id, path) VALUES (?,?)", (gid, p))


def mark_images_deleted(github_id: str, paths: List[str], *, owner_github_id: str = "") -> int:
    """原子标记图片删除并清理关联状态。文件和删除日志由调用方在事务外处理。"""
    clean_paths = []
    seen = set()
    for p in paths or []:
        p = str(p or "").replace("\\", "/").strip()
        if p and p not in seen:
            seen.add(p)
            clean_paths.append(p)
    if not clean_paths:
        return 0
    now = _time_module.time()
    with transaction(immediate=True) as conn:
        for p in clean_paths:
            conn.execute(
                "INSERT OR IGNORE INTO deleted_images (github_id, path, marked_at) VALUES (?,?,?)",
                (github_id, p, now))
        placeholders = ",".join("?" * len(clean_paths))
        if owner_github_id:
            conn.execute(
                f"DELETE FROM user_images WHERE github_id=? AND path IN ({placeholders})",
                [owner_github_id] + clean_paths)
        else:
            conn.execute(f"DELETE FROM user_images WHERE path IN ({placeholders})", clean_paths)
        conn.execute(f"DELETE FROM featured WHERE path IN ({placeholders})", clean_paths)
        conn.execute(f"DELETE FROM creator_ips WHERE path IN ({placeholders})", clean_paths)
        conn.execute(
            f"UPDATE reports SET status='resolved', resolved_action='dismiss' WHERE status='pending' AND image_path IN ({placeholders})",
            clean_paths)
    return len(clean_paths)


# ═══════════════════════════════════════════
# 用户图片清理（由 GC 统一调用，不在每次写入时触发）
# ═══════════════════════════════════════════


def prune_user_images(limit_per_user: int = 100000) -> int:
    """清理所有用户超出 limit_per_user 的最旧记录。返回删除总数。"""
    total = 0
    rows = _db().execute("SELECT DISTINCT github_id FROM user_images").fetchall()
    with transaction() as conn:
        for r in rows:
            gid = r["github_id"]
            count = conn.execute("SELECT COUNT(*) as c FROM user_images WHERE github_id=?", (gid,)).fetchone()["c"]
            if count > limit_per_user:
                excess = count - limit_per_user
                oldest = conn.execute(
                    "SELECT id FROM user_images WHERE github_id=? ORDER BY time ASC LIMIT ?",
                    (gid, excess)).fetchall()
                for o in oldest:
                    conn.execute("DELETE FROM user_images WHERE id=?", (o["id"],))
                    total += 1
    return total

def load_gen_logs() -> Dict[str, Dict]:
    rows = _db().execute("SELECT * FROM gen_logs ORDER BY created_at DESC").fetchall()
    return {r["log_id"]: dict(r) for r in rows}


def save_gen_log(github_id: str, login: str, prompt: str, workflow: str,
                 count: int, status: str, client_ip: str,
                 negative_prompt: str = "", file_paths: list = None,
                 error_reason: str = "") -> None:
    log_id = f"{int(_time_module.time() * 1000)}_{secrets.token_hex(4)}"
    fps = json.dumps([p.replace("\\", "/") for p in (file_paths or [])])
    _db().execute(
        "INSERT INTO gen_logs (log_id,github_id,login,prompt,negative_prompt,workflow,count,status,client_ip,created_at,file_paths,error_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (log_id, github_id, login or github_id,
         prompt[:25000], negative_prompt[:25000] if negative_prompt else "",
         workflow or "", count, status, client_ip, _time_module.time(), fps,
         error_reason[:500] if error_reason else ""))
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

def count_gen_logs_today(login: str = "") -> int:
    """今日（UTC）成功生图总数。可选 login 筛选。"""
    sql = "SELECT COUNT(*) as c FROM gen_logs WHERE status='success' AND date(created_at,'unixepoch')=date('now')"
    params: list = []
    if login:
        sql += " AND (login LIKE ? OR github_id LIKE ?)"
        params.extend([f"%{login}%", f"%{login}%"])
    r = _db().execute(sql, params).fetchone()
    return r["c"] if r else 0


def get_gen_logs_hourly_today(login: str = "") -> List[Dict]:
    """今日（UTC）每小时的生图数量。可选 login 筛选。"""
    sql = "SELECT strftime('%H',created_at,'unixepoch') as hour,COUNT(*) as count FROM gen_logs WHERE status='success' AND date(created_at,'unixepoch')=date('now')"
    params: list = []
    if login:
        sql += " AND (login LIKE ? OR github_id LIKE ?)"
        params.extend([f"%{login}%", f"%{login}%"])
    sql += " GROUP BY hour ORDER BY hour"
    rows = _db().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_gen_logs_daily_7days(login: str = "") -> List[Dict]:
    """最近7天（UTC）每日生图数量。可选 login 筛选。"""
    sql = "SELECT date(created_at,'unixepoch') as day,COUNT(*) as count FROM gen_logs WHERE status='success' AND created_at>=unixepoch('now','-7 days')"
    params: list = []
    if login:
        sql += " AND (login LIKE ? OR github_id LIKE ?)"
        params.extend([f"%{login}%", f"%{login}%"])
    sql += " GROUP BY day ORDER BY day"
    rows = _db().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count_gen_logs_range(date_from: float, date_to: float, login: str = "") -> int:
    """指定时间范围的生图总数。可选 login 筛选。"""
    sql = "SELECT COUNT(*) as c FROM gen_logs WHERE status='success' AND created_at>=? AND created_at<?"
    params: list = [date_from, date_to]
    if login:
        sql += " AND (login LIKE ? OR github_id LIKE ?)"
        params.extend([f"%{login}%", f"%{login}%"])
    r = _db().execute(sql, params).fetchone()
    return r["c"] if r else 0


def get_gen_logs_hourly_range(date_from: float, date_to: float, login: str = "", tz_offset: float = 0) -> List[Dict]:
    """指定时间范围每小时的生图数量。可选 login/tz_offset 筛选。tz_offset 非0时按本地时区聚合。"""
    if tz_offset:
        sql = f"SELECT CAST(strftime('%H',created_at,'unixepoch','{int(tz_offset):+d} hours') AS INTEGER) as hour,SUM(count) as count FROM gen_logs WHERE status='success' AND created_at>=? AND created_at<?"
    else:
        sql = "SELECT CAST(strftime('%H',created_at,'unixepoch') AS INTEGER) as hour,SUM(count) as count FROM gen_logs WHERE status='success' AND created_at>=? AND created_at<?"
    params: list = [date_from, date_to]
    if login:
        sql += " AND (login LIKE ? OR github_id LIKE ?)"
        params.extend([f"%{login}%", f"%{login}%"])
    sql += " GROUP BY hour ORDER BY hour"
    rows = _db().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_gen_logs_daily_range(date_from: float, date_to: float, login: str = "", tz_offset: float = 0) -> List[Dict]:
    """指定时间范围每日生图数量。可选 login/tz_offset 筛选。tz_offset 非0时按本地时区聚合。"""
    if tz_offset:
        sql = f"SELECT date(created_at,'unixepoch','{int(tz_offset):+d} hours') as day,SUM(count) as count FROM gen_logs WHERE status='success' AND created_at>=? AND created_at<?"
    else:
        sql = "SELECT date(created_at,'unixepoch') as day,SUM(count) as count FROM gen_logs WHERE status='success' AND created_at>=? AND created_at<?"
    params: list = [date_from, date_to]
    if login:
        sql += " AND (login LIKE ? OR github_id LIKE ?)"
        params.extend([f"%{login}%", f"%{login}%"])
    sql += " GROUP BY day ORDER BY day"
    rows = _db().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_gen_logs_raw_range(date_from: float = 0, date_to: float = 0) -> List[Dict]:
    """返回指定时间范围的 gen_logs（全字段，不限量），不传=全部。"""
    sql = "SELECT * FROM gen_logs"
    params: list = []
    conds: list = []
    if date_from:
        conds.append("created_at>=?")
        params.append(date_from)
    if date_to:
        conds.append("created_at<?")
        params.append(date_to)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY created_at DESC"
    return [dict(r) for r in _db().execute(sql, params).fetchall()]


def count_gen_logs_raw_total() -> int:
    r = _db().execute("SELECT COUNT(*) as c FROM gen_logs").fetchone()
    return r["c"] if r else 0


def get_gen_logs_date_range() -> Tuple[float, float]:
    """返回 gen_logs 最早和最晚的 created_at。"""
    r = _db().execute("SELECT MIN(created_at) as min_d, MAX(created_at) as max_d FROM gen_logs").fetchone()
    return (r["min_d"] or 0, r["max_d"] or 0) if r else (0, 0)


def get_gen_leaderboard(limit: int = 3, date_from: float = 0, date_to: float = 0, tz_offset: float = 0) -> dict:
    """生图排行榜：前三名的总数 + 24h分布 + 每日分布，一次查出。"""
    # 区间总生图数
    sql_total = "SELECT SUM(count) as c FROM gen_logs WHERE status='success'"
    params_total: list = []
    if date_from:
        sql_total += " AND created_at>=?"
        params_total.append(date_from)
    if date_to:
        sql_total += " AND created_at<?"
        params_total.append(date_to)
    r_total = _db().execute(sql_total, params_total).fetchone()
    total_count = r_total["c"] or 0 if r_total else 0

    # 排行榜前三名
    sql_top = "SELECT login, github_id, SUM(count) as gen_count FROM gen_logs WHERE status='success'"
    params_top: list = []
    if date_from:
        sql_top += " AND created_at>=?"
        params_top.append(date_from)
    if date_to:
        sql_top += " AND created_at<?"
        params_top.append(date_to)
    sql_top += " GROUP BY login, github_id ORDER BY gen_count DESC LIMIT ?"
    params_top.append(limit)
    rows = [dict(r) for r in _db().execute(sql_top, params_top).fetchall()]

    if not rows:
        return {"total": total_count, "items": []}

    logins = [r["login"] for r in rows]
    placeholders = ",".join("?" * len(logins))

    # 24h 分布（本地时区）
    if tz_offset:
        sql_hourly = (
            f"SELECT login, CAST(strftime('%H',created_at,'unixepoch','{int(tz_offset):+d} hours') AS INTEGER) as h, "
            "SUM(count) as c FROM gen_logs "
            f"WHERE status='success' AND login IN ({placeholders})"
        )
    else:
        sql_hourly = (
            "SELECT login, CAST(strftime('%H',created_at,'unixepoch') AS INTEGER) as h, "
            "SUM(count) as c FROM gen_logs "
            f"WHERE status='success' AND login IN ({placeholders})"
        )
    params_hourly = list(logins)
    if date_from:
        sql_hourly += " AND created_at>=?"
        params_hourly.append(date_from)
    if date_to:
        sql_hourly += " AND created_at<?"
        params_hourly.append(date_to)
    sql_hourly += " GROUP BY login, h"
    hourly_rows = _db().execute(sql_hourly, params_hourly).fetchall()

    # 每日分布（本地时区）
    if tz_offset:
        sql_daily = (
            f"SELECT login, date(created_at,'unixepoch','{int(tz_offset):+d} hours') as d, SUM(count) as c FROM gen_logs "
            f"WHERE status='success' AND login IN ({placeholders})"
        )
    else:
        sql_daily = (
            "SELECT login, date(created_at,'unixepoch') as d, SUM(count) as c FROM gen_logs "
            f"WHERE status='success' AND login IN ({placeholders})"
        )
    params_daily = list(logins)
    if date_from:
        sql_daily += " AND created_at>=?"
        params_daily.append(date_from)
    if date_to:
        sql_daily += " AND created_at<?"
        params_daily.append(date_to)
    sql_daily += " GROUP BY login, d"
    daily_rows = _db().execute(sql_daily, params_daily).fetchall()

    # 组装
    hourly_map: dict = {}
    for r in hourly_rows:
        hourly_map.setdefault(r["login"], {})[r["h"]] = r["c"]
    daily_map: dict = {}
    for r in daily_rows:
        daily_map.setdefault(r["login"], {})[r["d"]] = r["c"]

    items = []
    for i, r in enumerate(rows):
        login = r["login"]
        h_data = hourly_map.get(login, {})
        hourly = [h_data.get(h, 0) for h in range(24)]
        d_data = daily_map.get(login, {})
        peak_day = max(d_data, key=d_data.get) if d_data else ""
        peak_day_count = d_data.get(peak_day, 0) if peak_day else 0
        peak_hour = max(range(24), key=lambda x: hourly[x]) if sum(hourly) > 0 else -1
        peak_hour_count = hourly[peak_hour] if peak_hour >= 0 else 0
        items.append({
            "rank": i + 1,
            "login": login,
            "github_id": r["github_id"],
            "gen_count": r["gen_count"],
            "hourly": hourly,
            "peak_day": peak_day,
            "peak_day_count": peak_day_count,
            "peak_hour": peak_hour,
            "peak_hour_count": peak_hour_count,
        })

    return {"total": total_count, "items": items}


def find_gen_log_by_file_path(file_path: str) -> Optional[Dict]:
    rows = _db().execute("SELECT * FROM gen_logs WHERE file_paths LIKE ?", (f'%{file_path}%',)).fetchall()
    for r in rows:
        try:
            fps = json.loads(r["file_paths"] or "[]")
        except Exception:
            fps = []
        if file_path in fps:
            return dict(r)
    return None



def clean_gen_logs_by_file_paths(deleted_paths: set) -> int:
    """删除所有 file_paths 已全部被删的日志。"""
    all_logs = _db().execute("SELECT log_id, file_paths FROM gen_logs").fetchall()
    removed = 0
    with transaction() as conn:
        for r in all_logs:
            try:
                fps = set(json.loads(r["file_paths"] or "[]"))
            except Exception:
                fps = set()
            if fps and fps.issubset(deleted_paths):
                conn.execute("DELETE FROM gen_logs WHERE log_id=?", (r["log_id"],))
                removed += 1
    return removed

def get_all_gen_log_file_paths() -> set:
    """返回所有 gen_logs 中引用的文件路径集合，用于判断缩略图是否可清理。"""
    rows = _db().execute("SELECT file_paths FROM gen_logs").fetchall()
    paths = set()
    for r in rows:
        try:
            fps = json.loads(r["file_paths"] or "[]")
            paths.update(fps)
        except Exception:
            pass
    return paths


def load_gen_logs_path_user_map() -> Dict[str, tuple]:
    """返回 {file_path: (github_id, login)} 映射，用于缓存路径归属查找。"""
    result = {}
    try:
        rows = _db().execute(
            "SELECT github_id, login, file_paths FROM gen_logs WHERE file_paths != '[]'"
        ).fetchall()
        for r in rows:
            try:
                fps = json.loads(r["file_paths"] or "[]")
            except Exception:
                continue
            for fp in (fps if isinstance(fps, list) else []):
                fp = str(fp).replace("\\", "/")
                if fp and fp not in result:
                    result[fp] = (r["github_id"], r["login"] or r["github_id"])
    except Exception:
        pass
    return result


def query_gen_logs(login: str = "", date_from: float = 0, date_to: float = 0,
                   limit: int = 20, offset: int = 0, path: str = "") -> Tuple[List[Dict], int]:
    conditions = []
    params = []
    if login:
        conditions.append("login LIKE ?")
        params.append(f"%{login}%")
    if path:
        conditions.append("file_paths LIKE ?")
        params.append(f"%{path}%")
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
        with transaction() as conn:
            conn.execute("DELETE FROM gen_logs")
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
        with transaction() as conn:
            conn.execute(f"DELETE FROM gen_logs{where}", params)
    return removed

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


def query_deletion_logs_thumb(path: str = "", date_from: float = 0, date_to: float = 0) -> List[Dict]:
    conditions = []
    params = []
    if path:
        conditions.append("path=?")
        params.append(path)
    if date_from:
        conditions.append("deleted_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("deleted_at <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = _db().execute(f"SELECT * FROM deletion_logs{where}", params).fetchall()
    return [dict(r) for r in rows]


def clear_deletion_logs(path: str = "", date_from: float = 0, date_to: float = 0) -> int:
    conditions = []
    params = []
    if path:
        conditions.append("path=?")
        params.append(path)
    if date_from:
        conditions.append("deleted_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("deleted_at <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    r = _db().execute(f"DELETE FROM deletion_logs{where}", params)
    _db().commit()
    return r.rowcount


def get_empty_thumb_logs() -> List[Dict]:
    """查询 thumb_file 为空的删除记录。"""
    rows = _db().execute("SELECT * FROM deletion_logs WHERE thumb_file='' ORDER BY deleted_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_thumb_file(log_id: int, thumb_file: str) -> None:
    """更新删除记录的 thumb_file。"""
    _db().execute("UPDATE deletion_logs SET thumb_file=? WHERE id=?", (thumb_file, log_id))
    _db().commit()


def query_deletion_log(search: str = "", date_from: float = 0, date_to: float = 0,
                       limit: int = 60, offset: int = 0, path: str = "") -> Tuple[List[Dict], int]:
    conditions = []
    params = []
    if search:
        conditions.append("(deleted_by_login LIKE ? OR creator_login LIKE ? OR path LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s])
    if path:
        conditions.append("path LIKE ?")
        params.append(f"%{path}%")
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


def cleanup_resolved_and_orphan_reports() -> int:
    """GC 用：清理已处理的举报，返回删除数。"""
    removed = _db().execute("DELETE FROM reports WHERE status != 'pending'").rowcount
    if removed:
        _db().commit()
    return removed


def dismiss_reports_by_ids(report_ids: list) -> int:
    """按举报 id 批量忽略待处理举报。"""
    if not report_ids:
        return 0
    placeholders = ",".join(["?"] * len(report_ids))
    cur = _db().execute(
        f"UPDATE reports SET status='resolved', resolved_action='dismiss' WHERE status='pending' AND id IN ({placeholders})",
        report_ids)
    _db().commit()
    return cur.rowcount


def save_reports(reports: list) -> None:
    """兼容旧调用：全量重写 reports 表。"""
    with transaction(immediate=True) as conn:
        conn.execute("DELETE FROM reports")
        for report in reports or []:
            conn.execute(
                "INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?,?)",
                (report.get("id", ""), report.get("image_path", ""),
                 report.get("reporter_gid", ""), report.get("reporter_login", ""),
                 report.get("reason", ""), report.get("status", "pending"),
                 report.get("timestamp", 0), report.get("resolved_action", ""),
                 report.get("reporter_ip", "")))


def cleanup_orphan_pending_reports() -> list[dict]:
    """GC 用：返回所有待处理举报的记录（id / image_path），供调用方判断文件是否存在。"""
    rows = _db().execute("SELECT id, image_path FROM reports WHERE status='pending'").fetchall()
    return [dict(r) for r in rows]


def count_pending_reports(reporter_ip: str) -> int:
    """查询某 IP 的待处理举报数。"""
    r = _db().execute(
        "SELECT COUNT(*) as c FROM reports WHERE reporter_ip=? AND status='pending'",
        (reporter_ip,)).fetchone()
    return r["c"] if r else 0


def has_pending_report(image_path: str, reporter_ip: str) -> bool:
    """检查是否已举报过同一图片。"""
    r = _db().execute(
        "SELECT 1 FROM reports WHERE image_path=? AND reporter_ip=? AND status='pending'",
        (image_path, reporter_ip)).fetchone()
    return r is not None


def update_email_user_role(email: str, role: str) -> None:
    """同步角色到 email_users 表。"""
    _db().execute("UPDATE email_users SET role=? WHERE email=?", (role, email))
    _db().commit()


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
    with transaction() as conn:
        old = {r["path"] for r in conn.execute("SELECT path FROM featured").fetchall()}
        new_set = set(paths)
        for pth in old:
            if pth not in new_set:
                conn.execute("DELETE FROM featured WHERE path=?", (pth,))
        for i, pth in enumerate(paths):
            conn.execute("INSERT OR REPLACE INTO featured (path, sort_order) VALUES (?,?)", (pth, i))

def load_banned_ips() -> List[str]:
    rows = _db().execute("SELECT ip FROM banned_ips").fetchall()
    return [r["ip"] for r in rows]



def save_banned_ips(ips: List[str]) -> None:
    with transaction() as conn:
        old = {r["ip"] for r in conn.execute("SELECT ip FROM banned_ips").fetchall()}
        new_set = set(ips)
        for ip in old:
            if ip not in new_set:
                conn.execute("DELETE FROM banned_ips WHERE ip=?", (ip,))
        for ip in ips:
            if ip not in old:
                conn.execute("INSERT OR IGNORE INTO banned_ips VALUES (?)", (ip,))

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
    with transaction(immediate=True) as conn:
        conn.execute("DELETE FROM styles")
        for i, s in enumerate(styles):
            conn.execute(
                "INSERT INTO styles (name, tags, alias, thumbnail, sort_order) VALUES (?,?,?,?,?)",
                (s.get("name", ""), s.get("tags", ""), s.get("alias", ""), s.get("thumbnail", ""), i))


def load_characters() -> List[Dict]:
    rows = _db().execute("SELECT * FROM characters ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def save_characters(characters: List[Dict]) -> None:
    with transaction(immediate=True) as conn:
        conn.execute("DELETE FROM characters")
        for i, c in enumerate(characters):
            conn.execute(
                "INSERT INTO characters (name, tags, alias, thumbnail, sort_order) VALUES (?,?,?,?,?)",
                (c.get("name", ""), c.get("tags", ""), c.get("alias", ""), c.get("thumbnail", ""), i))


def load_resolutions() -> Dict[str, Any]:
    rows = _db().execute("SELECT * FROM resolutions ORDER BY sort_order").fetchall()
    return {"presets": [{"w": r["w"], "h": r["h"], "label": r["label"]} for r in rows]}


def save_resolutions(presets: List[Dict]) -> None:
    with transaction(immediate=True) as conn:
        conn.execute("DELETE FROM resolutions")
        for i, r in enumerate(presets):
            conn.execute(
                "INSERT INTO resolutions (w, h, label, sort_order) VALUES (?,?,?,?)",
                (r.get("w", 0), r.get("h", 0), r.get("label", ""), i))


def load_workflow_meta() -> List[Dict]:
    rows = _db().execute("SELECT * FROM workflow_meta ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def save_workflow_meta(meta: List[Dict]) -> None:
    with transaction(immediate=True) as conn:
        conn.execute("DELETE FROM workflow_meta")
        for i, m in enumerate(meta):
            conn.execute(
                "INSERT INTO workflow_meta (workflow, thumbnail, lora_link, display_name, sort_order) VALUES (?,?,?,?,?)",
                (m.get("workflow", ""), m.get("thumbnail", ""), m.get("lora_link", ""), m.get("display_name", ""), i))


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

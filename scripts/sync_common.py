"""SQLite → MySQL 同步公共逻辑。

正式同步入口：
- scripts/sync_sqlite_to_mysql.py  命令行
- scripts/sync_gui.py              图形界面

设计目标：
1. 表清单与 web/db/schema.py 保持一致。
2. 覆盖同步时安全清空 MySQL，避免外键删除顺序问题。
3. 兼容旧 SQLite 缺列，按 MySQL schema 补默认值。
4. 自动补齐 email_users 对应的 users(email:<邮箱>) 主表记录。
5. 同步后执行基础完整性检查。
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
ENV_PATH = ROOT_DIR / ".env"


def load_env() -> None:
    """加载项目 .env；不覆盖调用方已经设置的环境变量。"""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
sys.path.insert(0, str(WEB_DIR))

from db.schema import get_db, init_db, db_lock, transaction  # noqa: E402

LogFn = Callable[[str], None]

# 和 web/db/schema.py::TABLES 对齐；顺序按导入依赖调整：users/email_users 先导入，
# 补齐邮箱主用户后，再导入 sessions/user_images/notifications 等引用 users 的表。
TABLE_SPECS: list[dict[str, Any]] = [
    {
        "table": "users",
        "sql": "REPLACE INTO users (github_id,login,email,avatar_url,role,banned,banned_reason,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        "columns": ["github_id", "login", "email", "avatar_url", "role", "banned", "banned_reason", "created_at"],
    },
    {
        "table": "email_users",
        "sql": "REPLACE INTO email_users (email,password_hash,role,banned,banned_reason,created_at,verified,verify_token,totp_secret,totp_enabled,login_fails,login_fail_time,invite_code) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        "columns": ["email", "password_hash", "role", "banned", "banned_reason", "created_at", "verified", "verify_token", "totp_secret", "totp_enabled", "login_fails", "login_fail_time", "invite_code"],
    },
    {
        "table": "sessions",
        "sql": "REPLACE INTO sessions (token,github_id,expires_at,access_granted,claimed_key) VALUES (%s,%s,%s,%s,%s)",
        "columns": ["token", "github_id", "expires_at", "access_granted", "claimed_key"],
        "fk_user_column": "github_id",
    },
    {
        "table": "access_keys",
        "sql": "REPLACE INTO access_keys (`key`,used_by,created_at,disabled_at,expires_at,max_uses,used_count) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        "columns": ["key", "used_by", "created_at", "disabled_at", "expires_at", "max_uses", "used_count"],
    },
    {
        "table": "user_images",
        "sql": "INSERT IGNORE INTO user_images (github_id,path,prompt,time) VALUES (%s,%s,%s,%s)",
        "columns": ["github_id", "path", "prompt", "time"],
        "fk_user_column": "github_id",
    },
    {
        "table": "deleted_images",
        "sql": "REPLACE INTO deleted_images (github_id,path,marked_at) VALUES (%s,%s,%s)",
        "columns": ["github_id", "path", "marked_at"],
    },
    {
        "table": "gen_logs",
        "sql": "REPLACE INTO gen_logs (log_id,github_id,login,prompt,negative_prompt,workflow,count,status,client_ip,created_at,file_paths,error_reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        "columns": ["log_id", "github_id", "login", "prompt", "negative_prompt", "workflow", "count", "status", "client_ip", "created_at", "file_paths", "error_reason"],
    },
    {
        "table": "deletion_logs",
        "sql": "INSERT INTO deletion_logs (path,thumb_file,deleted_by_gid,deleted_by_login,deleted_at,creator_ip,creator_gid,creator_login) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        "columns": ["path", "thumb_file", "deleted_by_gid", "deleted_by_login", "deleted_at", "creator_ip", "creator_gid", "creator_login"],
    },
    {
        "table": "queue_items",
        "sql": "INSERT INTO queue_items (github_id,login,workflow,client_ip,status,created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        "columns": ["github_id", "login", "workflow", "client_ip", "status", "created_at"],
    },
    {
        "table": "reports",
        "sql": "REPLACE INTO reports (id,image_path,reporter_gid,reporter_login,reason,status,timestamp,resolved_action,reporter_ip) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        "columns": ["id", "image_path", "reporter_gid", "reporter_login", "reason", "status", "timestamp", "resolved_action", "reporter_ip"],
    },
    {
        "table": "config",
        "sql": "REPLACE INTO config (section,`key`,value) VALUES (%s,%s,%s)",
        "columns": ["section", "key", "value"],
    },
    {
        "table": "styles",
        "sql": "INSERT INTO styles (name,tags,alias,thumbnail,sort_order) VALUES (%s,%s,%s,%s,%s)",
        "columns": ["name", "tags", "alias", "thumbnail", "sort_order"],
    },
    {
        "table": "characters",
        "sql": "INSERT INTO characters (name,tags,alias,thumbnail,sort_order) VALUES (%s,%s,%s,%s,%s)",
        "columns": ["name", "tags", "alias", "thumbnail", "sort_order"],
    },
    {
        "table": "resolutions",
        "sql": "INSERT INTO resolutions (w,h,label,sort_order) VALUES (%s,%s,%s,%s)",
        "columns": ["w", "h", "label", "sort_order"],
    },
    {
        "table": "workflow_meta",
        "sql": "INSERT INTO workflow_meta (workflow,thumbnail,lora_link,display_name,sort_order) VALUES (%s,%s,%s,%s,%s)",
        "columns": ["workflow", "thumbnail", "lora_link", "display_name", "sort_order"],
    },
    {
        "table": "notifications",
        "sql": "INSERT INTO notifications (github_id,message,created_at,`read`) VALUES (%s,%s,%s,%s)",
        "columns": ["github_id", "message", "created_at", "read"],
        "fk_user_column": "github_id",
    },
    {
        "table": "featured",
        "sql": "REPLACE INTO featured (path,sort_order) VALUES (%s,%s)",
        "columns": ["path", "sort_order"],
    },
    {
        "table": "banned_ips",
        "sql": "INSERT IGNORE INTO banned_ips (ip) VALUES (%s)",
        "columns": ["ip"],
    },
    {
        "table": "creator_ips",
        "sql": "REPLACE INTO creator_ips (path,ip) VALUES (%s,%s)",
        "columns": ["path", "ip"],
    },
    {
        "table": "kv_state",
        "sql": "REPLACE INTO kv_state (`key`,value) VALUES (%s,%s)",
        "columns": ["key", "value"],
    },
    {
        "table": "gc_logs",
        "sql": "INSERT INTO gc_logs (timestamp,duration,cleaned,backup_dir) VALUES (%s,%s,%s,%s)",
        "columns": ["timestamp", "duration", "cleaned", "backup_dir"],
    },
    {
        "table": "invite_codes",
        "sql": "REPLACE INTO invite_codes (code,used_count,max_uses,created_at) VALUES (%s,%s,%s,%s)",
        "columns": ["code", "used_count", "max_uses", "created_at"],
    },
    {
        "table": "password_resets",
        "sql": "REPLACE INTO password_resets (email,token,expires_at) VALUES (%s,%s,%s)",
        "columns": ["email", "token", "expires_at"],
    },
    {
        "table": "email_logs",
        "sql": "INSERT INTO email_logs (recipient,subject,status,error,created_at) VALUES (%s,%s,%s,%s,%s)",
        "columns": ["recipient", "subject", "status", "error", "created_at"],
    },
]

TABLE_NAMES = [spec["table"] for spec in TABLE_SPECS]

NUMERIC_DEFAULTS = {
    "banned": 0,
    "created_at": 0,
    "expires_at": 0,
    "access_granted": 0,
    "disabled_at": 0,
    "max_uses": 0,
    "used_count": 0,
    "time": 0,
    "marked_at": 0,
    "count": 0,
    "deleted_at": 0,
    "timestamp": 0,
    "sort_order": 0,
    "w": 0,
    "h": 0,
    "read": 0,
    "duration": 0,
    "verified": 1,
    "totp_enabled": 0,
    "login_fails": 0,
    "login_fail_time": 0,
}

COLUMN_DEFAULTS = {
    "role": "user",
    "status": "waiting",
    "file_paths": "[]",
    "cleaned": "{}",
    "error": "",
    "error_reason": "",
    "claimed_key": "",
    "banned_reason": "",
    "avatar_url": "",
    "password_hash": "",
    "verify_token": "",
    "totp_secret": "",
    "invite_code": "",
    **NUMERIC_DEFAULTS,
}


def default_for(column: str) -> Any:
    return COLUMN_DEFAULTS.get(column, "")


def row_keys(row: sqlite3.Row) -> set[str]:
    return set(row.keys())


def value_for(row: sqlite3.Row, column: str) -> Any:
    if column not in row_keys(row):
        return default_for(column)
    value = row[column]
    if value is None:
        return default_for(column)
    return value


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def fetch_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if not table_exists(conn, table):
        raise sqlite3.OperationalError(f"no such table: {table}")
    return conn.execute(f"SELECT * FROM {table}").fetchall()


def create_readonly_snapshot(sqlite_path: Path, log: LogFn) -> tuple[tempfile.TemporaryDirectory, Path]:
    """只读复制 SQLite 快照，避免同步工具写入老项目数据库/WAL。"""
    tmp = tempfile.TemporaryDirectory(prefix="ndi-sqlite-snapshot-")
    snapshot = Path(tmp.name) / "natureDrawImage.snapshot.db"
    uri = "file:" + sqlite_path.as_posix() + "?mode=ro"
    log("📋 创建 SQLite 只读快照...")
    src_conn = sqlite3.connect(uri, uri=True)
    dst_conn = sqlite3.connect(str(snapshot))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return tmp, snapshot


def clear_mysql_tables(mysql, log: LogFn) -> None:
    """覆盖同步前清空表；临时关闭外键检查，避免删除顺序导致失败。"""
    log("\n🔄 清空 MySQL 现有数据...")
    try:
        mysql.execute("SET FOREIGN_KEY_CHECKS=0")
        for table_name in reversed(TABLE_NAMES):
            mysql.execute(f"DELETE FROM {table_name}")
        mysql.commit()
        log(f"   已清空 {len(TABLE_NAMES)} 张表")
    except Exception:
        mysql.rollback()
        raise
    finally:
        try:
            mysql.execute("SET FOREIGN_KEY_CHECKS=1")
            mysql.commit()
        except Exception as exc:
            log(f"⚠ 重新启用 FOREIGN_KEY_CHECKS 失败: {type(exc).__name__}: {exc}")


def source_user_ids(sl: sqlite3.Connection) -> set[str]:
    ids: set[str] = set()
    if table_exists(sl, "users"):
        for row in sl.execute("SELECT github_id FROM users").fetchall():
            gid = row["github_id"]
            if gid:
                ids.add(str(gid))
    if table_exists(sl, "email_users"):
        for row in sl.execute("SELECT email FROM email_users").fetchall():
            email = str(row["email"] or "").strip().lower()
            if email:
                ids.add("email:" + email)
    return ids


def ensure_main_email_users(sl: sqlite3.Connection, db, log: LogFn) -> int:
    """把 email_users 补齐到 users，避免 sessions 外键和登录写 session 失败。

    注意：旧库里可能出现 users.role='admin' 但 email_users.role='user' 的情况。
    补齐时必须保留主 users 表里的管理员身份，不能被 email_users 降权。
    """
    if not table_exists(sl, "email_users"):
        return 0
    source_main_roles: dict[str, str] = {}
    if table_exists(sl, "users"):
        for user_row in sl.execute("SELECT github_id, role FROM users").fetchall():
            gid = str(user_row["github_id"] or "")
            if gid:
                source_main_roles[gid] = str(user_row["role"] or "user")

    rows = fetch_rows(sl, "email_users")
    count = 0
    promoted = 0
    for row in rows:
        email = str(value_for(row, "email") or "").strip().lower()
        if not email:
            continue
        uid = "email:" + email
        email_role = str(value_for(row, "role") or "user")
        source_main_role = source_main_roles.get(uid, "")
        final_role = "admin" if email_role == "admin" or source_main_role == "admin" else "user"
        db.execute(
            """
            INSERT INTO users (github_id,login,email,avatar_url,role,banned,banned_reason,created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                login=VALUES(login),
                email=VALUES(email),
                role=IF(role='admin' OR VALUES(role)='admin', 'admin', VALUES(role)),
                banned=VALUES(banned),
                banned_reason=VALUES(banned_reason)
            """,
            (
                uid,
                email.split("@")[0],
                email,
                "",
                final_role,
                value_for(row, "banned"),
                value_for(row, "banned_reason"),
                value_for(row, "created_at"),
            ),
        )
        if final_role == "admin" and email_role != "admin":
            db.execute("UPDATE email_users SET role='admin' WHERE email=%s", (email,))
            promoted += 1
        count += 1
    if count:
        msg = f"  🔗 email_users → users 补齐: {count} 条"
        if promoted:
            msg += f"，保留/同步管理员角色 {promoted} 条"
        log(msg)
    return count


def iter_values(
    rows: Iterable[sqlite3.Row],
    columns: list[str],
    fk_user_column: str | None,
    valid_user_ids: set[str],
) -> tuple[list[tuple[Any, ...]], int]:
    values: list[tuple[Any, ...]] = []
    skipped = 0
    for row in rows:
        if fk_user_column:
            gid = str(value_for(row, fk_user_column) or "")
            if gid and gid not in valid_user_ids:
                skipped += 1
                continue
        values.append(tuple(value_for(row, column) for column in columns))
    return values, skipped


def run_integrity_checks(log: LogFn) -> dict[str, int]:
    db = get_db()
    checks = {
        "orphan_sessions": "SELECT COUNT(*) AS c FROM sessions s LEFT JOIN users u ON u.github_id=s.github_id WHERE u.github_id IS NULL",
        "orphan_user_images": "SELECT COUNT(*) AS c FROM user_images i LEFT JOIN users u ON u.github_id=i.github_id WHERE u.github_id IS NULL",
        "orphan_notifications": "SELECT COUNT(*) AS c FROM notifications n LEFT JOIN users u ON u.github_id=n.github_id WHERE u.github_id IS NULL",
        "missing_email_main_users": "SELECT COUNT(*) AS c FROM email_users eu LEFT JOIN users u ON u.github_id=CONCAT('email:', eu.email) WHERE u.github_id IS NULL",
    }
    result: dict[str, int] = {}
    for name, sql in checks.items():
        row = db.execute(sql).fetchone()
        result[name] = int(row["c"] if row else 0)
    bad = {k: v for k, v in result.items() if v}
    if bad:
        log("⚠ 完整性检查发现问题: " + ", ".join(f"{k}={v}" for k, v in bad.items()))
    else:
        log("✅ 完整性检查通过：无孤儿外键，邮箱主用户已补齐")
    return result


def _sync_sqlite_file_to_mysql(sqlite_path: Path, *, truncate: bool, log: LogFn) -> dict[str, Any]:
    sl = sqlite3.connect(str(sqlite_path))
    sl.row_factory = sqlite3.Row
    try:
        log(f"📦 SQLite: {sqlite_path} ({sqlite_path.stat().st_size // 1024} KB)")
        log("🐬 连接 MySQL...")
        init_db()
        mysql = get_db()

        stats: dict[str, Any] = {"tables": {}, "total": 0, "skipped_fk": 0, "missing_tables": []}
        valid_user_ids = source_user_ids(sl)

        with db_lock():
            if truncate:
                clear_mysql_tables(mysql, log)
            with transaction() as db:
                for spec in TABLE_SPECS:
                    table_name = spec["table"]
                    try:
                        rows = fetch_rows(sl, table_name)
                    except sqlite3.OperationalError as exc:
                        stats["missing_tables"].append(table_name)
                        log(f"  ⏭️  {table_name}: 跳过 ({exc})")
                        continue

                    values, skipped = iter_values(
                        rows,
                        spec["columns"],
                        spec.get("fk_user_column"),
                        valid_user_ids,
                    )
                    if values:
                        db.executemany(spec["sql"], values)
                    stats["tables"][table_name] = len(values)
                    stats["total"] += len(values)
                    stats["skipped_fk"] += skipped
                    suffix = f"，跳过孤儿外键 {skipped} 条" if skipped else ""
                    log(f"  ✅ {table_name}: {len(values)} 条{suffix}")

                    if table_name == "email_users":
                        ensure_main_email_users(sl, db, log)
                        # 补齐后，后续 sessions/notifications 等允许引用邮箱用户。
                        valid_user_ids = source_user_ids(sl)

        stats["integrity"] = run_integrity_checks(log)
        log(f"\n✨ 同步完成！共写入 {stats['total']} 条记录到 MySQL")
        if stats["missing_tables"]:
            log("ℹ 源 SQLite 缺少表: " + ", ".join(stats["missing_tables"]))
        return stats
    finally:
        sl.close()


def sync_sqlite_to_mysql(sqlite_path: str | Path, *, truncate: bool = True, log: LogFn = print) -> dict[str, Any]:
    sqlite_path = Path(sqlite_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {sqlite_path}")

    tmp, snapshot = create_readonly_snapshot(sqlite_path, log)
    try:
        return _sync_sqlite_file_to_mysql(snapshot, truncate=truncate, log=log)
    finally:
        tmp.cleanup()


def preview_sqlite(sqlite_path: str | Path) -> list[tuple[str, int | str]]:
    sqlite_path = Path(sqlite_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {sqlite_path}")
    uri = "file:" + sqlite_path.as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        result: list[tuple[str, int | str]] = []
        for table in sorted(tables):
            try:
                count = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            except Exception:
                count = "?"
            result.append((table, count))
        return result
    finally:
        conn.close()

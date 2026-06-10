"""
SQLite 数据库 Schema & 初始化

用法:
    from db.schema import get_db, init_db, migrate_from_json

    init_db()                          # 创建/升级表结构
    db = get_db()                      # 获取连接

所有 JSON 文件迁移到 SQLite 后，app.py 中的 _load_json/_save_json 可逐步替换为
db.execute() / db.fetchone() / db.fetchall() 操作。
"""

import sqlite3
import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "natureDrawImage.db"

# ── 连接池（单连接，SQLite 串行模式足够） ──
_conn: Optional[sqlite3.Connection] = None


def get_db() -> sqlite3.Connection:
    """获取数据库连接（自动创建）。"""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


# ═══════════════════════════════════════════
# Schema DDL
# ═══════════════════════════════════════════

SCHEMA = [
    # ── 用户 ──
    """
    CREATE TABLE IF NOT EXISTS users (
        github_id    TEXT PRIMARY KEY,
        login        TEXT NOT NULL DEFAULT '',
        email        TEXT NOT NULL DEFAULT '',
        avatar_url   TEXT NOT NULL DEFAULT '',
        role         TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin','user')),
        banned       INTEGER NOT NULL DEFAULT 0,
        banned_reason TEXT NOT NULL DEFAULT '',
        created_at   REAL NOT NULL DEFAULT 0
    )
    """,

    # ── 会话 ──
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token          TEXT PRIMARY KEY,
        github_id      TEXT NOT NULL,
        expires_at     REAL NOT NULL DEFAULT 0,
        access_granted INTEGER NOT NULL DEFAULT 0,
        claimed_key    TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_github_id ON sessions(github_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)",

    # ── 访问密钥 ──
    """
    CREATE TABLE IF NOT EXISTS access_keys (
        key          TEXT PRIMARY KEY,
        used_by      TEXT NOT NULL DEFAULT '',
        created_at   REAL NOT NULL DEFAULT 0,
        disabled_at  REAL NOT NULL DEFAULT 0,
        expires_at   REAL NOT NULL DEFAULT 0,
        max_uses     INTEGER NOT NULL DEFAULT 0,
        used_count   INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_access_keys_used_by ON access_keys(used_by)",

    # ── 用户图片 ──
    """
    CREATE TABLE IF NOT EXISTS user_images (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id TEXT NOT NULL,
        path      TEXT NOT NULL,
        prompt    TEXT NOT NULL DEFAULT '',
        time      REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_images_github_id ON user_images(github_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_images_path ON user_images(path)",

    # ── 删除标记 ──
    """
    CREATE TABLE IF NOT EXISTS deleted_images (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id TEXT NOT NULL,
        path      TEXT NOT NULL,
        marked_at REAL NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deleted_images_path ON deleted_images(path)",
    "CREATE INDEX IF NOT EXISTS idx_deleted_images_github ON deleted_images(github_id)",

    # ── 生图日志 ──
    """
    CREATE TABLE IF NOT EXISTS gen_logs (
        log_id           TEXT PRIMARY KEY,
        github_id        TEXT NOT NULL DEFAULT '',
        login            TEXT NOT NULL DEFAULT '',
        prompt           TEXT NOT NULL DEFAULT '',
        negative_prompt  TEXT NOT NULL DEFAULT '',
        workflow         TEXT NOT NULL DEFAULT '',
        count            INTEGER NOT NULL DEFAULT 0,
        status           TEXT NOT NULL DEFAULT 'success',
        client_ip        TEXT NOT NULL DEFAULT '',
        created_at       REAL NOT NULL DEFAULT 0,
        file_paths       TEXT NOT NULL DEFAULT '[]'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gen_logs_created ON gen_logs(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_gen_logs_github ON gen_logs(github_id)",

    # ── 删除日志（回收站） ──
    """
    CREATE TABLE IF NOT EXISTS deletion_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        path            TEXT NOT NULL DEFAULT '',
        thumb_file      TEXT NOT NULL DEFAULT '',
        deleted_by_gid  TEXT NOT NULL DEFAULT '',
        deleted_by_login TEXT NOT NULL DEFAULT '',
        deleted_at      REAL NOT NULL DEFAULT 0,
        creator_ip      TEXT NOT NULL DEFAULT '',
        creator_gid     TEXT NOT NULL DEFAULT '',
        creator_login   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deletion_logs_deleted_at ON deletion_logs(deleted_at)",
    "CREATE INDEX IF NOT EXISTS idx_deletion_logs_path ON deletion_logs(path)",

    # ── 队列 ──
    """
    CREATE TABLE IF NOT EXISTS queue_items (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id   TEXT NOT NULL DEFAULT '',
        login       TEXT NOT NULL DEFAULT '',
        workflow    TEXT NOT NULL DEFAULT '',
        client_ip   TEXT NOT NULL DEFAULT '',
        status      TEXT NOT NULL DEFAULT 'waiting',
        created_at  REAL NOT NULL DEFAULT 0
    )
    """,

    # ── 举报 ──
    """
    CREATE TABLE IF NOT EXISTS reports (
        id               TEXT PRIMARY KEY,
        image_path       TEXT NOT NULL DEFAULT '',
        reporter_gid     TEXT NOT NULL DEFAULT '',
        reporter_login   TEXT NOT NULL DEFAULT '',
        reason           TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'pending',
        timestamp        REAL NOT NULL DEFAULT 0,
        resolved_action  TEXT NOT NULL DEFAULT '',
        reporter_ip      TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)",
    "ALTER TABLE reports ADD COLUMN reporter_ip TEXT NOT NULL DEFAULT ''",

    # ── 配置（KV 存储，替代所有 config JSON） ──
    """
    CREATE TABLE IF NOT EXISTS config (
        section TEXT NOT NULL,
        key     TEXT NOT NULL,
        value   TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (section, key)
    )
    """,

    # ── 画风 ──
    """
    CREATE TABLE IF NOT EXISTS styles (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        name      TEXT NOT NULL,
        tags      TEXT NOT NULL DEFAULT '',
        alias     TEXT NOT NULL DEFAULT '',
        thumbnail TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── 分辨率预设 ──
    """
    CREATE TABLE IF NOT EXISTS resolutions (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        w         INTEGER NOT NULL,
        h         INTEGER NOT NULL,
        label     TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── 工作流元数据 ──
    """
    CREATE TABLE IF NOT EXISTS workflow_meta (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow     TEXT NOT NULL,
        thumbnail    TEXT NOT NULL DEFAULT '',
        lora_link    TEXT NOT NULL DEFAULT '',
        display_name TEXT NOT NULL DEFAULT '',
        sort_order   INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── 用户通知 ──
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id   TEXT NOT NULL,
        message     TEXT NOT NULL DEFAULT '',
        created_at  REAL NOT NULL DEFAULT 0,
        read        INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notifications_github ON notifications(github_id, read)",

    # ── 精选 ──
    """
    CREATE TABLE IF NOT EXISTS featured (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        path      TEXT NOT NULL UNIQUE,
        sort_order INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── 封禁 IP ──
    """
    CREATE TABLE IF NOT EXISTS banned_ips (
        ip TEXT PRIMARY KEY
    )
    """,

    # ── 生图者 IP 映射 ──
    """
    CREATE TABLE IF NOT EXISTS creator_ips (
        path TEXT PRIMARY KEY,
        ip   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_creator_ips_ip ON creator_ips(ip)",

    # ── KV 状态存储 ──
    """
    CREATE TABLE IF NOT EXISTS kv_state (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    )
    """,

    # ── GC 日志 ──
    """
    CREATE TABLE IF NOT EXISTS gc_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   REAL NOT NULL,
        duration    REAL NOT NULL DEFAULT 0,
        cleaned     TEXT NOT NULL DEFAULT '{}',
        backup_dir  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gc_logs_timestamp ON gc_logs(timestamp)",

    # ── 邮箱用户 ──
    """
    CREATE TABLE IF NOT EXISTS email_users (
        email          TEXT PRIMARY KEY,
        password_hash  TEXT NOT NULL DEFAULT '',
        role           TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin','user')),
        banned         INTEGER NOT NULL DEFAULT 0,
        banned_reason  TEXT NOT NULL DEFAULT '',
        created_at     REAL NOT NULL DEFAULT 0,
        verified       INTEGER NOT NULL DEFAULT 1,
        verify_token   TEXT NOT NULL DEFAULT '',
        totp_secret    TEXT NOT NULL DEFAULT '',
        totp_enabled   INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── 邀请码 ──
    """
    CREATE TABLE IF NOT EXISTS invite_codes (
        code        TEXT PRIMARY KEY,
        used_count  INTEGER NOT NULL DEFAULT 0,
        max_uses   INTEGER NOT NULL DEFAULT 1,
        created_at  REAL NOT NULL DEFAULT 0
    )
    """,

    # ── 密码重置 ──
    """
    CREATE TABLE IF NOT EXISTS password_resets (
        email       TEXT PRIMARY KEY,
        token       TEXT NOT NULL DEFAULT '',
        expires_at  REAL NOT NULL DEFAULT 0
    )
    """,

    # ── 发信日志 ──
    """
    CREATE TABLE IF NOT EXISTS email_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient   TEXT NOT NULL DEFAULT '',
        subject     TEXT NOT NULL DEFAULT '',
        status      TEXT NOT NULL DEFAULT 'ok',
        error       TEXT NOT NULL DEFAULT '',
        created_at  REAL NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_email_logs_created ON email_logs(created_at)",
]


# ═══════════════════════════════════════════
# 初始化 & 迁移
# ═══════════════════════════════════════════

def init_db():
    """创建/升级表结构。"""
    db = get_db()
    for sql in SCHEMA:
        try:
            db.execute(sql)
        except sqlite3.OperationalError as e:
            print(f"[schema] 跳过: {e}")
    db.commit()
    # 完整性检查
    try:
        result = db.execute("PRAGMA integrity_check").fetchone()
        if result and result[0] == "ok":
            print(f"[schema] 数据库就绪 (完整性检查通过): {DB_PATH}")
        else:
            print(f"[schema] 警告: 数据库可能损坏 - {result[0] if result else 'unknown'}")
    except Exception:
        print(f"[schema] 数据库就绪: {DB_PATH}")


def migrate_from_json(data_dir: Path):
    """
    从 JSON/TXT 文件迁移数据到 SQLite。
    调用时机：首次运行时，如果 DB 为空则执行。

    Args:
        data_dir: web/ 目录路径（包含所有 JSON 文件）
    """
    db = get_db()
    # 检查是否已迁移
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        print("[migrate] 已有数据，跳过迁移")
        return

    print("[migrate] 开始从 JSON 迁移...")

    # ── 用户 ──
    _import_json(db, data_dir / "users.json", "users",
                 keys=["github_id", "login", "email", "avatar_url", "role", "banned", "banned_reason", "created_at"],
                 defaults={"role": "user", "banned": 0, "banned_reason": "", "created_at": 0})

    # ── 会话 ──
    _import_json(db, data_dir / "sessions.json", "sessions",
                 keys=["token", "github_id", "expires_at", "access_granted", "claimed_key"],
                 defaults={"access_granted": 0, "claimed_key": ""})

    # ── 访问密钥 ──
    ak = _load_json(data_dir / "access_keys.json").get("keys", {})
    for k, v in ak.items():
        db.execute(
            "INSERT INTO access_keys VALUES (?,?,?,?,?,?,?)",
            (k, v.get("used_by", ""), v.get("created_at", 0),
             v.get("disabled_at", 0), v.get("expires_at", 0),
             v.get("max_uses", 0), v.get("used_count", 0))
        )

    # ── 用户图片 ──
    ui = _load_json(data_dir / "user_images.json")
    for gid, entries in ui.items():
        for e in entries:
            db.execute(
                "INSERT INTO user_images (github_id, path, prompt, time) VALUES (?,?,?,?)",
                (gid, e.get("path", ""), e.get("prompt", ""), e.get("time", 0))
            )

    # ── 删除标记 ──
    di = _load_json(data_dir / "deleted_images.json")
    for gid, paths in di.items():
        for p in paths:
            db.execute(
                "INSERT INTO deleted_images (github_id, path) VALUES (?,?)",
                (gid, p)
            )

    # ── 生图日志 ──
    gl = _load_json(data_dir / "gen_log.json")
    for lid, e in gl.items():
        fps = json.dumps(e.get("file_paths", []))
        db.execute(
            "INSERT INTO gen_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (lid, e.get("github_id", ""), e.get("login", ""),
             e.get("prompt", ""), e.get("negative_prompt", ""),
             e.get("workflow", ""), e.get("count", 0),
             e.get("status", "success"), e.get("client_ip", ""),
             e.get("created_at", 0), fps)
        )

    # ── 删除日志 ──
    dl = _load_json_list(data_dir / "deletion_log.json")
    for e in dl:
        db.execute(
            "INSERT INTO deletion_logs (path,thumb_file,deleted_by_gid,deleted_by_login,deleted_at,creator_ip,creator_gid,creator_login) VALUES (?,?,?,?,?,?,?,?)",
            (e.get("path", ""), e.get("thumb_file", ""),
             e.get("deleted_by_github_id", e.get("github_id", "")),
             e.get("deleted_by_login", e.get("login", "")),
             e.get("deleted_at", e.get("time", 0)),
             e.get("creator_ip", ""), e.get("creator_github_id", ""), e.get("creator_login", ""))
        )

    # ── 配置 ──
    for fname, section in [
        ("limits.json", "limits"),
        ("llm_config.json", "llm"),
        ("announcement.json", "announcement"),
        ("maintenance.json", "maintenance"),
        ("custom_head.json", "custom_head"),
    ]:
        data = _load_json(data_dir / fname)
        for k, v in data.items():
            db.execute("INSERT OR REPLACE INTO config VALUES (?,?,?)",
                       (section, k, json.dumps(v) if not isinstance(v, str) else v))

    # ── 画风 ──
    styles = _load_json_list(data_dir / "styles.json")
    for i, s in enumerate(styles):
        db.execute(
            "INSERT INTO styles (name, tags, alias, thumbnail, sort_order) VALUES (?,?,?,?,?)",
            (s.get("name", ""), s.get("tags", ""), s.get("alias", ""), s.get("thumbnail", ""), i)
        )

    # ── 分辨率 ──
    res = _load_json(data_dir / "resolutions.json").get("presets", [])
    for i, r in enumerate(res):
        db.execute(
            "INSERT INTO resolutions (w, h, label, sort_order) VALUES (?,?,?,?)",
            (r.get("w", 0), r.get("h", 0), r.get("label", ""), i)
        )

    # ── 工作流元数据 ──
    wm = _load_json_list(data_dir / "workflow_meta.json")
    for i, m in enumerate(wm):
        db.execute(
            "INSERT INTO workflow_meta (workflow, thumbnail, lora_link, display_name, sort_order) VALUES (?,?,?,?,?)",
            (m.get("workflow", ""), m.get("thumbnail", ""), m.get("lora_link", ""), m.get("display_name", ""), i)
        )

    # ── 用户通知 ──
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        github_id   TEXT NOT NULL,
        message     TEXT NOT NULL DEFAULT '',
        created_at  REAL NOT NULL DEFAULT 0,
        read        INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notifications_github ON notifications(github_id, read)",

    # ── 精选 ──
    ft = _load_txt_lines(data_dir / "featured.txt")
    for i, p in enumerate(ft):
        db.execute("INSERT INTO featured (path, sort_order) VALUES (?,?)", (p, i))

    # ── 封禁 IP ──
    for ip in _load_txt_lines(data_dir / "banned_ips.txt"):
        db.execute("INSERT OR IGNORE INTO banned_ips VALUES (?)", (ip,))

    # ── 生图者 IP ──
    for line in _load_txt_lines(data_dir / "creator_ips.txt"):
        if "\t" in line:
            path, ip = line.split("\t", 1)
            db.execute("INSERT OR REPLACE INTO creator_ips VALUES (?,?)", (path.strip(), ip.strip()))

    db.commit()
    print("[migrate] 迁移完成")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _load_json(path: Path) -> dict:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _load_json_list(path: Path) -> list:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _load_txt_lines(path: Path) -> List[str]:
    try:
        if path.is_file():
            return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        pass
    return []


def _import_json(db, path: Path, table: str, keys: List[str], defaults: dict):
    """通用 JSON 导入：dict-of-dict 或 list-of-dict。"""
    try:
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            rows = []
            for pk, vals in data.items():
                if isinstance(vals, dict):
                    row = {}
                    for k in keys:
                        val = vals.get(k, defaults.get(k, ""))
                        if k == "token":
                            val = pk
                        row[k] = val
                    # Set primary key if it's the dict key
                    if keys[0] not in row or not row[keys[0]]:
                        row[keys[0]] = pk
                    rows.append(row)
            if rows:
                cols = ", ".join(keys)
                placeholders = ", ".join(["?"] * len(keys))
                db.executemany(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
                               [tuple(r.get(k, defaults.get(k, "")) for k in keys) for r in rows])
    except Exception as e:
        print(f"[migrate] 导入 {table} 失败: {e}")


# ═══════════════════════════════════════════
# 配置读写（替代 limits.json / llm_config.json 等）
# ═══════════════════════════════════════════

def config_get(section: str, key: str, default: Any = None) -> Any:
    """读取配置项。"""
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE section=? AND key=?", (section, key)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return row[0]


def config_set(section: str, key: str, value: Any):
    """写入配置项。"""
    db = get_db()
    val = json.dumps(value) if not isinstance(value, str) else value
    db.execute("INSERT OR REPLACE INTO config VALUES (?,?,?)", (section, key, val))
    db.commit()


def config_get_section(section: str) -> Dict[str, Any]:
    """读取整个配置 section。"""
    db = get_db()
    rows = db.execute("SELECT key, value FROM config WHERE section=?", (section,)).fetchall()
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            result[r["key"]] = r["value"]
    return result

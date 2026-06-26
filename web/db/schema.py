"""
MySQL 数据库 Schema & 初始化

用法:
    from db.schema import get_db, init_db

    init_db()                          # 创建/升级表结构
    db = get_db()                      # 获取连接
"""

import pymysql
import pymysql.cursors
import json
import os
import time
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterator

# ── MySQL 连接配置（从环境变量读取，灵活适配各种部署环境） ──
_DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
_DB_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
_DB_USER = os.environ.get("MYSQL_USER", "root")
_DB_PASS = os.environ.get("MYSQL_PASSWORD", "")
_DB_NAME = os.environ.get("MYSQL_DATABASE", "natureDrawImage")
_DB_CHARSET = "utf8mb4"

DB_DIR = Path(__file__).parent

# ── 连接（单连接 + 全局可重入锁，与旧版 sqlite3 模式兼容） ──
_conn: Optional["LockedConnection"] = None
_db_lock = threading.RLock()
_mysqldump_path = None  # 启动时自动探测


def _find_mysqldump() -> str:
    """自动探测 mysqldump 路径，兼容各种部署场景。"""
    candidates = [
        "mysqldump",
        str(Path(__file__).parent.parent.parent / "mysql-8.0.28-winx64" / "bin" / "mysqldump.exe"),
        str(Path(__file__).parent.parent / "mysql-8.0.28-winx64" / "bin" / "mysqldump.exe"),
        "C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqldump.exe",
    ]
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "mysqldump"  # 最后尝试系统 PATH


class LockedConnection:
    """pymysql.Connection 的加锁包装，保留旧版 db.execute().fetchone() 接口。"""

    def __init__(self, conn: pymysql.Connection):
        self._conn = conn

    def _cursor(self):
        return self._conn.cursor()

    def execute(self, sql: str, params=None):
        with _db_lock:
            c = self._cursor()
            c.execute(sql, params)
            return c

    def executemany(self, sql: str, seq):
        with _db_lock:
            c = self._cursor()
            c.executemany(sql, seq)
            return c

    def executescript(self, sql: str):
        with _db_lock:
            c = self._cursor()
            for stmt in sql.split(";"):
                s = stmt.strip()
                if s:
                    c.execute(s)
            return c

    def commit(self):
        with _db_lock:
            return self._conn.commit()

    def rollback(self):
        with _db_lock:
            return self._conn.rollback()

    def backup(self, dst_path: str):
        """mysqldump 在线热备——不锁表、不阻塞读写。"""
        backup_database(dst_path)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def db_lock() -> threading.RLock:
    """返回数据库全局写锁。"""
    return _db_lock


@contextmanager
def transaction(immediate: bool = False) -> Iterator[LockedConnection]:
    """MySQL 写事务。immediate 参数向下兼容（MySQL 不需要 BEGIN IMMEDIATE）。"""
    with _db_lock:
        db = get_db()
        db.execute("START TRANSACTION")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def get_db() -> LockedConnection:
    """获取数据库连接（自动创建 + 连接存活检测）。"""
    global _conn, _mysqldump_path
    with _db_lock:
        if _conn is None:
            if _mysqldump_path is None:
                _mysqldump_path = _find_mysqldump()
            raw = pymysql.connect(
                host=_DB_HOST,
                port=_DB_PORT,
                user=_DB_USER,
                password=_DB_PASS,
                database=_DB_NAME,
                charset=_DB_CHARSET,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
            )
            _conn = LockedConnection(raw)
        else:
            try:
                _conn._conn.ping(reconnect=True)
            except Exception:
                raw = pymysql.connect(
                    host=_DB_HOST, port=_DB_PORT, user=_DB_USER,
                    password=_DB_PASS, database=_DB_NAME,
                    charset=_DB_CHARSET, cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False, connect_timeout=10,
                )
                _conn._conn = raw
        return _conn


def backup_database(dst_path: str):
    """mysqldump 在线热备，不阻塞读写。"""
    global _mysqldump_path
    if _mysqldump_path is None:
        _mysqldump_path = _find_mysqldump()
    cmd = [
        _mysqldump_path,
        "--single-transaction",
        "--quick",
        "-h", _DB_HOST,
        "-P", str(_DB_PORT),
        "-u", _DB_USER,
    ]
    if _DB_PASS:
        cmd.extend([f"-p{_DB_PASS}"])
    cmd.append(_DB_NAME)
    with open(dst_path, "w", encoding="utf-8") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=True, timeout=300)


# ═══════════════════════════════════════════
# Schema DDL（MySQL 语法，TEXT 列不加 DEFAULT）
# ═══════════════════════════════════════════

# 表清单，用于迁移检查
TABLES = [
    "users", "sessions", "access_keys", "user_images", "deleted_images",
    "gen_logs", "deletion_logs", "queue_items", "reports", "config",
    "styles", "characters", "resolutions", "workflow_meta", "notifications",
    "featured", "banned_ips", "creator_ips", "kv_state", "gc_logs",
    "email_users", "invite_codes", "password_resets", "email_logs",
]

SCHEMA = [
    # ── 用户 ──
    """
    CREATE TABLE IF NOT EXISTS users (
        github_id    VARCHAR(255) PRIMARY KEY,
        login        VARCHAR(255) NOT NULL DEFAULT '',
        email        VARCHAR(255) NOT NULL DEFAULT '',
        avatar_url   TEXT,
        role         VARCHAR(50) NOT NULL DEFAULT 'user',
        banned       INT NOT NULL DEFAULT 0,
        banned_reason TEXT,
        created_at   DOUBLE NOT NULL DEFAULT 0
    )
    """,

    # ── 会话 ──
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token          VARCHAR(255) PRIMARY KEY,
        github_id      VARCHAR(255) NOT NULL,
        expires_at     DOUBLE NOT NULL DEFAULT 0,
        access_granted INT NOT NULL DEFAULT 0,
        claimed_key    VARCHAR(255) NOT NULL DEFAULT '',
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_sessions_github_id ON sessions(github_id)",
    "CREATE INDEX idx_sessions_expires ON sessions(expires_at)",

    # ── 访问密钥 ──
    """
    CREATE TABLE IF NOT EXISTS access_keys (
        `key`        VARCHAR(255) PRIMARY KEY,
        used_by      VARCHAR(255) NOT NULL DEFAULT '',
        created_at   DOUBLE NOT NULL DEFAULT 0,
        disabled_at  DOUBLE NOT NULL DEFAULT 0,
        expires_at   DOUBLE NOT NULL DEFAULT 0,
        max_uses     INT NOT NULL DEFAULT 0,
        used_count   INT NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX idx_access_keys_used_by ON access_keys(used_by)",

    # ── 用户图片 ──
    """
    CREATE TABLE IF NOT EXISTS user_images (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        github_id VARCHAR(255) NOT NULL,
        path      TEXT,
        prompt    TEXT,
        time      DOUBLE NOT NULL DEFAULT 0,
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_user_images_github_id ON user_images(github_id)",
    "CREATE INDEX idx_user_images_path ON user_images(path(255))",

    # ── 删除标记 ──
    """
    CREATE TABLE IF NOT EXISTS deleted_images (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        github_id VARCHAR(255) NOT NULL,
        path      TEXT,
        marked_at DOUBLE NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX idx_deleted_images_path ON deleted_images(path(255))",
    "CREATE INDEX idx_deleted_images_github ON deleted_images(github_id)",
    "CREATE UNIQUE INDEX idx_deleted_images_unique ON deleted_images(github_id, path(255))",

    # ── 生图日志 ──
    """
    CREATE TABLE IF NOT EXISTS gen_logs (
        log_id           VARCHAR(255) PRIMARY KEY,
        github_id        VARCHAR(255) NOT NULL DEFAULT '',
        login            VARCHAR(255) NOT NULL DEFAULT '',
        prompt           TEXT,
        negative_prompt  TEXT,
        workflow         TEXT,
        count            INT NOT NULL DEFAULT 0,
        status           VARCHAR(50) NOT NULL DEFAULT 'success',
        client_ip        VARCHAR(50) NOT NULL DEFAULT '',
        created_at       DOUBLE NOT NULL DEFAULT 0,
        file_paths       TEXT,
        error_reason     TEXT
    )
    """,
    "CREATE INDEX idx_gen_logs_created ON gen_logs(created_at)",
    "CREATE INDEX idx_gen_logs_github ON gen_logs(github_id)",

    # ── 删除日志（回收站） ──
    """
    CREATE TABLE IF NOT EXISTS deletion_logs (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        path            TEXT,
        thumb_file      VARCHAR(255) NOT NULL DEFAULT '',
        deleted_by_gid  VARCHAR(255) NOT NULL DEFAULT '',
        deleted_by_login VARCHAR(255) NOT NULL DEFAULT '',
        deleted_at      DOUBLE NOT NULL DEFAULT 0,
        creator_ip      VARCHAR(50) NOT NULL DEFAULT '',
        creator_gid     VARCHAR(255) NOT NULL DEFAULT '',
        creator_login   VARCHAR(255) NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX idx_deletion_logs_deleted_at ON deletion_logs(deleted_at)",
    "CREATE INDEX idx_deletion_logs_path ON deletion_logs(path(255))",

    # ── 队列 ──
    """
    CREATE TABLE IF NOT EXISTS queue_items (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        github_id   VARCHAR(255) NOT NULL DEFAULT '',
        login       VARCHAR(255) NOT NULL DEFAULT '',
        workflow    TEXT,
        client_ip   VARCHAR(50) NOT NULL DEFAULT '',
        status      VARCHAR(50) NOT NULL DEFAULT 'waiting',
        created_at  DOUBLE NOT NULL DEFAULT 0
    )
    """,

    # ── 举报 ──
    """
    CREATE TABLE IF NOT EXISTS reports (
        id               VARCHAR(255) PRIMARY KEY,
        image_path       TEXT,
        reporter_gid     VARCHAR(255) NOT NULL DEFAULT '',
        reporter_login   VARCHAR(255) NOT NULL DEFAULT '',
        reason           TEXT,
        status           VARCHAR(50) NOT NULL DEFAULT 'pending',
        timestamp        DOUBLE NOT NULL DEFAULT 0,
        resolved_action  TEXT,
        reporter_ip      VARCHAR(50) NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX idx_reports_status ON reports(status)",

    # ── 配置（KV 存储） ──
    """
    CREATE TABLE IF NOT EXISTS config (
        section VARCHAR(255) NOT NULL,
        `key`   VARCHAR(255) NOT NULL,
        value   TEXT,
        PRIMARY KEY (section, `key`)
    )
    """,

    # ── 画风 ──
    """
    CREATE TABLE IF NOT EXISTS styles (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        name      VARCHAR(255) NOT NULL,
        tags      TEXT,
        alias     VARCHAR(255) NOT NULL DEFAULT '',
        thumbnail VARCHAR(255) NOT NULL DEFAULT '',
        sort_order INT NOT NULL DEFAULT 0
    )
    """,

    # ── 角色 ──
    """
    CREATE TABLE IF NOT EXISTS characters (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        name      VARCHAR(255) NOT NULL,
        tags      TEXT,
        alias     VARCHAR(255) NOT NULL DEFAULT '',
        thumbnail VARCHAR(255) NOT NULL DEFAULT '',
        sort_order INT NOT NULL DEFAULT 0
    )
    """,

    # ── 分辨率预设 ──
    """
    CREATE TABLE IF NOT EXISTS resolutions (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        w         INT NOT NULL,
        h         INT NOT NULL,
        label     VARCHAR(255) NOT NULL DEFAULT '',
        sort_order INT NOT NULL DEFAULT 0
    )
    """,

    # ── 工作流元数据 ──
    """
    CREATE TABLE IF NOT EXISTS workflow_meta (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        workflow     TEXT,
        thumbnail    VARCHAR(255) NOT NULL DEFAULT '',
        lora_link    VARCHAR(255) NOT NULL DEFAULT '',
        display_name VARCHAR(255) NOT NULL DEFAULT '',
        sort_order   INT NOT NULL DEFAULT 0
    )
    """,

    # ── 用户通知 ──
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        github_id   VARCHAR(255) NOT NULL,
        message     TEXT,
        created_at  DOUBLE NOT NULL DEFAULT 0,
        `read`      INT NOT NULL DEFAULT 0,
        FOREIGN KEY (github_id) REFERENCES users(github_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_notifications_github ON notifications(github_id, `read`)",

    # ── 精选 ──
    """
    CREATE TABLE IF NOT EXISTS featured (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        path      VARCHAR(500) NOT NULL,
        sort_order INT NOT NULL DEFAULT 0
    )
    """,

    # ── 封禁 IP ──
    """
    CREATE TABLE IF NOT EXISTS banned_ips (
        ip VARCHAR(50) PRIMARY KEY
    )
    """,

    # ── 生图者 IP 映射 ──
    """
    CREATE TABLE IF NOT EXISTS creator_ips (
        path VARCHAR(500) PRIMARY KEY,
        ip   VARCHAR(50) NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX idx_creator_ips_ip ON creator_ips(ip)",

    # ── KV 状态存储 ──
    """
    CREATE TABLE IF NOT EXISTS kv_state (
        `key` VARCHAR(255) PRIMARY KEY,
        value TEXT
    )
    """,

    # ── GC 日志 ──
    """
    CREATE TABLE IF NOT EXISTS gc_logs (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        timestamp   DOUBLE NOT NULL,
        duration    DOUBLE NOT NULL DEFAULT 0,
        cleaned     TEXT,
        backup_dir  VARCHAR(500) NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX idx_gc_logs_timestamp ON gc_logs(timestamp)",

    # ── 邮箱用户 ──
    """
    CREATE TABLE IF NOT EXISTS email_users (
        email          VARCHAR(255) PRIMARY KEY,
        password_hash  TEXT,
        role           VARCHAR(50) NOT NULL DEFAULT 'user',
        banned         INT NOT NULL DEFAULT 0,
        banned_reason  TEXT,
        created_at     DOUBLE NOT NULL DEFAULT 0,
        verified       INT NOT NULL DEFAULT 1,
        verify_token   TEXT,
        totp_secret    TEXT,
        totp_enabled   INT NOT NULL DEFAULT 0,
        login_fails    INT NOT NULL DEFAULT 0,
        login_fail_time DOUBLE NOT NULL DEFAULT 0,
        invite_code    VARCHAR(255) NOT NULL DEFAULT ''
    )
    """,

    # ── 邀请码 ──
    """
    CREATE TABLE IF NOT EXISTS invite_codes (
        code        VARCHAR(255) PRIMARY KEY,
        used_count  INT NOT NULL DEFAULT 0,
        max_uses    INT NOT NULL DEFAULT 1,
        created_at  DOUBLE NOT NULL DEFAULT 0
    )
    """,

    # ── 密码重置 ──
    """
    CREATE TABLE IF NOT EXISTS password_resets (
        email      VARCHAR(255) PRIMARY KEY,
        token      TEXT,
        expires_at DOUBLE NOT NULL DEFAULT 0
    )
    """,

    # ── 发信日志 ──
    """
    CREATE TABLE IF NOT EXISTS email_logs (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        recipient VARCHAR(255) NOT NULL DEFAULT '',
        subject   VARCHAR(255) NOT NULL DEFAULT '',
        status    VARCHAR(50) NOT NULL DEFAULT 'ok',
        error     TEXT,
        created_at DOUBLE NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX idx_email_logs_created ON email_logs(created_at)",
]


# ═══════════════════════════════════════════
# 初始化
# ═══════════════════════════════════════════

def init_db():
    """创建/升级表结构。"""
    with db_lock():
        db = get_db()
        errors = 0
        for sql in SCHEMA:
            try:
                db.execute(sql)
            except Exception as e:
                errors += 1
                # 表已存在、索引已存在等可预期错误不打印
                if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                    print(f"[schema] 跳过: {e}")
        db.commit()
        total = len(SCHEMA)
        ok = total - errors
        if errors == 0:
            print(f"[schema] 数据库就绪: {_DB_NAME} @ {_DB_HOST}:{_DB_PORT} ({total}/{total})")
        else:
            print(f"[schema] 初始化完成: {ok}/{total}（{errors} 条跳过）")


# ═══════════════════════════════════════════
# 数据迁移（从 JSON 导入）
# ═══════════════════════════════════════════

def migrate_from_json(data_dir: Path):
    """
    从 JSON/TXT 文件迁移数据到 MySQL。
    调用时机：首次运行时，如果数据表为空则执行。

    Args:
        data_dir: web/ 目录路径（包含所有 JSON 文件）
    """
    with db_lock():
        db = get_db()
        try:
            if db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"] > 0:
                print("[migrate] 已有数据，跳过迁移")
                return
        except Exception:
            pass

    print("[migrate] 开始从 JSON 迁移...")

    with transaction() as db:
        _import_json(db, data_dir / "users.json", "users",
                     keys=["github_id", "login", "email", "avatar_url", "role", "banned", "banned_reason", "created_at"],
                     defaults={"role": "user", "banned": 0, "banned_reason": "", "created_at": 0})

        _import_json(db, data_dir / "sessions.json", "sessions",
                     keys=["token", "github_id", "expires_at", "access_granted", "claimed_key"],
                     defaults={"access_granted": 0, "claimed_key": ""})

        ak = _load_json(data_dir / "access_keys.json").get("keys", {})
        for k, v in ak.items():
            db.execute(
                "REPLACE INTO access_keys VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (k, v.get("used_by", ""), v.get("created_at", 0),
                 v.get("disabled_at", 0), v.get("expires_at", 0),
                 v.get("max_uses", 0), v.get("used_count", 0))
            )

        ui = _load_json(data_dir / "user_images.json")
        for gid, entries in ui.items():
            for e in entries:
                db.execute(
                    "INSERT INTO user_images (github_id, path, prompt, time) VALUES (%s,%s,%s,%s)",
                    (gid, e.get("path", ""), e.get("prompt", ""), e.get("time", 0))
                )

        di = _load_json(data_dir / "deleted_images.json")
        for gid, paths in di.items():
            for path in paths:
                db.execute(
                    "REPLACE INTO deleted_images (github_id, path) VALUES (%s,%s)",
                    (gid, path)
                )

        gl = _load_json(data_dir / "gen_log.json")
        for lid, e in gl.items():
            fps = json.dumps(e.get("file_paths", []))
            db.execute(
                "REPLACE INTO gen_logs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (lid, e.get("github_id", ""), e.get("login", ""),
                 e.get("prompt", ""), e.get("negative_prompt", ""),
                 e.get("workflow", ""), e.get("count", 0),
                 e.get("status", "success"), e.get("client_ip", ""),
                 e.get("created_at", 0), fps, e.get("error_reason", ""))
            )

        dl = _load_json_list(data_dir / "deletion_log.json")
        for e in dl:
            db.execute(
                "INSERT INTO deletion_logs (path,thumb_file,deleted_by_gid,deleted_by_login,deleted_at,creator_ip,creator_gid,creator_login) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (e.get("path", ""), e.get("thumb_file", ""),
                 e.get("deleted_by_github_id", e.get("github_id", "")),
                 e.get("deleted_by_login", e.get("login", "")),
                 e.get("deleted_at", e.get("time", 0)),
                 e.get("creator_ip", ""), e.get("creator_github_id", ""), e.get("creator_login", ""))
            )

        for fname, section in [
            ("limits.json", "limits"),
            ("llm_config.json", "llm"),
            ("announcement.json", "announcement"),
            ("maintenance.json", "maintenance"),
            ("custom_head.json", "custom_head"),
        ]:
            data = _load_json(data_dir / fname)
            for k, v in data.items():
                db.execute("REPLACE INTO config VALUES (%s,%s,%s)",
                           (section, k, json.dumps(v) if not isinstance(v, str) else v))

        styles = _load_json_list(data_dir / "styles.json")
        for i, style in enumerate(styles):
            db.execute(
                "INSERT INTO styles (name, tags, alias, thumbnail, sort_order) VALUES (%s,%s,%s,%s,%s)",
                (style.get("name", ""), style.get("tags", ""), style.get("alias", ""), style.get("thumbnail", ""), i)
            )

        characters = _load_json_list(data_dir / "characters.json")
        for i, c in enumerate(characters):
            db.execute(
                "INSERT INTO characters (name, tags, alias, thumbnail, sort_order) VALUES (%s,%s,%s,%s,%s)",
                (c.get("name", ""), c.get("tags", ""), c.get("alias", ""), c.get("thumbnail", ""), i)
            )

        res = _load_json(data_dir / "resolutions.json").get("presets", [])
        for i, r in enumerate(res):
            db.execute(
                "INSERT INTO resolutions (w, h, label, sort_order) VALUES (%s,%s,%s,%s)",
                (r.get("w", 0), r.get("h", 0), r.get("label", ""), i)
            )

        wm = _load_json_list(data_dir / "workflow_meta.json")
        for i, m in enumerate(wm):
            db.execute(
                "INSERT INTO workflow_meta (workflow, thumbnail, lora_link, display_name, sort_order) VALUES (%s,%s,%s,%s,%s)",
                (m.get("workflow", ""), m.get("thumbnail", ""), m.get("lora_link", ""), m.get("display_name", ""), i)
            )

        ft = _load_txt_lines(data_dir / "featured.txt")
        for i, path in enumerate(ft):
            db.execute("INSERT INTO featured (path, sort_order) VALUES (%s,%s)", (path, i))

        for ip in _load_txt_lines(data_dir / "banned_ips.txt"):
            db.execute("INSERT IGNORE INTO banned_ips VALUES (%s)", (ip,))

        for line in _load_txt_lines(data_dir / "creator_ips.txt"):
            if "\t" in line:
                path, ip = line.split("\t", 1)
                db.execute("REPLACE INTO creator_ips VALUES (%s,%s)", (path.strip(), ip.strip()))

    print("[migrate] 迁移完成")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _load_json(path: Path) -> dict:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[migrate] 读取 JSON 失败 {path}: {type(e).__name__}: {e}")
    return {}


def _load_json_list(path: Path) -> list:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[migrate] 读取 JSON 列表失败 {path}: {type(e).__name__}: {e}")
    return []


def _load_txt_lines(path: Path) -> List[str]:
    try:
        if path.is_file():
            return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as e:
        print(f"[migrate] 读取文本失败 {path}: {type(e).__name__}: {e}")
    return []


def _import_json(db, path: Path, table: str, keys: List[str], defaults: dict):
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
                    if keys[0] not in row or not row[keys[0]]:
                        row[keys[0]] = pk
                    rows.append(row)
            if rows:
                cols = ", ".join(keys)
                placeholders = ", ".join(["%s"] * len(keys))
                db.executemany(f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
                               [tuple(r.get(k, defaults.get(k, "")) for k in keys) for r in rows])
    except Exception as e:
        print(f"[migrate] 导入 {table} 失败: {e}")


# ═══════════════════════════════════════════
# 配置读写（替代 limits.json / llm_config.json 等）
# ═══════════════════════════════════════════

def config_get(section: str, key: str, default: Any = None) -> Any:
    db = get_db()
    row = db.execute("SELECT value FROM config WHERE section=%s AND `key`=%s", (section, key)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return row["value"]


def config_set(section: str, key: str, value: Any):
    val = json.dumps(value) if not isinstance(value, str) else value
    with transaction() as db:
        db.execute("REPLACE INTO config VALUES (%s,%s,%s)", (section, key, val))


def config_get_section(section: str) -> Dict[str, Any]:
    db = get_db()
    rows = db.execute("SELECT `key`, value FROM config WHERE section=%s", (section,)).fetchall()
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, TypeError):
            result[r["key"]] = r["value"]
    return result

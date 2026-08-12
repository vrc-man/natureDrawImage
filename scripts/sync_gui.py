"""SQLite → MySQL 数据同步工具（Tkinter 界面）。

正式图形界面入口。命令行入口见 scripts/sync_sqlite_to_mysql.py。
同步/预览逻辑统一在 scripts/sync_common.py，避免 GUI 和命令行表清单不一致。

线程模型（UI 与后端完全分离，不阻塞）：
  - 主线程   : 仅处理 tkinter 事件 + 定时轮询队列（100ms）
  - 日志     : 后台线程只入队 self._log_queue，主线程 _poll_logs 刷新 Text
  - 状态检测 : MySQL/Web 探测放入后台线程，结果经 _status_queue 回传
  - 长任务   : 备份/还原/同步/预览全部在 daemon 线程执行
"""
from __future__ import annotations

import os
import queue
import socket
import subprocess
import threading
import pymysql.cursors
from pathlib import Path
from tkinter import END, E, N, S, W, Button, Entry, Label, Scrollbar, Text, Tk, filedialog, messagebox

from sync_common import load_env, preview_sqlite, sync_sqlite_to_mysql

load_env()

# ── MySQL 连接参数（从 .env 读取） ──
_DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
_DB_PORT = os.environ.get("MYSQL_PORT", "3306")
_DB_USER = os.environ.get("MYSQL_USER", "root")
_DB_PASS = os.environ.get("MYSQL_PASSWORD", "")
_DB_NAME = os.environ.get("MYSQL_DATABASE", "natureDrawImage")
WEB_PORT = int(os.environ.get("WEB_PORT", "23601"))

# ── 自动探测 mysqldump/mysql 路径 ──
_MYSQL_BIN_DIR = None
for _candidate in [
    Path(__file__).parent.parent.parent / "mysql-8.0.28-winx64" / "bin",
    Path(__file__).parent.parent / "mysql-8.0.28-winx64" / "bin",
    Path("C:/Program Files/MySQL/MySQL Server 8.0/bin"),
]:
    if _candidate.exists():
        _MYSQL_BIN_DIR = _candidate
        break

_MYSQL_CLIENT_PATH = str(_MYSQL_BIN_DIR / "mysql.exe") if _MYSQL_BIN_DIR else "mysql"
DEFAULT_SQLITE_PATH = r"I:\网站\shengtu\natureDrawImage-main-sqlit\web\db\natureDrawImage.db"


def _mysql_password_arg() -> list[str]:
    return [f"-p{_DB_PASS}"] if _DB_PASS else []


def _check_mysql_running() -> bool:
    """检测 MySQL 是否在运行。"""
    try:
        import pymysql

        conn = pymysql.connect(
            host=_DB_HOST,
            port=int(_DB_PORT),
            user=_DB_USER,
            password=_DB_PASS,
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def _check_web_running() -> bool:
    """检测 Web 是否在监听 WEB_PORT。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", WEB_PORT))
        s.close()
        return result == 0
    except Exception:
        return False


class SyncTool:
    def __init__(self, root: Tk):
        self.root = root
        root.title("数据库管理工具 — 同步 / 备份 / 还原")
        root.geometry("700x600")
        root.resizable(True, True)

        # 线程安全队列（UI 与后端解耦）
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._status_queue: "queue.Queue[tuple]" = queue.Queue()

        # ⚠ Web/MySQL 状态栏
        self.warn_frame = Label(root, fg="red")
        self.warn_frame.grid(row=0, column=0, columnspan=4, padx=5, pady=(5, 0))
        self.warn_label = Label(self.warn_frame, fg="red", font=("", 10, "bold"), wraplength=680)
        self.warn_label.pack()

        # SQLite 路径选择
        Label(root, text="SQLite 数据库:").grid(row=1, column=0, sticky=E, padx=5, pady=5)
        self.sqlite_path = Entry(root, width=55)
        self.sqlite_path.grid(row=1, column=1, padx=5, pady=5, columnspan=2)
        self.sqlite_path.insert(0, DEFAULT_SQLITE_PATH)
        Button(root, text="浏览...", command=self.browse_sqlite).grid(row=1, column=3, padx=5)

        # MySQL 连接信息
        Label(root, text="MySQL 连接:").grid(row=2, column=0, sticky=E, padx=5, pady=5)
        self.mysql_info = Entry(root, width=55)
        self.mysql_info.grid(row=2, column=1, padx=5, pady=5, columnspan=2)
        self.mysql_info.insert(0, f"mysql://{_DB_USER}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}")
        self.mysql_info.config(state="readonly")

        # ── 第一行按钮：SQLite 同步 ──
        Label(root, text="同步（SQLite→MySQL）:").grid(row=3, column=0, sticky=E, padx=5, pady=3)
        btn_row1 = Label(root)
        btn_row1.grid(row=3, column=1, columnspan=3, sticky=W, pady=3)
        Button(btn_row1, text="仅预览", command=self.preview_only, width=14).pack(side="left", padx=2)
        self.sync_btn = Button(
            btn_row1,
            text="同步覆盖写入",
            command=self.start_sync,
            width=14,
            bg="#4CAF50",
            fg="white",
        )
        self.sync_btn.pack(side="left", padx=2)

        # ── 第二行按钮：MySQL 备份 ──
        Label(root, text="备份（MySQL→文件）:").grid(row=4, column=0, sticky=E, padx=5, pady=3)
        btn_row2 = Label(root)
        btn_row2.grid(row=4, column=1, columnspan=3, sticky=W, pady=3)
        Button(btn_row2, text="备份为...", command=self.backup_mysql, width=14, bg="#2196F3", fg="white").pack(
            side="left", padx=2
        )

        # ── 第三行按钮：MySQL 还原 ──
        Label(root, text="还原（文件→MySQL）:").grid(row=5, column=0, sticky=E, padx=5, pady=3)
        btn_row3 = Label(root)
        btn_row3.grid(row=5, column=1, columnspan=3, sticky=W, pady=3)
        self.restore_btn = Button(
            btn_row3,
            text="从文件还原...",
            command=self.restore_mysql,
            width=14,
            bg="#FF5722",
            fg="white",
        )
        self.restore_btn.pack(side="left", padx=2)

        # 日志输出
        Label(root, text="日志:").grid(row=6, column=0, sticky=N + W, padx=5, pady=(5, 0))
        log_frame = Label(root)
        log_frame.grid(row=7, column=0, columnspan=4, padx=5, pady=5, sticky=N + S + E + W)
        self.log_text = Text(log_frame, height=20, width=90, wrap="word")
        scroll = Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        root.grid_rowconfigure(7, weight=1)
        root.grid_columnconfigure(1, weight=1)
        self.running = False

        # 启动主线程轮询（日志队列 + 状态队列），绝不在后台线程触碰 UI
        self.root.after(100, self._poll_logs)
        self.root.after(100, self._poll_status)
        # 状态检测放入后台线程，避免阻塞主线程
        self._update_warnings()

    # ── 线程安全的日志：后台线程只入队，主线程轮询刷新 ──
    def log(self, msg: str) -> None:
        self._log_queue.put(msg)

    def _poll_logs(self) -> None:
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self.log_text.insert(END, msg + "\n")
                self.log_text.see(END)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_logs)

    # ── 状态检测：后台线程探测，结果经队列回传主线程 ──
    def _update_warnings(self) -> None:
        def _probe():
            try:
                web = _check_web_running()
                mysql = _check_mysql_running()
            except Exception:
                web, mysql = False, False
            self._status_queue.put((web, mysql))

        threading.Thread(target=_probe, daemon=True).start()
        self.root.after(3000, self._update_warnings)

    def _poll_status(self) -> None:
        try:
            while True:
                web, mysql = self._status_queue.get_nowait()
                self._apply_warning_state(web, mysql)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_status)

    def _apply_warning_state(self, web: bool, mysql: bool) -> None:
        msgs = []
        if web:
            msgs.append(f"⚠ Web 正在运行（端口 {WEB_PORT}）")
        if not mysql:
            msgs.append("⚠ MySQL 未启动")
        if msgs:
            self.warn_label.config(text="  |  ".join(msgs), fg="red")
            if web:
                self.sync_btn.config(state="disabled", bg="gray")
            else:
                self.sync_btn.config(state="normal", bg="#4CAF50")
        else:
            self.warn_label.config(text="✅ MySQL 已就绪，Web 已关闭", fg="green")
            self.sync_btn.config(state="normal", bg="#4CAF50")

    def _set_busy(self, busy: bool) -> None:
        """任务进行中禁用操作按钮，防止并发误操作。"""
        self.running = busy
        state = "disabled" if busy else "normal"
        for btn in (self.sync_btn, self.restore_btn):
            btn.config(state=state)

    def browse_sqlite(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 SQLite 数据库文件",
            filetypes=[("SQLite DB", "*.db"), ("所有文件", "*.*")],
        )
        if path:
            self.sqlite_path.delete(0, END)
            self.sqlite_path.insert(0, path)

    # ── 备份 ──
    def backup_mysql(self) -> None:
        if self.running:
            messagebox.showinfo("提示", "正在执行任务，请等待完成")
            return
        if not _check_mysql_running():
            messagebox.showerror("MySQL 未运行", "MySQL 数据库没有启动！\n请先启动 MySQL。")
            return
        dst = filedialog.asksaveasfilename(
            title="保存 MySQL 备份",
            defaultextension=".sql",
            filetypes=[("SQL 文件", "*.sql"), ("所有文件", "*.*")],
            initialfile="natureDrawImage_backup.sql",
        )
        if not dst:
            return
        self.log_text.delete("1.0", END)
        self.log("=== 开始备份 MySQL ===\n")
        self._set_busy(True)
        t = threading.Thread(target=self._do_backup, args=(dst,), daemon=True)
        t.start()

    def _do_backup(self, dst_path: str) -> None:
        tmp_path = dst_path + ".tmp"
        conn = None
        try:
            self.log(f"⏳ 正在备份 {_DB_NAME}...")
            conn = pymysql.connect(
                host=_DB_HOST,
                port=int(_DB_PORT),
                user=_DB_USER,
                password=_DB_PASS,
                database=_DB_NAME,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
            )
            with conn.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute("SHOW TABLES")
                tables_key = list(cursor.fetchone().keys())[0]
                cursor.execute("SHOW TABLES")
                tables = [row[tables_key] for row in cursor.fetchall()]

                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(f"-- natureDrawImage MySQL backup\n")
                    f.write(f"-- {_DB_NAME} @ {_DB_HOST}:{_DB_PORT}\n\n")

                    for table in tables:
                        cursor.execute(f"SHOW CREATE TABLE `{table}`")
                        create_row = cursor.fetchone()
                        create_sql = create_row.get("Create Table", "")
                        f.write(f"-- Table: `{table}`\n")
                        f.write(create_sql + ";\n\n")

                        cursor.execute(f"SELECT * FROM `{table}`")
                        rows = cursor.fetchall()
                        if rows:
                            col_names = [f"`{k}`" for k in rows[0].keys()]
                            cols_str = ", ".join(col_names)
                            for row in rows:
                                vals = []
                                for k in rows[0].keys():
                                    v = row[k]
                                    if v is None:
                                        vals.append("NULL")
                                    elif isinstance(v, (int, float)):
                                        vals.append(str(v))
                                    elif isinstance(v, bytes):
                                        vals.append(f"X'{v.hex()}'")
                                    else:
                                        s = str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
                                        vals.append(f"'{s}'")
                                f.write(f"INSERT INTO `{table}` ({cols_str}) VALUES ({', '.join(vals)});\n")
                            f.write("\n")

                conn.rollback()

            os.replace(tmp_path, dst_path)
            size = os.path.getsize(dst_path) // 1024
            self.log(f"✅ 备份完成: {dst_path} ({size} KB)")
        except Exception as e:
            self.log(f"❌ 备份失败: {type(e).__name__}: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            self._set_busy(False)

    # ── 还原 ──
    def restore_mysql(self) -> None:
        if self.running:
            messagebox.showinfo("提示", "正在执行任务，请等待完成")
            return
        if not _check_mysql_running():
            messagebox.showerror("MySQL 未运行", "MySQL 数据库没有启动！\n请先启动 MySQL。")
            return
        if _check_web_running():
            messagebox.showerror("Web 正在运行", "⚠ 还原期间必须关闭 Web 应用！\n请先关闭 Web 再重试。")
            return
        src = filedialog.askopenfilename(title="选择要还原的 SQL 备份文件", filetypes=[("SQL 文件", "*.sql"), ("所有文件", "*.*")])
        if not src:
            return
        if not messagebox.askyesno(
            "确认还原",
            f"将从以下文件还原 MySQL 数据库：\n{src}\n\n"
            "⚠ 当前 MySQL 中的所有数据将被覆盖！\n\n"
            "建议先备份当前数据再还原。\n继续吗？",
        ):
            return
        self.log_text.delete("1.0", END)
        self.log("=== 开始还原 MySQL ===\n")
        self._set_busy(True)
        t = threading.Thread(target=self._do_restore, args=(src,), daemon=True)
        t.start()

    # 还原分片大小 / 超时（GB 级 SQL 可能跑很久）
    _RESTORE_CHUNK = 4 * 1024 * 1024      # 4MB/片，流式写入，不占内存
    _RESTORE_TIMEOUT = 3600               # 1 小时上限
    _PROGRESS_LOG_STEP = 32 * 1024 * 1024 # 每 32MB 或到 100% 打一次进度日志

    def _do_restore(self, src_path: str) -> None:
        try:
            total = os.path.getsize(src_path)
            self.log(f"📦 备份文件: {src_path} ({total // 1024} KB / {total // 1024 // 1024} MB)")
            self.log(f"⏳ 正在分片还原 {_DB_NAME}...（GB 级文件请耐心等待）")
            cmd = [
                _MYSQL_CLIENT_PATH,
                "-h",
                _DB_HOST,
                "-P",
                str(_DB_PORT),
                "-u",
                _DB_USER,
                *_mysql_password_arg(),
                _DB_NAME,
            ]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            read = 0
            last_log = 0
            try:
                # 分片流式写入 stdin：逐块读取并 flush，避免大文件一次读入内存
                with open(src_path, "rb") as f:
                    while True:
                        chunk = f.read(self._RESTORE_CHUNK)
                        if not chunk:
                            break
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                        read += len(chunk)
                        # 按固定步长 + 完成点打进度，避免刷屏
                        if read - last_log >= self._PROGRESS_LOG_STEP or read >= total:
                            pct = read * 100 // total if total else 100
                            self.log(
                                f"  已写入 {read // 1024 // 1024} MB / {total // 1024 // 1024} MB ({pct}%)"
                            )
                            last_log = read
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                # mysql 提前退出（如 SQL 语法错误），读一次输出诊断
                pass

            try:
                out, err = proc.communicate(timeout=self._RESTORE_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()
                self.log("❌ 还原超时（超过 1 小时），已强制终止")
                return

            if proc.returncode == 0:
                self.log("✅ 还原完成！")
            else:
                # 优先取 stderr 尾部错误，其次 stdout 尾部
                diag = (err or out) or ""
                detail = diag[-1500:] if diag else "未知错误"
                self.log(f"❌ 还原失败（退出码 {proc.returncode}）: {detail}")
        except FileNotFoundError:
            self.log(f"❌ 找不到 mysql 客户端: {_MYSQL_CLIENT_PATH}")
        except Exception as e:
            self.log(f"❌ 还原失败: {type(e).__name__}: {e}")
        finally:
            self._set_busy(False)

    # ── SQLite 预览（后台线程执行，避免大库卡死 UI）──
    def preview_only(self) -> None:
        if self.running:
            messagebox.showinfo("提示", "正在执行任务，请等待完成")
            return
        path = self.sqlite_path.get().strip()
        if not os.path.exists(path):
            messagebox.showerror("错误", f"SQLite 数据库不存在:\n{path}")
            return
        self.log_text.delete("1.0", END)
        self.log("=== 预览模式（不写入数据）===\n")
        self._set_busy(True)
        t = threading.Thread(target=self._do_preview, args=(path,), daemon=True)
        t.start()

    def _do_preview(self, path: str) -> None:
        try:
            rows = preview_sqlite(path)
            self.log(f"📋 SQLite 表清单: {len(rows)} 张表\n")
            for table, count in rows:
                self.log(f"   {table}: {count} 条")
            self.log("\n✅ 预览完成，未写入任何数据")
        except Exception as e:
            self.log(f"❌ 读取失败: {type(e).__name__}: {e}")
        finally:
            self._set_busy(False)

    # ── SQLite → MySQL 同步 ──
    def start_sync(self) -> None:
        if self.running:
            messagebox.showinfo("提示", "正在执行任务，请等待完成")
            return
        path = self.sqlite_path.get().strip()
        if not os.path.exists(path):
            messagebox.showerror("错误", f"SQLite 数据库不存在:\n{path}")
            return
        if _check_web_running():
            messagebox.showerror(
                "Web 正在运行",
                f"Web 服务正在监听端口 {WEB_PORT}！\n\n"
                "同步期间必须关闭 Web 应用，否则会导致数据不一致。\n"
                "请先关闭 Web 再重试。",
            )
            return
        if not _check_mysql_running():
            messagebox.showerror(
                "MySQL 未运行",
                "MySQL 数据库没有启动！\n\n"
                "请先启动 MySQL（双击 mysql-8.0.28-winx64\\start-mysql.bat）\n"
                "再重新打开同步工具。",
            )
            return
        if not messagebox.askyesno(
            "确认",
            "将清空 MySQL 现有数据后从 SQLite 覆盖写入。\n\n"
            "⚠ 同步期间请确保 Web 服务已关闭！\n\n继续吗？",
        ):
            return
        self.log_text.delete("1.0", END)
        self.log("=== 开始同步 ===\n")
        self._set_busy(True)
        t = threading.Thread(target=self._do_sync, args=(path,), daemon=True)
        t.start()

    def _do_sync(self, path: str) -> None:
        try:
            if _check_web_running():
                self.log("❌ 检测到 Web 仍在运行！同步终止。")
                return
            sync_sqlite_to_mysql(path, truncate=True, log=self.log)
        except Exception as e:
            self.log(f"❌ 同步失败: {type(e).__name__}: {e}")
        finally:
            self._set_busy(False)


if __name__ == "__main__":
    root = Tk()
    SyncTool(root)
    root.mainloop()

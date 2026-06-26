"""SQLite → MySQL 数据同步工具（Tkinter 界面）。

正式图形界面入口。命令行入口见 scripts/sync_sqlite_to_mysql.py。
同步/预览逻辑统一在 scripts/sync_common.py，避免 GUI 和命令行表清单不一致。
"""
from __future__ import annotations

import os
import socket
import subprocess
import threading
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

_MYSQLDUMP_PATH = str(_MYSQL_BIN_DIR / "mysqldump.exe") if _MYSQL_BIN_DIR else "mysqldump"
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

        # 启动定时检测（所有控件已创建完成）
        self._update_warnings()

    def _update_warnings(self) -> None:
        web = _check_web_running()
        mysql = _check_mysql_running()
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
        self.root.after(3000, self._update_warnings)

    def log(self, msg: str) -> None:
        self.log_text.insert(END, msg + "\n")
        self.log_text.see(END)
        self.root.update()

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
        t = threading.Thread(target=self._do_backup, args=(dst,), daemon=True)
        t.start()

    def _do_backup(self, dst_path: str) -> None:
        self.running = True
        try:
            self.log(f"⏳ 正在备份 {_DB_NAME}...")
            cmd = [
                _MYSQLDUMP_PATH,
                "--single-transaction",
                "--quick",
                "-h",
                _DB_HOST,
                "-P",
                str(_DB_PORT),
                "-u",
                _DB_USER,
                *_mysql_password_arg(),
                _DB_NAME,
            ]
            with open(dst_path, "w", encoding="utf-8") as f:
                subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=True, timeout=300)
            size = os.path.getsize(dst_path) // 1024
            self.log(f"✅ 备份完成: {dst_path} ({size} KB)")
        except subprocess.TimeoutExpired:
            self.log("❌ 备份超时（300秒）")
        except subprocess.CalledProcessError as e:
            self.log(f"❌ 备份失败: {e.stderr.decode('utf-8', errors='replace')}")
        except Exception as e:
            self.log(f"❌ 备份失败: {type(e).__name__}: {e}")
        finally:
            self.running = False

    # ── 还原 ──
    def restore_mysql(self) -> None:
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
        t = threading.Thread(target=self._do_restore, args=(src,), daemon=True)
        t.start()

    def _do_restore(self, src_path: str) -> None:
        self.running = True
        try:
            size = os.path.getsize(src_path) // 1024
            self.log(f"📦 备份文件: {src_path} ({size} KB)")
            self.log(f"⏳ 正在还原 {_DB_NAME}...（数据量大可能需要几分钟）")
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
            with open(src_path, "r", encoding="utf-8") as f:
                result = subprocess.run(cmd, stdin=f, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                self.log("✅ 还原完成！")
            else:
                err = result.stderr[:500] if result.stderr else "未知错误"
                self.log(f"❌ 还原失败: {err}")
        except subprocess.TimeoutExpired:
            self.log("❌ 还原超时（600秒），可能文件过大")
        except FileNotFoundError:
            self.log(f"❌ 找不到 mysql 客户端: {_MYSQL_CLIENT_PATH}")
        except Exception as e:
            self.log(f"❌ 还原失败: {type(e).__name__}: {e}")
        finally:
            self.running = False

    # ── SQLite 预览 ──
    def preview_only(self) -> None:
        path = self.sqlite_path.get().strip()
        if not os.path.exists(path):
            messagebox.showerror("错误", f"SQLite 数据库不存在:\n{path}")
            return
        self.log_text.delete("1.0", END)
        self.log("=== 预览模式（不写入数据）===\n")
        try:
            rows = preview_sqlite(path)
            self.log(f"📋 SQLite 表清单: {len(rows)} 张表\n")
            for table, count in rows:
                self.log(f"   {table}: {count} 条")
            self.log("\n✅ 预览完成，未写入任何数据")
        except Exception as e:
            self.log(f"❌ 读取失败: {type(e).__name__}: {e}")

    # ── SQLite → MySQL 同步 ──
    def start_sync(self) -> None:
        path = self.sqlite_path.get().strip()
        if not os.path.exists(path):
            messagebox.showerror("错误", f"SQLite 数据库不存在:\n{path}")
            return
        if self.running:
            messagebox.showinfo("提示", "正在同步中，请等待完成")
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
        t = threading.Thread(target=self._do_sync, args=(path,), daemon=True)
        t.start()

    def _do_sync(self, path: str) -> None:
        self.running = True
        try:
            if _check_web_running():
                self.log("❌ 检测到 Web 仍在运行！同步终止。")
                return
            sync_sqlite_to_mysql(path, truncate=True, log=self.log)
        except Exception as e:
            self.log(f"❌ 同步失败: {type(e).__name__}: {e}")
        finally:
            self.running = False


if __name__ == "__main__":
    root = Tk()
    SyncTool(root)
    root.mainloop()

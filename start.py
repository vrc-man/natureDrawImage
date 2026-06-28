"""
启动管理脚本（简化版）。

MySQL 已设为开机自启（Windows 启动目录），本脚本只做：
  1. 读取 .env 获取 MySQL 配置
  2. 检查 MySQL 是否正常运行
  3. 启动 uvicorn Web 服务

用法：
  natureDrawImage-env\Scripts\python.exe start.py
"""

import os
import sys
import subprocess
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ── MySQL 便携版候选目录（仅用于定位 mysqladmin） ──
MYSQL_CANDIDATES = [
    ROOT / "mysql-8.0.28-winx64",
    ROOT.parent / "mysql-8.0.28-winx64",
    Path("I:/cc/mysql-8.0.28-winx64"),
]


def _load_env():
    """读取 .env 文件并设置到 os.environ（兼容现有 os.environ.get 用法）。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        print("[start] .env 不存在，使用系统环境变量")
        return {}
    env = {}
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            env[k] = v
            os.environ.setdefault(k, v)
    return env


def _find_mysqladmin() -> Path | None:
    """找到 mysqladmin.exe（用于 ping 检测）。"""
    for cand in MYSQL_CANDIDATES:
        p = cand / "bin/mysqladmin.exe"
        if p.exists():
            return p
    return None


def _mysql_ping(mysqladmin: Path, password: str) -> bool:
    """检查 MySQL 是否可连接。"""
    args = [
        str(mysqladmin),
        "-u", "root",
        "--protocol=TCP",
        "-h", "127.0.0.1",
    ]
    if password:
        args.append(f"--password={password}")
    args.append("ping")
    try:
        subprocess.run(args, capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def main():
    env = _load_env()
    password = env.get("MYSQL_PASSWORD", "")
    host = env.get("WEB_HOST", "127.0.0.1")
    port = int(env.get("WEB_PORT", "23601"))

    # 等待 MySQL 就绪（最多 60 秒）
    mysqladmin = _find_mysqladmin()
    if mysqladmin:
        import time as _time
        for i in range(30):
            if _mysql_ping(mysqladmin, password):
                print("[start] MySQL 运行正常")
                break
            print(f"[start] 等待 MySQL 就绪... ({i+1}/30)")
            _time.sleep(2)
        else:
            print("[start] 错误：MySQL 未就绪，请检查是否已启动")
            sys.exit(1)
    else:
        print("[start] 警告：找不到 mysqladmin，跳过 MySQL 检查")

    venv_python = ROOT / "natureDrawImage-env" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print(f"[start] 错误：虚拟环境不存在：{venv_python}")
        sys.exit(1)

    print(f"[start] Web: http://{host}:{port}")
    print(f"[start] Ctrl+C 优雅关闭\n")

    cmd = [
        str(venv_python),
        "-m", "uvicorn",
        "web.app:app",
        "--host", host,
        "--port", str(port),
        "--forwarded-allow-ips=127.0.0.1",
        "--timeout-graceful-shutdown", "60",
        "--reload",
    ]

    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT))
        proc.wait()
    except KeyboardInterrupt:
        print("\n[start] 收到 Ctrl+C，正在关闭 Web...")
        proc.terminate()
        proc.wait()
        print("[start] Web 已关闭。MySQL 保持运行（开机自启）。")
    except Exception as e:
        print(f"[start] 启动失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

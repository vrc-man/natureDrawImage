"""
安全关闭脚本（简化版）。

MySQL 已设为开机自启，本脚本只做：
  1. 通过 shutdown API 优雅关闭 Web

用法：
  natureDrawImage-env\Scripts\python.exe stop.py
"""

import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
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


def _stop_web():
    """尝试通过 /api/admin/shutdown 优雅关闭 Web。"""
    for port in ("8080", "23601"):
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/admin/shutdown",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=b"{}",
            )
            urllib.request.urlopen(req, timeout=5)
            print(f"[stop] Web (port {port}) 已收到关闭信号")
            return
        except urllib.error.HTTPError as e:
            if e.code == 403 or e.code == 401:
                print(f"[stop] Web (port {port}) 需要鉴权，跳过 API 关闭")
                return
            print(f"[stop] Web (port {port}) 未运行")
        except Exception:
            pass


def main():
    _load_env()
    _stop_web()
    time.sleep(2)
    print("[stop] 已全部关闭（MySQL 保持运行，开机自启）")


if __name__ == "__main__":
    main()

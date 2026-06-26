"""从最新 SQLite 数据库同步数据到 MySQL（覆盖式写入）。

正式命令行入口。图形界面入口见 scripts/sync_gui.py。

用法：
    cd 项目目录
    python scripts/sync_sqlite_to_mysql.py

也可以指定 SQLite 路径：
    python scripts/sync_sqlite_to_mysql.py "I:\\网站\\shengtu\\natureDrawImage-main-sqlit\\web\\db\\natureDrawImage.db"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sync_common import sync_sqlite_to_mysql

DEFAULT_SQLITE_PATH = Path(r"I:\网站\shengtu\natureDrawImage-main-sqlit\web\db\natureDrawImage.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite → MySQL 覆盖同步工具")
    parser.add_argument(
        "sqlite_path",
        nargs="?",
        default=str(DEFAULT_SQLITE_PATH),
        help=f"SQLite 数据库路径，默认：{DEFAULT_SQLITE_PATH}",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="不清空 MySQL，直接追加/覆盖写入（一般不推荐）",
    )
    args = parser.parse_args()

    try:
        sync_sqlite_to_mysql(args.sqlite_path, truncate=not args.no_truncate)
    except Exception as exc:
        print(f"❌ 同步失败: {type(exc).__name__}: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

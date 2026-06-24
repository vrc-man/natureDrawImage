"""
features 依赖中转层。

设计原则（务必遵守）：
  - features/ 下的模块只向下依赖 db/ 和本文件，**绝不 `from app import ...`**，
    以杜绝循环依赖、并把老 app.py 与新功能彻底隔离。
  - 需要 app.py 里的纯函数工具时，在此处**复制一份**（它们无状态，复制最干净），
    而不是反向 import app。
  - 路径常量在此独立推导，与 app.py 用同样的规则（环境变量 / 相对位置），
    保证指向同一批目录，但不产生对 app 的依赖。

如果某个工具将来在 app.py 改了规则，记得同步本文件——这是隔离换来的小代价。
"""

import os
from pathlib import Path
from fastapi import Request, HTTPException

# ── 路径常量（与 app.py 顶层保持一致的推导规则）──
# app.py: OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR_STR", ""))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR_STR", ""))
# app.py: THUMB_CACHE_DIR = web/../thumb_cache  （web 目录的上一级）
_WEB_DIR = Path(__file__).resolve().parent.parent          # .../web
THUMB_CACHE_DIR = _WEB_DIR.parent / "thumb_cache"
DELETION_THUMBS_DIR = _WEB_DIR / "deletion_thumbs"

# app.py: OUTPUT_IMAGE_EXTS
OUTPUT_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


# ── 鉴权（复用 app 的中间件已设好的 request.state.is_admin）──
def require_admin(request: Request) -> None:
    """管理员校验。中间件已在请求进入时设置 request.state.is_admin。"""
    if not getattr(request.state, "is_admin", False):
        raise HTTPException(403)


# ── 纯函数工具（从 app.py 复制，无状态）──
def validate_rel_path(rel: str) -> bool:
    """校验相对路径合法（不含 .. / 绝对路径 / 盘符），与 app._validate_rel_path 等价。"""
    if not rel or not isinstance(rel, str):
        return False
    p = rel.replace("\\", "/").strip()
    if not p:
        return False
    if p.startswith("/") or ".." in p.split("/"):
        return False
    # 盘符开头（Windows 绝对路径）
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        return False
    return True


def resolve_output_path(rel: str) -> Path | None:
    """OUTPUT_DIR 相对路径 -> 绝对路径，含路径穿越防护。

    与 app._resolve_output_path 行为对齐（直接拼接 + 安全子路径校验）。
    返回 Path（可能不存在），非法路径返回 None。
    """
    if not validate_rel_path(rel):
        return None
    rel_norm = rel.replace("\\", "/").lstrip("/")
    direct = (OUTPUT_DIR / rel_norm).resolve()
    try:
        if not direct.is_relative_to(OUTPUT_DIR.resolve()):
            return None
    except Exception:
        return None
    return direct


def thumb_cache_path(output_rel: str) -> Path | None:
    """OUTPUT_DIR 相对路径 -> thumb_cache 下的 .webp 路径。与 app._thumb_cache_path 对齐。"""
    if not validate_rel_path(output_rel):
        return None
    p = Path(output_rel.replace("\\", "/")).with_suffix(".webp")
    safe = str(p).lstrip("/").lstrip("\\")
    if ".." in safe:
        return None
    full = (THUMB_CACHE_DIR / safe).resolve()
    try:
        if not full.is_relative_to(THUMB_CACHE_DIR.resolve()):
            return None
    except Exception:
        return None
    return full


def thumb_exists(output_rel: str) -> bool:
    tp = thumb_cache_path(output_rel)
    return bool(tp and tp.is_file())


# ── 中间人注入容器（app.py 启动时回填，features 绝不 import app）──
# 设计：features 模块需要 app.py 的"数据函数 / 锁 / session 函数"时，
#   不直接 import app（避免循环依赖），而是通过这里取 app 注入的引用。
#   数据库读写永远走 app.py 注入的同一批函数 → 单一入口、共享锁、不争抢。
_app_ctx: dict = {}


def set_app_ctx(fns: dict) -> None:
    """app.py 启动时调用，把数据函数 / 锁 / session 函数注入进来。"""
    _app_ctx.update(fns)


def ctx(name: str):
    """取注入项。未注入时抛错（仅表示该模块暂不可用，绝不影响数据库）。"""
    if name not in _app_ctx:
        raise RuntimeError(f"features 依赖未注入: {name}（app.py 未调用 set_app_ctx 或顺序错误）")
    return _app_ctx[name]

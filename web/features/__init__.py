"""
features 外挂插件统一注册入口。

用法（app.py 中只调用一次）：
    from features import register_all
    register_all(app)

插件机制（ComfyUI custom_nodes 式自动发现）：
    1. 每个插件 = features/ 下的一个目录，含 __init__.py 导出 `router = APIRouter(...)`
    2. 可选 plugin.json 声明（name/description/router/requires/enabled），无则走约定
    3. 自动发现：扫描 features/ 直接子目录，跳过 `_` 开头 / config / `.disabled` 结尾
    4. 单插件加载失败 try/except 隔离，不影响主应用启动

新增插件三步：
    1. 复制目录到 web/features/ 下
    2. 写 __init__.py 导出 router
    3. 重启后端自动挂载

禁用插件：目录名加 `.disabled` 后缀，或 plugin.json 里 "enabled": false
"""

import importlib
import json
from pathlib import Path

_BASE = Path(__file__).resolve().parent


def _load_plugin_manifest(p: Path) -> dict | None:
    """读取可选 plugin.json。解析失败返回 None（走约定）。"""
    try:
        mf = p / "plugin.json"
        if mf.is_file():
            return json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def register_all(app) -> None:
    """自动发现并挂载所有外挂插件路由。单插件失败不影响主应用启动。"""
    for p in sorted(_BASE.iterdir()):
        if not p.is_dir():
            continue
        if p.name.startswith("_") or p.name == "config":
            continue
        if p.name.endswith(".disabled"):
            print(f"[features] 跳过禁用插件: {p.name}")
            continue
        entry = p / "__init__.py"
        if not entry.is_file():
            continue
        manifest = _load_plugin_manifest(p)
        if manifest and manifest.get("enabled") is False:
            print(f"[features] 跳过禁用插件: {p.name}（plugin.json enabled=false）")
            continue
        try:
            m = importlib.import_module(f"features.{p.name}")
            router = getattr(m, "router", None)
            if router is None:
                print(f"[features] {p.name} 未导出 router，跳过")
                continue
            app.include_router(router)
            print(f"[features] 已挂载: {p.name}")
        except Exception as e:
            print(f"[features] {p.name} 加载失败: {type(e).__name__}: {e}")

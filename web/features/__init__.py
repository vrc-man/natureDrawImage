"""
features 外挂功能统一注册入口。

用法（app.py 中只调用一次）：
    from features import register_all
    register_all(app)

新增功能：
    1. 在 features/ 下新建 xxx.py，导出一个 `router = APIRouter(...)`
    2. 在 register_all() 里加一行 include_router
    （app.py 永远不需要再改动）
"""


def register_all(app) -> None:
    """挂载所有外挂功能路由。失败时打印但不影响主应用启动。"""
    routers = []
    try:
        from .health_check import router as health_router
        routers.append(("health-check", health_router))
    except Exception as e:
        print(f"[features] health_check 加载失败: {type(e).__name__}: {e}")

    try:
        from .llm_prompt_templates import router as llm_tpl_router
        routers.append(("llm-templates", llm_tpl_router))
    except Exception as e:
        print(f"[features] llm_prompt_templates 加载失败: {type(e).__name__}: {e}")

    try:
        from .access_keys import router as access_keys_router
        routers.append(("access-keys", access_keys_router))
    except Exception as e:
        print(f"[features] access_keys 加载失败: {type(e).__name__}: {e}")

    for name, r in routers:
        try:
            app.include_router(r)
            print(f"[features] 已挂载: {name}")
        except Exception as e:
            print(f"[features] 挂载失败 {name}: {type(e).__name__}: {e}")

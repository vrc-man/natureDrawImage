# features/ 外挂功能开发规范

> 老 `app.py` 已冻结。所有**新功能**写在本目录，老代码只保留一行 `register_all(app)`。
> 目标：新功能隔离、可独立删除/回退、出 bug 不波及老代码、app.py 永不再膨胀。

## 核心原则（铁律）

1. **绝不 `from app import ...`** —— features 模块只能向下依赖 `db/` 和 `features/_deps.py`，
   杜绝循环依赖，并把老代码与新功能彻底隔离。
2. **一个功能 = 一个文件 + 一个 `APIRouter`** —— 出 bug 范围锁死在单文件，可独立删。
3. **后台任务自带锁和状态** —— 不碰 app.py 的全局变量/锁。
4. **每加一个模块**：`py_compile` → 启动冒烟 → `git commit`，小步可回退。
5. **共享纯函数复制进 `_deps.py`** —— 不反向引用 app，保持单向依赖。

## 目录结构

```
features/
├── __init__.py       # register_all(app)：统一挂载入口
├── _deps.py          # 依赖中转层：鉴权 + 复制的纯函数 + 路径常量
├── README.md         # 本文件
└── <feature>.py      # 每个功能一个文件
```

## 新增一个功能的步骤

1. 新建 `features/my_feature.py`：

   ```python
   from fastapi import APIRouter, Request
   from db import operations as db
   from features._deps import require_admin

   router = APIRouter(prefix="/api/admin/features/my", tags=["my-feature"])

   @router.get("/ping")
   async def ping(request: Request):
       require_admin(request)
       return {"ok": True}
   ```

2. 在 `features/__init__.py` 的 `register_all()` 里加一行：

   ```python
   from .my_feature import router as my_router
   routers.append(("my-feature", my_router))
   ```

3. `py_compile` + 重启冒烟 + commit。**app.py 不需要任何改动。**

## 鉴权

中间件已在请求进入时设置 `request.state.is_admin`，APIRouter 自动继承。
统一用 `from features._deps import require_admin` → `require_admin(request)`。

## 可安全依赖的东西

| 依赖 | 来源 | 说明 |
|------|------|------|
| 数据库操作 | `from db import operations as db` | db 层不依赖 app，无循环风险 |
| 鉴权 | `features._deps.require_admin` | 复用中间件结果 |
| 纯函数工具 | `features._deps`（validate_rel_path / resolve_output_path / thumb_exists 等） | 从 app.py 复制，无状态 |
| 路径常量 | `features._deps`（OUTPUT_DIR / THUMB_CACHE_DIR / ...） | 独立按同规则推导 |

## 注意事项

- **后台任务**：用 `asyncio.to_thread` 跑 CPU/IO 密集活，沿用 db 层的 busy_timeout。
- **_deps 与 app 的同步**：若 app.py 改了某个被复制函数的规则，需手动同步 `_deps.py`
  （这是隔离换来的小代价；大多数纯函数极少变动）。
- **不要在模块顶层做重操作**：import 时只定义，副作用放进路由/任务里。

## 写操作安全判断（重要）

外挂**可以写**，能不能写取决于「写的资源老 app.py 会不会也写」。判断流程：

```
要写的是什么？
├─ SQLite 表（含老代码也写的表）
│    → ✅ 安全。统一 from db import operations as db 调用，
│       共享单连接 + WAL，写自动串行。哪怕老代码也写同一张表，
│       只要都走 db 模块的函数（如 db.mark_images_deleted），就不冲突。
│
├─ 外挂专属的新文件 / 新目录（导出、报表、新缓存）
│    → ✅ 安全。只有外挂自己写，配一把模块内 asyncio.Lock 防自我并发即可。
│
├─ 老代码用「纯文件」管理的共享资源（featured.txt、limits.json …）
│    → ⚠️ 危险。外挂的锁锁不住老代码那边，会后写覆盖先写。
│       → 这类写操作留在 app.py，不要放外挂。
│
├─ 老代码用「纯内存状态/锁」管理的东西（_limits dict、各种全局 _xxx_lock）
│    → ⚠️ 危险。外挂 new 的锁与老代码不是同一把，锁不住。
│       → 留 app.py，或极少数情况把锁经 _deps 暴露共享（破坏隔离，慎用）。
│
└─ 删 OUTPUT_DIR 原图 / 写 deleted_images 标记并删文件
     → ⚠️ 与 GC / 启动清理竞争（TOCTOU）。留 app.py 统一处理。
```

**一句话**：写 DB（走 db 模块）和写外挂自己的新文件，都安全且不受限；
只有「老代码用文件/内存锁独占管理的那几样核心资源」才碰不得。
新业务建新表、批量改 DB、生成导出文件等绝大多数写功能，外挂都能放心做。

## 已有模块

| 模块 | 前缀 | 说明 |
|------|------|------|
| `health_check.py` | `/api/admin/features/health` | 图片目录健康检查（只读统计：总数/占用/缺缩略图/孤儿） |

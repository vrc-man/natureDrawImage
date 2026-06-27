# features/ 外挂功能开发规范（MySQL 版）

> 老 `app.py` 已冻结：所有**新增功能**优先写在 `web/features/`。
> 目标：新功能隔离、可独立删除/回退、出 bug 不波及老代码、`app.py` 不再继续膨胀。

本文是后续开发外挂功能的详细说明，适用于当前 MySQL 版项目。

---

## 1. 设计目标

`features/` 的定位是：

```text
新功能插件区 / 外挂 API 区
```

它解决的问题：

1. `web/app.py` 已经很大，不适合继续塞新功能；
2. 新功能如果直接 import app，容易循环依赖；
3. 新功能出 bug 时，希望能单文件删除/回滚；
4. 数据库读写要统一经过 `web/db/operations.py`，避免 SQL 散落；
5. 后台任务、缓存、锁都要限制在单个 feature 内，减少对主流程影响。

推荐整体分层：

```text
web/app.py
  ├─ 老主业务、启动流程、全局中间件、核心生图队列
  └─ 只负责调用 features.register_all(app) 挂载外挂

web/features/*.py
  ├─ 新功能 API
  ├─ 只做路由、参数校验、调用 operations、轻量状态
  └─ 不直接 import app，不直接拿 get_db

web/features/_deps.py
  ├─ 鉴权工具
  ├─ 路径常量
  ├─ 复制的纯函数工具
  └─ 少量 app 上下文注入

web/db/operations.py
  ├─ 日常业务数据库读写
  ├─ 用户、会话、日志、图片、配置、统计、access key 等
  └─ feature 需要数据库能力时先加这里

web/db/schema.py
  ├─ MySQL 连接管理
  ├─ transaction()
  ├─ init_db() 建表/升级表结构
  └─ 不放新业务逻辑
```

---

## 2. 核心铁律

### 2.1 绝不 import app

禁止：

```python
from app import xxx
import app
from web.app import xxx
```

原因：

- 会制造循环依赖；
- app 顶层副作用很多，import app 可能导致路由/任务重复初始化；
- feature 应该能独立加载失败，不影响主应用启动。

如果确实需要 app 中的纯函数：

1. 优先复制一份到 `features/_deps.py`；
2. 如果需要少量上下文函数，由 `app.py` 通过 `features._deps.set_app_ctx()` 注入；
3. 不要反向 import app。

---

### 2.2 一个功能 = 一个文件 + 一个 APIRouter

推荐：

```text
features/my_feature.py
```

里面只导出：

```python
router = APIRouter(...)
```

不要一个文件塞多个不相关功能。这样出问题时可以直接从 `features/__init__.py` 里移除注册。

---

### 2.3 数据库能力先封装到 operations.py

禁止在 feature 里直接写：

```python
from db.schema import get_db
get_db().execute("SELECT ...")
```

推荐：

```python
from db import operations as db

rows = db.query_xxx(...)
```

如果 `operations.py` 里没有需要的函数，先新增一个业务函数，例如：

```python
def get_gen_leaderboard(...):
    ...
```

然后 feature 调用它。

这样以后表结构、索引、缓存、事务调整都集中在 `operations.py`。

---

### 2.4 不在模块顶层做重操作

feature 文件顶层只允许：

- import；
- 定义常量；
- 定义轻量内存缓存；
- 定义锁；
- 定义 router；
- 定义函数。

不要在 import 时执行：

- 扫描大目录；
- 查询大量数据库；
- 启动后台任务；
- 读写大文件；
- 网络请求。

副作用放到具体接口或后台任务函数里。

---

### 2.5 后台任务自带状态和锁

如果 feature 有后台任务，必须在自己模块内维护：

```python
_task = None
_lock = asyncio.Lock()
_status = {...}
```

不要复用 `app.py` 的全局锁，不要改 `app.py` 的全局状态。

---

## 3. 目录结构

当前结构：

```text
features/
├── __init__.py                 # register_all(app)：统一挂载入口
├── _deps.py                    # 鉴权、路径工具、少量 app 上下文注入
├── README.md                   # 本文档
├── access_keys.py              # 访问密钥管理
├── gen_leaderboard.py          # 生图排行榜
├── health_check.py             # 图片目录健康检查
└── llm_prompt_templates.py     # LLM 提示词模板
```

---

## 4. 新增 feature 的标准流程

### 第 1 步：确认功能边界

先判断：

| 问题 | 放哪里 |
|---|---|
| 新 API / 新管理功能 | `web/features/<feature>.py` |
| 新数据库查询/写入 | `web/db/operations.py` |
| 新表结构 | `web/db/schema.py` 的 `SCHEMA` |
| 新纯函数工具 | `web/features/_deps.py` |
| 老核心队列/生图流程 | 暂留 `web/app.py`，慎重改 |
| 插件自己的小 JSON | 可放 `web/<plugin>.json` 或插件专属目录 |

---

### 第 2 步：新增 feature 文件

示例：`web/features/my_feature.py`

```python
"""外挂功能：示例功能。"""

from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException

from db import operations as db
from features._deps import require_admin

router = APIRouter(prefix="/api/admin/features/my-feature", tags=["my-feature"])


@router.get("/ping")
async def ping(request: Request):
    require_admin(request)
    return {"ok": True}


@router.get("/items")
async def list_items(request: Request, limit: int = 20, offset: int = 0):
    require_admin(request)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    return db.list_my_feature_items(limit=limit, offset=offset)
```

注意：

- 管理员接口使用 `/api/admin/features/...`；
- 普通用户接口使用 `/api/features/...`；
- 所有管理员接口都要 `require_admin(request)`；
- 分页参数必须限制上限。

---

### 第 3 步：在 `features/__init__.py` 注册

在 `register_all(app)` 中加：

```python
try:
    from .my_feature import router as my_feature_router
    routers.append(("my-feature", my_feature_router))
except Exception as e:
    print(f"[features] my_feature 加载失败: {type(e).__name__}: {e}")
```

然后统一 include：

```python
for name, r in routers:
    try:
        app.include_router(r)
        print(f"[features] 已挂载: {name}")
    except Exception as e:
        print(f"[features] 挂载失败 {name}: {type(e).__name__}: {e}")
```

注册必须放在 try/except 里，保证单个 feature 加载失败不影响主应用启动。

---

### 第 4 步：如需数据库能力，先改 operations.py

例如排行榜：

```python
def get_gen_leaderboard(limit: int = 3, date_from: float = 0, date_to: float = 0) -> dict:
    conditions = ["status='success'"]
    params = []
    if date_from > 0:
        conditions.append("created_at >= %s")
        params.append(date_from)
    if date_to > 0:
        conditions.append("created_at <= %s")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions)
    rows = _db().execute(
        f"SELECT login, SUM(`count`) as total FROM gen_logs{where} GROUP BY login ORDER BY total DESC LIMIT %s",
        params + [max(1, min(limit, 50))]
    ).fetchall()
    return {"items": [dict(r) for r in rows]}
```

feature 里调用：

```python
data = db.get_gen_leaderboard(...)
```

不要在 feature 里写裸 SQL。

---

### 第 5 步：编译检查

至少运行：

```bash
natureDrawImage-env/Scripts/python.exe -m py_compile web/features/my_feature.py web/features/__init__.py web/db/operations.py
```

如果改了 schema：

```bash
natureDrawImage-env/Scripts/python.exe -m py_compile web/db/schema.py
```

---

### 第 6 步：启动冒烟

启动 Web 后观察日志：

```text
[features] 已挂载: my-feature
```

请求：

```text
GET /api/admin/features/my-feature/ping
```

未登录应返回 401/403；管理员登录后应返回 200。

---

## 5. 路由命名规范

### 5.1 管理员功能

推荐：

```text
/api/admin/features/<feature-name>/...
```

示例：

```text
/api/admin/features/health/ping
/api/admin/features/gen-leaderboard?range=today
/api/admin/features/llm-templates
```

### 5.2 普通用户功能

推荐：

```text
/api/features/<feature-name>/...
```

示例：

```text
/api/features/llm-templates
```

### 5.3 已存在老接口兼容

如果某个 feature 是从 `app.py` 迁出的老接口，为了前端兼容，可以保留原路径，例如：

```text
/api/admin/access-keys
```

但新功能优先使用 `/api/admin/features/...`。

---

## 6. 鉴权规范

### 6.1 管理员接口

统一：

```python
from features._deps import require_admin

@router.get("/xxx")
async def xxx(request: Request):
    require_admin(request)
    ...
```

`require_admin()` 依赖主 app 中间件设置的：

```python
request.state.is_admin
```

### 6.2 普通登录接口

如果只是要求登录但不要求管理员，优先通过 app 注入的：

```python
get_user = _deps.ctx("get_user")
user = get_user(request)
```

如果 `user is None`，返回 401。

### 6.3 不要自己解析 session cookie

不要在 feature 里自己读 cookie 查 session。统一复用 app 注入的 `get_user` 或已有 db.operations 函数。

---

## 7. 数据库开发规范

### 7.1 新表放 schema.py

如果 feature 需要新表，在 `web/db/schema.py` 的 `SCHEMA` 里新增：

```python
"""
CREATE TABLE IF NOT EXISTS my_feature_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL DEFAULT '',
    created_at DOUBLE NOT NULL DEFAULT 0
)
""",
"CREATE INDEX idx_my_feature_created ON my_feature_items(created_at)",
```

注意：

- MySQL `TEXT` 列不要设置普通字符串 DEFAULT；
- 常用查询字段加索引；
- 外键慎用，确认删除行为；
- SQL 写法使用 MySQL 语法，不写 SQLite PRAGMA。

### 7.2 日常读写放 operations.py

推荐按业务区块组织：

```python
# ═══════════════════════════════════════════
# My Feature
# ═══════════════════════════════════════════

def list_my_feature_items(...):
    ...

def save_my_feature_item(...):
    ...
```

### 7.3 参数化 SQL

必须使用参数绑定：

```python
_db().execute("SELECT * FROM table WHERE id=%s", (id_,))
```

禁止拼接用户输入：

```python
# 禁止
_db().execute(f"SELECT * FROM table WHERE name='{name}'")
```

### 7.4 事务

多条写入需要一致性时：

```python
from db.schema import transaction

with transaction() as conn:
    conn.execute(...)
    conn.execute(...)
```

feature 不直接调用 transaction，优先把事务封装在 `operations.py` 函数里。

### 7.5 不要暴露通用 execute_sql

不要为了省事新增：

```python
def execute_sql(sql, params):
    ...
```

这会破坏分层，让 SQL 重新散落到 feature 里。

---

## 8. JSON 文件使用原则

当前项目是 MySQL 版，但不是所有 JSON 都必须消灭。

### 可以保留 JSON 的场景

| 场景 | 说明 |
|---|---|
| 插件自己的小配置 | 如提示词模板列表 |
| 数据量小 | 不需要分页/统计 |
| 低频写入 | 管理员偶尔编辑 |
| 不影响核心一致性 | 损坏不会破坏用户/日志/队列 |

推荐统一放在：

```text
web/features/config/<feature_module_name>.json
```

例如：

```text
web/features/config/llm_prompt_templates.json
web/features/config/my_feature.json
web/features/config/banner_rules.json
```

命名规则：Python 模块名和 JSON 文件名保持一致，`my_feature.py` 对应 `config/my_feature.json`。

注意：这些 JSON 属于运行时配置/插件私有数据，**默认不要提交到 Git**；文档中说明约定即可，不需要提交 `default_xxx.json` 或真实配置文件。

### 应该进 MySQL 的场景

| 数据 | 原因 |
|---|---|
| 用户 / session | 登录核心状态 |
| access key | 权限控制 |
| 生图日志 | 数据量大，需要查询/分页/统计 |
| 删除记录 | 与图片生命周期相关 |
| 队列状态 | 运行状态 |
| IP 封禁 / creator IP | 多接口共享 |
| 管理后台统计 | 需要 SQL 聚合 |

### 敏感配置

API key、密码、token 不要写进普通 JSON。优先：

- `.env`；
- 或受控的 MySQL 配置项；
- 并确保不会提交到 Git。

---

## 9. 文件和图片操作安全边界

### 9.1 只读扫描可以放 feature

例如：

- 统计图片数量；
- 检查缺失缩略图；
- 扫描孤儿文件；
- 生成只读报表。

这类适合 feature。

### 9.2 删除原图要慎重

以下操作不建议放新 feature 里直接做：

- 删除 `OUTPUT_DIR` 原图；
- 删除缩略图；
- 同时更新 `deleted_images`、`user_images`、`creator_ips`、`deletion_logs`；
- 与 GC / 启动清理竞争的文件操作。

原因是容易产生 TOCTOU：

```text
检查时文件存在 → 另一任务删除 → 当前任务继续写日志/删缩略图 → 状态不一致
```

这类仍建议由老 `app.py` 中已有统一删除流程处理，或先专门设计一套 operations + 文件锁方案。

---

## 10. 后台任务规范

如果 feature 需要后台任务：

```python
_task = None
_lock = asyncio.Lock()
_status = {
    "running": False,
    "progress": 0,
    "error": "",
}
```

启动接口示例：

```python
@router.post("/scan")
async def start_scan(request: Request):
    require_admin(request)
    global _task
    async with _lock:
        if _task and not _task.done():
            return {"ok": False, "message": "任务已在运行"}
        _task = asyncio.create_task(_run_scan())
    return {"ok": True}
```

状态接口：

```python
@router.get("/scan/status")
async def scan_status(request: Request):
    require_admin(request)
    return _status
```

CPU/IO 密集任务使用：

```python
await asyncio.to_thread(sync_func)
```

不要阻塞事件循环。

---

## 11. 缓存规范

轻量缓存可以放模块内，例如：

```python
_cache = {}
_CACHE_TTL = 60
```

要求：

- 有 TTL；
- 有清理函数；
- 写操作后主动清缓存；
- 不缓存敏感明文；
- 不缓存太大的列表。

示例：`gen_leaderboard.py` 使用 60 秒缓存，避免重复聚合查询。

---

## 12. 错误处理规范

### 12.1 加载失败不能影响主应用

在 `features/__init__.py` 里每个 feature 单独 try/except。

### 12.2 接口错误返回

业务输入错误：

```python
raise HTTPException(400, "参数错误")
```

未登录：

```python
raise HTTPException(401, "请先登录")
```

非管理员：

```python
raise HTTPException(403)
```

资源不存在：

```python
raise HTTPException(404, "不存在")
```

### 12.3 不吞掉重要异常

不要写：

```python
except Exception:
    pass
```

除非这是明确的兼容兜底，并且不会影响数据一致性。至少应记录：

```python
print(f"[my-feature] 操作失败: {type(e).__name__}: {e}")
```

---

## 13. 安全规范

### 13.1 管理员接口必须鉴权

任何 `/api/admin/...` 都必须检查管理员权限。

### 13.2 路径参数必须校验

处理图片/文件路径时使用：

```python
from features._deps import validate_rel_path, resolve_output_path
```

不要直接拼接用户输入路径。

### 13.3 限制分页和批量操作数量

例如：

```python
limit = max(1, min(limit, 200))
```

批量删除/批量更新也应限制最大数量。

### 13.4 不返回敏感数据

尤其注意：

- 完整 access key；
- session token；
- API key；
- SMTP 密码；
- LLM 密钥；
- 用户隐私字段。

如果确实需要 reveal，必须是管理员接口，并记录审计日志。

---

## 14. 前端配合规范

如果 feature 需要管理后台 UI：

1. 后端 API 放 `web/features/<feature>.py`；
2. 数据库能力放 `web/db/operations.py`；
3. 前端组件放 `frontend/src/components/admin/<FeatureSection>.vue`；
4. 在 `frontend/src/pages/Admin.vue` 注册对应 section；
5. 接口路径优先使用 `/api/admin/features/<feature>`。

不要为了一个新管理面板去改 `web/app.py`。

---

## 15. 已有模块说明

| 模块 | 路径 / 前缀 | 说明 |
|---|---|---|
| `health_check.py` | `/api/admin/features/health` | 图片目录健康检查，只读统计总数/占用/缺缩略图/孤儿 |
| `llm_prompt_templates.py` | `/api/admin/features/llm-templates` 和 `/api/features/llm-templates` | LLM 提示词模板，插件自有 JSON 存储 |
| `access_keys.py` | `/api/admin/access-keys` | 访问密钥管理，从 app.py 迁出，保留老接口路径兼容前端 |
| `gen_leaderboard.py` | `/api/admin/features/gen-leaderboard` | 生图排行榜，从 MySQL `gen_logs` 聚合统计 |

---

## 16. 新功能开发检查清单

新增 feature 前后逐项确认：

### 代码结构

- [ ] 没有 `from app import ...`；
- [ ] 没有 `from db.schema import get_db`；
- [ ] 数据库读写已封装到 `db.operations.py`；
- [ ] 一个 feature 一个 `APIRouter`；
- [ ] 已在 `features/__init__.py` 注册；
- [ ] 管理员接口已 `require_admin(request)`；
- [ ] 分页/批量参数有限制。

### 数据库

- [ ] 新表已加入 `schema.py`；
- [ ] 常用查询字段有索引；
- [ ] SQL 使用 `%s` 参数绑定；
- [ ] 多表/多步写入有事务；
- [ ] 没有 SQLite 语法。

### 文件操作

- [ ] 路径经过 `validate_rel_path` / `resolve_output_path`；
- [ ] 没有直接删除核心图片资源，除非已有统一流程；
- [ ] 插件私有文件有自己的锁和原子写策略。

### 验证

- [ ] `py_compile` 通过；
- [ ] Web 启动日志显示 `[features] 已挂载: xxx`；
- [ ] 未登录访问管理员接口被拒绝；
- [ ] 管理员登录后接口返回 200；
- [ ] 浏览器控制台无 error；
- [ ] Network 中相关 API 无 500。

---

## 17. 推荐命令

编译单个 feature：

```bash
natureDrawImage-env/Scripts/python.exe -m py_compile web/features/my_feature.py web/features/__init__.py
```

编译 feature + 数据库层：

```bash
natureDrawImage-env/Scripts/python.exe -m py_compile web/features/my_feature.py web/features/__init__.py web/db/operations.py web/db/schema.py
```

启动 Web 冒烟：

```bash
natureDrawImage-env/Scripts/python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60
```

验证接口：

```text
GET http://127.0.0.1:23601/api/admin/features/<feature>/ping
```

---

## 18. 什么时候不要做成 feature

以下情况不建议直接做成 feature：

1. 修改核心生图队列；
2. 修改 WebSocket 广播机制；
3. 修改 `_run_lock` / `_queue_lock` 等核心锁；
4. 多 worker / Redis / 分布式队列相关；
5. 删除原图和多表状态强一致流程；
6. 邮箱认证主流程大改；
7. 需要大量改前端主页面和 app.py 状态的功能。

这些应单独设计，不能简单当外挂塞进 `features/`。

---

## 19. 最小模板

```python
"""外挂功能：我的功能。"""

from fastapi import APIRouter, Request, HTTPException

from db import operations as db
from features._deps import require_admin

router = APIRouter(prefix="/api/admin/features/my-feature", tags=["my-feature"])


@router.get("/ping")
async def ping(request: Request):
    require_admin(request)
    return {"ok": True, "feature": "my-feature"}
```

注册：

```python
try:
    from .my_feature import router as my_feature_router
    routers.append(("my-feature", my_feature_router))
except Exception as e:
    print(f"[features] my_feature 加载失败: {type(e).__name__}: {e}")
```

---

## 20. 一句话原则

> 新功能放 `features/`，数据库能力放 `operations.py`，表结构放 `schema.py`，不要 import app，不要直接拿 get_db，能只读就只读，能小步提交就小步提交。

# 2026-06-27 Claude 维护工作总结

本文记录本轮在 `natureDrawImage-main-mysqlRefactoring` 项目中完成的主要维护、重构与验证工作，便于后续继续开发和提交前复盘。

> 说明：当前工作区中还存在一些 `frontend/` 文件改动，这些不是本文总结的重点；本文只记录本轮明确围绕 MySQL、启动脚本、数据库分层和 features 插件体系完成的工作。

## 1. MySQL 连接层重构

涉及文件：

- `web/db/schema.py`
- `web/db/operations.py`
- `web/app.py`
- `web/email_auth.py`

### 改动内容

原先 `web/db/schema.py` 虽然已经使用 MySQL，但连接层仍然保留 SQLite 时代的模式：

- 单个全局连接；
- 全局 `_db_lock`；
- `execute()` / `commit()` / `transaction()` 都被同一把 Python 锁串行化。

本轮改为：

- 每线程持有自己的 MySQL 连接；
- `transaction()` 复用当前线程连接并支持嵌套兼容；
- 普通 SQL 执行不再被 `_db_lock` 全局串行化；
- `_db_lock` 仅保留为兼容旧调用方的进程内锁，不再包住所有 SQL。

### 目的

释放 MySQL 自身的并发能力，避免类似以下场景被 Python 全局锁阻塞：

- 用户批量删除/标记日志；
- 同时有生图日志写入；
- 管理后台查询日志、图片、用户、access key；
- 后台清理任务和普通请求同时访问数据库。

这不会提升单张图片生成速度，因为单图瓶颈仍然是 GPU / ComfyUI 工作流，但能减少数据库访问层的人为串行等待。

## 2. 清理 SQLite PRAGMA 残留

涉及文件：

- `web/app.py`

### 改动内容

删除/替换了 MySQL 版本不适用的 SQLite 语句：

```sql
PRAGMA wal_checkpoint(TRUNCATE)
```

这些逻辑原先出现在：

- 应用 shutdown；
- `/api/admin/force-restart`；
- `/api/admin/graceful-restart`。

现在改为通过：

```python
db.commit_current_connection()
```

进行当前线程 MySQL 连接收尾提交。

## 3. 移除旧 JSON 自动迁移逻辑

涉及文件：

- `web/app.py`
- `web/db/schema.py`
- `web/db/__init__.py`

### 背景

项目当前已是 MySQL 版，历史 JSON 数据迁移不再通过 Web 启动自动执行，而是使用：

```text
scripts/sync_gui.py
```

### 改动内容

移除 `schema.py` 中旧的自动迁移逻辑：

- `migrate_from_json()`；
- `_load_json()`；
- `_load_json_list()`；
- `_load_txt_lines()`；
- `_import_json()`。

`app.py` 启动流程由：

```python
init_db()
migrate_from_json(data_dir)
```

调整为：

```python
init_db()
```

并添加说明：历史 JSON 数据请使用 `scripts/sync_gui.py` 手动迁移。

### 当前分层

现在推荐分层为：

```text
schema.py      = MySQL 连接、事务、建表、配置 KV 基础能力
operations.py  = 日常业务数据库读写
features/*.py  = 外挂功能 API，调用 operations.py
app.py         = 老主业务、启动、路由挂载
scripts/sync_gui.py = JSON / 旧数据到 MySQL 的手动迁移工具
```

## 4. 收敛数据库访问入口

涉及文件：

- `web/app.py`
- `web/db/operations.py`
- `web/features/_deps.py`
- `web/features/README.md`
- `web/features/access_keys.py`
- `web/features/llm_prompt_templates.py`

### 改动内容

- `app.py` 不再直接导入 `get_db`；
- `app.py` 中三处 `get_db().commit()` 改为 `db.commit_current_connection()`；
- `features` 注入上下文中移除了底层 `get_db`；
- 文档和注释中清理了旧的 SQLite / WAL / 共享单连接表述；
- 明确 features 不直接拿底层连接，如需新增数据库能力，应先封装到 `db/operations.py`。

### 目的

以后新增外挂模块时，数据库相关逻辑应优先放到：

```text
web/db/operations.py
```

feature 模块只调用业务函数，不直接写裸 SQL、不直接依赖 `db.schema.get_db`。

## 5. 生图排行榜 feature 注册与 MySQL 查询支持

涉及文件：

- `web/features/gen_leaderboard.py`
- `web/features/__init__.py`
- `web/db/operations.py`

### 改动内容

项目中已有：

```text
web/features/gen_leaderboard.py
```

但尚未注册，且依赖的 `db.get_gen_leaderboard()` 不存在。

本轮完成：

1. 在 `web/db/operations.py` 新增：

```python
def get_gen_leaderboard(limit=3, date_from=0, date_to=0, tz_offset=0) -> dict:
    ...
```

它直接查询 MySQL `gen_logs` 表，按 `login` 分组，统计 `status='success'` 的 `SUM(count)`。

2. 在 `web/features/__init__.py` 注册：

```text
gen-leaderboard
```

对应接口：

```text
GET /api/admin/features/gen-leaderboard?range=today
GET /api/admin/features/gen-leaderboard?range=weekly
```

### 验证结果

登录管理员后，以下接口均返回 200：

```text
/api/admin/features/gen-leaderboard?range=today
/api/admin/features/gen-leaderboard?range=weekly
```

管理后台中也能看到“🏆 生图排行榜”模块。

## 6. 启动 / 停止脚本修复

涉及文件：

- `start-all.bat`
- `stop-all.bat`

### `start-all.bat`

改为真正的一键启动流程：

1. 检查虚拟环境；
2. 自动寻找便携 MySQL 目录；
3. 检查 MySQL 是否运行；
4. MySQL 未运行时自动启动；
5. 等待 MySQL ready；
6. 启动 Web；
7. Redis 不启动、不作为依赖。

`Ctrl+C` 停止 Web 后的按键逻辑调整为：

| 按键 | 行为 |
|---|---|
| `N` | 重启 Web |
| `Y` | 关闭 Web |

MySQL 保持运行，需通过 `stop-all.bat` 或 MySQL 目录下 `stop_mysql.bat stop` 安全关闭。

### `stop-all.bat`

改为更保守的安全停止脚本：

- 提示用户在 Web 窗口中 `Ctrl+C`；
- 不强杀 Web，避免中断正在生成的任务；
- 调用 MySQL 安全关闭脚本；
- Redis 不处理。

## 7. MySQL 安全关闭脚本修复

涉及文件：

- `I:\cc\mysql-8.0.28-winx64\stop_mysql.bat`（项目目录外）

### 问题

脚本中原有：

```bat
echo [1] Set read-only & flush all tables to disk
```

Windows 批处理会把 `&` 当命令分隔符，导致出现：

```text
'flush' 不是内部或外部命令
```

### 修复

改为转义：

```bat
echo [1] Set read-only ^& flush all tables to disk
```

该问题只是显示命令的 bat 语法问题，MySQL 实际安全关闭流程此前已能成功执行。

## 8. Redis / 多 worker 结论

本轮确认：

- Redis 当前不是必需服务；
- Web 单进程 + MySQL 是当前推荐部署方式；
- 不建议直接使用多 worker。

原因：

- 当前任务队列、运行锁、WebSocket 订阅者、后台任务等仍是进程内状态；
- 多 worker 会导致每个 worker 有独立队列和锁，可能引发任务状态不一致；
- 单 GPU 生图吞吐瓶颈主要在 GPU / ComfyUI，不在 MySQL 或 Redis。

推荐策略：

```text
MySQL + 单 Web worker + 单 GPU 队列
```

Redis 保留备用，不默认启动。

## 9. 验证记录

### Python 编译检查

已执行并通过：

```bash
natureDrawImage-env/Scripts/python.exe -m py_compile web/app.py web/db/schema.py web/db/operations.py web/db/__init__.py web/features/_deps.py web/features/access_keys.py web/features/gen_leaderboard.py web/features/__init__.py web/features/llm_prompt_templates.py
```

### Web 启动验证

手动启动 MySQL 后，启动 Web：

```bash
natureDrawImage-env/Scripts/python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60
```

验证结果：

```text
/                                          200
/robots.txt                               200
/api/whoami                               200
/api/admin/features/gen-leaderboard?range=today 401（未登录时正常）
```

登录管理员后，管理后台接口大范围验证均为 200，包括：

```text
/api/admin/whoami
/api/admin/stats/generation?tz_offset=8
/api/admin/queue
/api/admin/features/gen-leaderboard?range=today
/api/admin/features/gen-leaderboard?range=weekly
/api/admin/access-keys
/api/admin/users
/api/admin/gen-logs
/api/admin/deletion-log
/api/admin/gc/status
/api/admin/llm
/api/features/llm-templates
```

浏览器控制台无 error。

## 10. 注意事项 / 后续建议

1. `web/email_auth.py` 仍有直接使用 `db.schema.get_db/config_get/config_set/transaction` 的逻辑，本轮未纳入重构。建议后续单独整理邮箱认证数据访问层。
2. 当前工作区存在一些 `frontend/` 改动和未跟踪文件，提交前应仔细区分哪些是本轮要提交的内容。
3. 推送前必须按项目 `CLAUDE.md` 要求做敏感文件检查，尤其注意：
   - `.env`
   - `llm_config.json`
   - `users.json` / `sessions.json` / `access_keys.json`
   - `*.db`
   - 运行时图片/缩略图/备份目录
4. 如果要继续增强并发，不建议先上 Redis 或多 worker；应先单独设计队列、分布式锁、WebSocket 广播和后台任务 leader 机制。

## 11. 当前已知外部状态

- Web 服务曾由本轮测试启动；如仍在运行，可在对应终端 `Ctrl+C` 停止。
- MySQL 曾由本轮测试直接启动；如需关闭，请使用：

```bat
I:\cc\mysql-8.0.28-winx64\stop_mysql.bat stop
```

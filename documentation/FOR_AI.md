# natureDrawImage — AI 快速上手指南

> 写给 AI 开发者的项目速查文档，想找什么功能直接搜关键词。

---

## 项目一句话

**二次元绘梦** — 一个接在 ComfyUI 前面的轻量级 Web 控制台，主打**多人共用一张显卡**。每个用户各选各的工作流、各写各的 prompt，但同一时刻只有一个人在用 GPU，其他人能实时看到进度。

后端：FastAPI + MySQL  
前端：Vue 3 SPA + Tailwind CSS  
项目根：`I:\cc\natureDrawImage-main-mysqlRefactoring`

---

## 快速定位 — 你想改什么？

| 你想做的事 | 去哪个文件 | 找什么 |
|---|---|---|
| 改**排队/队列**逻辑 | `web/app.py` | `_task_queue` (5312行)、`_run_lock` (5310行)、`_process_queue` (5819行)、`_run_task` (6385行)、`/ws/run` 路由 (5969行) |
| 改**ComfyUI 交互**（提交、中断、查历史、下载图片） | `web/app.py` | `submit_prompt` (2658行)、`interrupt_prompt` (2677行)、`get_history` (2682行)、`download_image` (2690行) |
| 改**LLM prompt 生成**（翻译、改写） | `web/app.py` | `translate_prompt` (2998行)、`_llm_google` (3146行)、`_llm_openai_compat` (3282行) |
| 改**用户认证**（GitHub OAuth / 邮箱 / 会话） | `web/app.py` + `web/email_auth.py` | `_auth_middleware` (1414行)、`_create_session` (332行)、`/auth/login` (3843行)、`/auth/callback` (3902行) |
| 改**前端生图页面**（按钮、输入框、设置面板） | `frontend/src/pages/Home.vue` | `<script setup>` 从 20行开始；模板从 ~1050行开始 |
| 改**前端管理后台** | `frontend/src/pages/Admin.vue` + `frontend/src/components/admin/` | 24 个 Section 组件，按功能拆分 |
| 改**数据库表结构或连接** | `web/db/schema.py` | `SCHEMA` 列表定义全部表 DDL，`get_db()` 管理连接 |
| 改**数据库 CRUD** | `web/db/operations.py` | ~3000 行，覆盖所有表的读写操作 |
| 改**样式/主题**（颜色、透明度、布局） | `frontend/src/assets/style.css` | Tailwind + CSS 自定义属性 |
| 改**路由/API 端点** | `web/app.py` | `@app.get/post/put/delete/ws()` 装饰器 |
| 改**前端路由** | `frontend/src/router/index.ts` | 6 条路由：Home、Admin、EmailLogin、Privacy、Maintenance |

---

## 目录结构速览

```
根目录/
├── web/                          # Python 后端
│   ├── app.py                    # ★ 主程序 (~9500行) — 路由、队列、WS、ComfyUI、LLM
│   ├── email_auth.py             # 邮箱认证、TOTP、邀请码
│   ├── db/
│   │   ├── schema.py             # MySQL 建表 + 连接池
│   │   └── operations.py         # 数据访问层 (CRUD)
│   ├── features/                 # ★ 插件化功能模块
│   │   ├── __init__.py           # register_all(app) — 挂载入口
│   │   ├── _deps.py              # 依赖注入 (auth, paths)
│   │   ├── health_check.py       # 健康检查
│   │   ├── access_keys.py        # 访问密钥
│   │   ├── llm_prompt_templates.py  # LLM 模板
│   │   ├── gen_stats.py          # 统计
│   │   └── gen_leaderboard.py    # 排行榜
│   └── static/dist/              # Vue SPA 构建产物
│
├── frontend/                     # Vue 3 SPA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.vue          # ★ 主页面 (~1300行, script + template)
│   │   │   └── Admin.vue         # 管理后台
│   │   ├── components/
│   │   │   ├── CharStylePicker.vue   # 画风/角色选择器
│   │   │   ├── GalleryGrid.vue       # 画廊网格
│   │   │   ├── MyWorksGrid.vue       # 我的作品网格
│   │   │   ├── GPUBar.vue            # GPU 状态条
│   │   │   ├── Img2ImgUpload.vue     # 图生图上传
│   │   │   ├── Lightbox.vue          # 图片灯箱
│   │   │   ├── WorkflowPicker.vue    # 工作流选择器
│   │   │   ├── PresetManager.vue     # prompt 预设管理
│   │   │   ├── TotpSettings.vue      # TOTP 设置
│   │   │   ├── FeaturedGrid.vue      # 精选展示
│   │   │   └── admin/                # 24 个管理后台子组件
│   │   ├── api/
│   │   │   ├── client.ts         # fetch 封装
│   │   │   ├── endpoints.ts      # 全部 API 调用函数
│   │   │   └── types.ts          # TS 类型定义
│   │   ├── stores/user.ts        # Pinia 用户状态
│   │   ├── router/index.ts       # 前端路由
│   │   └── assets/style.css      # 全局样式
│   └── vite.config.ts            # Vite 配置
│
├── start-all.bat                 # 一键启动
├── stop-all.bat                   # 安全关闭
├── start.py                       # Python 启动入口
├── requirements.txt
├── scripts/                       # SQLite→MySQL 迁移工具
│   ├── sync_common.py
│   ├── sync_gui.py
│   └── sync_sqlite_to_mysql.py
├── documentation/                 # 更多文档
└── .env                           # 环境变量（勿提交）
```

---

## 核心工作流 — 用户点"生图"后发生了什么

```
用户点「开始生成」
    │
    ▼
Vue 端 prepareGen() → 收集 prompt / 风格 / 工作流 / 参数
    │
    ▼
WebSocket /ws/run 发送到后端
    │
    ▼
后端接收 → 检查重复提交 → 入队 _task_queue
    │
    ▼
_process_queue() 从队列取一个
    │  (asyncio.Lock 保证单 GPU)
    ▼
_run_task() → LLM 翻译/改写 prompt → 加载 ComfyUI 工作流 JSON
    │                        → 注入 prompt / 分辨率 / checkpoint
    │                        → submit_prompt() → ComfyUI API
    │
    ▼
_wait_for() → 轮询 ComfyUI WebSocket 进度 → 前端实时显示
    │
    ▼
ComfyUI 完成 → get_history() 取结果 → 下载图片
    │
    ▼
记录到 user_images / gen_logs / 数据库通知
    │
    ▼
前端收到完成消息 → 刷新"我的作品" → 播放通知音
```

---

## 队列系统关键结构

**全局变量**（都在 `web/app.py`）：

```python
_run_lock = asyncio.Lock()            # 单 GPU 锁
_task_queue: List[Dict]               # 等待队列
_current_run_task: asyncio.Task | None # 正在执行的 _process_queue 任务
```

队列项 `Dict` 结构：
```python
{
    "github_id": str,       # 用户 ID
    "ws_id": int,           # WebSocket 连接 ID
    "status": "waiting" | "running",
    "created_at": float,    # 入队时间戳
    "req": RunRequest,      # 原始请求
    "client_ip": str,
    "prompt_id": str | None # ComfyUI prompt_id
}
```

**关键函数行号：**

| 函数 | 行号 | 做什么 |
|---|---|---|
| `_save_queue_state()` | 5347 | 队列持久化到 JSON |
| `_load_queue_state()` | 5364 | 启动时恢复队列 |
| `_recover_queue_on_startup()` | 5381 | 启动恢复 + 超时清理 |
| `_process_queue()` | 5819 | 循环取任务执行 |
| `_run_task()` | 6385 | 执行单个任务（LLM → 工作流 → 提交 ComfyUI） |
| `_wait_for()` | 6739 | 等待 ComfyUI 完成 |
| `_broadcast_queue()` | 5431 | 广播队列状态到所有 WS 客户端 |

---

## app.py 内部模块划分（按行号）

```
 1-38   print() 打时间戳补丁、加载 .env
40-110  配置常量（ComfyUI/Web 地址等）
114-192 MySQL 数据层导入、PIL 安全限制、反代 IP 配置、兼容常量
192-282 gen_log / 密钥 / 已删图片 / 用户图片 操作函数
284-438 用户 & 会话管理（GitHub OAuth 相关）
440-473 封禁 / 精选操作
477-545 http 客户端、限流配置
546-720 公告 / 维护模式 / 自定义 Head
722-848 画风 / 角色 / 分辨率 配置
848-894 工作流元数据
895-1070 LLM 配置 + API Key 加解密
1071-1206 举报 / IP / IP 白名单 / 精选 / 创建者映射
1207-1420 FastAPI 应用创建、各中间件（gzip、限流、鉴权等）
1623-2286 GC 循环、启动清理、备份循环、shutdown
2286-2314 外挂功能注册、WebP 转码
2320-2600 删除记录 / 缩略图 / 图片服务
2602-2702 KV state / ComfyUI helper 函数
2704-2963 workflow → prompt API 提取
2963-3349 LLM 翻译（Google AI Studio / OpenAI 兼容）
3349-3364 GitHub API 工具
3364-3998 路由 + GitHub OAuth 流程
3998-4109 claim-key / dev_login
4109-4261 工作流列表 / 缩略图 / 风格 / 角色
4261-4520 ComfyUI 输出目录浏览
4520-4786 Fork 工作流 / 分辨率注入 / 当前工作流
4786-4935 Lora 链接 / 图片服务
4935-5196 GPU / 翻译 / interrupt / 管理员授权 / 强制重启 / 图片压缩
5196-5262 图生图上传
5262-5431 RunRequest / 队列核心状态（锁、队列、持久化、恢复）
5431-5692 广播 / 通知 / emit / push_status
5692-5817 /ws/status WebSocket（只读状态订阅）
5819-5967 _process_queue() 主队列处理器
5969-6385 /ws/run WebSocket（任务提交 + 进度推送）
6385-6737 _run_task()（LLM → 工作流 → ComfyUI 提交）
6739-6832 _wait_for() 等待 ComfyUI 完成
6833-7139 辅助 / 验证 / WS 关闭清理
7139-7395 图片删除 / 管理后台用户管理
7395-7531 封禁 / IP 管理 / 近期活动
7531-7660 管理后台图片操作
7660-7937 批量删除 / 精选管理
7937-8032 限流 / GC / 孤立文件扫描
8032-8094 GC 功能
8094-8385 公告 / 维护 / 自定义 Head / 风格 / 角色 / 分辨率
8385-8480 缩略图上传 / 校验
8478-8735 工作流管理 / 元数据 / 批量缩略图
8735-8982 LLM 配置管理 / 测试 / 模型列表
8982-9090 举报管理 / 生图日志
9090-9370 生图日志孤分析 / 缩略图回填 / 删除
```

---

## 前端 Home.vue 内部模块划分

```
 <script> 部分：
 20-56    Store / 组合式函数 / Tab 状态
 58-125   响应式状态（模式、prompt、进度、队列等）
125-137   WebSocket / 通知状态
138-222   设置相关（声音、背景图、缩放、紧凑、缩略图、透明度等）
234-320   onMounted / onUnmounted 生命周期
333-412   初始化 / 工作流加载 / 模式切换
439-463   分辨率 / LLM 模板 加载
463-583   轮询 / WebSocket / GPU / 通知
598-739   生图核心（prepareGen → startRun → actuallyStartRun）
739-872   handleMsg / pushHistory / resetRunUiState / finishRun / cooldown
874-1012  访问密钥 / 暗色模式 / 设置 / 背景图 / 改密码 / 登出
1017-1051 公告 / textarea 同步 / Fork / 预设填充

<template> 部分：
~1050-1098 顶部（GPU 条、在线人数、暗色模式、通知铃）
~1098-1128 模式选择（文生图/图生图）
~1128-1270 生图表单（prompt 输入、风格/角色选择、工作流、分辨率）
~1270-1350 生成中状态 / 进度 / 结果展示
~1350-1510 设置弹窗（主设置 / 外观子设置 / 密码 / TOTP）
~1510-1530 底部 Tab 栏
```

---

## 数据库表结构

全部定义在 `web/db/schema.py` 的 `SCHEMA` 列表中。

| 表名 | 用途 | 主键 |
|---|---|---|
| `users` | GitHub 用户 | `github_id` |
| `email_users` | 邮箱注册用户 | `email` |
| `sessions` | 登录会话 | `token` |
| `access_keys` | 访问密钥 | `key` |
| `user_images` | 生成的图片记录 | `id` (auto) |
| `deleted_images` | 软删除标记 | `id` (auto) |
| `gen_logs` | 生图日志 | `log_id` |
| `queue_items` | 队列持久化 | `id` (auto) |
| `notifications` | 用户通知 | `id` (auto) |
| `styles` | 画风预设 | `id` (auto) |
| `characters` | 角色预设 | `id` (auto) |
| `resolutions` | 分辨率预设 | `id` (auto) |
| `workflow_meta` | 工作流元数据 | `id` (auto) |
| `config` | KV 配置 | `(section, key)` |
| `featured` | 精选图片 | `id` (auto) |
| 更多... | 封禁、举报、邀请码等 | |

数据访问层在 `web/db/operations.py`（~3000行），所有 CRUD 都在那里。

---

## 配置 (.env)

见 `.env.example`，关键项：

| 配置项 | 说明 |
|---|---|
| `COMFYUI_HOST/PORT` | ComfyUI 地址 |
| `WEB_HOST/PORT` | 本服务端口 |
| `OUTPUT_DIR_STR` | ComfyUI 输出目录 |
| `COMFYUI_WORKFLOWS_DIR` | 工作流目录 |
| `GITHUB_CLIENT_ID/SECRET` | GitHub OAuth |
| `SITE_URL` | 站点域名 |
| `DEV_MODE` | 1=跳过 OAuth（开发用） |
| `MYSQL_*` | 数据库连接 |
| `SMTP_*` | 邮箱发信 |
| `LLM_ENCRYPTION_KEY` | LLM API Key 加密密钥 |

---

## 构建与启动

```bash
# 一键启动
start-all.bat

# 仅启动 Web
start-web.bat

# 安全关闭
stop-all.bat

# 前端构建
cd frontend
pnpm build          # 输出到 web/static/dist/
pnpm dev            # 开发模式，端口 5173

# 初始化数据库（首次）
init-db.bat
```

---

## 给 AI 的提示

1. **想找后端功能** → 行号范围在 `web/app.py`，搜函数名或行号
2. **想找前端界面** → 去 `frontend/src/pages/Home.vue`
3. **想管理数据库** → 表结构在 `schema.py`，读写用 `operations.py`
4. **想加新功能但怕 app.py 再膨胀** → 在 `web/features/` 建新文件，参考现有 feature 的写法
5. **队列超时 / 死锁 / 断连** → 看 `_process_queue`、`_run_task`、`_clear_ws_state` 这三个函数
6. **LLM prompt 不对** → 看 `_run_task` 里 LLM 那一段 + `translate_prompt` 函数
7. **SSL/HTTPS** → 本项目用 Nginx 反代或 Cloudflare Tunnel，不直接配置

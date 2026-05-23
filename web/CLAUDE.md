[根目录](../../CLAUDE.md) > [natureDrawImage-main](../) > **web**

# web 模块

> 自然语言生图 Web 控制台 -- 单文件 FastAPI 后端 + 原生 JS 前端

## 模块职责

提供 HTTP API + WebSocket + 静态文件服务，作为 ComfyUI 的 Web 前端。核心能力：

1. **用户认证**：GitHub OAuth 登录/会话管理/访问密钥（无密码模式）
2. **工作流管理**：扫描 ComfyUI 工作流目录、缩略图、Lora 链接、选中/摘要
3. **自然语言翻译**：LLM 将自然语言翻译为 Danbooru tags（支持 LM Studio / Google AI / 自定义 OpenAI API）
4. **生图代理**：通过 WebSocket 提交 ComfyUI 生成任务，实时推送进度、节点状态、生成结果
5. **输出画廊**：浏览 ComfyUI 输出目录、灯箱查看、Fork 工作流、精选展示
6. **管理后台**：用户管理、IP 封禁、图片管理、举报处理、精选维护、限流配置、画风管理、公告系统
7. **基础安全**：IP 限流、CSRF 校验、路径遍历防护、请求体大小限制、维护模式

## 入口与启动

- **入口文件**：`app.py`
- **启动命令**：
  ```bash
  uv run web/app.py --host 0.0.0.0 --port 8080
  # 或通过 uvicorn
  uvicorn web.app:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips 127.0.0.1
  ```
- **Windows 脚本**：`../start.bat`（自动循环重启、检查 venv 和依赖）
- **FastAPI 实例创建**：`app = FastAPI(title="自然语言生图")`（第 929 行）
- **生命周期**：
  - `startup`：启动 GC 循环和过期数据清理任务
  - `shutdown`：关闭共享 httpx 客户端
- **静态文件挂载**：`app.mount("/static", StaticFiles(directory=str(STATIC_DIR)))` -- 提供 `favicon.avif`、`chiz.webp` 等

## 对外接口

### 公共 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 用户前端 SPA |
| `GET` | `/access` | 访问密钥输入页 |
| `GET` | `/auth/login` | GitHub OAuth 登录跳转 |
| `GET` | `/auth/callback` | OAuth 回调处理 |
| `POST` | `/auth/logout` | 登出 |
| `GET` | `/auth/dev_login` | 开发测试登录（仅 DEV_MODE） |
| `POST` | `/api/auth/claim-key` | 访问密钥认领 |
| `GET` | `/api/whoami` | 当前用户信息 |
| `GET` | `/api/workflows` | 列出工作流 |
| `GET` | `/api/workflows/current` | 工作流摘要 + 默认分辨率 + 内置 prompt |
| `POST` | `/api/workflows/select` | 选中工作流 |
| `GET` | `/api/thumbnail` | 工作流缩略图 |
| `GET` | `/api/styles` | 画风列表 |
| `GET` | `/api/style_thumbnail` | 画风缩略图 |
| `GET` | `/api/resolutions` | 分辨率预设 |
| `GET` | `/api/output/list` | 输出目录分页（mtime 倒序） |
| `GET` | `/api/output/file` | 取输出图（自动 WebP 转码） |
| `GET` | `/api/output/creator` | 查询生图者 IP |
| `GET` | `/api/output/meta` | 读 PNG 元数据（正向 prompt） |
| `GET` | `/api/output/featured` | 精选列表 + 提示语 |
| `POST` | `/api/output/fork` | 从 PNG 抽出 workflow |
| `GET` | `/api/image` | 代理 ComfyUI 实时输出图 |
| `GET` | `/api/gpu` | nvidia-smi GPU 状态 |
| `GET` | `/api/announcement` | 当前公告 |
| `POST` | `/api/translate` | LLM 翻译（自然语言 -> tags） |
| `POST` | `/api/report` | 举报图片 |
| `POST` | `/api/interrupt` | 中断当前任务 |
| `POST` | `/api/img2img/upload` | 图生图上传 |
| `GET` | `/api/my-queue` | 我的队列位置 |
| `GET` | `/api/my-images` | 我的作品列表 |
| `DELETE` | `/api/my-images` | 删除我的作品 |

### WebSocket 端点

| 路径 | 方向 | 说明 |
|------|------|------|
| `/ws/run` | 客户端 -> 服务端 | 提交生图请求（工作流路径、prompt、分辨率、画风等） |
| `/ws/run` | 服务端 -> 客户端 | 推送：log、llm_chunk、progress、image、done、error |
| `/ws/status` | 服务端 -> 客户端 | 订阅全局队列状态（当前任务、进度、等候人数） |

### 管理 API（需反向代理鉴权保护）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/admin` | 管理页面 |
| `GET/POST` | `/api/admin/limits` | 限流配置 |
| `GET/POST` | `/api/admin/styles` | 画风管理 |
| `GET/POST` | `/api/admin/resolutions` | 分辨率预设 |
| `GET/POST` | `/api/admin/workflow_meta` | 工作流缩略图 & Lora 链接 |
| `GET` | `/api/admin/workflow_files` | 扫描工作流目录 |
| `POST` | `/api/admin/workflow_rename` | 重命名工作流 |
| `POST` | `/api/admin/wf_thumbnail` | 上传工作流缩略图 |
| `POST` | `/api/admin/style_thumbnail` | 上传画风缩略图 |
| `GET/POST` | `/api/admin/llm` | LLM 配置 |
| `POST` | `/api/admin/llm/test` | 测试 LLM 连接 |
| `POST` | `/api/admin/llm/models` | 获取 LLM 模型列表 |
| `GET/POST` | `/api/admin/announcement` | 公告管理 |
| `GET/POST` | `/api/admin/maintenance` | 维护模式 |
| `GET/POST` | `/api/admin/custom_head` | 自定义 `<head>` 注入 |
| `GET` | `/api/admin/bans` | 封禁列表 |
| `POST` | `/api/admin/ban` / `unban` | 加/解封 IP |
| `GET` | `/api/admin/images_by_ip` | 查看某 IP 生图记录 |
| `GET` | `/api/admin/recent` | 全输出图分页 |
| `POST` | `/api/admin/delete` | 删图 |
| `POST` | `/api/admin/delete_batch` | 批量删图 |
| `GET/POST` | `/api/admin/featured/{add,remove,reorder}` | 精选维护 |
| `GET` | `/api/admin/reports` | 待处理举报 |
| `POST` | `/api/admin/report/resolve` | 处理举报 |
| `GET` | `/api/admin/users` | 用户列表 |
| `POST` | `/api/admin/users/{ban,unban,set_role}` | 用户管理 |
| `GET/POST` | `/api/admin/access-keys/{generate,delete,enable,reveal}` | 访问密钥管理 |
| `GET/DELETE` | `/api/admin/gen-logs` | 生图日志 |
| `POST` | `/api/admin/gc` | 手动 GC |
| `POST` | `/api/admin/force-restart` | 强制重启 |

### WebSocket 协议 (`/ws/run`)

客户端首包：
```json
{
  "workflow_path": "文生图/某个工作流.json",
  "inline_workflow": null,
  "direct_prompt": "1girl, ...",
  "nl_prompt": "一个穿红裙的女孩",
  "rewrite": false,
  "width": 832,
  "height": 1216,
  "style_tags": "by xxx",
  "image_data_url_1": null,
  "image_data_url_2": null
}
```

服务端推送消息类型：`log`、`llm_start`、`llm_chunk`、`llm_done`、`prompt_id`、`progress`、`image`、`done`、`error`。

## 关键依赖与配置

### Python 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `fastapi` | 0.136+ | Web 框架 |
| `uvicorn[standard]` | 0.47+ | ASGI 服务器 |
| `httpx` | 0.28+ | HTTP 客户端（ComfyUI API / GitHub API / LLM 调用） |
| `websockets` | 16.0+ | WebSocket 客户端（连接 ComfyUI） |
| `pydantic` | 2.x | 数据校验 |
| `pillow` | 12.2+ | 图片处理（WebP 转码、缩略图、分辨率校验） |

### 启动配置（app.py 顶部常量）

- `COMFYUI_HOST` / `COMFYUI_PORT`：ComfyUI 服务地址（默认 127.0.0.1:8188）
- `OUTPUT_DIR_STR`：ComfyUI 输出目录路径
- `COMFYUI_WORKFLOWS_DIR`：ComfyUI 工作流扫描目录
- `WF_DIR_TXT2IMG` / `WF_DIR_IMG2IMG`：文生图/图生图工作流子目录名
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`：GitHub OAuth 凭证
- `SITE_URL`：站点域名（用于 OAuth 回调）
- `TRUSTED_PROXY_IPS`：信任的反代 IP（X-Forwarded-For 解析）

### 中间件链（按注册顺序）

1. `GZipMiddleware`（第 931 行）-- 文本响应 gzip 压缩
2. `_body_limit_middleware`（第 937 行）-- 请求体 10MB 限制
3. `_maintenance_middleware`（第 973 行）-- 维护模式拦截
4. `_no_index_headers`（第 1010 行）-- 禁止搜索引擎索引
5. `_image_rate_limit`（第 1038 行）-- 图片端点滑动窗口限流
6. `_auth_middleware`（第 1069 行）-- 管理路径鉴权 + CSRF 校验

## 数据模型

### 核心数据实体

- **用户** (`users.json`)：`{github_id: {login, email, avatar_url, role, banned, banned_reason, created_at}}`
- **会话** (`sessions.json`)：`{token: {github_id, expires_at, access_granted}}`
- **访问密钥** (`access_keys.json`)：`{keys: {key: {used_by, created_at, enabled}}}`
- **用户图片** (`user_images.json`)：`{github_id: [{path, prompt, time}]}`（每人最多 200 条）
- **删除标记** (`deleted_images.json`)：`{github_id: [path, ...]}`
- **生图日志** (`gen_log.json`)：`{log_id: {github_id, login, prompt, workflow, count, status, client_ip, created_at}}`（最多 2000 条）
- **队列状态** (`queue_state.json`)：`{id_counter, items: [{id, github_id, login, workflow_name, client_ip, status, created_at}]}`

### 配置实体

- **限流** (`limits.json`)：生图冷却、图片限流窗口/上限、举报限制
- **画风** (`styles.json`)：`[{name, tags, alias, thumbnail?}]`
- **分辨率** (`resolutions.json`)：`{presets: [{w, h, label}]}`
- **LLM** (`llm_config.json`)：provider, endpoint, api_key, model
- **工作流元数据** (`workflow_meta.json`)：`[{workflow, thumbnail, lora_link?, display_name?}]`
- **公告** (`announcement.json`)：`{enabled, title, content}`
- **维护模式** (`maintenance.json`)：`{enabled, message}`

### IP 封禁

- `banned_ips.txt` -- 每行一个 IP
- `creator_ips.txt` -- `相对路径/IP` 映射（记录每张输出图的生图者 IP）

## 测试与质量

- **无自动化测试**。测试策略详见根 `CLAUDE.md` 的测试策略部分。
- 代码质量：Python 广泛使用类型注解；函数命名 `_` 前缀表示内部函数。

## 常见问题 (FAQ)

### Q: 为什么是单文件后端？
A: 项目追求零构建步骤、快速迭代。约 6500 行的 `app.py` 包含了所有路由、中间件、工具函数。对于当前功能规模是可接受的，但如果继续增长，建议按功能域拆分为多个模块（如 `auth.py`、`comfyui.py`、`llm.py`、`admin.py`）。

### Q: 管理后台如何保护？
A: 项目本身**不做鉴权**（`/admin` 和 `/api/admin/*` 公开可达）。生产部署**必须**通过反向代理（Cloudflare Access、nginx auth_basic 等）做访问控制。

### Q: 数据如何持久化？
A: 所有数据以 JSON/TXT 文件存储在 `web/` 目录下。改动的文件在 `.gitignore` 中，不纳入版本控制。JSON 写入采用原子操作（先写 `.tmp` 再 `os.replace`）。

### Q: 前端如何工作？
A: 前端使用原生 JavaScript（无框架），通过 Tailwind CSS CDN 做样式。页面切换通过简单的 Tab 机制（CSS `display:none/block`）。灯箱、画廊、画风选择等交互逻辑均内嵌在 HTML `<script>` 标签中。

## 相关文件清单

```
web/
├── app.py                      # FastAPI 后端（核心，~6500行）
├── requirements.txt            # Python 依赖
├── CLAUDE.md                   # 本文件
├── static/
│   ├── index.html              # 用户前端 SPA（生图、画廊、个人中心）
│   ├── admin.html              # 管理员控制台
│   ├── maintenance.html        # 维护模式页面
│   ├── favicon.avif            # 站点图标
│   └── chiz.webp               # 备用站点图标
├── users.json                  # 用户数据（gitignored）
├── sessions.json               # 会话数据（gitignored）
├── access_keys.json            # 访问密钥（gitignored）
├── user_images.json            # 用户-图片映射
├── deleted_images.json         # 用户删除记录
├── gen_log.json                # 生图日志
├── queue_state.json            # 任务队列状态
├── featured.txt                # 精选图片路径（gitignored）
├── banned_ips.txt              # 封禁 IP（gitignored）
├── creator_ips.txt             # 生图者 IP 映射（gitignored）
├── limits.json                 # 限流配置（gitignored）
├── styles.json                 # 画风配置（gitignored）
├── resolutions.json            # 分辨率预设（gitignored）
├── llm_config.json             # LLM 配置（gitignored）
├── announcement.json           # 公告配置（gitignored）
├── workflow_meta.json          # 工作流缩略图+Lora链接（gitignored）
├── maintenance.json            # 维护模式配置（gitignored）
├── custom_head.json            # 自定义HTML头（gitignored）
├── thumbnails/                 # 工作流缩略图（gitignored）
├── style_thumbnails/           # 画风缩略图（gitignored）
└── lora_links/                 # Lora链接（旧方式，gitignored）
```

## 变更记录 (Changelog)

| 日期 | 变更内容 |
|------|----------|
| 2026-05-22 | 初始化模块 CLAUDE.md。已扫描：API 路由（90+端点）、WebSocket 协议、中间件链、数据模型、前端页面。缺口：HTML 内嵌 JS 的具体实现细节未逐行分析（前端 JS 逻辑包含在 index.html 和 admin.html 的 `<script>` 标签中，约数千行）。 |

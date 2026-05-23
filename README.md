# natureDrawImage

> 基于 [afoim/natureDrawImage](https://github.com/afoim/natureDrawImage) 的改进版本，增加了用户认证系统与更多管理功能。

一个塞进 ComfyUI 前面的轻量级网页控制台，主打**多人共用一台显卡**的场景：每个浏览器各选各的工作流、各写各的 prompt，但同一时刻只有一个人在用 GPU，其它人能实时看到当前任务进度。

—— 单文件 FastAPI 后端 + Tailwind CDN 前端，无构建步骤。

## 与原项目的差异

| 方面 | 原项目 | 本 Fork |
|------|--------|---------|
| 用户认证 | 无，完全公开 | GitHub OAuth 登录 |
| 图生图 | 不支持 | 支持（上传单图/双图） |
| 用户中心 | 无 | 我的作品、我的队列 |
| 管理功能 | 基础管理 | +用户管理、队列管理、维护模式、生图日志、自定义 `<head>` |
| 配置方式 | 硬编码在 app.py | `.env` 环境变量 |
| 部署方式 | 手动 `uv run` | + `start.bat` 自动重启脚本 |

## 它能做什么

- **GitHub OAuth 登录**：用户通过 GitHub 账号登录
- **图生图**：上传单图或双图，自动匹配工作流生成
- **工作流管理**：列出 / 搜索 ComfyUI 已保存的工作流，支持缩略图、Lora 链接配置。「无 Lora」字样的工作流自动置顶。支持文生图/图生图分类
- **画风一键切换**：管理员预配画风卡片（tags + 缩略图），用户点击即选，tags 自动追加到 prompt 最前面
- **两种 prompt 写法**：
  - 直接 Tag：选择工作流后内置 prompt 自动填入，可直接编辑
  - 自然语言翻译：LLM 把中/英文描述翻译成 SD/Pony/Illustrious tag
  - 改写模式：让 LLM 基于现有 prompt 整体重写（智能增删）
- **多 LLM 后端**：支持 LM Studio（本地）、Google AI Studio、自定义 OpenAI 兼容 API，管理面板切换
- **分辨率管理**：管理员配置允许的分辨率预设，前端只能从预设中选择，后端强制校验
- **WebSocket 实时进度**：节点名 + 步进进度条 + 取消按钮
- **GPU 状态条**（顶栏）：轮询 `nvidia-smi`，显示 GPU/VRAM 占用、温度、功耗、风扇、频率
- **全局并发锁 + 旁观模式**：同一时刻只允许一个生图任务，其它页面在状态横幅里实时看到当前任务进度
- **ComfyUI 输出目录浏览**：分页加载，自建灯箱，左右键翻图，异步注入正向 prompt，可一键 Fork 工作流二改
- **Fork 工作流**：从输出 PNG 抽出 workflow，临时存在浏览器内存里提交生图；Fork 时自动匹配并还原画风选择
- **精选展示**：站长在 `/admin` 维护一组「优秀作品」，可拖拽排序、自定义提示语，游客首页可折叠展示
- **用户中心**：查看我的作品、我的队列位置、删除自己的作品
- **公告系统**：管理员可开关公告、设置标题和内容
- **限流配置**：单 IP 生图冷却 + 出图端点滑动窗口限流，全部在管理面板实时改
- **生图者溯源**：每张输出图关联生图者（GitHub 用户或 IP），灯箱/管理面板可见
- **IP 封禁 / 删图 / 批量删图**：管理面板手动维护，被封 IP 提交直接拒绝
- **用户管理**：管理员可封禁/解封用户、设置角色
- **维护模式**：一键开关，自定义维护页消息（支持 Markdown）
- **giscus 评论区**
- **WebP 自动转码**：输出图、缩略图自动转 WebP 节省带宽
- **全局禁止搜索引擎索引**

## 速览

```
┌─ GPU 状态条（nvidia-smi）
├─ 公告横幅
├─ 全局任务进度（其它人正在跑 → 此处可见）
├─ 工作流卡片网格（搜索 + 选中高亮，支持文生图/图生图分类）
├─ 画风卡片（一键切换，有别名的优先显示）
├─ 生图表单
│  ├─ 直接 Tag（工作流内置 prompt 自动填入）
│  ├─ 自然语言描述（LLM 翻译/改写）
│  ├─ ☑ 改写模式
│  ├─ 图生图上传区（单图/双图）
│  ├─ 分辨率预设按钮
│  └─ ▶ 开始生成 / ✕ 取消
├─ 进度区（日志 + LLM 流式 + 进度条）
├─ 结果区（本次生成的图）
├─ 精选展示（站长维护，可折叠）
├─ 输出目录画廊（懒加载 + 灯箱 + Fork）
├─ 我的作品 / 我的队列
└─ 评论区
```

## 前置要求

- **Python 3.10+**
- **ComfyUI** 已安装并正常运行
- **NVIDIA GPU**（用于 `nvidia-smi` 状态显示）
- **GitHub OAuth App**（用于用户登录，在 [GitHub Settings](https://github.com/settings/developers) 创建）
- **LLM 服务**（可选）：LM Studio / Google AI Studio / 任意 OpenAI 兼容 API

## 部署步骤

### 1. 安装依赖

推荐 [uv](https://github.com/astral-sh/uv)：

```bash
uv pip install -r web/requirements.txt
```

或用 pip：

```bash
pip install -r web/requirements.txt
```

依赖列表（`web/requirements.txt`）：

```
fastapi
uvicorn[standard]
httpx
websockets
pydantic
pillow
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入实际配置：

```bash
cp .env.example .env
```

`.env` 文件说明：

```bash
# ========== ComfyUI 连接 ==========
COMFYUI_HOST=127.0.0.1
COMFYUI_PORT=8188

# ========== LM Studio（可选） ==========
LMS_HOST=127.0.0.1
LMS_PORT=1234

# ========== Web 服务 ==========
WEB_HOST=127.0.0.1
WEB_PORT=8080

# ========== 目录路径（必填） ==========
OUTPUT_DIR_STR=C:\path\to\ComfyUI\output
COMFYUI_WORKFLOWS_DIR=C:\path\to\ComfyUI\user\default\workflows

# ========== 工作流子目录 ==========
WF_DIR_TXT2IMG=文生图
WF_DIR_IMG2IMG=图生图

# ========== GitHub OAuth（必填） ==========
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
SITE_URL=http://localhost:8080

# ========== 开发模式 ==========
DEV_MODE=0

# ========== 信任的代理 IP ==========
TRUSTED_PROXY_IPS=127.0.0.1,::1

# ========== LLM API Key 加密密钥（可选） ==========
LLM_ENCRYPTION_KEY=
```

### 3. 启动

```bash
# Windows：直接双击 start.bat（自动重启、检查依赖）
start.bat

# 或手动启动
uv run web/app.py

# 监听所有地址（局域网 / 反向代理后端）
uv run web/app.py --host 0.0.0.0

# 已配好反向代理鉴权，跳过启动确认
uv run web/app.py --host 0.0.0.0 --i-have-configured-auth

# 开发模式：保存 .py 自动重启
uv run web/app.py --host 0.0.0.0 --reload
```

打开 <http://127.0.0.1:8080>。

### 4. 配置反向代理鉴权（生产部署必须）

管理路由 `/admin` 与 `/api/admin/*` 由内置的 GitHub OAuth 管理员角色保护。但如果你需要额外的安全层，建议在反向代理上做访问控制：

- **Cloudflare Access / Zero Trust**（推荐）
- **nginx auth_basic / auth_request**
- **IP 白名单**
- **私有网络**（Tailscale / WireGuard）

nginx 示例：

```nginx
location / {
  proxy_pass http://127.0.0.1:8080;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header X-Forwarded-For $remote_addr;
}
```

### 5. 后续配置（管理面板）

以下配置全部在 `/admin` 管理面板中在线完成，无需改代码：

- **画风**：添加画风卡片（tags + 缩略图）
- **分辨率**：配置允许的分辨率预设
- **工作流缩略图 & Lora 链接**：为工作流上传缩略图、配置 Lora 链接、重命名工作流
- **LLM**：切换 LLM 服务商、配置 API Key
- **限流**：调整生图冷却、图片限流参数
- **公告**：开关公告、设置内容
- **精选**：维护精选展示
- **用户管理**：封禁/解封用户、设置管理员角色

## 管理控制台 `/admin`

| 区块 | 功能 |
|---|---|
| 公告管理 | 开关公告 + 标题 / 内容编辑 |
| 分辨率管理 | 增删分辨率预设（宽 × 高 + 标签），自动保存 |
| 画风管理 | 增删画风卡片（tags + 别名 + 缩略图上传），自动保存 |
| 工作流缩略图 & Lora 链接 | 自动扫描 ComfyUI 目录，上传缩略图、配置链接、重命名工作流 |
| LLM 配置 | LM Studio / Google AI Studio / 自定义 API 切换，测试连接 |
| 限流配置 | 生图冷却、图片限流、GPU 轮询间隔、精选提示语 |
| 用户管理 | 用户列表、封禁/解封、设置管理员角色 |
| 队列管理 | 查看当前队列、取消任务、强制解锁 |
| 封禁 IP | 时间线显示、手动封禁/解封、查看某 IP 生图记录、批量删图 |
| 精选展示 | 拖拽排序 |
| 生图记录 | 全输出图分页浏览 + 生图日志查询 |
| 维护模式 | 一键开关维护页，自定义 Markdown 消息 |
| 自定义 `<head>` | 注入自定义 HTML 到所有页面 `<head>` |

## 目录结构

```
web/
├── app.py                  FastAPI 后端（单文件）
├── requirements.txt        Python 依赖
├── workflow_meta.json      工作流元数据（缩略图 + Lora 链接映射）
├── static/
│   ├── index.html          用户前端
│   ├── admin.html          管理控制台
│   ├── maintenance.html    维护模式页面
│   ├── favicon.avif
│   └── chiz.webp
├── thumbnails/             工作流缩略图
├── style_thumbnails/       画风缩略图
├── lora_links/             Lora 链接（旧方式，已被 workflow_meta.json 取代）
├── users.json              用户数据（gitignored）
├── sessions.json           会话 token（gitignored）
├── user_images.json        用户-图片映射（gitignored）
├── deleted_images.json     用户删除记录（gitignored）
├── gen_log.json            生图日志（gitignored）
├── queue_state.json        任务队列状态（gitignored）
├── creator_ips.txt         生图者 IP 映射（gitignored）
├── banned_ips.txt          封禁 IP 列表（gitignored）
├── featured.txt            精选图片路径（gitignored）
├── limits.json             限流 + 精选提示语配置（gitignored）
├── styles.json             画风配置（gitignored）
├── resolutions.json        分辨率预设（gitignored）
├── llm_config.json         LLM 服务商配置（gitignored）
├── announcement.json       公告配置（gitignored）
├── maintenance.json        维护模式配置（gitignored）
├── custom_head.json        自定义 <head> 注入（gitignored）
```

## API

### 认证

| 路径 | 说明 |
|---|---|
| `GET  /auth/login` | GitHub OAuth 登录跳转 |
| `GET  /auth/callback` | OAuth 回调处理 |
| `POST /auth/logout` | 登出 |
| `GET  /auth/dev_login` | 开发测试登录（仅 DEV_MODE） |
| `GET  /api/whoami` | 当前用户信息 |

### 公共

| 路径 | 说明 |
|---|---|
| `GET  /api/workflows` | 列出所有工作流 |
| `GET  /api/workflows/current?path=` | 工作流摘要 + 默认分辨率 + 内置 prompt |
| `POST /api/workflows/select` | 选中工作流 |
| `GET  /api/thumbnail?path=` | 工作流缩略图 |
| `GET  /api/styles` | 画风列表 |
| `GET  /api/resolutions` | 分辨率预设列表 |
| `GET  /api/style_thumbnail?name=` | 画风缩略图 |
| `GET  /api/output/list?limit=&offset=` | 输出目录分页（mtime 倒序） |
| `GET  /api/output/file?path=` | 取输出图（自动 WebP 转码，`?full=1` 取原图） |
| `GET  /api/output/meta?path=` | 读 PNG 元数据，提取正向 prompt |
| `GET  /api/output/featured` | 精选列表 + 提示语 |
| `GET  /api/output/creator?path=` | 该图的生图者 |
| `POST /api/output/fork` | 抽出 PNG 内的 workflow |
| `GET  /api/image?...` | 代理 ComfyUI 实时输出图 |
| `GET  /api/gpu` | nvidia-smi 状态 |
| `GET  /api/announcement` | 当前公告 |
| `POST /api/translate` | LLM 翻译 |
| `POST /api/interrupt` | 中断当前任务 |
| `POST /api/img2img/upload` | 图生图上传 |
| `GET  /api/my-queue` | 我的队列位置 |
| `GET  /api/my-images` | 我的作品列表 |
| `DELETE /api/my-images` | 删除我的作品 |
| `WS   /ws/run` | 提交生图 + 接收进度 |
| `WS   /ws/status` | 订阅全局任务状态 |

### 管理（需管理员角色）

| 路径 | 说明 |
|---|---|
| `GET  /admin` | 管理页 |
| `GET  /api/admin/whoami` | 当前管理员信息 |
| `GET  /api/admin/limits` / `POST` | 限流配置 |
| `GET  /api/admin/styles` / `POST` | 画风管理 |
| `GET  /api/admin/resolutions` / `POST` | 分辨率预设 |
| `GET  /api/admin/workflow_meta` / `POST` | 工作流缩略图 & Lora 链接 |
| `GET  /api/admin/workflow_files` | 扫描 ComfyUI 工作流目录 |
| `POST /api/admin/workflow_rename` | 重命名工作流 |
| `POST /api/admin/wf_thumbnail` | 上传工作流缩略图 |
| `POST /api/admin/style_thumbnail` | 上传画风缩略图 |
| `GET  /api/admin/llm` / `POST` | LLM 配置 |
| `POST /api/admin/llm/test` | 测试 LLM 连接 |
| `POST /api/admin/llm/models` | 获取可用模型列表 |
| `GET  /api/admin/announcement` / `POST` | 公告管理 |
| `GET  /api/admin/maintenance` / `POST` | 维护模式 |
| `GET  /api/admin/custom_head` / `POST` | 自定义 `<head>` 注入 |
| `GET  /api/admin/users` | 用户列表 |
| `POST /api/admin/users/ban` | 封禁用户 |
| `POST /api/admin/users/unban` | 解封用户 |
| `POST /api/admin/users/set_role` | 设置用户角色 |
| `GET  /api/admin/queue` | 查看任务队列 |
| `POST /api/admin/queue/cancel` | 取消任务 |
| `POST /api/admin/queue/force-unlock` | 强制解锁 GPU |
| `GET  /api/admin/bans` | 封禁 IP 列表 |
| `POST /api/admin/ban` / `unban` | 加/解封 IP |
| `GET  /api/admin/images_by_ip?ip=` | 查看某 IP 的生图记录 |
| `GET  /api/admin/recent?limit=&offset=` | 全输出图分页（管理用） |
| `GET  /api/admin/images` | 全输出图列表 |
| `POST /api/admin/delete` | 删图 |
| `POST /api/admin/delete_batch` | 批量删图 |
| `POST /api/admin/mark_delete_batch` | 批量标记删除 |
| `GET  /api/admin/featured` | 精选列表 |
| `POST /api/admin/featured/{add,remove,reorder}` | 精选维护 |
| `GET  /api/admin/gen-logs` | 生图日志 |
| `DELETE /api/admin/gen-logs` | 清空生图日志 |
| `POST /api/admin/gc` | 手动触发垃圾回收 |
| `POST /api/admin/force-restart` | 强制重启后端 |

### `/ws/run` 协议

客户端首包：

```jsonc
{
  "workflow_path": "文生图/WAI - 莫宁.json",
  "inline_workflow": null,
  "direct_prompt": "1girl, ...",
  "nl_prompt": "",
  "rewrite": false,
  "width": null,
  "height": null,
  "style_tags": "",
  "image_data_url_1": null,
  "image_data_url_2": null
}
```

服务端推送：

```jsonc
{"type": "log",       "message": "..."}
{"type": "llm_start"}
{"type": "llm_chunk", "delta": "..."}
{"type": "llm_done",  "text": "..."}
{"type": "prompt_id", "prompt_id": "...", "final_prompt": "..."}
{"type": "progress",  "node": "KSampler", "value": 10, "max": 20, "done": 3, "total": 8}
{"type": "image",     "url": "/api/image?...", "filename": "...", "subfolder": "", "image_type": "output"}
{"type": "done",      "final_prompt": "...", "count": 1}
{"type": "error",     "message": "..."}
```

## 限流与封禁

- **生图冷却**：单 IP 两次提交 `/ws/run` 间隔不少于 `gen_cooldown_sec`（默认 30s）
- **图片限流**：`/api/output/file`、`/api/image`、`/api/thumbnail` 三端点合并按 IP 滑动窗口限流（默认 60s 内 120 次），超限返回 429
- **IP 封禁**：被封 IP 提交 `/ws/run` 立即收到错误并断开。仅看图不影响
- **用户封禁**：管理员可封禁 GitHub 用户，被封用户无法提交生图
- **真实 IP 解析**：依次取 `cf-connecting-ip` → `x-forwarded-for[0]` → socket。挂在反代后请确保转发 `X-Forwarded-For`

## 安全

- GitHub OAuth 登录 + 会话管理
- 管理 API 需管理员角色（通过 `_auth_middleware` 校验）
- CSRF 校验：所有 POST 请求检查 Origin 头
- 输出目录浏览只读，路径校验：拒绝绝对路径、拒绝 `..` 段、`Path.is_relative_to()` 校验
- 上传文件流式写入，256KB 分块边写边校验大小（上限 5MB）
- `lora_link` 强制 `http://` 或 `https://` 协议
- 所有用户输入 HTML 转义后再渲染
- 全局禁止搜索引擎索引（`X-Robots-Tag`、`<meta robots>`、`/robots.txt`）
- 维护模式可一键切断所有非管理请求

## 常用资源

- [danbooru-artist 画师库](https://www.downloadmost.com/NoobAI-XL/danbooru-artist/)：换画风，格式 `by xxx` 或 `(by xxx:1.2)`
- [danbooru-character 角色库](https://www.downloadmost.com/NoobAI-XL/danbooru-character/)：换角色，建议配合无 Lora 工作流
- [新手教程 · 从零开始造老婆](https://2x.nz/posts/ai-wife/)

## 来源

本项目 Fork 自 [afoim/natureDrawImage](https://github.com/afoim/natureDrawImage)，原项目后端核心（`workflow_to_prompt_api` 等）移植自一个 NoneBot Telegram 插件。

本 Fork 主要增加了：
- GitHub OAuth 用户认证系统
- 图生图支持
- 用户中心（我的作品、我的队列）
- 用户管理、维护模式、生图日志等管理功能
- `.env` 配置化

## License

[AGPL-3.0](./LICENSE)

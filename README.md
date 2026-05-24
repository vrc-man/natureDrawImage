# 二次元绘梦

> ComfyUI 前端 Web 控制台 — 多人共用单 GPU，自然语言 AI 生图。

基于 [afoim/natureDrawImage](https://github.com/afoim/natureDrawImage) 二次开发，在原有基础上增加了 GitHub OAuth 登录、用户系统、图生图、访问密钥、生图日志等功能。

—— 单文件 FastAPI 后端 + Tailwind CDN 前端，无构建步骤。

## 与原项目的区别

| 维度 | 原项目 | 本 Fork |
|------|--------|---------|
| 用户认证 | 无，依赖反向代理保护 | GitHub OAuth 登录 + 会话滑动续期 |
| 管理后台保护 | 仅靠反代鉴权 | 管理员角色校验 + CSRF 保护 |
| 图生图 | 无 | 上传图片自动匹配工作流 |
| 用户系统 | 无 | 用户角色（admin/user）、封禁、访问密钥 |
| 个人中心 | 无 | 我的队列、我的作品、删除作品 |
| 评论区 | giscus | 免责声明 |
| 年龄确认 | 18+ 弹窗 | 已移除 |
| 配置方式 | 硬编码在 app.py | .env 环境变量 |
| 维护模式 | 无 | 支持，可自定义消息 |
| 自定义 head | 无 | 可注入自定义 HTML（统计脚本等） |
| 生图日志 | 无 | 记录所有生图请求，管理面板可查 |

## 功能概览

- **GitHub OAuth 登录**：用户通过 GitHub 账号登录，支持会话滑动续期
- **工作流管理**：列出 / 搜索 ComfyUI 已保存的工作流，支持缩略图、Lora 链接配置
- **画风一键切换**：管理员预配画风卡片（tags + 缩略图），用户点击即选
- **两种 prompt 写法**：
  - 直接 Tag：选择工作流后内置 prompt 自动填入
  - 自然语言翻译：LLM 把中/英文描述翻译成 SD/Pony/Illustrious tag
  - 改写模式：LLM 基于现有 prompt 整体重写
- **图生图**：上传图片，自动匹配工作流生成
- **多 LLM 后端**：LM Studio（本地）、Google AI Studio、自定义 OpenAI 兼容 API
- **分辨率管理**：管理员配置预设，前端只能从预设中选择，后端强制校验
- **WebSocket 实时进度**：节点名 + 步进进度条 + 取消按钮
- **GPU 状态条**（顶栏）：轮询 `nvidia-smi`，显示 GPU/VRAM 占用、温度、功耗
- **全局并发锁 + 旁观模式**：同时只允许一个生图任务，其他人实时看到进度
- **输出目录画廊**：分页加载，灯箱左右键翻图，可一键 Fork 工作流二改
- **Fork 工作流**：从输出 PNG 抽出 workflow，自动匹配画风
- **精选展示**：管理员维护精选作品，可拖拽排序，首页可折叠展示
- **公告系统**：管理员可开关公告、设置标题和内容
- **举报系统**：用户可举报图片，管理员可删图 / 封禁 / 驳回
- **限流配置**：单 IP 生图冷却 + 图片端点滑动窗口限流
- **IP 封禁 / 删图 / 批量删图**：管理面板维护
- **用户管理**：管理员可封禁/解封用户、设置角色
- **访问密钥**：生成一次性或限次密钥，供无 GitHub 账号用户使用
- **生图日志**：完整记录每次生成请求
- **WebP 自动转码**：输出图、缩略图自动转 WebP
- **全局禁止搜索引擎索引**

## 前置要求

- **Python 3.10+**
- **ComfyUI** 已安装并正常运行
- **NVIDIA GPU**（用于 `nvidia-smi` 状态显示）
- **GitHub OAuth App**（在 GitHub Settings > Developer settings 创建）
- **LLM 服务**（可选）：LM Studio / Google AI Studio / 任意 OpenAI 兼容 API

## 部署步骤

### 1. 安装依赖

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
cryptography
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，修改配置：

```bash
cp .env.example .env
```

**必填项**：

```ini
# ComfyUI 输出目录（只读浏览）
OUTPUT_DIR_STR=C:\path\to\ComfyUI\output
# ComfyUI 工作流目录（自动扫描）
COMFYUI_WORKFLOWS_DIR=C:\path\to\ComfyUI\user\default\workflows

# GitHub OAuth（在 https://github.com/settings/developers 创建 OAuth App）
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# 站点域名（OAuth 回调地址，与 GitHub OAuth App 配置一致）
SITE_URL=https://your-domain.com
```

其余配置项（ComfyUI 地址、端口、LLM 地址等）有默认值，按需修改。完整配置项见 `.env.example`。

### 3. 启动

```bash
# 默认监听 127.0.0.1:8080
python -m uvicorn web.app:app --host 127.0.0.1 --port 8080

# 监听所有地址（反代后端）
python -m uvicorn web.app:app --host 0.0.0.0 --port 8080 --forwarded-allow-ips 127.0.0.1

# 或直接运行 Windows 脚本（崩溃自动重启）
start.bat
```

打开 `http://127.0.0.1:8080`。

### 4. 配置反向代理（生产部署）

管理后台（`/admin`）通过用户角色校验保护，但建议在生产环境通过反向代理再做一层访问控制：

- **Cloudflare Access / Zero Trust**（推荐）
- **nginx auth_basic / auth_request**
- **IP 白名单**

nginx 示例：

```nginx
location / {
  proxy_pass http://127.0.0.1:8080;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header Host $host;
}
```

### 5. 首次设置

1. 用 GitHub 账号登录站点
2. 编辑 `web/users.json`，将自己的 `role` 设为 `"admin"`
3. 访问 `/admin` 进行后续配置（画风、分辨率、LLM 等）

后续可在管理面板的「用户管理」中为其他用户设置角色。

## 管理控制台 `/admin`

| 区块 | 功能 |
|---|---|
| 公告管理 | 开关公告 + 标题 / 内容编辑 |
| 分辨率管理 | 增删分辨率预设 |
| 画风管理 | 增删画风卡片（tags + 别名 + 缩略图） |
| 工作流缩略图 & Lora 链接 | 扫描 ComfyUI 目录，上传缩略图、配置链接 |
| LLM 配置 | 服务商切换、API Key、测试连接 |
| 限流配置 | 生图冷却、图片限流、举报限制 |
| 封禁 IP | 手动封禁/解封、查看某 IP 生图记录、批量删图 |
| 用户管理 | 用户列表、封禁/解封、设置角色 |
| 访问密钥 | 生成/删除/启停密钥 |
| 举报管理 | 待处理举报，支持删图/封禁/驳回 |
| 精选展示 | 拖拽排序 |
| 生图记录 | 全部输出图分页浏览 |
| 生图日志 | 所有生成请求记录（用户、prompt、工作流、状态、IP） |
| 维护模式 | 开关 + 自定义消息 |
| 自定义 Head | 注入自定义 HTML（统计脚本等） |
| 队列管理 | 查看/取消/强制解锁 |

## 目录结构

```
web/
├── app.py                    FastAPI 后端（单文件）
├── requirements.txt          Python 依赖
├── static/
│   ├── index.html            用户前端
│   ├── admin.html            管理控制台
│   ├── maintenance.html      维护模式页面
│   └── favicon.avif
├── thumbnails/               工作流缩略图（运行时）
├── style_thumbnails/         画风缩略图（运行时）
└── *.json / *.txt            运行时数据文件（均在 .gitignore）
```

## API

### 公共

| 路径 | 说明 |
|---|---|
| `GET  /` | 用户前端 |
| `GET  /access` | 访问密钥输入页 |
| `GET  /auth/login` | GitHub OAuth 登录 |
| `GET  /auth/callback` | OAuth 回调 |
| `POST /auth/logout` | 登出 |
| `POST /api/auth/claim-key` | 访问密钥认领 |
| `GET  /api/whoami` | 当前用户信息 |
| `GET  /api/workflows` | 列出工作流 |
| `GET  /api/workflows/current?path=` | 工作流摘要 + 默认分辨率 + 内置 prompt |
| `POST /api/workflows/select` | 选中工作流 |
| `GET  /api/thumbnail?path=` | 工作流缩略图 |
| `GET  /api/styles` | 画风列表 |
| `GET  /api/style_thumbnail?name=` | 画风缩略图 |
| `GET  /api/resolutions` | 分辨率预设 |
| `GET  /api/output/list?limit=&offset=` | 输出目录分页 |
| `GET  /api/output/file?path=` | 取输出图（自动 WebP 转码） |
| `GET  /api/output/meta?path=` | 读 PNG 元数据（正向 prompt） |
| `GET  /api/output/featured` | 精选列表 |
| `GET  /api/output/creator?path=` | 生图者 IP |
| `POST /api/output/fork` | 抽出 PNG 内 workflow |
| `GET  /api/image?...` | 代理 ComfyUI 实时输出图 |
| `GET  /api/gpu` | nvidia-smi 状态 |
| `GET  /api/announcement` | 当前公告 |
| `POST /api/translate` | LLM 翻译 |
| `POST /api/interrupt` | 中断当前任务 |
| `POST /api/report` | 举报图片 |
| `POST /api/img2img/upload` | 图生图上传 |
| `GET  /api/my-queue` | 我的队列位置 |
| `GET  /api/my-images` | 我的作品 |
| `DELETE /api/my-images` | 删除我的作品 |
| `WS   /ws/run` | 提交生图 + 接收进度 |
| `WS   /ws/status` | 订阅全局任务状态 |

### 管理（需 admin 角色）

| 路径 | 说明 |
|---|---|
| `GET  /admin` | 管理页面 |
| `GET  /api/admin/whoami` | 管理员身份校验 |
| `GET  /api/admin/queue` | 队列状态 |
| `POST /api/admin/queue/cancel` | 取消任务 |
| `POST /api/admin/queue/force-unlock` | 强制解锁 |
| `GET/POST /api/admin/limits` | 限流配置 |
| `GET/POST /api/admin/styles` | 画风管理 |
| `GET/POST /api/admin/resolutions` | 分辨率预设 |
| `GET/POST /api/admin/workflow_meta` | 工作流缩略图 & Lora 链接 |
| `GET  /api/admin/workflow_files` | 扫描工作流目录 |
| `POST /api/admin/workflow_rename` | 重命名工作流 |
| `POST /api/admin/wf_thumbnail` | 上传工作流缩略图 |
| `POST /api/admin/style_thumbnail` | 上传画风缩略图 |
| `GET/POST /api/admin/llm` | LLM 配置 |
| `POST /api/admin/llm/test` | 测试 LLM 连接 |
| `POST /api/admin/llm/models` | 获取 LLM 模型列表 |
| `GET/POST /api/admin/announcement` | 公告管理 |
| `GET/POST /api/admin/maintenance` | 维护模式 |
| `GET/POST /api/admin/custom_head` | 自定义 head 注入 |
| `GET  /api/admin/bans` | 封禁 IP 列表 |
| `POST /api/admin/ban` / `unban` | 加/解封 IP |
| `GET  /api/admin/images_by_ip` | 某 IP 生图记录 |
| `GET  /api/admin/recent` | 全输出图分页 |
| `POST /api/admin/delete` | 删图 |
| `POST /api/admin/delete_batch` | 批量删图 |
| `GET/POST /api/admin/featured` | 精选维护 |
| `GET  /api/admin/reports` | 待处理举报 |
| `POST /api/admin/report/resolve` | 处理举报 |
| `GET  /api/admin/users` | 用户列表 |
| `POST /api/admin/users/{ban,unban,set_role}` | 用户管理 |
| `GET/POST /api/admin/access-keys` | 访问密钥管理 |
| `GET/DELETE /api/admin/gen-logs` | 生图日志 |
| `POST /api/admin/gc` | 手动 GC |
| `POST /api/admin/force-restart` | 强制重启 |

### `/ws/run` 协议

客户端首包：

```jsonc
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

- **生图冷却**：单 IP 两次提交间隔不少于配置值（默认 30s）
- **图片限流**：图片端点合并按 IP 滑动窗口限流，超限返回 429
- **IP 封禁**：被封 IP 提交生图立即拒绝；仅看图不受影响
- **用户封禁**：被封用户无法登录使用
- **真实 IP 解析**：依次取 `cf-connecting-ip` → `x-forwarded-for[0]` → socket

## 安全

- GitHub OAuth 登录 + 会话滑动续期 + HttpOnly Cookie
- CSRF 校验（管理端点 + 敏感操作）
- 管理端点角色校验（admin 角色）
- 输出目录只读，路径校验拒绝绝对路径和 `..`
- 上传文件流式写入，256KB 分块边写边校验大小（上限 5MB）
- 所有用户输入 HTML 转义后再渲染
- 全局禁止搜索引擎索引（`X-Robots-Tag`、`<meta robots>`、`/robots.txt`）
- 信任代理 IP 可配（`TRUSTED_PROXY_IPS`）

## 常用资源

- [danbooru-artist 画师库](https://www.downloadmost.com/NoobAI-XL/danbooru-artist/)：换画风，格式 `by xxx`
- [danbooru-character 角色库](https://www.downloadmost.com/NoobAI-XL/danbooru-character/)：换角色
- [新手教程 · 从零开始造老婆](https://2x.nz/posts/ai-wife/)

## 来源

后端核心（`workflow_to_prompt_api` 等）移植自 `dev/comfyui.py`，一个 NoneBot Telegram 插件。本项目在此基础上增加了 Web 控制台、用户系统和管理后台。

上游仓库：[afoim/natureDrawImage](https://github.com/afoim/natureDrawImage)

## License

[AGPL-3.0](./LICENSE)

# 二次元绘梦（natureDrawImage 二次开发版）
> 给老婆套个壳，让她在浏览器里跑。

一个塞进 ComfyUI 前面的轻量级网页控制台，主打**多人共用一台显卡**的场景：每个浏览器各选各的工作流、各写各的 prompt，但同一时刻只有一个人在用 GPU，其它人能实时看到当前任务进度。

## 🔴 AGPLv3 开源声明（合规必备）
本项目为 **个人公益非盈利项目**，基于原项目二次开发：
- **原项目**：afoim/natureDrawImage
- **原仓库**：https://github.com/afoim/natureDrawImage
- **本项目**：https://github.com/vrc-man/natureDrawImage
- **首次修改日期**：2026-05-23
- **开源协议**：**GNU Affero General Public License v3.0 (AGPLv3)**
- **说明**：本项目所有修改均已完整开源，若通过网络使用本项目，可在本仓库获取全部源码。

---

## 项目介绍
基于 afoim/natureDrawImage 二次开发，在原有基础上增加了 GitHub OAuth 登录、邮箱注册/登录（含邀请码+TOTP）、用户系统、图生图、访问密钥、生图日志等功能。
单文件 FastAPI 后端 + Tailwind CSS 前端 + SQLite 数据库，无构建步骤，开箱即用。

## 与原项目的区别
| 维度 | 原项目 | 本 Fork |
|------|--------|---------|
| 用户认证 | 无，依赖反向代理保护 | GitHub OAuth + 邮箱注册/登录 + 邀请码 |
| 两步验证 | 无 | TOTP（Google Authenticator 兼容） |
| 管理后台保护 | 仅靠反代鉴权 | 管理员角色校验 + CSRF 保护 + 敏感操作二次密码（可选） |
| 图生图 | 无 | 上传图片自动匹配工作流 |
| 用户系统 | 无 | 用户角色（admin/user）、封禁、访问密钥 |
| 个人中心 | 无 | 我的队列、我的作品、删除作品 |
| 评论区 | giscus | 免责声明 |
| 年龄确认 | 18+ 弹窗 | 已移除 |
| 配置方式 | 硬编码在 app.py | .env 环境变量 |
| 维护模式 | 支持，可自定义消息 | 支持，可自定义消息 |
| 自定义 head | 可注入自定义 HTML（统计脚本等） | 可注入自定义 HTML（统计脚本等） |
| 生图日志 | 无 | 记录所有生图请求，管理面板可查 |
| 数据存储 | 18 个 JSON 文件分散存储 | 单文件 SQLite 数据库，查询更快，备份更简单 |

## 它能做什么



- **工作流管理**：列出 / 搜索 ComfyUI 已保存的工作流，支持缩略图、Lora 链接配置。「无 Lora」字样的工作流自动置顶

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

- **公告系统**：管理员可开关公告、设置标题和内容

- **举报系统**：用户可举报图片，管理员可删图 / 封禁生图者 / 封禁举报者 / 驳回

- **限流配置**：单 IP 生图冷却 + 出图端点滑动窗口限流，全部在管理面板实时改

- **生图者 IP 溯源**：每张输出图的 IP 记录在 `web/creator_ips.txt`，灯箱里显示

- **IP 封禁 / 删图 / 批量删图**：管理面板手动维护，被封 IP 提交直接拒绝

- **giscus 评论区**

- **WebP 自动转码**：输出图、缩略图自动转 WebP 节省带宽

- **全局禁止搜索引擎索引**



## 速览



```

┌─ GPU 状态条（nvidia-smi）

├─ 公告横幅

├─ 全局任务进度（其它人正在跑 → 此处可见）

├─ 工作流卡片网格（搜索 + 选中高亮）

├─ 画风卡片（一键切换，有别名的优先显示）

├─ 生图表单

│  ├─ 直接 Tag（工作流内置 prompt 自动填入）

│  ├─ 自然语言描述（LLM 翻译/改写）

│  ├─ ☑ 改写模式

│  ├─ 分辨率预设按钮

│  └─ ▶ 开始生成 / ✕ 取消

├─ 进度区（日志 + LLM 流式 + 进度条）

├─ 结果区（本次生成的图）

├─ 精选展示（站长维护，可折叠）

├─ 输出目录画廊（懒加载 + 灯箱 + Fork）

└─ 评论区

```



## 前置要求



- **Python 3.10+**

- **ComfyUI** 已安装并正常运行

- **NVIDIA GPU**（用于 `nvidia-smi` 状态显示）

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



### 2. 配置 .env

将 `.env.example` 复制为 `.env`，编辑以下内容（**只需改这几项**）：

```ini
# ========== 目录路径（必填） ==========
OUTPUT_DIR_STR=C:\path\to\ComfyUI\output
COMFYUI_WORKFLOWS_DIR=C:\path\to\ComfyUI\user\default\workflows

# ========== ComfyUI 连接 ==========
COMFYUI_HOST=127.0.0.1
COMFYUI_PORT=8188

# ========== GitHub OAuth（必填） ==========
GITHUB_CLIENT_ID=你的Client ID
GITHUB_CLIENT_SECRET=你的Client Secret

# ========== 站点域名 ==========
SITE_URL=https://你的域名

# ========== 邮箱服务（SMTP 发信） ==========
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASS=邮箱授权码

# Cloudflare Turnstile（可选）
TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=
```


- `OUTPUT_DIR_STR`：改成你的 ComfyUI 实际输出目录

- `COMFYUI_WORKFLOWS_DIR`：改成你的 ComfyUI 工作流目录（通常是 `ComfyUI/user/default/workflows`）

- `COMFYUI_PORT`：改成你的 ComfyUI 端口（ComfyUI 默认 8188，确认你的实际端口）



### 3. 启动



```bash

# 默认只监听 127.0.0.1:8080（本机访问）

uv run web/app.py



# 监听所有地址（局域网 / 反向代理后端）

uv run web/app.py --host 0.0.0.0



# 已配好反向代理鉴权，跳过启动确认

uv run web/app.py --host 0.0.0.0 --i-have-configured-auth



# 开发模式：保存 .py 自动重启

uv run web/app.py --host 0.0.0.0 --reload

```



打开 <http://127.0.0.1:8080>。



> 只监听 `127.0.0.1` 时不会弹启动确认；监听非回环地址且未带 `--i-have-configured-auth` 时，会要求你在终端输入 `yes` 确认已经配好访问控制再继续启动。



### 4. 配置反向代理鉴权（生产部署必须）



**本服务自身不做任何鉴权。** `/admin` 与 `/api/admin/*` 公开可达——任何人能访问端口就能调用。



不要直接把 `--host 0.0.0.0` 暴露到公网。生产部署**必须**在反向代理上做访问控制，至少满足其一：



- **Cloudflare Access / Zero Trust**（推荐）

- **nginx auth_basic / auth_request**

- **IP 白名单**

- **私有网络**（Tailscale / WireGuard）



nginx 示例：



```nginx

location ~ ^/(admin|api/admin) {

  auth_basic "admin only";

  auth_basic_user_file /etc/nginx/.htpasswd;

  proxy_pass http://127.0.0.1:8080;

  proxy_set_header X-Forwarded-For $remote_addr;

}

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



## 管理控制台 `/admin`



| 区块 | 功能 |

|---|---|

| 📢 公告管理 | 开关公告 + 标题 / 内容编辑 |

| 📐 分辨率管理 | 增删分辨率预设（宽 × 高 + 标签），自动保存 |

| 🖌️ 画风管理 | 增删画风卡片（tags + 别名 + 缩略图上传），自动保存 |

| 🔗 工作流缩略图 & Lora 链接 | 自动扫描 ComfyUI 目录，上传缩略图、配置链接、重命名工作流 |

| 🤖 LLM 配置 | LM Studio / Google AI Studio / 自定义 API 切换，测试连接 |

| ⚙️ 限流配置 | 生图冷却、图片限流、举报限制、GPU 轮询间隔、精选提示语 |

| 🚫 封禁 IP | 时间线显示、手动封禁/解封、查看某 IP 生图记录、批量删图 |

| 📝 举报管理 | 待处理举报列表，支持删图/封禁/驳回 |

| ⭐ 精选展示 | 拖拽排序 |

| 📋 生图记录 | 全部输出图分页浏览，每张图可：封禁 IP、加/移精选、删图 |



## 目录结构



```

web/
├── app.py                   FastAPI 后端（单文件）
├── requirements.txt         Python 依赖
├── db/
│   ├── schema.py            数据库 Schema（15 张表）
│   ├── operations.py        数据操作层
│   └── natureDrawImage.db   SQLite 数据库（运行时生成，已 gitignore）
├── static/
│   ├── index.html           用户前端
│   ├── admin.html           管理控制台
│   ├── maintenance.html     维护模式页面
│   ├── tailwind.min.css     Tailwind CSS 本地回退（主要走 CDN）
│   ├── favicon.avif         站点图标
│   └── chiz.webp            站点图标
├── deletion_thumbs/         删除记录缩略图存档（运行时）
├── thumbnails/              工作流缩略图（运行时）
├── style_thumbnails/        画风卡片缩略图（运行时）
├── lora_links/              Lora 链接文件（运行时）
├── uploads/                 图生图用户上传（运行时）
└── 全部数据存储于 SQLite，无 JSON 数据文件
```

项目根目录（非 web/ 内）：

| 目录 | 说明 |
|------|------|
| `thumb_cache/` | 输出图缩略图磁盘缓存（运行时） |
| `backups/` | 定时备份（含 SQLite 完整副本） |
| `gcbackups/` | GC 清理前备份（运行时） |

**运行时配置文件**（均在 `web/` 下，gitignored，由管理面板在线修改）：

| 文件 | 说明 |
|------|------|
| `limits.json` | 限流参数（生图冷却/图片限流/GPU轮询/GC间隔） |
| `styles.json` | 画风卡片定义（tags + 别名 + 缩略图） |
| `resolutions.json` | 分辨率预设（宽×高 + 标签） |
| `llm_config.json` | LLM 服务商/API Key/模型配置 |
| `workflow_meta.json` | 工作流缩略图 + Lora 链接映射 |
| `announcement.json` | 公告开关 + 标题 + 内容 |
| `maintenance.json` | 维护模式开关 + 自定义消息 |
| `rate_limits.json` | 邮箱注册/登录/密码重置速率限制 |
| `banned_ips.txt` | 封禁 IP 黑名单，每行一个 |
| `creator_ips.txt` | 输出图 → 生图者 IP 映射 |
| `db/natureDrawImage.db` | SQLite 主数据库（用户/会话/密钥/日志/举报等全部数据） |

> **注意**：以上目录和配置文件存储的是用户隐私数据与运行时缓存（非源码），已全部列入 `.gitignore`，不应上传至 Git。项目首次运行时自动生成，部署者只需准备 `.env` 即可启动。



## API



### 公共



| 路径 | 说明 |

|---|---|

| `GET  /api/workflows` | 列出所有工作流 |

| `GET  /api/workflows/current?path=` | 工作流摘要 + 默认分辨率 + 内置 prompt |

| `GET  /api/thumbnail?path=` | 工作流缩略图 |

| `GET  /api/styles` | 画风列表 |

| `GET  /api/resolutions` | 分辨率预设列表 |

| `GET  /api/style_thumbnail?name=` | 画风缩略图 |

| `GET  /api/output/list?limit=&offset=` | 输出目录分页（mtime 倒序） |

| `GET  /api/output/file?path=` | 取输出图（自动 WebP 转码，`?full=1` 取原图） |

| `GET  /api/output/meta?path=` | 读 PNG 元数据，提取正向 prompt |

| `GET  /api/output/featured` | 精选列表 + 提示语 |

| `GET  /api/output/creator?path=` | 该图的生图者 IP |

| `POST /api/output/fork` | 抽出 PNG 内的 workflow |

| `GET  /api/image?...` | 代理 ComfyUI 实时输出图 |

| `GET  /api/gpu` | nvidia-smi 状态 |

| `GET  /api/announcement` | 当前公告 |

| `POST /api/translate` | LLM 翻译 |

| `POST /api/interrupt` | 中断当前任务 |

| `POST /api/report` | 举报图片 |

| `WS   /ws/run` | 提交生图 + 接收进度 |

| `WS   /ws/status` | 订阅全局任务状态 |



### 管理（**必须由反向代理保护**）



| 路径 | 说明 |

|---|---|

| `GET  /admin` | 管理页 |

| `GET  /api/admin/limits` / `POST` | 限流配置 |

| `GET  /api/admin/styles` / `POST` | 画风管理 |

| `GET  /api/admin/resolutions` / `POST` | 分辨率预设 |

| `GET  /api/admin/workflow_meta` / `POST` | 工作流缩略图 & Lora 链接 |

| `GET  /api/admin/workflow_files` | 扫描 ComfyUI 工作流目录 |

| `POST /api/admin/workflow_rename` | 重命名工作流（通过 ComfyUI API） |

| `POST /api/admin/wf_thumbnail` | 上传工作流缩略图 |

| `POST /api/admin/style_thumbnail` | 上传画风缩略图 |

| `GET  /api/admin/llm` / `POST` | LLM 配置 |

| `POST /api/admin/llm/test` | 测试 LLM 连接 |

| `POST /api/admin/llm/models` | 获取可用模型列表 |

| `GET  /api/admin/announcement` / `POST` | 公告管理 |

| `GET  /api/admin/bans` | 封禁 IP 列表 |

| `POST /api/admin/ban` / `unban` | 加/解封 IP |

| `GET  /api/admin/images_by_ip?ip=` | 查看某 IP 的生图记录 |

| `GET  /api/admin/recent?limit=&offset=` | 全输出图分页（管理用） |

| `POST /api/admin/delete` | 删图 |

| `POST /api/admin/delete_batch` | 批量删图 |

| `GET  /api/admin/featured` | 精选列表 |

| `POST /api/admin/featured/{add,remove,reorder}` | 精选维护 |

| `GET  /api/admin/reports` | 待处理举报 |

| `POST /api/admin/report/resolve` | 处理举报 |

| `GET/DELETE /api/admin/gen-logs` | 生图日志查询与清空，支持日期筛选 |

| `GET /api/admin/deletion-log` | 删除记录回收站，支持日期筛选 |

| `GET /api/admin/deletion-thumb/{filename}` | 删除记录缩略图 |

| `POST /api/admin/deletion-log/clear` | 清理删除记录（按路径/日期/全清） |

| `POST /api/admin/mark_delete_batch` | 批量标记删除 |

| `POST /api/admin/gc` | 手动 GC（支持先备份再清理） |

| `GET /api/admin/gc/status` | GC 状态查询 |

| `POST /api/admin/force-restart` | 强制重启后端 |

| `POST /api/admin/auth-elevate` | 管理员提权（敏感操作二次密码验证，可选） |

| `GET /api/admin/auth-elevate-status` | 查询提权状态 |

### 邮箱认证

| 路径 | 说明 |
|---|---|
| `POST /api/auth/register-email` | 邮箱注册（需 Turnstile + 可选邀请码） |
| `POST /api/auth/login-email` | 邮箱登录（需 Turnstile，支持 TOTP 两步验证） |
| `POST /api/auth/forgot-password` | 忘记密码（需 Turnstile，含限流） |
| `GET /api/auth/reset-password` | 重置密码页面 |
| `POST /api/auth/reset-password` | 提交新密码 |
| `GET /api/auth/verify-email` | 邮箱验证 |
| `GET /api/auth/totp-qrcode` | TOTP 二维码 |
| `POST /api/auth/totp-setup` | 初始化 TOTP |
| `POST /api/auth/totp-enable` | 启用 TOTP |
| `POST /api/auth/totp-disable` | 关闭 TOTP |
| `GET /api/admin/invite-codes` | 邀请码列表 |
| `POST /api/admin/invite-codes/generate` | 生成邀请码 |
| `POST /api/admin/invite-codes/delete` | 删除邀请码 |
| `GET /api/admin/email-users` | 邮箱用户列表 |
| `POST /api/admin/email-users/ban` / `unban` | 封禁/解封邮箱用户 |
| `POST /api/admin/email-users/resend-verify` | 重新发送验证邮件 |
| `POST /api/admin/email-users/reset-totp` | 重置用户 TOTP |
| `GET/POST /api/admin/email-config` | 邮箱限流配置 |
| `GET/POST /api/admin/rate-limits` | 邮箱速率限制 |
| `GET /api/admin/email-logs` | 邮件发送日志 |
| `GET /api/admin/email-abuse-ips` | 恶意 IP 列表 |



### `/ws/run` 协议



客户端首包：



```jsonc

{

  "workflow_path": "WAI - 莫宁.json",

  "inline_workflow": null,

  "direct_prompt": "1girl, ...",

  "nl_prompt": "",

  "rewrite": true,

  "width": null,

  "height": null,

  "style_tags": ""

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

- **真实 IP 解析**：依次取 `cf-connecting-ip` → `x-forwarded-for[0]` → socket。挂在反代后请确保转发 `X-Forwarded-For`



## 安全

- **CSRF 保护**：所有 POST/PUT/DELETE 请求校验 Origin/Referer 头
- **CSP 内容安全策略**：nonce-based script-src，禁止 inline script
- **安全响应头**：`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`HSTS`、`Permissions-Policy`
- **DEV_MODE 启动保护**：`DEV_MODE=1` 且 `SITE_URL` 已配置时拒绝启动；否则需手动输入 `yes` 确认
- **管理员二次密码**：可选配置 `ADMIN_ELEVATION_PASSWORD`，敏感操作（删图/封禁/清日志等）需额外验证
- **密码重置人机验证**：忘记密码需通过 Turnstile，防自动化滥用
- **密码哈希**：PBKDF2-SHA256 200,000 轮迭代
- **账户锁定**：邮箱登录 5 次失败锁定 15 分钟
- 输出目录浏览只读，路径校验：拒绝绝对路径、拒绝 `..` 段、Unicode 规范化防绕过、`Path.is_relative_to()` 校验
- 上传文件流式写入，256KB 分块边写边校验大小（上限 5MB），PIL 校验文件有效性
- **SQL 参数化查询**：全量使用 `?` 占位符，无 SQL 注入风险
- **LLM API Key 加密存储**：Fernet (AES-128-CBC + HMAC-SHA256)
- `lora_link` 强制 `http://` 或 `https://` 协议
- 所有用户输入 HTML 转义后再渲染
- 全局禁止搜索引擎索引（`X-Robots-Tag`、`<meta robots>`、`/robots.txt`）
- 图片端点滑动窗口限流、WebSocket 连接数上限、全局发信量限制

## 常用资源



- [danbooru-artist 画师库](https://www.downloadmost.com/NoobAI-XL/danbooru-artist/)：换画风，格式 `by xxx` 或 `(by xxx:1.2)`

- [danbooru-character 角色库](https://www.downloadmost.com/NoobAI-XL/danbooru-character/)：换角色，建议配合无 Lora 工作流

- [新手教程 · 从零开始造老婆](https://2x.nz/posts/ai-wife/)



## 来源



后端核心（`workflow_to_prompt_api` 等）移植自 `dev/comfyui.py`，一个 NoneBot Telegram 插件。这个项目把它扒出来，套上一层 web 控制台，让本机/局域网/反代后更多人能用。



## License



[LICENSE](./LICENSE)

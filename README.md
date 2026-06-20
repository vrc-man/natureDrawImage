# 二次元绘梦（natureDrawImage 二次开发版）

一个塞进 ComfyUI 前面的轻量级网页控制台，主打**多人共用一台显卡**：每个浏览器各选各的工作流、各写各的 prompt，但同一时刻只有一个人在用 GPU，其它人能实时看到当前任务进度。

## 开源声明

本项目为 **个人公益非盈利项目**，基于 [afoim/natureDrawImage](https://github.com/afoim/natureDrawImage) 二次开发，以 **AGPLv3** 协议开源。

## 与原项目的区别

| 维度 | 原项目 | 本 Fork |
|------|--------|---------|
| 用户认证 | 无，依赖反向代理保护 | GitHub OAuth + 邮箱注册/登录 + 邀请码 |
| 两步验证 | 无 | TOTP（Google Authenticator 兼容） |
| 管理后台保护 | 仅靠反代鉴权 | 管理员角色校验 + CSRF + 敏感操作二次密码 |
| 图生图 | 无 | 上传图片自动匹配工作流 |
| 用户系统 | 无 | 角色（admin/user）、封禁、访问密钥 |
| 个人中心 | 无 | 我的队列、我的作品、删除作品 |
| 评论区 | giscus | 转静态免责声明 |
| 配置方式 | 硬编码 | .env 环境变量 |
| 生图日志 | 无 | 记录所有请求，管理面板可查 |
| 数据存储 | 18 个 JSON 文件 | 单文件 SQLite |

## 功能

- **工作流管理**：列出/搜索 ComfyUI 工作流，缩略图 + Lora 链接配置
- **画风一键切换**：管理员预配画风卡片，用户点击即选
- **两种 prompt 写法**：直接 Tag / LLM 自然语言翻译 + 改写
- **多 LLM 后端**：LM Studio / Google AI Studio / 自定义 OpenAI 兼容 API
- **WebSocket 实时进度**：节点名 + 进度条 + 取消按钮
- **GPU 状态条**：nvidia-smi 轮询
- **全局并发锁 + 旁观模式**：同一时刻单任务
- **ComfyUI 输出目录浏览**：分页 + 灯箱 + Fork 工作流
- **精选展示**：站长维护，拖拽排序
- **举报系统 + IP 封禁 + 生图者 IP 溯源**
- **WebP 自动转码**：节省带宽

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


```

## 前置要求

- Python 3.10+
- Node.js 18+（前端构建）
- ComfyUI 已安装并正常运行
- NVIDIA GPU（用于 nvidia-smi 状态显示）
- LLM 服务（可选）：LM Studio / Google AI Studio / 任意 OpenAI 兼容 API

## 部署步骤

### 1. 安装后端依赖

```bash
# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install fastapi uvicorn[standard] httpx websockets pydantic pillow
```

或使用 `requirements.txt`（如存在）。

### 2. 安装前端依赖

```bash
cd frontend
npm install
```

### 3. 构建前端

```bash
cd frontend
npm run build
# 输出到 web/static/dist/
```

### 4. 配置 .env

将 `.env.example` 复制为 `.env`，编辑以下内容：

```ini
OUTPUT_DIR_STR=C:\path\to\ComfyUI\output
COMFYUI_WORKFLOWS_DIR=C:\path\to\ComfyUI\user\default\workflows
GITHUB_CLIENT_ID=你的Client ID
GITHUB_CLIENT_SECRET=你的Client Secret
SITE_URL=https://你的域名
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASS=邮箱授权码
```

### 5. 启动

```bash
# 方式一：双击 start.bat（自动重启）
start.bat

# 方式二：手动启动
.venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080

# 方式三：开发模式（热重载）
.venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --reload
```

打开 http://127.0.0.1:8080。管理后台：http://127.0.0.1:8080/admin

### 6. 前端开发（修改 Vue 后）

```bash
cd frontend
npm run build          # 构建
# 输出到 web/static/dist/
# 刷新浏览器即可，无需重启 Python 后端
```

### 4. 反向代理鉴权（生产必须）

**本服务自身不做任何鉴权。
** `/admin` 与 `/api/admin/*` 公开可达——任何人能访问端口就能调用。
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

## 目录结构

```
web/                          # Python 后端
├── app.py                   主程序（~8900 行）
├── email_auth.py            邮箱认证模块（含管理 API）
├── db/
│   ├── __init__.py           模块入口
│   ├── schema.py             数据库表结构
│   └── operations.py         数据操作层
├── static/
│   ├── index.html            用户前端（Vue SPA）
│   ├── admin.html            前代管理后台（参考用）
│   ├── email-login.html      邮箱登录页
│   ├── privacy.html          隐私政策
│   ├── maintenance.html      维护模式页面
│   ├── dist/                 Vue 构建输出（自动生成）
│   └── ...
├── thumbnails/               工作流缩略图（运行时）
├── style_thumbnails/         画风缩略图（运行时）
├── deletion_thumbs/          删除缩略图（运行时）
└── db/natureDrawImage.db     SQLite 数据库（运行时）

frontend/                     # Vue 3 前端
├── src/
│   ├── pages/
│   │   ├── Admin.vue         管理后台（手风琴式，21 个子组件）
│   │   ├── Home.vue          用户首页（5 Tab 页）
│   │   └── ...
│   ├── components/
│   │   ├── admin/            21 个管理板块组件
│   │   │   ├── useAdminApi.ts     共享 API 工具
│   │   │   ├── AdminLightbox.vue  灯箱
│   │   │   ├── QueueSection.vue   队列管理
│   │   │   ├── AnnSection.vue     公告管理
│   │   │   └── ...                （每板块独立组件）
│   │   ├── MyWorksGrid.vue   我的作品（多选删除）
│   │   └── ...
│   └── api/
│       ├── endpoints.ts       API 封装
│       └── types.ts           类型定义
├── package.json
└── vite.config.ts

documentation/
└── Project-documentation.md  项目文档
```

## API

### 公共

| 路径 | 说明 |
|---|---|
| `GET /api/workflows` | 列出所有工作流 |
| `GET /api/workflows/current?path=` | 工作流摘要 + 默认分辨率 + 内置 prompt |
| `GET /api/thumbnail?path=` | 工作流缩略图 |
| `GET /api/styles` | 画风列表 |
| `GET /api/resolutions` | 分辨率预设列表 |
| `GET /api/style_thumbnail?name=` | 画风缩略图 |
| `GET /api/output/list?limit=&offset=` | 输出目录分页 |
| `GET /api/output/file?path=` | 取输出图（自动 WebP 转码） |
| `GET /api/output/featured` | 精选列表 |
| `GET /api/output/creator?path=` | 该图的生图者 IP |
| `POST /api/output/fork` | 抽出 PNG 内的 workflow |
| `GET /api/image` | 代理 ComfyUI 实时输出图 |
| `GET /api/gpu` | nvidia-smi 状态 |
| `GET /api/announcement` | 当前公告 |
| `POST /api/translate` | LLM 翻译 |
| `POST /api/interrupt` | 中断当前任务 |
| `POST /api/report` | 举报图片 |
| `WS /ws/run` | 提交生图 + 接收进度 |
| `WS /ws/status` | 订阅全局任务状态 |

### 管理（需管理员权限，Vue SPA 管理后台）

管理后台已重构为 Vue 3 SPA，21 个功能板块独立组件，手风琴式导航。访问 `/admin` 即可。

| 路径 | 说明 |
|---|---|
| `GET /admin` | 管理面板（Vue SPA） |
| `GET/POST /api/admin/limits` | 限流配置 |
| `GET/POST /api/admin/styles` | 画风管理（含缩略图上传） |
| `GET/POST /api/admin/characters` | 角色管理 |
| `GET/POST /api/admin/resolutions` | 分辨率预设 |
| `GET/POST /api/admin/workflow_meta` | 工作流缩略图 & Lora 链接 |
| `GET/POST /api/admin/workflow_files` | 工作流文件列表 |
| `POST /api/admin/workflow_rename` | 工作流重命名 |
| `GET/POST /api/admin/llm` | LLM 配置 |
| `POST /api/admin/llm/test` | 测试 LLM 连接 |
| `POST /api/admin/llm/models` | 探测 LLM 模型 |
| `GET/POST /api/admin/announcement` | 公告管理 |
| `GET/POST /api/admin/maintenance` | 维护模式 |
| `GET/POST /api/admin/custom_head` | 自定义 Head 注入 |
| `POST /api/admin/ban` / `unban` | 加/解封 IP |
| `GET/POST /api/admin/ip-whitelist` | IP 白名单 |
| `POST /api/admin/delete` | 单图删除 |
| `POST /api/admin/delete_batch` | 批量删除 |
| `POST /api/admin/mark_delete_batch` | 批量标记删除（GC 处理） |
| `POST /api/admin/images/delete-by-query` | 按条件筛选删除（日期/创建者） |
| `POST /api/admin/featured/*` | 精选维护 |
| `POST /api/admin/report/resolve` | 处理举报 |
| `GET/DELETE /api/admin/gen-logs` | 生图日志 |
| `GET/POST /api/admin/deletion-log` | 删除记录回收站 |
| `POST /api/admin/gc` | 手动 GC |
| `GET /api/admin/gc/stats` | GC 统计 |
| `GET /api/admin/gc/status` | GC 状态轮询 |
| `GET/POST /api/admin/access-keys` | 访问密钥管理 |
| `GET/POST /api/admin/email-dashboard` | 邮箱管理仪表盘 |
| `GET /api/admin/email-users` | 邮箱用户列表（分页） |
| `GET /api/admin/email-logs` | 发信日志 |
| `POST /api/admin/email-log/clear` | 清空发信日志 |
| `GET/POST /api/admin/email-config` | 邮箱注册限流配置 |
| `GET/POST /api/admin/rate-limits` | 速率限制 |
| `GET/POST /api/admin/invite-codes/*` | 邀请码管理 |
| `GET /api/admin/email-abuse-ips` | 恶意 IP 列表 |
| `POST /api/admin/email-abuse-ips/clear` | 清空恶意 IP |
| `POST /api/admin/email-users/resend-verify` | 重发验证邮件 |
| `POST /api/admin/email-users/reset-totp` | 重置 2FA |
| `POST /api/admin/email-users/reset-password` | 重置密码 |
| `POST /api/admin/email-users/send-custom-email` | 发送自定义邮件 |
| `GET /api/admin/users` | 用户列表 |
| `POST /api/admin/users/ban` / `unban` | 封禁/解封用户 |
| `DELETE /api/admin/gen-logs` | 清空生图日志（可带筛选） |
| `POST /api/admin/gen-logs/delete` | 批量删除生图日志 |
| `POST /api/admin/force-restart` | 强制重启服务 |
| `POST /api/admin/graceful-restart` | 优雅重启 |
| `POST /api/admin/scan-thumbnails` | 扫描缩略图 |
| `POST /api/admin/auth-elevate` | 管理员提权 |

### 邮箱认证

| 路径 | 说明 |
|---|---|
| `POST /api/auth/register-email` | 邮箱注册 |
| `POST /api/auth/login-email` | 邮箱登录（支持 TOTP） |
| `POST /api/auth/forgot-password` | 忘记密码 |
| `POST /api/auth/reset-password` | 提交新密码 |
| `GET /api/auth/verify-email` | 邮箱验证 |
| `POST /api/auth/change-password` | 修改密码 |
| `GET/POST /api/auth/totp-*` | TOTP 双因素认证 |

### 用户端图片管理

| 路径 | 说明 |
|---|---|
| `GET /api/my-images` | 我的作品列表 |
| `DELETE /api/my-images` | 单图标记删除 |
| `POST /api/my-images/delete-batch` | 批量标记删除 |
| `POST /api/my-images/delete-all` | 全部标记删除 |
| `GET /api/my-queue` | 我的队列 |

## 安全

- CSRF 保护 + CSP nonce-based script-src
- DEV_MODE 启动保护（需手动确认）
- 管理员敏感操作二次密码（可选）
- 密码哈希：PBKDF2-SHA256 200,000 轮迭代
- 邮箱登录 5 次失败锁定 15 分钟
- SQL 参数化查询，无注入风险
- LLM API Key 加密存储（Fernet）
- 路径校验、上传校验、HTML 转义
- 全局禁止搜索引擎索引

### ⚠️ 签名下载链接密钥

`/api/output/signed-url` 生成的临时下载链接使用 `DL_SECRET_KEY` 做 HMAC-SHA256 签名。

**默认情况下**，代码内有一个硬编码的回退密钥 `sha256("natureDrawImage_dl_2026")`，源码公开故等同于公开，任何人可伪造下载链接。

**务必在 `.env` 中设置自定义密钥：**

```ini
DL_SECRET_KEY=你的随机字符串
```

生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

未设定自定义密钥时应用仍能正常运行，但存在安全隐患。

### ⚙️ SPA 静态文件缓存

前端构建后的 JS/CSS 文件带有 hash 指纹（如 `index-BJk6YaG4.css`），可安全地设置为永久缓存。

在 `.env` 中设置：

```ini
# SPA 静态文件缓存时间（秒）。0=不缓存（开发用），31536000=1年（生产推荐）
SPA_CACHE_MAX_AGE=31536000
```

不设置则默认 `no-cache`，每次请求都重新验证。

## License

AGPLv3 — 详见 [LICENSE](./LICENSE)

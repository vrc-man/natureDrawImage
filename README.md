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

## 前置要求

- Python 3.10+
- ComfyUI 已安装并正常运行
- NVIDIA GPU（用于 nvidia-smi 状态显示）
- LLM 服务（可选）：LM Studio / Google AI Studio / 任意 OpenAI 兼容 API

## 部署步骤

### 1. 安装依赖

```bash
pip install fastapi uvicorn[standard] httpx websockets pydantic pillow
```

### 2. 配置 .env

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

### 3. 启动

```bash
.venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080
```

或双击 `start.bat`（自动重启）。打开 http://127.0.0.1:8080。

### 4. 反向代理鉴权（生产必须）

本服务自身不做鉴权，`/admin` 和 `/api/admin/*` 公开可达——必须用反向代理保护。nginx 示例：

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
web/
├── app.py                   主程序
├── email_auth.py            邮箱认证模块
├── db/
│   ├── __init__.py           模块入口
│   ├── schema.py             数据库表结构
│   └── operations.py         数据操作层
├── static/
│   ├── index.html            用户前端
│   ├── admin.html            管理控制台
│   ├── email-login.html      邮箱登录页
│   ├── privacy.html          隐私政策
│   ├── maintenance.html      维护模式页面
│   ├── favicon.avif          站点图标
│   └── chiz.webp             站点头像
├── thumbnails/               工作流缩略图（运行时）
├── style_thumbnails/         画风缩略图（运行时）
├── lora_links/               Lora 链接（运行时）
├── uploads/                  图生图上传（运行时）
├── deletion_thumbs/          删除缩略图（运行时）
└── db/natureDrawImage.db     SQLite 数据库（运行时）
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

### 管理（需管理员权限）

| 路径 | 说明 |
|---|---|
| `GET /admin` | 管理面板 |
| `GET/POST /api/admin/limits` | 限流配置 |
| `GET/POST /api/admin/styles` | 画风管理 |
| `GET/POST /api/admin/resolutions` | 分辨率预设 |
| `GET/POST /api/admin/workflow_meta` | 工作流缩略图 & Lora 链接 |
| `GET/POST /api/admin/llm` | LLM 配置 |
| `GET/POST /api/admin/announcement` | 公告管理 |
| `POST /api/admin/ban` / `unban` | 加/解封 IP |
| `POST /api/admin/delete` / `delete_batch` | 删图 |
| `POST /api/admin/featured/*` | 精选维护 |
| `POST /api/admin/report/resolve` | 处理举报 |
| `GET/DELETE /api/admin/gen-logs` | 生图日志 |
| `GET /api/admin/deletion-log` | 删除记录回收站 |
| `POST /api/admin/gc` | 手动 GC |
| `POST /api/admin/auth-elevate` | 管理员提权 |

### 邮箱认证

| 路径 | 说明 |
|---|---|
| `POST /api/auth/register-email` | 邮箱注册 |
| `POST /api/auth/login-email` | 邮箱登录（支持 TOTP） |
| `POST /api/auth/forgot-password` | 忘记密码 |
| `POST /api/auth/reset-password` | 提交新密码 |
| `GET /api/auth/verify-email` | 邮箱验证 |
| `GET/POST /api/auth/totp-*` | TOTP 双因素认证 |
| `GET/POST /api/admin/invite-codes/*` | 邀请码管理 |
| `GET/POST /api/admin/email-*` | 邮箱用户/日志/限流管理 |

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

## License

AGPLv3 — 详见 [LICENSE](./LICENSE)

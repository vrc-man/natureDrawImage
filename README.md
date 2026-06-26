# 二次元绘梦（natureDrawImage MySQL 重构版）

一个接在 ComfyUI 前面的轻量级网页控制台，主打 **多人共用一台显卡**：每个浏览器各选各的工作流、各写各的 prompt，但同一时刻只有一个人在用 GPU，其它人能实时看到当前任务进度。

本分支是基于原项目的二次开发版，当前重点是：

- 用户认证与管理后台；
- Vue 3 前端管理面板；
- SQLite → MySQL 数据层重构；
- 便携式 Windows 部署脚本；
- SQLite 旧库到 MySQL 的同步、备份、还原工具。

---

## 开源声明

本项目为 **个人公益非盈利项目**，基于 [afoim/natureDrawImage](https://github.com/afoim/natureDrawImage) 二次开发，以 **AGPLv3** 协议开源。

---

## 当前版本重点

| 维度 | 原项目/旧版本 | 当前 MySQL 重构版 |
|---|---|---|
| 用户认证 | 无或依赖反向代理 | GitHub OAuth + 邮箱注册/登录 + 邀请码 |
| 两步验证 | 无 | TOTP（Google Authenticator 兼容） |
| 用户系统 | 无 | 角色（admin/user）、封禁、访问密钥 |
| 管理后台 | 基础页面 | Vue 3 SPA 管理后台 |
| 数据存储 | JSON / SQLite | MySQL 8.0 |
| 旧数据迁移 | 无 | SQLite → MySQL 同步工具 |
| 数据备份 | 手动 | GUI 备份/还原 MySQL `.sql` |
| 启动方式 | 手动命令 | Windows `.bat` 一键启动/关闭 |
| 配置方式 | 硬编码或本地文件 | `.env` 环境变量 |

---

## 功能概览

- **工作流管理**：列出/搜索 ComfyUI 工作流，支持缩略图与 Lora 链接配置。
- **画风一键切换**：管理员预配画风卡片，用户点击即可追加 tags。
- **两种 prompt 写法**：直接 Tag / LLM 自然语言翻译 + 改写。
- **多 LLM 后端**：LM Studio / Google AI Studio / 自定义 OpenAI 兼容 API。
- **WebSocket 实时进度**：节点名、进度条、取消按钮。
- **GPU 状态条**：通过 `nvidia-smi` 轮询 GPU/显存/温度等状态。
- **全局并发锁 + 旁观模式**：同一时刻只允许一个生图任务。
- **ComfyUI 输出目录浏览**：分页、灯箱、Fork 工作流。
- **精选展示**：站长维护优秀作品，可拖拽排序。
- **举报系统**：举报图片、处理举报、封禁 IP/用户。
- **用户作品管理**：我的作品、批量删除、回收站/GC。
- **邮箱认证**：邮箱注册/登录、找回密码、验证邮件、TOTP。
- **MySQL 数据层**：用户、日志、配置、图片记录、邮箱用户等统一存储到 MySQL。
- **数据库同步工具**：旧 SQLite 只读快照同步到新 MySQL，支持备份/还原。

---

## 端口与访问地址

默认 Web 端口：

```text
23601
```

本机访问：

```text
http://127.0.0.1:23601
```

管理后台：

```text
http://127.0.0.1:23601/admin
```

---

## 新手怎么启动

### 平时启动 Web

双击：

```text
start-all.bat
```

或：

```text
start-web.bat
```

### 第一次创建/修复虚拟环境并启动

双击：

```text
start-Py64-311.bat
```

项目当前使用虚拟环境：

```text
natureDrawImage-env
```

不要再使用旧文档里的 `.venv`。

### 安全关闭 Web/MySQL

双击：

```text
stop-all.bat
```

它会尝试通知 Web，然后安全关闭 MySQL。

---

## 数据库同步、备份、还原

### 打开图形同步工具

双击：

```text
启动同步工具.bat
```

它实际运行：

```text
scripts\sync_gui.py
```

### 同步旧 SQLite 到 MySQL

推荐流程：

```text
关闭 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 仅预览
点 同步覆盖写入
看到 完整性检查通过
重启 Web
```

当前同步逻辑会：

1. 只读打开旧 SQLite；
2. 复制临时快照；
3. 从临时快照同步到 MySQL；
4. 不直接写老项目 SQLite；
5. 保留邮箱管理员角色；
6. 同步后检查孤儿外键和邮箱主用户补齐。

### 备份当前 MySQL

```text
关闭 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 备份为...
保存 .sql 文件
```

### 从 MySQL 备份还原

```text
关闭 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 从文件还原...
选择 .sql 文件
```

详细说明见：

```text
documentation\Database-Sync-Guide.md
```

---

## 初始部署文档

首次部署请看：

```text
documentation\Deployment-Guide.md
```

它包含：

- MySQL 绿色版目录结构；
- `.env` 配置；
- `natureDrawImage-env` 虚拟环境；
- `init-db.bat` 建表；
- `start-all.bat` 启动；
- `stop-all.bat` 安全关闭；
- SQLite → MySQL 数据导入；
- MySQL 备份/还原。

---

## 目录结构

```text
natureDrawImage-main-mysqlRefactoring\
├── web\
│   ├── app.py                    # FastAPI 主程序
│   ├── email_auth.py             # 邮箱认证、邀请、TOTP、邮箱管理 API
│   ├── db\
│   │   ├── schema.py              # MySQL schema、连接、建表
│   │   └── operations.py          # 数据访问层
│   ├── features\                 # 外挂功能模块
│   └── static\                   # 静态资源、登录页、旧页面等
│
├── frontend\                     # Vue 3 前端
│   ├── src\
│   │   ├── pages\
│   │   │   ├── Home.vue
│   │   │   └── Admin.vue
│   │   ├── components\
│   │   └── api\
│   └── package.json
│
├── scripts\
│   ├── sync_common.py             # SQLite→MySQL 同步公共逻辑
│   ├── sync_gui.py                # 图形同步/备份/还原工具
│   ├── sync_sqlite_to_mysql.py    # 命令行同步工具
│   ├── migrate_data.py            # 已废弃
│   └── convert_operations.py      # 已废弃
│
├── documentation\
│   ├── Deployment-Guide.md        # 初始部署与日常启动指南
│   ├── Database-Sync-Guide.md     # 数据库同步、备份、还原指南
│   ├── Project-documentation.md
│   └── project-architecture.md
│
├── natureDrawImage-env\           # Python 虚拟环境
├── start-Py64-311.bat             # 创建/检查虚拟环境并启动
├── start-all.bat                  # 启动 Web
├── start-web.bat                  # 启动 Web
├── stop-all.bat                   # 安全关闭 Web/MySQL
├── init-db.bat                    # 初始化数据库/建表
├── 启动同步工具.bat                # 打开同步工具
├── requirements.txt
└── .env                           # 环境变量，勿提交
```

---

## 前置要求

- Windows 10/11；
- Python 3.11+ 或便携 Python：`I:\cc\Py64-311\python-3.11.8.amd64\python.exe`；
- MySQL 8.0 绿色版：`I:\cc\mysql-8.0.28-winx64`；
- ComfyUI 已安装并正常运行；
- NVIDIA GPU（用于 `nvidia-smi` 状态显示）；
- Node.js 18+（仅前端开发/重新构建时需要）。

---

## `.env` 关键配置

常见配置示例：

```ini
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的MySQL密码
MYSQL_DATABASE=natureDrawImage

OUTPUT_DIR_STR=C:\path\to\ComfyUI\output
COMFYUI_WORKFLOWS_DIR=C:\path\to\ComfyUI\user\default\workflows

SITE_URL=http://127.0.0.1:23601
SITE_NAME=二次元绘梦

SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASS=邮箱授权码
```

敏感信息只写 `.env`，不要写进源码或 `.bat`。

---

## 前端开发

如果修改 Vue 前端：

```bat
cd frontend
npm install
npm run build
```

构建输出会被后端静态服务使用。

---

## API 概览

### 公共接口

| 路径 | 说明 |
|---|---|
| `GET /api/workflows` | 工作流列表 |
| `GET /api/workflows/current?path=` | 工作流摘要 + 默认分辨率 + 内置 prompt |
| `GET /api/thumbnail?path=` | 工作流缩略图 |
| `GET /api/styles` | 画风列表 |
| `GET /api/resolutions` | 分辨率预设 |
| `GET /api/output/list?limit=&offset=` | 输出目录分页 |
| `GET /api/output/file?path=` | 取输出图 |
| `GET /api/output/featured` | 精选列表 |
| `GET /api/gpu` | GPU 状态 |
| `GET /api/announcement` | 当前公告 |
| `POST /api/translate` | LLM 翻译/改写 |
| `POST /api/report` | 举报图片 |
| `WS /ws/run` | 提交生图 + 接收进度 |
| `WS /ws/status` | 订阅全局任务状态 |

### 管理接口

管理后台访问：

```text
/admin
```

常见接口：

| 路径 | 说明 |
|---|---|
| `GET /admin` | Vue SPA 管理后台 |
| `GET/POST /api/admin/limits` | 限流配置 |
| `GET/POST /api/admin/styles` | 画风管理 |
| `GET/POST /api/admin/characters` | 角色管理 |
| `GET/POST /api/admin/resolutions` | 分辨率预设 |
| `GET/POST /api/admin/workflow_meta` | 工作流缩略图 & Lora 链接 |
| `GET/POST /api/admin/llm` | LLM 配置 |
| `GET/POST /api/admin/announcement` | 公告管理 |
| `GET/POST /api/admin/maintenance` | 维护模式 |
| `POST /api/admin/delete` | 单图删除 |
| `POST /api/admin/delete_batch` | 批量删除 |
| `POST /api/admin/featured/*` | 精选维护 |
| `POST /api/admin/report/resolve` | 处理举报 |
| `GET/DELETE /api/admin/gen-logs` | 生图日志 |
| `GET/POST /api/admin/deletion-log` | 删除记录回收站 |
| `GET/POST /api/admin/access-keys` | 访问密钥管理 |
| `GET/POST /api/admin/email-dashboard` | 邮箱管理仪表盘 |
| `GET /api/admin/email-users` | 邮箱用户列表 |
| `GET /api/admin/email-logs` | 发信日志 |
| `POST /api/admin/email-logs/clear` | 清空发信日志 |
| `GET/POST /api/admin/email-config` | 邮箱注册限流配置 |
| `GET/POST /api/admin/invite-codes/*` | 邀请码管理 |
| `POST /api/admin/email-users/reset-totp` | 重置邮箱用户 2FA |
| `POST /api/admin/email-users/reset-password` | 重置邮箱用户密码 |
| `POST /api/admin/auth-elevate` | 管理员敏感操作提权 |

### 邮箱认证接口

| 路径 | 说明 |
|---|---|
| `POST /api/auth/register-email` | 邮箱注册 |
| `POST /api/auth/login-email` | 邮箱登录 |
| `POST /api/auth/forgot-password` | 忘记密码 |
| `POST /api/auth/reset-password` | 提交新密码 |
| `GET /api/auth/verify-email` | 邮箱验证 |
| `POST /api/auth/change-password` | 修改密码 |
| `GET/POST /api/auth/totp-*` | TOTP 双因素认证 |

---

## 安全说明

- CSRF 保护；
- CSP nonce-based script-src；
- 管理员角色校验；
- 管理员敏感操作二次密码（可选）；
- 密码哈希：PBKDF2-SHA256 200,000 轮；
- SQL 参数化查询；
- 路径校验、上传校验、HTML 转义；
- 全局禁止搜索引擎索引。

### 签名下载链接密钥

`/api/output/signed-url` 使用 `DL_SECRET_KEY` 生成 HMAC-SHA256 签名。

请在 `.env` 中设置自定义密钥：

```ini
DL_SECRET_KEY=你的随机字符串
```

生成随机密钥示例：

```bat
natureDrawImage-env\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

---

## 已废弃脚本

不要再用：

```text
scripts\migrate_data.py
scripts\convert_operations.py
```

请使用：

```text
启动同步工具.bat
```

或命令行：

```bat
natureDrawImage-env\Scripts\python.exe scripts\sync_sqlite_to_mysql.py
```

---

## 更多文档

| 文档 | 说明 |
|---|---|
| `documentation\Deployment-Guide.md` | 初始部署、启动、关闭、备份流程 |
| `documentation\Database-Sync-Guide.md` | SQLite→MySQL 同步、MySQL 备份/还原 |
| `documentation\project-architecture.md` | 项目架构说明 |
| `documentation\Project-documentation.md` | 项目详细功能文档 |
| `documentation\Bug-Hunting-Guide.md` | 排错指南 |

---

## License

AGPLv3 — 详见 [LICENSE](./LICENSE)

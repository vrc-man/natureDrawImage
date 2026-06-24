# natureDrawImage 项目架构文档

> 生成时间：2026-06-24
> 技术栈：FastAPI + SQLite + Vue 3 SPA
> 外挂体系：GitHub OAuth + 邮箱登录 + 访问密钥门禁 + ComfyUI 生图控制台

---

## 一、项目目录结构

```
natureDrawImage-main-sqlit/
├── .env                          # 环境变量（密钥、OAuth 配置等）
├── .env.example                  # 环境变量模板
├── .gitignore
├── AGENTS.md
├── CLAUDE.md                     # AI 协助规则
├── LICENSE                       # AGPLv3
├── README.md
│
├── web/                          # ★ 后端（FastAPI）
│   ├── app.py                    #   主入口（9554 行），单文件大但功能完整
│   ├── email_auth.py             #   邮箱认证独立模块（1221 行）
│   ├── llm_config.json           #   LLM 提供商配置
│   ├── llm_prompt_templates.json #   LLM 提示词模板（外挂 JSON）
│   ├── announcement.json         #   公告内容
│   ├── resolutions.json          #   分辨率预设
│   ├── styles.json               #   画风数据
│   ├── characters.json           #   角色数据
│   ├── workflow_meta.json        #   工作流缩略图 & Lora 链接
│   ├── limits.json               #   限流/频率配置
│   ├── rate_limits.json          #   IP 速率限制状态
│   ├── queue_state.json          #   队列状态持久化
│   ├── deletion_log.json         #   删除记录
│   ├── creator_ips.txt           #   图片 → IP 映射文件（非 SQLite）
│   │
│   ├── db/                       #   数据库层
│   │   ├── __init__.py           #     db 包标记
│   │   ├── schema.py             #     建表、迁移、配置读写（629 行）
│   │   ├── operations.py         #     SQL 操作（1106 行）
│   │   └── natureDrawImage.db    #     SQLite 主库（含 -shm / -wal）
│   │
│   ├── features/                 #   ★ 外挂功能模块（新功能在此新增，不进 app.py）
│   │   ├── __init__.py           #     register_all(app) 统一挂载点
│   │   ├── _deps.py              #     依赖注入容器 + 纯函数工具（features 不 import app）
│   │   ├── health_check.py       #     健康检查
│   │   ├── llm_prompt_templates.py #   LLM 提示词模板管理（CRUD）
│   │   └── access_keys.py        #     访问密钥管理（迁出样板）
│   │
│   ├── static/                   #   前端构建产物
│   │   └── dist/                 #     npm run build 输出目录
│   ├── thumbnails/               #   工作流缩略图
│   ├── style_thumbnails/         #   画风缩略图
│   ├── character_thumbnails/     #   角色缩略图
│   ├── lora_links/               #   Lora 链接文件
│   ├── deletion_thumbs/          #   删除图片的缩略图存档
│   └── uploads/                  #   图生图参考图上传统计
│
├── frontend/                     # ★ 前端（Vue 3 SPA + TypeScript）
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.ts               #   Vue 入口
│       ├── App.vue               #   根组件（路由 + 全局布局）
│       ├── router/
│       │   └── index.ts          #   路由配置
│       ├── stores/
│       │   └── user.ts           #   Pinia 用户状态
│       ├── api/
│       │   ├── client.ts         #   HTTP 客户端（封装 fetch）
│       │   ├── endpoints.ts      #   API 接口函数
│       │   └── types.ts          #   类型定义
│       ├── composables/
│       │   ├── useLightbox.ts    #   灯箱逻辑
│       │   ├── useSound.ts       #   音效播放
│       │   └── useToast.ts       #   Toast 提示
│       ├── assets/
│       │   └── style.css         #   全局样式
│       ├── pages/                #   ★ 页面组件
│       │   ├── Admin.vue         #     管理员控制台
│       │   ├── Admin_hdr.vue     #     管理员控制台（HDR 备用）
│       │   ├── Home.vue          #     生图首页（核心页面）
│       │   ├── EmailLogin.vue    #     邮箱登录页
│       │   ├── Maintenance.vue   #     维护中页面
│       │   ├── Privacy.vue       #     隐私政策页
│       │   └── template_part.txt #     AI 侧边栏模板片段
│       ├── components/           #   ★ 组件
│       │   ├── CharStylePicker.vue #   角色 & 画风选择器
│       │   ├── FeaturedGrid.vue    #   精选网格展示
│       │   ├── GalleryGrid.vue     #   画廊网格
│       │   ├── GPUBar.vue          #   GPU 状态条
│       │   ├── Img2ImgUpload.vue   #   图生图上传统组件
│       │   ├── Lightbox.vue        #   灯箱组件
│       │   ├── MyWorksGrid.vue     #   我的作品网格
│       │   ├── PresetManager.vue   #   预设管理
│       │   ├── TotpSettings.vue    #   二次验证设置
│       │   ├── WorkflowPicker.vue  #   工作流选择器
│       │   └── admin/             #   ★ 后台管理组件
│       │       ├── AdminLightbox.vue
│       │       ├── AccessKeySection.vue
│       │       ├── AnnSection.vue
│       │       ├── BanSection.vue
│       │       ├── CharacterSection.vue
│       │       ├── CheadSection.vue
│       │       ├── DeletionLogSection.vue
│       │       ├── EmailSection.vue
│       │       ├── FeaturedSection.vue
│       │       ├── GcSection.vue
│       │       ├── GenLogSection.vue
│       │       ├── ImageSection.vue
│       │       ├── LimitsSection.vue
│       │       ├── LlmSection.vue
│       │       ├── LlmTemplateSection.vue
│       │       ├── MaintSection.vue
│       │       ├── QueueSection.vue
│       │       ├── RecentSection.vue
│       │       ├── ReportSection.vue
│       │       ├── ResSection.vue
│       │       ├── StatsSection.vue
│       │       ├── StyleSection.vue
│       │       ├── UsersSection.vue
│       │       ├── WfMetaSection.vue
│       │       └── useAdminApi.ts   # 后台 API 通用 hook
│
├── tools/                         # 工具脚本
│   └── resize_thumbs_256.py       #   缩略图批量缩放（已 gitignore）
│
├── documentation/                 # 文档
│   ├── Project-documentation.md
│   └── llm-prompt-template-plan.md
│
├── thumb_cache/                   # 输出图缩略图缓存（自动生成）
├── backups/                       # 数据库/配置定时备份
└── .venv/                         # Python 虚拟环境
```

---

## 二、后端核心文件详解

### 2.1 app.py — 主入口（9554 行）

单文件结构，按功能分区（行号随版本浮动，但区域固定）：

| 行号范围 | 区域 | 说明 |
|----------|------|------|
| 1-290 | import + 配置 + 全局变量 | 包导入、环境变量、全局锁、文件路径常量 |
| 288-500 | 用户/会话/密钥核心函数 | `_load_users` `_create_session` `_get_user_from_session` `_load_access_keys` 等地基函数 |
| 500-950 | 各类配置读写 | 公告/维护模式/画风/角色/工作流元数据/LLM 配置的 load/save |
| 950-1450 | API Key 加密存储 | 密钥加密解密 |
| 1446-1668 | 中间件 | 鉴权、CSRF、限流、维护模式检查，`request.state.is_admin` 在此注入 |
| 1668-2350 | 定时 GC | GC 循环、孤儿扫描、缩略图删除、空目录清理 |
| 2350-3020 | 多种工具函数 | WebP 转码、删除记录、KV state、ComfyUI 工作流解析/读取 |
| 3022-3408 | LLM | `translate_prompt` `_llm_google` `_llm_openai_compat` `_parse_pos_neg` |
| 3408-3700 | GitHub API 工具 | _github_api 等 |
| 3700 + | ★ HTTP 路由 | 见下文路由表 |
| 5400-5550 | 广播/事件/状态 | `emit` `_broadcast` `_broadcast_queue` `_push_status` 等 |
| 5700-6020 | WS 鉴权 + 队列处理 | `_ws_get_user` `_process_queue` `_save_queue_state` |
| 6024-6350 | WS 路由 | `ws_run` 核心 WebSocket 生图入口 |
| 6416-6760 | `_run_task` | 完整生图流程：工作流加载、LLM、ComfyUI 提交、结果收集、日志写入 |

### 2.2 email_auth.py — 邮箱认证（1221 行）

独立模块，自包含邮箱验证码发送、邮箱登录路由、邮箱管理后台。

已有自己的 SQLite 表（`email_auth_requests` 等），不依赖 app.py 的数据层。

### 2.3 db/schema.py — 建表迁移（629 行）

- `init_db()` — 建所有表
- `migrate_from_json()` — 从旧 JSON 文件迁移到 SQLite
- `get_db()` — 获取数据库连接
- `config_get/set` — key-value 配置读写
- 所有表结构定义集中在此

### 2.4 db/operations.py — SQL 操作（1106 行）

所有数据操作的唯一实际执行者。

关键函数：

| 函数 | 作用 |
|------|------|
| `load_users()` | 读用户表 |
| `save_session()` | 写会话 |
| `load_sessions()` | 读会话 |
| `load_access_keys()` | 读密钥 |
| `add_access_key()` | 新增密钥 |
| `get_access_key()` | 查单个密钥 |
| `disable_access_key()` | 禁用 |
| `enable_access_key()` | 恢复 |
| `delete_access_key()` | 物理删除 |
| `cleanup_expired_access_keys()` | 清理过期 |
| `load_styles()` / `save_styles()` | 画风 |
| `load_characters()` / `save_characters()` | 角色 |
| `query_gen_logs()` | 查询生图日志 |
| 各类辅助函数 | |

### 2.5 features/ 外挂模块体系

```
features/_deps.py         注入容器（set_app_ctx / ctx）+ 纯函数工具
features/__init__.py       register_all(app) 挂载点
features/health_check.py   /api/health 健康检查
features/llm_prompt_templates.py   LLM 提示词模板管理（6 个接口）
features/access_keys.py    访问密钥管理（7 个接口，迁出样板）
```

**设计铁律**：features 模块绝不 `from app import ...`，所有数据函数和锁都通过 `_deps.set_app_ctx()` 注入。

---

## 三、JSON 数据文件详解

| 文件 | 位置 | 读写方 | 作用 |
|------|------|--------|------|
| `llm_config.json` | `web/` | app.py | LLM 提供商配置（endpoint / key / model / stream 开关） |
| `llm_prompt_templates.json` | `web/` | features/llm_prompt_templates.py | 管理员配置的 LLM 提示词模板库 |
| `announcement.json` | `web/` | app.py + Admin | 前台显示公告内容 |
| `resolutions.json` | `web/` | app.py + Admin/ResSection | 分辨率预设列表 |
| `styles.json` | `web/` | app.py + Admin/StyleSection | 画风配置（tags + name + image） |
| `characters.json` | `web/` | app.py + Admin/CharacterSection | 角色配置（tags + name + image + category） |
| `workflow_meta.json` | `web/` | app.py + Admin/WfMetaSection | 工作流缩略图路径 + Lora 链接 |
| `limits.json` | `web/` | app.py + Admin/LimitsSection | 限流/冷却/GC 开关配置 |
| `rate_limits.json` | `web/` | app.py | IP 速率限制持久化状态 |
| `queue_state.json` | `web/` | app.py | 生图队列持久化（进程重启恢复） |
| `deletion_log.json` | `web/` | app.py | 删除记录（原图/缩略图） |

**注意**：用户数据（用户/会话/密钥）已迁移到 SQLite，不使用 JSON。

---

## 四、后端路由大全

### 4.1 页面路由

| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（Vue SPA） |
| `/privacy` | GET | 隐私政策页 |
| `/access` | GET | 密钥访问页面 |

### 4.2 鉴权与用户

| 路径 | 方法 | 说明 |
|------|------|------|
| `/auth/login` | GET | GitHub OAuth 登录跳转 |
| `/auth/callback` | GET | GitHub OAuth 回调 |
| `/auth/logout` | POST | 登出（清除 session cookie） |
| `/auth/email-login` | GET | 邮箱登录跳转 |
| `/auth/dev_login` | GET | 开发模式快捷登录 |
| `/api/whoami` | GET | 当前用户信息（含 key 状态） |
| `/api/notifications` | GET | 未读通知 |
| `/api/whoami/read-notifications` | POST | 标记通知已读 |
| `/api/auth/claim-key` | POST | 用户绑定访问密钥 |

### 4.3 生图核心

| 路径 | 方法 | 说明 |
|------|------|------|
| `/ws/run` | WebSocket | 提交生图任务，接收实时进度/结果（核心入口） |
| `/ws/status` | WebSocket | 状态订阅（队列/冷却/在线人数） |
| `/api/workflows` | GET | 列出可用工作流目录及文件 |
| `/api/styles` | GET | 获取画风列表 |
| `/api/resolutions` | GET | 获取分辨率预设 |
| `/api/characters` | GET | 获取角色列表 |
| `/api/thumbnail` | GET | 工作流缩略图 |
| `/api/style_thumbnail` | GET | 画风缩略图 |
| `/api/character_thumbnail` | GET | 角色缩略图 |
| `/api/my-queue` | GET | 当前用户的队列状态 |
| `/api/gpu` | GET | GPU 使用状态 |

### 4.4 图片浏览

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/output/list` | GET | 列出 output 目录图片 |
| `/api/output/file?path=` | GET | 获取原图 |
| `/api/output/thumb?path=` | GET | 获取缩略图（thumb_cache） |

### 4.5 管理员路由（Admin 控制台）

**鉴权**：全部要求 `request.state.is_admin === true`

- `/api/admin/whoami` — 管理员身份确认
- `/api/admin/stats/generation` — 系统统计
- `/api/admin/queue` — 队列管理（取消/调序）
- `/api/admin/announcement` — 公告管理
- `/api/admin/resolutions` — 分辨率管理
- `/api/admin/styles` — 画风管理（CRUD）
- `/api/admin/characters` — 角色管理（CRUD）
- `/api/admin/styles/upload-images` — 画风缩略图批量上传
- `/api/admin/characters/upload-images` — 角色缩略图批量上传
- `/api/admin/workflow-meta` — 工作流缩略图 & Lora
- `/api/admin/features/llm-config` — LLM 配置
- `/api/admin/features/llm-models` — LLM 模型列表
- `/api/admin/features/llm-templates` (+ CRUD) — LLM 提示词模板
- `/api/admin/limits` — 限流配置
- `/api/admin/maintenance` — 维护模式
- `/api/admin/chead` — 自定义 Head
- `/api/admin/bans` — IP 封禁管理
- `/api/admin/reports` — 举报管理
- `/api/admin/gen-logs` — 生图日志查看
- `/api/admin/gen-log/thumb` — 生图日志缩略图
- `/api/admin/gen-logs/delete-orphans-by-range` — 按日期清理孤儿日志
- `/api/admin/gen-logs/delete-orphans-week-ago` — 清理一周前孤儿
- `/api/admin/gc` — GC 手动触发
- `/api/admin/gc/clean-empty-dirs` — 清理空日期目录
- `/api/admin/gc/mark-orphan` — 手动标记孤儿
- `/api/admin/recent-images` — 最近生图记录（公告用）
- `/api/admin/images` — 图片管理查看/删除
- `/api/admin/image/file` — 原始图片文件
- `/api/admin/image/thumb` — 图片缩略图
- `/api/admin/deletion-log` — 删除记录
- `/api/admin/backup` — 触发备份
- `/api/admin/email` — 邮箱认证管理
- `/api/admin/users` (+ ban/unban/set_role) — 用户管理
- `/api/admin/access-keys` (+ 6 个子接口) — 访问密钥管理
- `GET /api/admin/oauth/callback` — 管理端 OAuth

### 4.6 外挂模块路由

| 路径 | 模块 | 说明 |
|------|------|------|
| `/api/health` | health_check | 健康检查 |
| `/api/features/llm-templates` | llm_prompt_templates | 用户端模板下拉（公开） |
| `/api/admin/features/llm-templates` (+ CRUD) | llm_prompt_templates | 管理端模板管理 |
| `/api/admin/access-keys` (+ 6 个子接口) | access_keys | 访问密钥管理（已迁出 app.py） |

---

## 五、前端核心文件详解

### 5.1 页面组件

| 文件 | 说明 |
|------|------|
| `Home.vue` | 生图首页（核心页面，约 1100 行）—— prompt 输入、工作流选择、画风/角色、WebSocket 通信、进度展示、队列监控 |
| `Admin.vue` | 管理员控制台——导航锚点 + 手风琴式 section 管理 |
| `Admin_hdr.vue` | Admin 备用版本 |
| `EmailLogin.vue` | 邮箱验证码登录 |
| `Maintenance.vue` | 维护中间页 |
| `Privacy.vue` | 隐私政策展示页 |

### 5.2 关键组件

| 组件 | 说明 |
|------|------|
| `CharStylePicker.vue` | 画风 & 角色选择弹出面板（搜索、分类、缩略图、多选角色） |
| `FeaturedGrid.vue` | 精选图片网格 |
| `GalleryGrid.vue` | 公共作品浏览 |
| `MyWorksGrid.vue` | 我的作品 |
| `Img2ImgUpload.vue` | 图生图参考上传（最多 3 张，含等待上传） |
| `Lightbox.vue` | 图片灯箱 |
| `WorkflowPicker.vue` | 工作流选择器 |

### 5.3 后台管理组件（每个对应一个后台功能 section）

| 组件 | 对应功能 |
|------|----------|
| `StatsSection.vue` | 系统统计 |
| `QueueSection.vue` | 队列管理 |
| `AnnSection.vue` | 公告 |
| `ResSection.vue` | 分辨率 |
| `StyleSection.vue` | 画风管理 |
| `CharacterSection.vue` | 角色管理 |
| `WfMetaSection.vue` | 工作流缩略图 & Lora |
| `FeaturedSection.vue` | 精选管理 |
| `LlmSection.vue` | LLM 配置 |
| `LlmTemplateSection.vue` | LLM 提示词模板 |
| `LimitsSection.vue` | 限流配置 |
| `MaintSection.vue` | 维护模式 |
| `CheadSection.vue` | 自定义 Head |
| `UsersSection.vue` | 用户管理 |
| `EmailSection.vue` | 邮箱认证 |
| `AccessKeySection.vue` | 访问密钥 |
| `GenLogSection.vue` | 生图日志 |
| `DeletionLogSection.vue` | 删除记录 |
| `BanSection.vue` | IP 封禁 |
| `ReportSection.vue` | 举报管理 |
| `ImageSection.vue` | 图片管理 |
| `GcSection.vue` | GC 系统 |
| `RecentSection.vue` | 最近生图 |

### 5.4 工具层

| 文件 | 说明 |
|------|------|
| `api/client.ts` | HTTP 客户端（`api()` / `apiRaw()` 封装 fetch，带自动 JSON 解析、超时） |
| `api/endpoints.ts` | 接口函数（loadStyles / loadCharacters 等） |
| `api/types.ts` | TypeScript 类型定义（StyleItem / CharacterItem 等） |
| `composables/useToast.ts` | Toast 提示 |
| `composables/useSound.ts` | 音效播放 |
| `composables/useLightbox.ts` | 灯箱逻辑 |
| `stores/user.ts` | Pinia 用户状态管理 |

---

## 六、核心数据流

### 6.1 生图主流程

```
用户点击"开始生成"
  ↓
Home.vue → WebSocket /ws/run → RunRequest JSON
  ↓
ws_run() → 队列/锁/密钥预扣
  ↓
_process_queue() → _run_task()
  ├─ 加载工作流（workflow_to_prompt_api → 找 CLIPTextEncode）
  ├─ LLM 翻译/改写（translate_prompt → 模板 or tags/natural）
  │   └─ 返回 POSITIVE / NEGATIVE
  ├─ 拼合最终 prompt（画风 + 角色 + LLM 结果）
  ├─ 提交 ComfyUI（/_wait_for 等待结果）
  ├─ 保存图片映射（creator_ips / user_images）
  ├─ _save_gen_log → 生图日志（SQLite）
  └─ done → 前端展示图片 → 异步生成缩略图
```

### 6.2 数据存储矩阵

| 数据类型 | 存储方式 | 读写路径 |
|----------|----------|----------|
| 用户/会话/密钥 | SQLite | app.py → db/operations.py |
| 生图日志 | SQLite（gen_logs 表） | app.py → db/operations.py |
| 画风/角色 | SQLite（逐步迁移中） | app.py → db/operations.py |
| 分辨率/公告/LLM 配置 | JSON | app.py 直接读写 |
| LLM 提示词模板 | JSON | features/llm_prompt_templates.py |
| 图片文件 | 文件系统 OUTPUT_DIR | ComfyUI 生成 → app.py 记录路径 |
| 缩略图 | 文件系统 thumb_cache/ | app.py 缩略图函数 |
| 创作者映射 | 文件 creator_ips.txt + SQLite | app.py 双写 |
| 队列状态 | JSON queue_state.json | app.py 持久化 |

### 6.3 外挂模块依赖注入

```
app.py
  ├─ from db import operations as db
  ├─ set_app_ctx({"db": db, "load_users": ..., "get_user": ...})  ← 注入
  ├─ register_all(app)  ← 挂载 features 路由
  │
  features/access_keys.py
      └─ 所有数据操作通过 _deps.ctx("db") / _deps.ctx("load_users") 调用
          → 实际执行的是 app.py 注入的同一批函数
          → 同一把锁、同一条数据库路径、0 循环依赖
```

---

## 七、安全体系

| 层 | 机制 |
|----|------|
| 门禁 | 访问密钥（time/count/both 类型） |
| 鉴权 | GitHub OAuth + 邮箱验证码登录 |
| 会话 | session cookie（hmac + SHA256 hash，30 天滑动过期） |
| 管理员 | `request.state.is_admin` 在中间件注入，所有管理路由校验 |
| 限流 | IP 速率限制 + 用户生图冷却 + 每 IP WS 连接数上限 |
| 防 CSRF | Origin/Referer 校验 |
| 防滥用 | 队列上限、密钥次数、数据长度截断 |

---

## 八、重构建议

如果你计划基于此项目重构到新目录，以下是最核心的迁移依赖：

### 最紧的耦合（需优先处理）

1. **app.py 的拆分**：按功能区段渐次抽到 features/（已建立 _deps 模式样板）
2. **SQLite 兼容**：schema.py + operations.py 是唯一数据库入口，重构时整包搬走即可
3. **JSON 配置兼容**：格式完全沿用，旧 JSON 直接复制
4. **ComfyUI 工作流格式**：prompt API 格式不变

### 最容易复用/迁移的部分

- `db/` 整包（SQLite 操作）
- `features/` 全部外挂模块（零 app.py 依赖）
- `features/_deps.py` 的注入模式
- `email_auth.py` 自包含模块
- 前端 `api/types.ts` / `api/endpoints.ts`（类型定义 + 接口封装）

### 注意事项

- `app.py` 内部函数之间调用链很深，拆分时遵循"只搬路由+业务，不搬数据函数"原则
- SQLite 写库必须经过 `db/operations.py`，不能跳过
- 图片路径机制用"相对 OUTPUT_DIR 路径+文件名"做唯一标识，重构时不要变
- 缩略图缓存 thumb_cache/ 是 file system cache，非必要数据，重构可不带

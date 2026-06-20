# Project Documentation

## 项目架构

```
natureDrawImage-main-sqlit/
├── web/
│   ├── app.py                  # FastAPI 后端（~8900 行）
│   ├── db.py                   # SQLite 数据库操作
│   ├── static/
│   │   ├── admin.html          # 原始管理后台（3630 行，前端参考）
│   │   ├── index.html          # 原始首页
│   │   └── dist/               # Vue 构建输出
│   └── 各种.json                # 数据存储文件
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Admin.vue       # 管理后台（模块化，21 个子组件）
│   │   │   ├── Home.vue        # 用户首页（5 Tab 页）
│   │   │   └── ...
│   │   ├── components/
│   │   │   ├── admin/          # 21 个管理板块子组件
│   │   │   │   ├── useAdminApi.ts       # 共享 API 工具
│   │   │   │   ├── AdminLightbox.vue    # 灯箱
│   │   │   │   ├── QueueSection.vue     # 队列管理
│   │   │   │   ├── AnnSection.vue       # 公告管理
│   │   │   │   ├── StyleSection.vue     # 画风管理
│   │   │   │   ├── CharacterSection.vue # 角色管理
│   │   │   │   ├── WfMetaSection.vue    # 工作流元数据
│   │   │   │   ├── LlmSection.vue       # LLM 配置
│   │   │   │   ├── LimitsSection.vue    # 限流配置
│   │   │   │   ├── MaintSection.vue     # 维护模式
│   │   │   │   ├── CheadSection.vue     # 自定义 Head
│   │   │   │   ├── UsersSection.vue     # 用户管理
│   │   │   │   ├── EmailSection.vue     # 邮箱管理
│   │   │   │   ├── AccessKeySection.vue # 访问密钥
│   │   │   │   ├── GenLogSection.vue    # 生图日志
│   │   │   │   ├── DeletionLogSection.vue # 删除记录
│   │   │   │   ├── BanSection.vue       # IP 封禁
│   │   │   │   ├── ReportSection.vue    # 举报管理
│   │   │   │   ├── FeaturedSection.vue  # 精选管理
│   │   │   │   ├── RecentSection.vue    # 生图记录
│   │   │   │   ├── ImageSection.vue     # 图片管理
│   │   │   │   └── GcSection.vue        # GC 系统
│   │   │   ├── MyWorksGrid.vue          # 我的作品
│   │   │   ├── Lightbox.vue             # 用户端灯箱
│   │   │   └── ...
│   │   ├── api/
│   │   │   ├── endpoints.ts     # 用户端 API 封装
│   │   │   └── types.ts         # TypeScript 类型定义
│   │   └── assets/style.css     # 全局 CSS（含 html, body { overflow: hidden }）
│   └── ...
└── documentation/
    └── Project-documentation.md  # 本文件
```

---

## 图片删除体系

### 完整删除到 GC 流程

```
用户/管理员删图 → 写 deleted_images + deletion_log + 清 user_images
    ↓
GC 触发（手动/定时）：
  ├─ 1. 清理已处理的举报（resolved_reports）
  ├─ 2. 清理孤儿缩略图（orphan_thumbs）
  ├─ 3. 清理 creator 映射孤儿条目（orphan_creator_entries）
  ├─ 4. 重试删物理文件 → 读 deleted_images → 删文件 → 清标记
  │    失败项保留在 deleted_images 下次重试
  ├─ 4b. 清理 user_images 死记录
  ├─ 4c. 清理 featured 死路径
  └─ 5. 清理过期限流/会话记录
    ↓
启动时兜底：
  ├─ _cleanup_stale_deleted_entries()  ← 文件已不存在的删图标记 → 清除
  └─ _cleanup_stale_user_images()      ← 文件已不存在的归属记录 → 清除
```

### 三层防护（前端 → API → GC）

```
用户/管理员删图
    ↓
① user_images 移除记录  +  写入 deleted_images（标记待 GC 清理）
    ↓
② GC 扫描 deleted_images → 删物理文件 → 清标记
    ↓
③ 启动时 backfill：检查文件是否存在，不存在则删 user_images 记录
```

### 删除 API 对照表

| API | 角色 | 说明 | 归属验证 | 写入 deleted_images | 写入 deletion_log |
|-----|------|------|---------|-------------------|-------------------|
| `DELETE /api/my-images` | 用户 | 单图标记删除 | ✅ 验证所有权 | ✅ | ✅ |
| `POST /api/my-images/delete-batch` | 用户 | 批量标记删除 | ✅ 批量验所有权 | ✅ | ✅ |
| `POST /api/my-images/delete-all` | 用户 | 全部标记删除 | ✅ 只取自己的 | ✅ | ✅ |
| `POST /api/admin/delete` | 管理员 | 单图标记删除 | ❌ 不验证 | ✅ | ✅ |
| `POST /api/admin/delete_batch` | 管理员 | 批量删（强制） | ❌ 不验证 | ✅ | ✅ |
| `POST /api/admin/mark_delete_batch` | 管理员 | 批量标记删除（GC 处理） | ❌ 不验证 | ✅ | ❌（只记删除日志，不走 _record_deletion） |
| `POST /api/admin/images/delete-by-query` | 管理员 | 按条件筛选删除 | ❌ 不验证 | ✅ | ✅ |

> **`mark_delete_batch`** 不调 `_record_deletion`，所以 deletion_log 里不会有条目。它只写 `deleted_images` 和清 `user_images`。
> **`delete_batch`** 和 **`delete`** 调 `_record_deletion`，所以 deletion_log 里有记录。

### 锁保护

```python
_user_images_lock = asyncio.Lock()      # 保护 user_images.json
_deleted_images_lock = asyncio.Lock()    # 保护 deleted_images.json
_creator_map_lock = asyncio.Lock()       # 保护 creator_ip 映射
_featured_lock = asyncio.Lock()          # 保护 featured 精选
```

**加锁原则：** 校验（读）和删除（写）必须在同一个锁内完成，消除 TOCTOU 窗口。

**已修复的锁遗漏（2026-06）：**
- `POST /api/admin/delete` line 7262: 缺 `_user_images_lock` ✅ 已加
- `POST /api/admin/delete_batch` line 7333: 缺 `_user_images_lock` ✅ 已加
- `POST /api/admin/mark_delete_batch` line 7436,7438: 缺 `_deleted_images_lock` + `_user_images_lock` ✅ 已加
- 举报处理删图 line 8388: 缺 `_user_images_lock` ✅ 已加

### 数据文件

| 文件 | 用途 | 读 | 写 |
|------|------|----|-----|
| `user_images.json` | `{github_id: [{path, ...}]}` 用户图片归属 | `_load_user_images()` | `db.remove_user_image()` |
| `deleted_images.json` | `{github_id: [path, ...]}` GC 待清理标记 | `_load_deleted_images()` | `db.add_deleted_image()` |
| `deletion_log.json` | 删除记录日志（含缩略图归档） | `db.query_deletion_log()` | `db.add_deletion_log_entry()` |
| `gen_log.json` | 生图日志 | `app.py` 各查询函数 | app 内部 |
| `featured.json` | 精选列表 | `_read_featured()` | `_write_featured()` |

---

## 用户端 API（endpoints.ts）

| 函数 | 方法 | API | 说明 |
|------|------|-----|------|
| `whoami()` | GET | `/api/whoami` | 当前用户信息 |
| `claimKey(key)` | POST | `/api/auth/claim-key` | 使用访问密钥 |
| `logout()` | POST | `/auth/logout` | 登出 |
| `loadWorkflows()` | GET | `/api/workflows` | 工作流列表 |
| `loadStyles()` | GET | `/api/styles` | 画风列表 |
| `loadCharacters()` | GET | `/api/characters` | 角色列表 |
| `loadResolutions()` | GET | `/api/resolutions` | 分辨率预设 |
| `myQueue()` | GET | `/api/my-queue` | 我的队列 |
| `loadGallery(params)` | GET | `/api/output/list` | 画廊 |
| `loadFeatured()` | GET | `/api/output/featured` | 精选 |
| `loadMyImages(params)` | GET | `/api/my-images` | 我的作品 |
| `deleteMyImage(path)` | DELETE | `/api/my-images` | 单图标记删除 |
| `deleteMyImages(paths)` | POST | `/api/my-images/delete-batch` | 批量标记删除 |
| `deleteAllMyImages()` | POST | `/api/my-images/delete-all` | 全部标记删除 |
| `fetchNotifications()` | GET | `/api/notifications` | 通知 |
| `fetchGPU()` | GET | `/api/gpu` | GPU 状态 |
| `fetchAnnouncement()` | GET | `/api/announcement` | 公告 |
| `submitReport(data)` | POST | `/api/report` | 提交举报 |
| `totpStatus/setup/enable/disable` | 各种 | `/api/auth/totp-*` | TOTP 两步验证 |
| `forkWorkflow(data)` | POST | `/api/output/fork` | Fork 工作流 |

---

## 管理后台 API（app.py 内）

### 核心管理 API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/admin/whoami` | 验证管理员 |
| GET | `/api/admin/queue` | 队列状态 |
| POST | `/api/admin/queue/cancel` | 取消任务 |
| POST | `/api/admin/queue/force-unlock` | 强制解锁 |
| GET/POST | `/api/admin/announcement` | 公告管理 |
| GET/POST | `/api/admin/resolutions` | 分辨率管理 |
| GET/POST | `/api/admin/styles` | 画风管理 |
| GET/POST | `/api/admin/characters` | 角色管理 |
| GET/POST | `/api/admin/workflow_meta` | 工作流元数据 |
| GET/POST | `/api/admin/workflow_files` | 工作流文件列表 |
| POST | `/api/admin/workflow_rename` | 工作流重命名 |
| GET/POST | `/api/admin/llm` | LLM 配置 |
| POST | `/api/admin/llm/test` | 测试 LLM |
| POST | `/api/admin/llm/models` | 探测模型 |
| GET/POST | `/api/admin/limits` | 限流配置 |
| GET/POST | `/api/admin/maintenance` | 维护模式 |
| GET/POST | `/api/admin/custom_head` | 自定义 Head |
| GET/POST | `/api/admin/bans` | IP 封禁 |
| GET/POST | `/api/admin/ip-whitelist` | IP 白名单 |
| POST | `/api/admin/ban` | 封禁 IP |
| POST | `/api/admin/unban` | 解封 IP |
| GET/POST | `/api/admin/users` | 用户管理 |
| GET/POST | `/api/admin/email-dashboard` | 邮箱仪表盘 |
| GET/POST | `/api/admin/email-users` | 邮箱用户 |
| GET/POST | `/api/admin/email-logs` | 发信日志 |
| GET/POST | `/api/admin/email-config` | 邮箱配置 |
| POST | `/api/admin/rate-limits` | 速率限制 |
| POST | `/api/admin/invite-codes/generate` | 生成邀请码 |
| POST | `/api/admin/invite-codes/delete` | 删除邀请码 |
| GET/POST | `/api/admin/access-keys` | 访问密钥管理 |
| POST | `/api/admin/access-keys/generate` | 生成密钥 |
| POST | `/api/admin/access-keys/delete` | 禁用密钥 |
| POST | `/api/admin/access-keys/enable` | 重新启用 |
| POST | `/api/admin/access-keys/remove` | 彻底删除 |
| POST | `/api/admin/access-keys/reveal` | 查看完整密钥 |
| POST | `/api/admin/access-keys/cleanup` | 清理失效 |
| GET/POST | `/api/admin/gen-logs` | 生图日志 |
| DELETE | `/api/admin/gen-logs` | 清空生图日志 |
| GET/POST | `/api/admin/deletion-log` | 删除记录 |
| POST | `/api/admin/deletion-log/clear` | 清空删除记录 |
| GET | `/api/admin/recent` | 最近生图 |
| GET | `/api/admin/images` | 图片列 |
| POST | `/api/admin/images/delete-by-query` | 按条件删除图片 |
| GET/POST | `/api/admin/featured` | 精选管理 |
| GET/POST | `/api/admin/reports` | 举报管理 |
| POST | `/api/admin/report/resolve` | 处理举报 |
| GET/POST | `/api/admin/gc/stats` | GC 统计 |
| GET/POST | `/api/admin/gc/logs` | GC 日志 |
| POST | `/api/admin/gc` | 触发 GC |
| GET | `/api/admin/gc/status` | GC 状态 |
| POST | `/api/admin/gc/logs/clear` | 清空 GC 日志 |
| POST | `/api/admin/force-restart` | 强制重启 |
| POST | `/api/admin/graceful-restart` | 优雅重启 |
| GET/POST | `/api/admin/scan-thumbnails` | 扫描缩略图 |

### 缩略图上传

| API | 说明 | 请求体 |
|-----|------|--------|
| `POST /api/admin/style_thumbnail` | 上传画风缩略图 | FormData file |
| `POST /api/admin/character_thumbnail` | 上传角色缩略图 | FormData file |
| `POST /api/admin/wf_thumbnail` | 上传工作流缩略图 | FormData file |

> 上传后返回 `{filename: "xxx.webp"}`，前端应存储此 filename 到对应条目 `image` 字段。

### 缩略图展示

| URL | 说明 |
|-----|------|
| `/api/style_thumbnail?name={filename}` | 画风缩略图 |
| `/api/character_thumbnail?name={filename}` | 角色缩略图 |
| `/api/thumbnail?path={workflow}&_t={filename}` | 工作流缩略图 |
| `/api/output/thumb?path={image_path}` | 生图缩略图（512px WebP） |

---

## 前端架构

### Admin 模块化架构

管理后台由 `Admin.vue` 作为外壳 + 21 个子组件构成。每个子组件对应一个板块，独立管理状态和数据。

**组件间共享：**
- `useAdminApi.ts` 提供 `api()`, `fmt()`, `fmtShort()`, `relTime()`, `copyText()`, `resizeImage()` 等工具函数
- `onlineGithubIds` 是一个全局 ref，队列组件更新后自动同步到用户管理组件
- `AdminLightbox.vue` 是自包含灯箱组件，在 Admin.vue 顶层渲染

**重要：** 每个板块的数据加载在 `onMounted` 中触发，因为 `v-show` 会立即挂载组件（即使折叠状态）。

### 手风琴折叠

```html
<div class="bg-white rounded shadow p-4 mb-4">
  <div class="flex items-center justify-between mb-2 cursor-pointer select-none" @click="toggleSection('xxx')">
    <h2 class="text-lg font-semibold">
      <span class="inline-block w-4 text-gray-400 transition-transform" :class="expanded.xxx ? 'rotate-90' : ''">▸</span>
      🏃 队列管理
    </h2>
  </div>
  <div v-show="expanded.xxx">
    <QueueSection :visible="true" />
  </div>
</div>
```

使用 `v-show` 而非 `v-if`，所以组件在 DOM 中始终保持挂载，内部状态不会丢失。

### 已知注意事项

1. **action 字段名匹配：** 举报处理的 `dismiss` 不是 `ignore`（`app.py` 接收 `dismiss`）
2. **日期参数格式：** 涉及日期筛选的 API 统一使用 epoch 秒（`new Date(val + 'T00:00:00').getTime() / 1000`），`date_to` 用 `T23:59:59`
3. **生图日志状态字段：** API 返回 `status: "success"` 而非 `"completed"`
4. **生图日志缩略图：** `item.images[0]` 是完整 URL，`lb-thumb` 的 `href` 应直接用此 URL
5. **全局 CSS：** `frontend/src/assets/style.css` 第 3 行设置了 `html, body { overflow: hidden }`，管理后台需要自己的滚动容器
6. **前端构建：** `cd frontend; npm run build` → 输出到 `web/static/dist/`，刷新页面即可，无需重启后端

---

## 常见 Bug 模式

### API 负载结构错误

```
错误: api('POST', '/api/admin/maintenance', { config: { enabled, message } })
正确: api('POST', '/api/admin/maintenance', { enabled, message })
```

admin.html 的 save 函数是扁平结构，不要额外包一层 `{config:...}` 或 `{announcement:...}`。

### 布尔真值判断

```
错误: if (d.current_task)  // 空对象 {} 也是 truthy
正确: if (d.busy)          // 用 d.busy 判断
```

### 日期格式

```
错误: `&date_from=${dateFrom.value}`         // 原始字符串 "2024-01-15"
正确: '&date_from=' + (new Date(dateFrom.value + 'T00:00:00').getTime() / 1000)
```

### 锁保护范围

```
错误:
  async with lock:
      data = load_data()  # 只读了
  # 锁释放后才写
  db.remove(data)

正确:
  async with lock:
      data = load_data()
      if data in owned:
          db.remove(data)  # 读写同一个锁
```

### 灯箱滚动锁定

灯箱打开时设置 `document.body.style.overflow = 'hidden'`，**必须**在关闭时重置。推荐灯箱自管理状态（不依赖父组件 prop），确保 `overflow` 能正确回收。

---

## 已知 Bug 与修复记录

### 路由注册顺序（2026-06-19）

**问题：** 邮箱认证模块 `init_email_auth()` 在 `web/app.py` 最底部（第 8891 行）调用，但 SPA 兜底路由 `/{path:path}` 在第 8881 行已注册。Starlette 按注册顺序匹配，`/{path:path}` 截获所有 `/api/*` 请求并返回 404，导致邮箱管理 API 全部不可用。

**修复：** 将 `init_email_auth()` 移到 SPA fallback 之前（`app.py:8880`），在 `/{path:path}` 注册前完成邮箱路由注册。

**其他 admin 路由不受影响的原因：** 它们直接在 `app.py` 顶部用 `@app.get(...)` 注册，早于 `/{path:path}`。

---

## 数据库架构备忘

### 删图安全链路

```
用户删图 → user_images 移除 + 写入 deleted_images → [GC] 删物理文件 + 清标记
                                                       → [重启] backfill 从 gen_logs 插回
                                                       → [API] GET /api/my-images 按 deleted_images 过滤
```

| 层 | 位置 | 机制 |
|----|------|------|
| ① 启动兜底 | `_cleanup_stale_user_images()` → `app.py:1938` | 检查文件是否存在，不存在则删 user_images 记录 |
| ② API 过滤 | `app.py GET /api/my-images` | 显式排除 deleted_images 中的路径 |
| ③ API 二次过滤 | 同一函数 | 顺便检查磁盘文件是否存在 |

关键：backfill 本身不检查 deleted_images，但 API 层兜底过滤，所以已删图片永远不会出现在前端。

---

## 构建部署

```bash
# 前端构建
cd frontend
npm run build
# 输出到 web/static/dist/
```

## 后端部署

```bash
# 方式一：直接运行（推荐）
# 在项目根目录执行（不要 cd web）
start.bat

# 方式二：手动启动
cd /d I:\网站\shengtu\natureDrawImage-main-sqlit
.venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 30

# 方式三：外网部署
# 使用反向代理（nginx/caddy）监听 443，转发到 127.0.0.1:8080
```

## 内网穿透测试

```
本地服务器 :8080
  ↕ frpc/ngrok 客户端
内网穿透 → https://cc.hjmmb.com （示例域名）
```

## 前端修改后部署流程

```bash
cd frontend
npm run build               # 构建
# 输出到 web/static/dist/
# 刷新浏览器即可，无需重启后端
```

> 注意：前端构建输出到 `web/static/dist/`，后端直接服务这些静态文件。修改 Vue 代码后只需重新构建，刷新页面即可，**不需要重启 Python 后端**。

---

# 测试指南

## 管理后台功能测试清单

| 模块 | 测试内容 | 预期结果 |
|------|---------|---------|
| 队列管理 | 展开/折叠，查看在线用户 | 正常显示 |
| 公告管理 | 创建/编辑/开启/关闭公告 | 公告在前端显示/隐藏 |
| 画风管理 | 添加/编辑/排序/上传缩略图 | 画风在用户端可选 |
| 角色管理 | 同上 | 同上 |
| 工作流元数据 | 分类管理/缩略图上传/重命名 | 工作流显示正常 |
| LLM 配置 | 切换提供商/保存/测试模型 | 连接成功/失败 |
| 限流配置 | 修改参数/保存/GC/重启 | 参数生效 |
| 邮箱管理 | 邀请码/注册限流/用户列表/发信日志 | 数据正常显示 |
| 访问密钥 | 生成/禁用/启用/清理 | 密钥可用/不可用 |
| 生图日志 | 筛选/编辑模式/批量删除/清空 | 日志操作正常 |
| 删除记录 | 缩略图查看/清理记录 | 记录可清理 |
| IP 封禁 | 添加/解封/白名单/IP图片查看 | 封禁生效 |
| 举报管理 | 处理举报（删除/封禁/忽略） | 举报消失 |
| 图片管理 | 全选/批量删除/条件筛选删除 | 图片标记删除 |
| GC 系统 | 执行 GC/查看日志/清空日志 | GC 完成并记录 |
| 生图记录 | 封禁/精选/删除 | 操作生效 |
| 精选管理 | 拖拽排序/加载更多 | 排序同步到前端 |

## 灯箱测试

在所有带缩略图的板块（生图日志、删除记录、图片管理、生图记录、精选）点击缩略图验证：

- [ ] 灯箱打开显示大图
- [ ] 键盘 ← → 切换
- [ ] Esc 关闭
- [ ] 下载按钮
- [ ] 封禁用户（管理员可见）

## API 测试（使用 PowerShell）

```powershell
# 测试路由是否注册（返回 401 表示路由存在，需要登录）
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/admin/email-dashboard" -TimeoutSec 5

# 测试邮箱用户列表
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/admin/email-users?limit=24&offset=0" -TimeoutSec 5

# 测试发信日志
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/admin/email-logs?limit=24&offset=0" -TimeoutSec 5

# 测试图片条件删除
Invoke-WebRequest -Uri "http://127.0.0.1:8080/api/admin/images/delete-by-query" -Method POST -Body '{"date_from": 1700000000, "date_to": 1800000000}' -ContentType "application/json" -TimeoutSec 10
```

> 返回 401 = 路由正常（未登录）。返回 404 = 路由未注册。

## 常见问题排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 邮箱 API 返回 404 | `init_email_auth()` 在 SPA 兜底之后注册 | 检查 `app.py` 底部路由顺序 |
| 修改代码后不生效 | Python 字节码缓存 | 删除 `web/__pycache__/` 重启 |
| 前端修改不生效 | 浏览器缓存 | Ctrl+F5 强制刷新 |
| 邮箱日志状态全红 | 前端不认 `"ok"` 状态码 | 检查 `logStatusText()` 是否包含 `'ok'` |
| 删除操作无响应 | 锁竞争或数据文件损坏 | 查看服务端日志，确认锁是否释放 |

---

# 变更日志

| 日期 | 提交 | 说明 |
|------|------|------|
| 2026-06-19 | `f264714` | 管理后台模块化重构：21 个独立组件、邮箱管理 API 修复、SPA 路由顺序修复、GC del_set 清理、项目文档 |

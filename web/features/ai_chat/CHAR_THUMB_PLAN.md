# 角色库缩略图本地化 + 代理池爬取 实施计划（待执行）

## 目标
把 AI 助手角色库（`ai_chat_data.db`，44104 角色）的 Zerochan 外链缩略图转成本地 WebP 缓存，
实现「本地优先 → 代理兜底 → 增量更新」，并用 tkinter 工具 + 代理池批量爬取。

## 背景（已确认的现状）
- 角色库：`web/features/ai_chat/config/ai_chat_data.db`
  - 表 `character`：`danbooru_tag, base_tag, franchise, post_count, name_cn, tags, image`
  - `image` 字段存 Zerochan URL（当前仅 110 个角色有，86 个不同 URL；大部分为空）
  - 启动时 `_load_char_mem()` 加载到内存 `_CHAR_MEM`（44104 条，含 image 字段）
- 查询：`_query_mem()` 纯内存 contains 匹配（main.py:1824）
- 前端接口 `api_search_characters`（main.py:1739）返回含 image 的 JSON
  - 当前逻辑（1892-1901）：image 是 http → 包装成代理 `char-thumb?u=`
- 代理端点 `char-thumb`（main.py:1907）：转发 zerochan 外链，Referer 防盗链规避，带 ETag 缓存
- 现有本地目录：`web/character_thumbnails/`（管理面板上传的精选角色，`/api/character_thumbnail` 读它）
- 新目录（用户已建）：`web/features/ai_chat/skills/search_characters/character_thumbnails/`（当前为空）→ **爬取缓存存放地**
- 现有管理面板刷新缓存先例：`POST /api/admin/features/ai-chat/workflows-refresh`（main.py:2178，仿它）
- 现有 tkinter 工具先例：`scripts/sync_gui.py`（线程模型：队列 + 后台线程 + 主线程轮询）

## 角色库与技能关系（已确认）
- `search_characters` 技能（`skills/search_characters/main.py`）：LLM 工具，返回纯文本，**不涉及缩略图**，不用改
- 缩略图改造只影响 `api_search_characters`（前端接口的 image 字段）

## 实施任务

### 任务 1：后端（web/features/ai_chat/main.py）
- [ ] **新增本地缩略图目录常量**：`CHAR_THUMB_LOCAL_DIR = Path(...)/skills/search_characters/character_thumbnails`
- [ ] **新增本地缩略图索引** `index.json` 加载：
  - 位置：`CHAR_THUMB_LOCAL_DIR/index.json`
  - 格式：`{"version":1, "updated_at":ts, "total":N, "thumbs": {"danbooru_tag": "tag.webp"}}`
  - 启动加载 → 内存 `_LOCAL_THUMBS: set`（tag 集合）
  - 兜底：index.json 不存在 → 扫描目录收集 .webp 文件名
- [ ] **新增刷新缓存端点**：`POST /api/admin/features/ai-chat/char-thumbs-refresh`
  - 仿 `workflows-refresh`（main.py:2178），require_admin
  - 重新读 index.json / 扫描目录 → 更新 `_LOCAL_THUMBS`
  - 返回 `{ok, before, count, total, updated}`
- [ ] **新增本地缩略图访问端点**：`GET /api/features/ai-chat/char-thumb-local?name={tag}`
  - 读 `CHAR_THUMB_LOCAL_DIR/{tag}.webp`，存在返回（Cache-Control 长缓存），不存在 404
  - 防穿越：tag 校验（`..`、`/`、`\` 拒绝）
- [ ] **改造 `api_search_characters` 返回逻辑**（main.py:1892-1901）本地优先/代理兜底：
  ```python
  tag = c["danbooru_tag"] or ""
  if tag in _LOCAL_THUMBS:
      img = f"/api/features/ai-chat/char-thumb-local?name={quote(tag)}"
  elif img.startswith("http"):
      img = f"/api/features/ai-chat/char-thumb?u={quote(img)}"
  else:
      img = ""
  ```
- [ ] **新增统计接口**（供管理面板显示 N/M）：`GET /api/admin/features/ai-chat/char-thumbs-stats`
  - 返回 `{ok, local_count, total}`（local_count=_LOCAL_THUMBS 长度，total=len(_CHAR_MEM)）

### 任务 2：前端（frontend/src/components/admin/AiChatSection.vue）
- [ ] 加「🎭 角色库缩略图」子区
  - 显示「本地 X / 总 Y 张」
  - 「🔄 更新缩略图缓存」按钮 → 调 char-thumbs-refresh → 刷新统计
  - 提示文案：本机 tkinter 工具爬取后，点此刷新生效

### 任务 3：tkinter 工具（scripts/char_thumbs_gui.py，独立脚本）
- [ ] **代理池管理**：
  - 从 GitHub 免费代理列表拉取（raw URL），如 TheSpeedX/PROXY-List 等
  - 存活检测（HTTP 代理连通性测试）
  - 过滤无效代理 + 手动「更新代理池」按钮
- [ ] **批量爬取**：
  - 读角色库 SQLite（character 表 danbooru_tag + image）
  - 过滤本地已存在的（断点续传）
  - 并发（如 20）下载：httpx + 代理轮换 + Referer 头
  - 转 WebP（最短边 512px，等比缩放，PIL LANCZOS，quality 80，原子写 .tmp+rename）
  - 存到 `CHAR_THUMB_LOCAL_DIR/{danbooru_tag}.webp`
  - 失败重试 + 失败清单落盘
- [ ] **index.json 维护**：分批写（每 100 张/结束时）更新 thumbs 映射 + total + updated_at
- [ ] **GUI**（复用 sync_gui 线程模型）：日志区 + 进度 + 代理池按钮 + 开始/暂停

### 任务 4：验证
- 后端编译 + 前端 build
- 手动调 char-thumbs-refresh / stats / char-thumb-local
- （可选）小批量爬取测试

## 关键文件
- `web/features/ai_chat/main.py`：所有后端改动
- `frontend/src/components/admin/AiChatSection.vue`：管理面板子区
- `scripts/char_thumbs_gui.py`：新建 tkinter 工具
- `web/features/ai_chat/skills/search_characters/character_thumbnails/`：本地缓存目录（index.json 也在这）

## 待确认（实施时）
- 代理源具体 GitHub 项目 raw 地址
- 并发数 / 是否限速（Zerochan 封 IP 风险）
- index.json 字段最终格式

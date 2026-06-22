# 自荐精选功能 — 设计文档（开发蓝图）

> 状态：**设计完成，待开发**。本文件是讨论成果的固化，开发时照此实现。
> 原则：尽量外挂（`features/`），老 `app.py` 与账户体系（`email_auth.py`）不动。

---

## 一、功能概述

用户从「我的作品」自荐自己生成的图片为精选 → 管理员审核（同意/拒绝）→ 用户在「用户名弹窗 → 我的自荐」查看状态。

```
用户端：我的作品[自荐] → 提交
管理端：自荐审核管理（卡片）→ 同意(加精选) / 拒绝(可选理由)
用户端：用户名弹窗「我的自荐」→ 看状态 + 👁灯箱 + 删除自己记录
清理：用户自助删 + 孤儿清理顺带删死记录
```

---

## 二、数据表

### 新增 `featured_requests`（自荐工单，schema.py 建表）
```sql
CREATE TABLE IF NOT EXISTS featured_requests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  path          TEXT NOT NULL,           -- 图片完整相对路径（含日期目录，用于拼缩略图）
  submitter_gid TEXT NOT NULL,           -- 提交者 github_id
  submitter_login TEXT DEFAULT '',
  status        TEXT DEFAULT 'pending',  -- pending / approved / rejected
  review_note   TEXT DEFAULT '',         -- 拒绝理由（可选，允许空）
  reviewed_by   TEXT DEFAULT '',
  reviewed_at   REAL DEFAULT 0,
  created_at    REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_freq_submitter ON featured_requests(submitter_gid);
CREATE INDEX IF NOT EXISTS idx_freq_status ON featured_requests(status);
CREATE INDEX IF NOT EXISTS idx_freq_path ON featured_requests(path);
```

### 修改 `featured`（精选表，加精选日期）
```sql
ALTER TABLE featured ADD COLUMN featured_at REAL DEFAULT 0;
-- 老数据 featured_at=0，显示时兜底为「—」
```

---

## 三、接口（features/featured_request.py）

| 方法 | 路径 | 端 | 鉴权 | 作用 |
|------|------|----|----|------|
| POST | `/api/features/featured-req/submit` | 用户 | 登录 | 自荐（去重校验，写 pending） |
| GET  | `/api/features/featured-req/mine` | 用户 | 登录·只看自己 | 我的自荐列表+状态 |
| POST | `/api/features/featured-req/withdraw` | 用户 | 登录·只删自己 | 删自己记录（任意状态） |
| GET  | `/api/admin/features/featured-req/list` | 管理员 | admin | 待审列表（卡片） |
| POST | `/api/admin/features/featured-req/approve` | 管理员 | admin | 同意→加精选+标记 |
| POST | `/api/admin/features/featured-req/reject` | 管理员 | admin | 拒绝→标记+可选理由 |
| POST | `/api/admin/features/featured-req/remove` | 管理员 | admin | 移除任意自荐记录 |

鉴权：用户端校验登录 + `submitter_gid == 当前用户`；管理端 `features._deps.require_admin`。

---

## 四、业务规则

### 提交去重（任一命中即拦截）
- 图已在 `featured` 精选表 → 「该图已是精选」
- 该图已有 `pending` 记录 → 「已自荐，待审核」
- 该图已有 `rejected` 记录 → 「已被拒绝，不可再荐」
- 校验图属于提交者本人（`user_images` / gen_logs）

### 审核
- 同意 → `status=approved` + `reviewed_*` + 调 `db.save_featured(load+append)` 加精选（记 `featured_at=now`）
- 拒绝 → `status=rejected` + `review_note=理由或""`（**可选，全链路容空，不报错**）

### 删除/撤销
- 用户：可删自己**任意状态**记录
  - pending → 撤销（管理员列表消失）
  - approved → 删工单记录，**图已在精选不受影响**
  - rejected → 清失败记录
- 管理员：移除**任意**自荐记录

### 拒绝理由可选（防报错）
- 数据库 `review_note DEFAULT ''`，后端 `(note or "").strip()`，前端显示 `note || '（无说明）'`
- 三层容空，不填也不报错

---

## 五、孤儿清理联动

在 `_do_orphan_scan`（已含「清死精选」段）追加：原图被本轮删除后，
**删除 `featured_requests` 中 path 命中 deleted_rels 的记录**（全状态都删）。
- 找不到对应记录 → 跳过
- 有记录但原图没了 → 删（精选表记录也已删，自洽）

> 注：用户删图走 `mark_images_deleted` 已同步清 `featured`；自荐工单表由孤儿清理段一并清。

---

## 六、精选灯箱（隐私脱敏，仅针对精选）

精选展示的灯箱大图，下方**只显示**：
```
生图人ID(脱敏)   精选日期   [下载原图]   [Fork]
```
- ❌ 不显示用户名、IP、其它历史灯箱字段（仅精选场景隐藏）
- 灯箱：用户端走前端 `Lightbox`，管理端走 `AdminLightbox`
- ❌ 返回：灯箱关→回上层菜单；菜单关→关闭

### ID 脱敏（展示层解决，**不动 github_id / 账户体系**）
```python
def mask_user_id(github_id: str, login: str = "") -> str:
    s = login or (github_id or "").replace("email:", "")
    if "@" in s:
        s = s.split("@")[0]          # 砍掉邮箱域名，防泄露
    s = s.rstrip("._- ")
    if len(s) <= 2: return "***"
    if len(s) <= 6: return s[0] + "***" + s[-1]
    return s[:3] + "***" + s[-3:]
```
- GitHub 数字 ID `1234567890` → `123***890`
- 邮箱用户 login `8888000123` → `888***123`
- 含 @ 的 login → 砍域名再脱敏，永不暴露邮箱
- **决策：不改 ID 生成逻辑**（`email:` 前缀是账户根基，6 处 `replace("email:","")` 反推邮箱依赖它，动了会破坏登录/改密/2FA/找回密码）

---

## 七、前端

### 用户端
- **我的作品**卡片/灯箱：加「⭐ 自荐精选」按钮 → submit
- **用户名弹窗**（现有 openSettings 弹窗）：加「我的自荐」区块
  - 卡片：图片名 + 状态徽章（🟡待审/🟢通过/🔴未通过+理由）+ 👁
  - 👁 → 前端 Lightbox 大图（脱敏ID/精选日期/下载/Fork），❌返回菜单
  - 每条可删（撤销/清记录）
- 缩略图拼接同我的作品：`/api/output/thumb?path=` + encodeURIComponent(path)

### 管理端
- 新增「自荐审核管理」section（卡片形式）
  - 显示：生图者用户名 + 图片名 + 申请日期 + 预览
  - [同意自荐] [拒绝(可选理由)] [移除]
  - 点预览 → AdminLightbox 大图

---

## 八、改动范围

| 文件 | 改动 | 类型 |
|------|------|------|
| `db/schema.py` | 建 featured_requests 表 + featured 加 featured_at | 底层（安全） |
| `db/operations.py` | 自荐表 CRUD + save_featured 写 featured_at | 底层 |
| `features/featured_request.py` | 全部接口（新文件） | 外挂 |
| `features/__init__.py` | 注册新 router | 外挂 |
| `app.py` `_do_orphan_scan` | 加一段：清死自荐记录 | 老代码（仅追加一段） |
| 前端 Home.vue | 我的作品自荐按钮 + 用户名弹窗「我的自荐」 | 前端 |
| 前端 admin | 自荐审核 section | 前端 |
| 精选灯箱组件 | 加「精选模式」脱敏显示 | 前端 |

老 `app.py` 主体、`email_auth.py` 账户体系**不碰**。

---

## 九、待开发时拍板的小点（已基本确定）
- ✅ 灯箱：用户走 Lightbox，管理走 AdminLightbox
- ✅ 去重：精选中/待审/已拒绝 都拦截
- ✅ 用户删：任意状态可删
- ✅ 拒绝理由：可选
- ✅ 脱敏：用 login，不动 ID
- ✅ 孤儿清理：联动删自荐记录（全状态）
- ✅ 精选表加 featured_at，老数据显示「—」

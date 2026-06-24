# Bug 排查思路指南

## 一、排查数据丢失类 Bug 的标准流程

### 第 1 步：定位嫌疑表

看现象锁定哪个表的数据丢了或错乱了。

```
例子：用户 session 丢了 → 查 sessions 表
      图片标记删除后还在 → 查 deleted_images / user_images
      密钥绑定丢了 → 查 access_keys
```

### 第 2 步：搜该表的所有写操作

在 `web/db/operations.py` 里 grep 表名，找出所有写该表的函数：

```bash
grep -n "表名" web/db/operations.py
```

重点看每个写函数的**操作模式**。

### 第 3 步：判断写操作模式

#### ✅ 安全模式（原子单行）

```python
def save_xxx(key, value):
    _db().execute(
        "INSERT OR REPLACE INTO xxx VALUES (?)",
        (value,)
    )
    _db().commit()
```

特点：
- `INSERT` / `UPDATE` / `DELETE` + `WHERE` 精准定位行
- 只操作目标行，不碰其他行
- 单个函数 1 条 SQL + commit

#### ✅ 安全模式（事务保护的多表操作）

```python
def batch_xxx(paths):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM a WHERE ...")
        conn.execute("INSERT INTO b ...")
        conn.commit()
    except:
        conn.execute("ROLLBACK")
        raise
```

特点：
- `BEGIN IMMEDIATE` 拿锁
- 纯 SQL，不放 Python 计算在事务中间
- `try/except` + `ROLLBACK` 保证数据一致性

#### ❌ 危险模式（全量读改写）

```python
data = load_all()       # SELECT 全表
data[key] = new_value   # 内存改
save_all(data)          # DELETE ALL + INSERT ALL
```

特征：
- 先 `SELECT *` 全部读出来
- 改 dict
- 再 `DELETE FROM xxx` + 逐条 `INSERT` 写回去

**并发写入者越多，被覆盖的数据越多。**

### 第 4 步：检查是否有多个入口写同一张表

```
app.py 写 access_keys     → _load → 改 → _save（全量）
features/access_keys.py   → db.claim_access_key()（原子单行）

两者并发时：
  ① app.py 读到了 {key1, key2}
  ② features 插入了 key3（INSERT）
  ③ app.py 写回 {key1, key2}
  ④ key3 凭空消失！！！
```

排查方法：在项目中 grep 表名，看哪些文件在操作它：

```bash
grep -rn "sessions\|access_keys\|reports" web/app.py web/features/ | grep -i "execute\|save\|delete\|insert\|update"
```

### 第 5 步：检查"读→判断→写"三段是否有保护

```python
# ❌ 不安全
count = db.get_count()        # 读
if count > 0:                  # 判断
    db.decrement_count()       # 写

# ✅ 安全（把判断写进 SQL）
cur = _db().execute(
    "UPDATE counters SET count=count-1 WHERE id=? AND count > 0",
    (id,)
)
```

### 第 6 步：检查锁保护范围

```python
# ❌ 不对：锁只保护了读
async with lock:
    data = load_all()
# 锁已释放
data[key] = new
save_all(data)   # 另一个协程可能在 save_all 前写了

# ✅ 正确：读写一个锁
async with lock:
    data = load_all()
    data[key] = new
    save_all(data)
```

但最好的方案是**不需要锁**——直接原子 SQL 操作，靠 SQLite 自串行。

---

## 二、已知 Bug 模式速查表

### 模式 1：JSON 迁移遗漏

现象：两个用户同时操作，一个用户的修改覆盖了另一个的。

根因：从 JSON 文件迁移到 SQLite 后，写操作仍然是"全量读→改dict→全量写"。

```python
# 旧的 JSON 思维方式
def save_sessions(data):
    json.dump(data, file)     # 整个文件全量写

# 迁移到 SQLite 后变成了
def save_sessions(data):
    _db().execute("DELETE FROM sessions")     # 仍然全量覆盖！
    for s in data:
        _db().execute("INSERT INTO sessions ...")
```

修复方向：拆成单行 `INSERT / UPDATE / DELETE`。

### 模式 2：读→改→写 三段无保护 TOCTOU

现象：极少发生，数据偶尔不一致，难以复现。

根因：在读和写之间，另一个协程插入了数据。

```python
# 框架
data = load()       # ① 读
if condition:       # ② 判断
    save(data)      # ③ 写
```

修复方向：把条件判断写进 SQL（WHERE 子句），或加锁把①②③包在同一个 `async with` 里。

### 模式 3：新旧代码操作同一张表但锁不同

现象：外挂新增的数据有时会丢失。

```python
# app.py 用 _access_keys_lock
async with _access_keys_lock:
    data = _load_access_keys()
    # 改...
    _save_access_keys(data)

# features/access_keys.py 用 db.xxx() 原子操作，不碰这个锁
db.add_access_key(...)  # 瞬间 INSERT
```

修复方向：全量写改为原子单行。

### 模式 4：异步协程不共享同一个 Lock 对象

```python
# ❌ 每个协程 new 一个锁
async def bad():
    lock = asyncio.Lock()   # 不同协程有不同的锁对象！
    async with lock:
        data = load()
        data[x] = y
        save(data)

# ✅ 模块级全局锁
_lock = asyncio.Lock()      # 所有人共享同一把锁
async def good():
    async with _lock:
        ...
```

### 模式 5：外挂和 GC 竞争同一资源

现象：GC 删图时，外挂正在写入新图，导致新图被误删。

根因：GC 的扫描和外挂的写入没有协调机制。

修复方向：
- GC 等所有活跃任务完成后再运行
- 写入先写 gen_logs，再写文件（GC 靠 gen_logs 判断文件是否有主）

### 模式 6：批量删除中间崩溃

现象：删了一半，部分记录已删，部分还在。

```python
# ❌ 循环里每个操作独立 commit
for p in paths:
    db.delete_deleted_image(p)    # 每张图 commit 一次
    db.delete_user_image(p)
    # 如果这里崩了，deleted_images 和 user_images 不一致

# ✅ 批量操作包在事务里
conn.execute("BEGIN IMMEDIATE")
for p in paths:
    conn.execute("DELETE FROM deleted_images WHERE path=?", (p,))
    conn.execute("DELETE FROM user_images WHERE path=?", (p,))
conn.commit()
```

---

## 三、排查数据丢失的分步清单

发现数据丢失时，按这个顺序排查：

```
□ 丢失了哪个表的数据？
    例如：session、access_keys、user_images、deleted_images

□ 该表有哪些写操作入口？
    grep 表名 → 列出来（可能分布在 app.py、features/、db/operations.py）

□ 每个写操作是原子单行还是全量读写？
    看代码：单行 SQL ✅ / DELETE+INSERT ALL ❌

□ 多个入口之间有没有并发冲突？
    比如：app.py 全量写 + features 原子写 → 可能覆盖

□ 是不是"读→判断→写"三段没有锁保护？
    判断和写是否在同一个锁/事务里？

□ 事务是否有 try/except ROLLBACK 保护？
    没有 ROLLBACK 的话，半截写崩无法恢复。

□ 是不是 JSON 文件在操作？
    检查文件路径：.json / .txt 后缀 → 需要文件级锁
```

---

## 四、预防性设计原则

### 写操作前先问自己

```
① 我这个操作会影响哪些表？
② 每个表是单行还是全量？
③ 和别人同时在写会冲突吗？
④ 写到一半崩了会不一致吗？
⑤ 有办法回滚吗？
```

### 数据库操作层级规范

```
app.py / features/ 
      ↓  db.xxx()   ← 只能用 db 层的函数，不写裸 SQL
db/operations.py 
      ↓  _db().execute()  ← 用 ? 参数化，不拼用户输入
db/schema.py 
      ↓  get_db()   ← 单连接单例
SQLite
```

### 架构层面的保护措施

| 措施 | 作用 |
|------|------|
| WAL 模式 | 读不挡写，写不挡读 |
| busy_timeout 30s | 写排队超时自动抛异常，不卡死 |
| `BEGIN IMMEDIATE` | 避免多表操作中途被插入 |
| 每个函数独立 commit | 减少锁占有时间 |
| features 隔离 | 新功能不影响老代码 |

---

## 五、过去踩过的坑总结

| 日期 | Bug | 根因 | 修复 |
|------|-----|------|------|
| JSON 迁移期 | 不活跃用户 session 丢失 | `_save_sessions` 全量覆盖 | 改为单行 `save_session` + `update_session_access` |
| JSON 迁移期 | access_keys 绑定丢失 | `_save_access_keys` 全量覆盖 feature 的原子 INSERT | 改为 `db.claim/unclaim/increment/decrement` 原子函数 |
| 2026-06 | 镜像删除时部分图片标记未落库 | 批量操作在循环外部 commit，中间崩溃导致部分丢失 | 引入 `mark_images_deleted` 事务保护 |
| 2026-06 | GC 误删新生成的图片 | GC 扫描和生图任务时序竞争（TOCTOU） | 加 5 分钟新文件保护窗口 |

---

## 六、快速排查脚本（PowerShell）

在项目根目录执行：

```powershell
# 1. 检查 app.py 中裸 SQL 操作（非 PRAGMA / 管理命令）
grep -n "get_db().execute\|db._db().execute" web/app.py

# 2. 检查 _save_* 全量写函数定义
grep -n "def _save_" web/app.py

# 3. 检查全量读改写的调用模式
grep -n "_load_.*\|_save_" web/app.py | grep -v "^.*def _"

# 4. 检查某个表的写入入口分布
grep -rn "sessions\|access_keys\|reports\|deleted_images\|user_images" web/app.py web/features/ | grep -i "execute\|save\|delete\|insert\|update"

# 5. 检查事务保护
grep -rn "BEGIN\|COMMIT\|ROLLBACK" web/db/operations.py
```

---

## 七、SQLite 操作规范（原子写入篇）

### 7.1 三种写入模式对比

```python
# ─── 模式 A：原子单行（推荐，90% 场景用这个） ───
def update_user_role(github_id: str, role: str) -> None:
    _db().execute(
        "UPDATE users SET role=? WHERE github_id=?",
        (role, github_id)          # ← 参数单独传
    )
    _db().commit()                 # ← 写完就放锁
```

| 特点 | 说明 |
|------|------|
| 单条 SQL | 一个 execute 完成读+判+写 |
| 条件写进 WHERE | 由 SQLite 原子判断，无 TOCTOU |
| 独立 commit | 锁占有时间 = 1 条 SQL 执行时间 |

```python
# ─── 模式 B：事务保护的多表操作（批量/多表用） ───
def mark_images_deleted(github_id, paths):
    conn = _db()
    conn.execute("BEGIN IMMEDIATE")   # ← 一次性拿写锁
    try:
        for p in paths:
            conn.execute("INSERT INTO deleted_images ...")
        conn.execute("DELETE FROM user_images WHERE ...")
        conn.execute("DELETE FROM creator_ips WHERE ...")
        conn.commit()                 # ← 一次性放锁
    except Exception:
        conn.execute("ROLLBACK")      # ← 出错了全回滚
        raise
```

| 特点 | 说明 |
|------|------|
| BEGIN IMMEDIATE | 避免多个表之间被插入 |
| 纯 SQL 在事务内 | 不放 Python 计算，减少锁占有时间 |
| try/except ROLLBACK | 要么全成功，要么全回滚 |

```python
# ─── 模式 C：全量读改写 ❌ 不要用 ───
def bad_save(data):
    _db().execute("DELETE FROM xxx")   # ← 全删
    for k, v in data.items():
        _db().execute("INSERT INTO xxx ...")  # ← 全插
```

| 问题 | 后果 |
|------|------|
| 覆盖并发写入 | 另一个协程刚 INSERT 的行被 DELETE 掉 |
| 锁占有时间长 | DELETE + N 条 INSERT = 一条一条跑完才放锁 |
| 浪费 IO | 即使只改 1 行，也把所有行重写一遍 |

### 7.2 四种原子写操作

```sql
-- ① INSERT OR REPLACE（存在就更新，不存在就插入）
INSERT OR REPLACE INTO users (github_id, login, role)
VALUES (?, ?, ?);

-- ② INSERT OR IGNORE（存在就跳过，不存在就插入）
INSERT OR IGNORE INTO deleted_images (github_id, path, marked_at)
VALUES (?, ?, ?);

-- ③ UPDATE 条件判断（原子完成 "读→判→写"）
UPDATE access_keys
SET used_by=?
WHERE key=? AND (used_by='' OR used_by=?);
-- 条件写在 WHERE 里，SQLite 自己原子判断

-- ④ UPDATE 自增减（不读当前值，直接操作）
UPDATE access_keys
SET used_count = used_count + 1
WHERE key=?;
```

### 7.3 安全占位符规则

```python
# ✅ 正确：参数用 ? 占位，数据放第二个参数
_db().execute(
    "UPDATE users SET login=? WHERE github_id=?",
    (new_login, gid)
)

# ✅ 正确：LIKE 的 % 也放参数里
params.append(f"%{search}%")
_db().execute("SELECT * FROM users WHERE login LIKE ?", params)

# ✅ 正确：IN 子句动态生成 ? 列表
placeholders = ",".join("?" * len(items))
_db().execute(f"DELETE FROM xxx WHERE id IN ({placeholders})", items)
#                     ↑ 这里 {placeholders} 生成的是 "?,?,?"
#                       不是用户输入，安全

# ❌ 错误：直接拼接用户输入
_db().execute(f"SELECT * FROM users WHERE login='{user_input}'")   # SQL 注入！
```

### 7.4 事务使用原则

```python
# ① 什么时候该用显式事务？
#    答：需要多张表保持一致的时候（批量删除、GC 清理）

# ② 什么时候不该用显式事务？
#    答：单表单行操作（锁占有时间长，没必要）

# ③ 事务里不能放什么？
#    ❌ 网络请求（requests）
#    ❌ 文件 IO（open/read/write）
#    ❌ 阻塞计算（sleep、大循环）
#    这些会长时间占着写锁，让其他请求排队饿死！

# ④ 事务的正确写法
conn = _db()
conn.execute("BEGIN IMMEDIATE")   # 拿写锁（非管理员不等待）
try:
    conn.execute("DELETE FROM a WHERE ...")
    conn.execute("INSERT INTO b ...")
    conn.commit()                 # 放锁
except Exception:
    conn.execute("ROLLBACK")      # 出错了回滚
    raise
```

### 7.5 WAL 模式下的读写关系

```
WAL 模式 = 读不挡写，写不挡读

多个读可以同时进行：
  读 A ──► SQLite
  读 B ──► SQLite   ← 同时进行，不排队
  读 C ──► SQLite

写操作仍然排队：
  写 A ──► SQLite ──► DB-WAL
  写 B ─── 等待 ──►  ← 等写 A commit 后才能写
  写 C ─── 等待 ──►

WAL 合并时机：
  ① 正常关闭应用 → 自动合并
  ② checkpoint(TRUNCATE) → 手动合并
  ③ WAL 文件超过 1000 页 → SQLite 自动合并
```

### 7.6 常见错误写法检测清单

```
写代码时对照检查：

□ 是不是用 ? 占位符代替了 f"...{user_input}..."？
□ 是不是每张表的写操作都写了 commit？
□ 是不是多表操作用了 BEGIN IMMEDIATE + ROLLBACK？
□ 是不是事务里没有放网络请求/文件 IO？
□ 是不是修改了一个 dict 后又全量写回？
    （这种大概率是 JSON 遗留思维，改成单行操作）
□ 是不是锁的范围包含了"读"和"写"？

如果以上全 ✅，那这个写操作就是安全的。
```

### 7.7 原子函数命名惯例

```python
# 本项目中 db/operations.py 的命名规则：

# 单行写操作 → save_/update_/delete_ + 表名
save_gen_log(...)           # 单行 INSERT
update_user_role(...)       # 单行 UPDATE
delete_session(...)         # 单行 DELETE

# 原子判断+写 → 动词 + 业务名
claim_access_key(...)       # UPDATE + WHERE 条件判断
decrement_key_usage(...)    # UPDATE count = count - 1

# 事务保护批量操作 → 动词 + 业务名
mark_images_deleted(...)    # BEGIN→多表操作→COMMIT/ROLLBACK

# 仅供启动/GC 批量使用的全量写 → 注释注明"仅批量使用"
save_deleted_images(...)    # 注释：仅迁移/启动清理等批量场景使用，有事务保护
```

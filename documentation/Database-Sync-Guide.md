# 数据库同步、备份与还原指南

> 本文档说明如何使用图形界面工具，把旧 SQLite 数据同步到新 MySQL，并进行 MySQL 备份/还原。
>
> 日常推荐入口：`启动同步工具.bat`

---

## 1. 你平时应该用哪个工具？

推荐双击：

```text
I:\cc\natureDrawImage-main-mysqlRefactoring\启动同步工具.bat
```

它会打开图形界面：

```text
scripts\sync_gui.py
```

并使用项目虚拟环境：

```text
natureDrawImage-env\Scripts\python.exe
```

---

## 2. 同步工具能做什么？

图形界面里主要有三类功能：

| 功能 | 按钮 | 作用 |
|---|---|---|
| SQLite → MySQL 同步 | `仅预览` / `同步覆盖写入` | 从旧 SQLite 导入数据到新 MySQL |
| MySQL 备份 | `备份为...` | 把当前 MySQL 导出为 `.sql` 文件 |
| MySQL 还原 | `从文件还原...` | 从 `.sql` 文件恢复 MySQL |

---

## 3. 重要安全提醒

### 3.1 同步会覆盖新 MySQL

点击：

```text
同步覆盖写入
```

会先清空当前 MySQL 的 24 张表，再从 SQLite 写入。

所以如果当前 MySQL 有重要数据，先备份：

```text
备份为...
```

---

### 3.2 同步不会直接改老 SQLite

当前同步逻辑已经改成：

```text
只读打开老 SQLite → 复制临时快照 → 从临时快照同步到 MySQL
```

也就是说，平时选择旧项目的：

```text
I:\网站\shengtu\natureDrawImage-main-sqlit\web\db\natureDrawImage.db
```

同步工具不会直接写这个老库。

---

### 3.3 同步前必须关闭 Web

同步前建议状态：

```text
Web：关闭
MySQL：运行
```

原因：

- Web 运行时可能正在读写 MySQL；
- 同步会清空并重写 MySQL；
- GUI 会检测端口 23601，如果 Web 正在运行，会阻止同步。

---

## 4. SQLite → MySQL 同步流程

### 第 1 步：关闭 Web

如果 Web 是通过 `start-all.bat` 或 `start-web.bat` 启动的：

```text
在 Web 窗口按 Ctrl + C
```

如果你还想关闭 MySQL，则用 `stop-all.bat`；但同步时 MySQL 必须运行，所以同步前不要把 MySQL 关掉。

---

### 第 2 步：保持 MySQL 运行

同步工具需要连接 MySQL。

如果 MySQL 没开，可以先启动 MySQL，或运行 `init-db.bat`/相关 MySQL 脚本确保数据库可连接。

---

### 第 3 步：打开同步工具

双击：

```text
启动同步工具.bat
```

---

### 第 4 步：确认 SQLite 路径

默认路径通常是：

```text
I:\网站\shengtu\natureDrawImage-main-sqlit\web\db\natureDrawImage.db
```

如果路径不同，点：

```text
浏览...
```

选择正确的 `.db` 文件。

---

### 第 5 步：先点“仅预览”

推荐每次同步前都先点：

```text
仅预览
```

它会列出 SQLite 表和数据量，不写 MySQL。

当前已检测过完整迁移应有：

```text
24 张业务表
```

---

### 第 6 步：点“同步覆盖写入”

确认预览没问题后，点：

```text
同步覆盖写入
```

成功时日志会看到类似：

```text
创建 SQLite 只读快照...
清空 MySQL 现有数据...
users: ... 条
email_users: ... 条
email_users → users 补齐: ... 条
...
完整性检查通过：无孤儿外键，邮箱主用户已补齐
同步完成
```

---

## 5. 同步完整性说明

当前同步脚本覆盖 MySQL schema 的 24 张表：

```text
users
sessions
access_keys
user_images
deleted_images
gen_logs
deletion_logs
queue_items
reports
config
styles
characters
resolutions
workflow_meta
notifications
featured
banned_ips
creator_ips
kv_state
gc_logs
email_users
invite_codes
password_resets
email_logs
```

同步后会自动检查：

| 检查项 | 说明 |
|---|---|
| `orphan_sessions` | session 是否引用不存在的用户 |
| `orphan_user_images` | 图片记录是否引用不存在的用户 |
| `orphan_notifications` | 通知是否引用不存在的用户 |
| `missing_email_main_users` | 邮箱用户是否缺少主 users 记录 |

看到下面日志表示通过：

```text
完整性检查通过：无孤儿外键，邮箱主用户已补齐
```

---

## 6. 管理员角色迁移说明

旧库里可能出现这种情况：

```text
users.role = admin
email_users.role = user
```

当前同步脚本已经处理：

- 如果 `users` 主表中 `email:<邮箱>` 是 `admin`，同步后会保留管理员；
- 不会被 `email_users.role=user` 覆盖成普通用户；
- 同步时会把对应 `email_users.role` 也修正为 `admin`。

---

## 7. MySQL 备份

### 什么时候备份？

建议在这些情况前备份：

- 准备再次从 SQLite 同步；
- 准备修改数据库；
- 准备升级代码；
- 当前 MySQL 数据已经确认可用，想保存一个恢复点。

### 如何备份？

1. 关闭 Web；
2. 保持 MySQL 运行；
3. 双击 `启动同步工具.bat`；
4. 点：

```text
备份为...
```

5. 选择保存位置和文件名。

推荐文件名：

```text
natureDrawImage_mysql_2026-06-26_2100.sql
```

备份成功会显示类似：

```text
备份完成: xxx.sql
```

并且 `.sql` 文件大小不应为 0 KB。

---

## 8. MySQL 还原

### 什么时候还原？

- 同步错了；
- 数据误删了；
- 想回到某个备份时间点。

### 如何还原？

1. 关闭 Web；
2. 保持 MySQL 运行；
3. 双击 `启动同步工具.bat`；
4. 点：

```text
从文件还原...
```

5. 选择之前备份的 `.sql` 文件；
6. 按提示确认。

> 还原会覆盖/改变当前 MySQL 数据，还原前最好再备份一次当前状态。

---

## 9. 命令行同步入口

如果不想用图形界面，也可以命令行运行：

```bat
cd /d I:\cc\natureDrawImage-main-mysqlRefactoring
natureDrawImage-env\Scripts\python.exe scripts\sync_sqlite_to_mysql.py
```

指定 SQLite 路径：

```bat
natureDrawImage-env\Scripts\python.exe scripts\sync_sqlite_to_mysql.py "I:\网站\shengtu\natureDrawImage-main-sqlit\web\db\natureDrawImage.db"
```

但新手日常推荐用 GUI：

```text
启动同步工具.bat
```

---

## 10. 已废弃脚本

不要再用：

```text
scripts\migrate_data.py
scripts\convert_operations.py
```

原因：

- `migrate_data.py` 是旧的一次性迁移脚本，兼容性不如新同步工具；
- `convert_operations.py` 是旧的批量转换脚本，曾经用粗暴字符串替换，风险高。

现在它们已改为废弃提示，避免误运行。

---

## 11. 常见问题

### Q: 我是小白，平时到底点哪个？

点：

```text
启动同步工具.bat
```

然后：

```text
仅预览 → 同步覆盖写入
```

---

### Q: 同步前要关 MySQL 吗？

不要。

同步前应该：

```text
Web 关闭
MySQL 运行
```

---

### Q: 备份前要关 MySQL 吗？

不要。

备份需要连接 MySQL。

推荐：

```text
Web 关闭
MySQL 运行
点 备份为...
```

---

### Q: 关闭数据库用哪个？

用：

```text
stop-all.bat
```

它会尝试通知 Web，然后调用 MySQL 安全停机脚本。

---

### Q: 可以直接关 `start-all.bat` 窗口吗？

可以关 Web，但推荐按：

```text
Ctrl + C
```

如果要安全关闭 MySQL，再运行：

```text
stop-all.bat
```

---

### Q: MySQL 多久保存一次？

不是定时保存。项目写入数据库时会立即提交事务。安全关闭是为了避免强杀/断电导致损坏。

---

## 12. 推荐日常操作

### 从旧 SQLite 同步

```text
关 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 仅预览
点 同步覆盖写入
看到 完整性检查通过
重启 Web
```

### 备份当前 MySQL

```text
关 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 备份为...
保存 .sql 文件
```

### 还原 MySQL

```text
关 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 从文件还原...
选择 .sql 文件
```

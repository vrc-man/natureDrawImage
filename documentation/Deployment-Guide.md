# 项目初始部署与日常启动指南

> 本文档面向新手，记录当前项目实际可用的部署、启动、关闭和维护方式。
>
> 项目目录示例：`I:\cc\natureDrawImage-main-mysqlRefactoring`

---

## 1. 目录结构

推荐目录结构如下：

```text
I:\cc\
├── mysql-8.0.28-winx64\                 # MySQL 8.0 绿色便携版
│   ├── bin\mysqld.exe
│   ├── bin\mysql.exe
│   ├── bin\mysqldump.exe
│   ├── my.ini
│   ├── mysql.bat                         # MySQL 管理脚本，如 init/start/backup
│   └── stop_mysql.bat                    # MySQL 安全关闭脚本
│
├── Py64-311\python-3.11.8.amd64\         # 可选：便携 Python
│   └── python.exe
│
└── natureDrawImage-main-mysqlRefactoring\
    ├── natureDrawImage-env\              # 本项目 Python 虚拟环境
    ├── web\app.py                        # Web 主程序，端口 23601
    ├── web\db\schema.py                  # MySQL schema 和连接配置
    ├── .env                              # 环境变量，含 MySQL 密码、站点配置等
    ├── start-Py64-311.bat                # 创建/检查虚拟环境并启动 Web
    ├── start-all.bat                     # 启动 Web 循环模式
    ├── start-web.bat                     # 启动 Web
    ├── stop-all.bat                      # 安全关闭 Web/MySQL
    ├── init-db.bat                       # 初始化数据库/建表
    ├── 启动同步工具.bat                   # 打开 SQLite→MySQL 同步/备份/还原工具
    └── scripts\sync_gui.py               # 同步工具 GUI
```

---

## 2. 新手最常用脚本

| 操作 | 双击哪个文件 |
|---|---|
| 第一次创建/修复虚拟环境并启动 Web | `start-Py64-311.bat` |
| 平时启动 Web | `start-all.bat` 或 `start-web.bat` |
| 安全关闭 Web/MySQL | `stop-all.bat` |
| 初始化数据库建表 | `init-db.bat` |
| 打开同步/备份/还原工具 | `启动同步工具.bat` |

所有项目启动脚本都使用当前虚拟环境：

```text
I:\cc\natureDrawImage-main-mysqlRefactoring\natureDrawImage-env
```

---

## 3. 第一次部署流程

### 第 1 步：准备 MySQL 绿色版

MySQL 目录建议放在项目上级目录：

```text
I:\cc\mysql-8.0.28-winx64
```

如果还没有初始化 MySQL 系统库，先运行：

```bat
cd /d I:\cc\natureDrawImage-main-mysqlRefactoring
..\mysql-8.0.28-winx64\mysql.bat init
```

> 只需要初始化一次。

---

### 第 2 步：检查 `.env`

项目会从 `.env` 读取 MySQL 连接参数，例如：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DATABASE=natureDrawImage
```

不要把密码写进 `.py` 或 `.bat` 文件里。

---

### 第 3 步：创建/检查 Python 虚拟环境

双击：

```text
start-Py64-311.bat
```

它会：

1. 检查 `natureDrawImage-env` 是否存在；
2. 不存在时尝试使用 `I:\cc\Py64-311\python-3.11.8.amd64\python.exe` 创建；
3. 安装 `requirements.txt` 和 `pymysql`；
4. 启动 Web。

如果窗口提示缺 Python，请确认便携 Python 路径是否存在。

---

### 第 4 步：初始化数据库表

双击：

```text
init-db.bat
```

它会：

1. 检查/启动 MySQL；
2. 创建 `natureDrawImage` 数据库；
3. 启动 Web，让 `init_db()` 自动创建 24 张表。

看到类似下面输出即表示建表正常：

```text
[schema] 数据库就绪
```

或：

```text
[schema] 初始化完成
```

---

### 第 5 步：从旧 SQLite 导入数据（可选）

如果你是从旧 SQLite 项目迁移，双击：

```text
启动同步工具.bat
```

然后：

1. 确保 Web 关闭、MySQL 运行；
2. 点 `仅预览`；
3. 确认表和数量正常；
4. 点 `同步覆盖写入`。

详细说明见：

```text
documentation\Database-Sync-Guide.md
```

---

## 4. 日常启动项目

### 推荐方式

双击：

```text
start-all.bat
```

然后浏览器打开：

```text
http://127.0.0.1:23601
```

### 只启动 Web

也可以双击：

```text
start-web.bat
```

---

## 5. 日常关闭项目/数据库

### 只关闭 Web

在 `start-all.bat` 或 `start-web.bat` 窗口中按：

```text
Ctrl + C
```

这通常只会停止 Web，不一定停止 MySQL。

### 安全关闭 Web 和 MySQL

推荐双击：

```text
stop-all.bat
```

它会：

1. 尝试通知 Web 保存/关闭；
2. 调用 `I:\cc\mysql-8.0.28-winx64\stop_mysql.bat stop` 安全停止 MySQL。

> 不建议直接叉掉 MySQL 窗口，更不建议运行中直接拔移动硬盘。

---

## 6. 数据保存和备份

### MySQL 什么时候保存数据？

项目写入 MySQL 时一般会立即 `commit`。也就是说：

- 用户注册；
- 登录 session；
- 生图记录；
- 删除记录；
- 后台配置；

都会在操作时写入数据库，不是几分钟保存一次。

### 手动备份 MySQL

双击：

```text
启动同步工具.bat
```

点：

```text
备份为...
```

保存 `.sql` 文件。

推荐备份前：

```text
关闭 Web，保持 MySQL 运行
```

### 从备份还原 MySQL

双击：

```text
启动同步工具.bat
```

点：

```text
从文件还原...
```

选择之前保存的 `.sql` 文件。

还原前同样建议关闭 Web，保持 MySQL 运行。

---

## 7. 各脚本状态说明

### 正式使用

```text
启动同步工具.bat
scripts\sync_gui.py
scripts\sync_sqlite_to_mysql.py
scripts\sync_common.py
```

### 已废弃，不要再用

```text
scripts\migrate_data.py
scripts\convert_operations.py
```

这两个文件已经改成废弃提示，避免误运行。

---

## 8. 常见问题

### Q: 我平时迁移数据用哪个？

用：

```text
启动同步工具.bat
```

也就是 GUI 工具。

---

### Q: 同步会改老 SQLite 项目吗？

当前同步逻辑默认会先只读复制 SQLite 临时快照，再从快照同步到 MySQL。

也就是说：

```text
不会直接写老项目 SQLite 数据库
```

---

### Q: 同步会清空新 MySQL 吗？

会。

`同步覆盖写入` 会先清空当前 MySQL 24 张表，然后从 SQLite 快照重新写入。

所以同步前如果新 MySQL 里有重要数据，先点：

```text
备份为...
```

---

### Q: 盘符变了怎么办？

大部分脚本使用 `%~dp0` 相对路径。只要 `mysql-8.0.28-winx64`、`Py64-311` 和项目目录仍保持同级关系，一般不需要改。

---

### Q: 管理员账号迁移会丢吗？

已修复同步逻辑：

- 如果旧 SQLite 的 `users` 表中 `email:<邮箱>` 是 `admin`，同步后会保留；
- 不会再被 `email_users.role=user` 降权；
- 同时会把 `email_users.role` 同步为 `admin`。

---

## 9. 推荐日常流程

### 启动

```text
双击 start-all.bat
打开 http://127.0.0.1:23601
```

### 关闭

```text
双击 stop-all.bat
```

### 同步旧 SQLite 到 MySQL

```text
关闭 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 仅预览
点 同步覆盖写入
```

### 备份 MySQL

```text
关闭 Web
保持 MySQL 运行
双击 启动同步工具.bat
点 备份为...
```

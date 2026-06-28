# Linux 部署指南

> 本文档面向在 Linux 服务器上部署本项目的场景，涵盖 Ubuntu/Debian、CentOS/Rocky Linux 等主流发行版。

---

## 目录

1. [环境要求](#1-环境要求)
2. [安装 MySQL](#2-安装-mysql)
3. [安装 Python 与虚拟环境](#3-安装-python-与虚拟环境)
4. [克隆项目与配置](#4-克隆项目与配置)
5. [初始化数据库](#5-初始化数据库)
6. [配置 systemd 服务](#6-配置-systemd-服务)
7. [配置 Nginx 反向代理（可选）](#7-配置-nginx-反向代理可选)
8. [启动与关闭](#8-启动与关闭)
9. [日常运维](#9-日常运维)
10. [常见问题](#10-常见问题)

---

## 1. 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.11+ | 建议 3.11 |
| MySQL | 8.0+ | MariaDB 10.5+ 亦可 |
| Node.js | 18+ | 仅前端构建时需要 |
| ComfyUI | 已安装 | 需与本项目在同一台或可访问的机器 |
| NVIDIA GPU | 可选 | 用于 GPU 状态显示（`nvidia-smi`），非必须 |

---

## 2. 安装 MySQL

### Ubuntu/Debian

```bash
# 安装 MySQL 8.0
sudo apt update
sudo apt install mysql-server -y

# 检查状态
sudo systemctl status mysql

# 安全配置（可选但推荐）
sudo mysql_secure_installation
```

### CentOS/Rocky Linux 9

```bash
# 安装 MySQL 8.0
sudo dnf install mysql-server -y

# 启动并设置开机自启
sudo systemctl enable --now mysqld

# 检查状态
sudo systemctl status mysqld

# 获取临时 root 密码
sudo grep 'temporary password' /var/log/mysqld.log
```

### 创建数据库

```bash
# 登录 MySQL
sudo mysql -u root -p

# 创建数据库
CREATE DATABASE IF NOT EXISTS natureDrawImage CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 创建专用用户（推荐，避免使用 root）
CREATE USER 'drawing'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON natureDrawImage.* TO 'drawing'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

---

## 3. 安装 Python 与虚拟环境

```bash
# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv python3-pip -y

# CentOS/Rocky Linux
sudo dnf install python3.11 python3.11-pip -y
```

推荐将项目放在 `/opt/` 或用户目录下：

```bash
# 使用用户目录（单用户部署）
cd ~
python3.11 -m venv natureDrawImage-env
source natureDrawImage-env/bin/activate

# 安装依赖
pip install --upgrade pip
pip install fastapi uvicorn[standard] httpx websockets pydantic pillow cryptography python-multipart qrcode[pil] pymysql
```

或从项目 `requirements.txt` 安装：

```bash
git clone https://github.com/你的仓库/natureDrawImage-main-mysqlRefactoring.git
cd natureDrawImage-main-mysqlRefactoring
python3.11 -m venv natureDrawImage-env
source natureDrawImage-env/bin/activate
pip install -r requirements.txt
pip install pymysql   # requirements.txt 中有 fastapi 等，但可能需要额外安装 pymysql
```

---

## 4. 克隆项目与配置

```bash
# 克隆项目
cd /opt
git clone https://github.com/你的仓库/natureDrawImage-main-mysqlRefactoring.git
cd natureDrawImage-main-mysqlRefactoring

# 创建 Python 虚拟环境
python3.11 -m venv natureDrawImage-env
source natureDrawImage-env/bin/activate
pip install -r requirements.txt
pip install pymysql
```

### 配置 `.env`

```bash
cp .env.example .env
nano .env
```

关键配置项：

```ini
# MySQL 连接（用刚创建的用户）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=drawing
MYSQL_PASSWORD=你的密码
MYSQL_DATABASE=natureDrawImage

# Web 服务
WEB_HOST=127.0.0.1
WEB_PORT=8080

# ComfyUI 路径（根据实际安装位置修改）
OUTPUT_DIR_STR=/home/你的用户名/ComfyUI/output
COMFYUI_WORKFLOWS_DIR=/home/你的用户名/ComfyUI/user/default/workflows

# 站点信息
SITE_URL=http://你的域名或IP:8080
SITE_NAME=二次元绘梦

# 签名下载密钥（生成随机串）
DL_SECRET_KEY=你的随机32字节hex字符串

# SMTP 配置（可选，用于邮箱注册/登录）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASS=邮箱授权码
```

### 生成 `DL_SECRET_KEY`

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. 初始化数据库

### 初始化表结构

**方法一：直接启动 Web 自动建表**

```bash
source natureDrawImage-env/bin/activate
python3 -m uvicorn web.app:app --host 127.0.0.1 --port 8080
```

看到日志输出 `[schema] 数据库就绪` 或 `[schema] 初始化完成` 后按 `Ctrl+C` 停止。

**方法二：手动运行建表脚本**

```bash
source natureDrawImage-env/bin/activate
python3 -c "
from db.schema import init_db
init_db()
print('数据库初始化完成')
"
```

### 从旧 SQLite 导入数据（可选）

```bash
# 确保 MySQL 运行，Web 关闭
source natureDrawImage-env/bin/activate
python3 scripts/sync_sqlite_to_mysql.py --sqlite /path/to/old/natureDrawImage.db
```

---

## 6. 配置 systemd 服务

> 使用 systemd 管理 Web 服务的开机自启和日志收集，替代 Windows 的 bat 脚本。

### 创建服务文件

```bash
sudo nano /etc/systemd/system/nature-draw-image.service
```

```ini
[Unit]
Description=NatureDrawImage Web Service
After=network.target mysql.service mariadb.service
Wants=mysql.service mariadb.service

[Service]
Type=simple
User=你的用户名
Group=你的用户组
WorkingDirectory=/opt/natureDrawImage-main-mysqlRefactoring
EnvironmentFile=/opt/natureDrawImage-main-mysqlRefactoring/.env
ExecStart=/opt/natureDrawImage-main-mysqlRefactoring/natureDrawImage-env/bin/python3 -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 60
Restart=on-failure
RestartSec=5

# 日志
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 启用并启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable nature-draw-image
sudo systemctl start nature-draw-image

# 查看状态
sudo systemctl status nature-draw-image

# 查看实时日志
sudo journalctl -u nature-draw-image -f
```

### 常用命令

```bash
# 启动
sudo systemctl start nature-draw-image

# 停止
sudo systemctl stop nature-draw-image

# 重启
sudo systemctl restart nature-draw-image

# 状态
sudo systemctl status nature-draw-image

# 日志
sudo journalctl -u nature-draw-image -f --no-hostname
```

---

## 7. 配置 Nginx 反向代理（可选）

> 推荐用 Nginx 反向代理提供 HTTPS、域名访问和静态文件缓存。

### 安装 Nginx

```bash
sudo apt install nginx -y          # Ubuntu/Debian
sudo dnf install nginx -y          # CentOS/Rocky
```

### 配置站点

```bash
sudo nano /etc/nginx/sites-available/nature-draw-image
```

```nginx
server {
    listen 80;
    server_name 你的域名;

    # 重定向到 HTTPS（如果有证书）
    # return 301 https://$host$request_uri;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（生图进度推送必需）
        proxy_read_timeout 86400;
    }

    # 静态文件缓存（缩略图等）
    location /spa-assets/ {
        proxy_pass http://127.0.0.1:8080;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

### HTTPS（使用 certbot）

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d 你的域名

# 自动续期
sudo certbot renew --dry-run
```

### 启用站点

```bash
sudo ln -s /etc/nginx/sites-available/nature-draw-image /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. 启动与关闭

### 启动

```bash
# 确保 MySQL 已运行
sudo systemctl start mysql          # 或 mariadb
sudo systemctl status mysql

# 启动 Web（systemd 方式）
sudo systemctl start nature-draw-image

# 检查服务状态
sudo systemctl status nature-draw-image

# 查看日志
sudo journalctl -u nature-draw-image -f --no-hostname
```

### 关闭

```bash
sudo systemctl stop nature-draw-image
```

### 不使用 systemd，直接启动

```bash
cd /opt/natureDrawImage-main-mysqlRefactoring
source natureDrawImage-env/bin/activate
python3 start.py
```

> **注意**：`start.py` 当前包含 Windows 专用路径硬编码（`mysql-8.0.28-winx64`、`I:/cc/` 等），在 Linux 上会跳过 MySQL 检查。如果要用 `start.py`，建议先修改 `MYSQL_CANDIDATES` 中的路径或直接删除 MySQL 检查逻辑（Linux 上 MySQL 由 systemd 管理，不需要脚本检测）。

---

## 9. 日常运维

### 前端修改后构建

```bash
cd frontend
npm install      # 仅首次
npm run build    # 输出到 web/static/dist/
# 刷新页面即可生效，无需重启后端
```

### 查看服务日志

```bash
# Web 日志
sudo journalctl -u nature-draw-image -f --no-hostname

# 仅查看最近 100 行
sudo journalctl -u nature-draw-image -n 100 --no-hostname

# 按时间筛选
sudo journalctl -u nature-draw-image --since "10 min ago" --no-hostname
```

### 查看 nginx 访问日志

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 备份 MySQL

```bash
# 使用自带同步工具的 CLI 备份
cd /opt/natureDrawImage-main-mysqlRefactoring
source natureDrawImage-env/bin/activate
python3 -c "
from scripts.sync_common import backup_mysql
backup_mysql('/path/to/backup/natureDrawImage_$(date +%Y%m%d).sql')
print('备份完成')
"
```

或用 `mysqldump`：

```bash
mysqldump -u drawing -p natureDrawImage > backup_$(date +%Y%m%d).sql
```

### 还原 MySQL

```bash
mysql -u drawing -p natureDrawImage < backup_20260601.sql
```

---

## 10. 常见问题

### Q: 找不到 `pymysql`

```bash
source natureDrawImage-env/bin/activate
pip install pymysql
```

### Q: 端口 8080 被占用

修改 `.env` 中的 `WEB_PORT`，或换一个端口：

```bash
sudo lsof -i :8080   # 查看谁在用
```

### Q: GPU 状态不显示

确保 `nvidia-smi` 可用：

```bash
nvidia-smi
```

如果没装驱动：

```bash
# Ubuntu
sudo apt install nvidia-driver-550  # 或最新版本
sudo reboot

# CentOS/Rocky
sudo dnf install nvidia-driver
sudo reboot
```

### Q: WebSocket 连接失败（Nginx 反向代理）

确保 Nginx 配置中包含：

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 86400;
```

### Q: 路径问题

本项目部分代码使用 `Path` 对象（跨平台兼容），但 `start.py` 中仍有 Windows 硬编码路径。如果使用 systemd 服务文件直接启动 uvicorn（推荐方式），不存在此问题。

### Q: 文件权限

确保运行 Web 的用户对以下目录有读写权限：

```bash
chmod 755 /opt/natureDrawImage-main-mysqlRefactoring
chmod 644 /opt/natureDrawImage-main-mysqlRefactoring/.env
chmod -R 755 /path/to/ComfyUI/output
```

---

## 推荐目录结构

```
/opt/
├── natureDrawImage-main-mysqlRefactoring/   # 项目根目录
│   ├── natureDrawImage-env/                  # Python 虚拟环境
│   ├── web/
│   ├── frontend/
│   ├── .env
│   └── ...
│
└── ComfyUI/
    ├── ComfyUI/
    └── output/
```

## 推荐部署方案对比

| 方案 | 适用场景 | 优点 |
|-----|---------|------|
| systemd + Nginx + HTTPS | 公网服务器 | 稳定、安全、自动启停 |
| systemd + 直接 8080 | 内网/开发机 | 简单快速 |
| 手动启动 `uvicorn` | 临时/调试 | 方便看日志 |

---

> **与 Windows 版的主要区别：**
>
> - MySQL 由 apt/dnf 安装，systemd 管理 → 不再需要 `mysql.bat`、`stop_mysql.bat`
> - Web 由 systemd 服务管理 → 不再需要 `start-all.bat`、`stop-all.bat`
> - 路径使用 Linux 风格 `/opt/...` 而非 `I:\cc\...`
> - GPU 状态依然支持（`nvidia-smi` 跨平台）
> - `.env` 配置完全兼容，无需修改即可在 Linux 使用

# AI Agent 开发规则

## 核心原则
- **效率至上**：快速单元式开发
- **不写文档**：只写代码，不创建 README、GUIDE 等文档文件
- **改完即退**：完成代码修改后立即退出，用户会手动测试
- **单元提交**：每个功能/修改单独提交到 Git（需用户允许后方可提交）
- **闭嘴**：非用户要求不输出任何内容，静默更改代码完毕后直接退出

## 工作流程
1. 理解需求
2. 编写/修改代码
3. 展示 git diff 给用户，让用户确认内容无敏感信息且**用户明确同意后**，方可创建 Git 提交
4. 退出（不等待测试结果）

## Git 规则

### 敏感信息检查
- 提交前运行 `git diff --cached` 检查是否有 API 密钥、密码、Token、连接串等敏感信息被纳入暂存区
- 检查 `git status` 是否意外跟踪了 `*.json`、`*.txt`、`*.env`、`*.ini`、`*.config` 等可能含敏感数据的文件
- 特别注意 `web/db/*.db`、`web/db/*.db-shm`、`web/db/*.db-wal`（SQLite 用户数据库）和 `backups/`、`web/backups/`（备份目录）是否被意外跟踪
- 发现敏感信息立即提醒用户处理，**不得提交**

### 禁止命令
- **严禁**执行 `git clean` 任何变体（`git clean -fd`、`-fdx` 等）
- 需要清理工作区时，必须使用 `git checkout`、`git restore` 等安全命令

### 远端推送
- **必须经用户再三确认**后方可执行 `git push`
- 推送前必须问清楚用户要推送到哪个远端仓库（origin/其他）和哪个分支
- 未经用户明确指定远端和分支，不得执行推送

## 数据库架构备忘

### 删图安全链路（三层防护）

```
用户删图 → user_images 移除 + 写入 deleted_images → [GC] 删物理文件 + 清标记
                                                       → [重启] backfill 从 gen_logs 插回
                                                       → [API] GET /api/my-images 按 deleted_images 过滤
```

| 层 | 位置 | 机制 |
|---|------|------|
| ① 启动兜底 | `_cleanup_stale_user_images()` → `operations.py:300` | 检查文件是否存在，不存在则删 user_images 记录 |
| ② API 过滤 | `app.py GET /api/my-images` :6471 | 显式排除 deleted_images 中的路径 |
| ③ API 二次过滤 | 同一行 | 顺便检查磁盘文件是否存在 |

关键：backfill 本身不检查 deleted_images，但 API 层兜底过滤，所以已删图片永远不会出现在前端。

## 提交规范
- `feat:` - 新功能
- `fix:` - 修复 bug
- `refactor:` - 代码重构
- `style:` - 样式调整
- `perf:` - 性能优化
- `chore:` - 构建/工具/配置更新

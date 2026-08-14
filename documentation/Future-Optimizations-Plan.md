# 未来优化计划（Future Optimizations）

本文档记录**当前不实施、留作未来扩展储备**的优化方案，避免遗忘设计与安全分析。全部为「未来计划」，当前代码保持现状不动。

---

## 一、删除并发化（标记删除串行 + 日志/存档并发）

### 现状
`api_delete_my_images_all`（`web/app.py:7935`）与 `api_delete_my_images_batch`（`web/app.py:7902`）中：
```python
for p in paths:
    await _record_deletion(p, ...)   # 逐张串行
```
每张 `_record_deletion`（`web/app.py:2522`）做 3 件事：
1. **缩略图存档**：生成/复制缩略图到 `DELETION_THUMBS_DIR`（磁盘 IO，最重）
2. **创建者信息**：`lookup_creator_ip`（DB 查询）+ 可能 `_load_user_images()` 全表扫
3. **删除日志**：`add_deletion_log_entry`（DB 写）

几百上千张时线性耗时，主要瓶颈是缩略图磁盘复制。

### 方案
```
1. 锁内：_load_user_images() 快照 → paths + 预查创建者表 {path: (gid, login, ip)}
2. 锁内：db.mark_images_deleted(...)   ← 核心标记，单事务，完全不并发（数据不丢的关键）
3. 锁外：for batch in chunks(paths, 20):
            await asyncio.gather(*[_record_deletion(p, ..., preload=meta) for p in batch])
```

### 安全性分析（已核实）
| 环节 | 安全性 |
|---|---|
| `mark_images_deleted` 单事务标记 | ✅ 锁内串行，核心不丢 |
| `add_deletion_log_entry` | ✅ `get_db()` 是 thread-local 独立连接（`db/schema.py:138`），并发安全 |
| 磁盘缩略图复制 | ✅ 不同路径独立文件，互不覆盖 |
| `_generate_thumb` | ✅ 同路径并发只是写相同内容，不写坏 |
| 创建者预查 | ✅ 用项目现有 `_deletion_creator_meta`（`web/app.py:2500`，含 `_gen_logs_lookup` gen_logs 兜底）；`web/app.py:8459` 已有「预查字典」成熟先例 |

### 结论
**当前不做**。原因：单用户场景（下载一张删一张，`delete-all` 罕见），串行几秒可接受；稳定性优先。此方案作为多用户扩展/大量删除场景的优化储备。

---

## 二、孤儿扫描/删除加 `_SAFE_WINDOW`（可选）

### 现状
- 孤儿文件清扫（GC）：有 `_SAFE_WINDOW = 300`（5 分钟内新文件不当孤儿，防竞态误报）
- 孤儿 gen_logs 扫描/删除（`web/app.py:9812` `_run_orphan_scan`、`web/app.py:9986` `_delete_orphan_gen_logs`）：**没有**安全窗口

### 潜在风险
极端场景：图片刚生成、gen_logs 已写、但原图因延迟/迁移/外挂盘暂不可见 → 可能被误判孤儿。

### 方案（如未来需要）
给 `_run_orphan_scan` 和 `_delete_orphan_gen_logs` 增加判定：`created_at > now - 300` 的记录不判为孤儿。

### 结论
**当前不做**。原因：日常使用「一周前孤儿清理」（`delete-orphans-week-ago`），时间窗口足够长，极端竞态基本不会命中；且删除是手动确认流程，风险可控。作为未来可选优化储备。

---

## 关联参考
- `web/app.py:2500` `_deletion_creator_meta` —— 删除前抓创建者（含 gen_logs 兜底）
- `web/app.py:8459` —— 批量预查创建者的成熟先例
- `web/app.py:2613` `_generate_thumb` —— 缩略图生成
- `web/db/schema.py:138` `get_db()` —— thread-local 数据库连接

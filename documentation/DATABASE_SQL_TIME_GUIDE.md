# 数据库读写与时间处理规范

> 适用于本项目后续新增功能、重构和 Bug 修复。重点防止 JSON → SQLite → MySQL 迁移后再次引入时区不一致问题。

---

## 1. 总原则

本项目所有业务时间字段统一使用 **Unix epoch 秒** 存储，例如：

```python
import time
created_at = time.time()
```

数据库中保存的是类似：

```text
1782693826.123
```

它代表一个绝对时间点，**不携带时区，也不依赖 MySQL 的 time_zone 设置**。

---

## 2. 禁止在业务统计中使用 MySQL 时区函数

新增功能时，涉及日期筛选、统计、排行、清理任务时，不要使用：

```sql
CURDATE()
UNIX_TIMESTAMP()
FROM_UNIXTIME()
NOW()
DATE(NOW())
DATE(FROM_UNIXTIME(...))
```

原因：这些函数会受到 MySQL server/session 时区影响。不同部署环境可能是 UTC、UTC+8、Docker 默认 UTC、云数据库自定义时区，容易导致统计日期错位。

---

## 3. 时间范围查询使用半开区间

统一使用：

```sql
created_at >= %s AND created_at < %s
```

不要使用：

```sql
created_at <= %s
```

推荐语义：

```text
[start, end)
包含开始时间，不包含结束时间
```

例如用户选择：

```text
2026-06-29 到 2026-06-29
```

前端应传：

```text
date_from = 2026-06-29 00:00:00
date_to   = 2026-06-30 00:00:00
```

后端查询：

```sql
WHERE created_at >= date_from AND created_at < date_to
```

这样可以完整覆盖：

```text
2026-06-29 00:00:00.000
到
2026-06-29 23:59:59.999...
```

并且不会包含第二天。

---

## 4. 前端日期参数规范

管理后台涉及日期范围时，统一使用：

```ts
function dayStartTs(date: string) {
  return new Date(date + 'T00:00:00').getTime() / 1000
}

function nextDayStartTs(date: string) {
  const d = new Date(date + 'T00:00:00')
  d.setDate(d.getDate() + 1)
  return d.getTime() / 1000
}
```

本项目已提供公共 helper：

```text
frontend/src/components/admin/dateRange.ts
```

用法：

```ts
import { dayStartTs, nextDayStartTs } from './dateRange'

if (dateFrom.value) params.push('date_from=' + dayStartTs(dateFrom.value))
if (dateTo.value) params.push('date_to=' + nextDayStartTs(dateTo.value))
```

不要再写：

```ts
new Date(dateTo.value + 'T23:59:59').getTime() / 1000
new Date(dateTo.value).setHours(23, 59, 59)
```

这些写法会漏掉结束日期最后一秒内的小数时间。

---

## 5. 后端 Python 参数规范

后端接收 `date_from` / `date_to` 后，不要再做时区转换，直接作为 epoch 秒参与比较：

```python
conditions = []
params = []

if date_from:
    conditions.append("created_at >= %s")
    params.append(date_from)

if date_to:
    conditions.append("created_at < %s")
    params.append(date_to)
```

删除日志、GC 日志、邮件日志等同理：

```sql
deleted_at >= %s AND deleted_at < %s
timestamp >= %s AND timestamp < %s
```

---

## 6. 今日 / 本周 / 本月统计规范

如果后端需要计算“今天”的时间范围，应基于浏览器传入的 `tz_offset` 计算 epoch 边界。

```python
now = time.time()
today_start = now - ((now + tz_offset * 3600) % 86400)
today_end = today_start + 86400
```

然后使用：

```sql
created_at >= today_start AND created_at < today_end
```

不要使用：

```sql
DATE(FROM_UNIXTIME(created_at)) = CURDATE()
```

---

## 7. 小时分组规范

按用户本地小时分组时，使用纯 epoch 数学：

```sql
FLOOR((created_at + %s) / 3600) % 24
```

其中 `%s = tz_offset * 3600`。

如果前端要求小时是字符串 `"00" ~ "23"`，SQL 可写：

```sql
LPAD(FLOOR((created_at + %s) / 3600) % 24, 2, '0') AS hour
```

注意参数顺序：如果 SQL 的第一个 `%s` 是 `created_at + %s`，那么参数列表第一个值必须是 `tz_offset * 3600`。

正确：

```python
params = [tz_offset * 3600, date_from, date_to]
```

如果已有其它查询条件参数，例如：

```sql
SELECT FLOOR((created_at+%s)/3600)%24 AS hh
FROM gen_logs
WHERE login=%s AND created_at >= %s AND created_at < %s
```

参数必须是：

```python
params = [tz_offset * 3600, login, date_from, date_to]
```

---

## 8. 日期分组规范

不要使用：

```sql
DATE(FROM_UNIXTIME(created_at + %s))
```

因为 `FROM_UNIXTIME` 仍会受 MySQL 会话时区影响，可能产生二次偏移。

推荐使用纯数学日期分组：

```sql
DATE('1970-01-01') + INTERVAL FLOOR((created_at + %s) / 86400) DAY AS day
```

其中 `%s = tz_offset * 3600`。

---

## 9. 存储规范

新增表如果需要业务时间字段，优先使用：

```sql
DOUBLE NOT NULL DEFAULT 0
```

或根据需要使用高精度数值字段。

字段命名建议：

```text
created_at
updated_at
deleted_at
timestamp
expires_at
```

写入时由 Python 生成：

```python
time.time()
```

不要依赖数据库默认值：

```sql
DEFAULT CURRENT_TIMESTAMP
```

除非该字段只是数据库内部审计用途，且不会参与前端日期筛选或业务统计。

---

## 10. 常见错误示例

### 错误：MySQL 今日统计

```sql
SELECT COUNT(*) FROM gen_logs
WHERE DATE(FROM_UNIXTIME(created_at)) = CURDATE()
```

### 正确：epoch 范围统计

```sql
SELECT COUNT(*) FROM gen_logs
WHERE created_at >= %s AND created_at < %s
```

---

### 错误：结束日期 23:59:59

```ts
new Date(dateTo + 'T23:59:59').getTime() / 1000
```

### 正确：下一天 00:00:00

```ts
nextDayStartTs(dateTo)
```

---

### 错误：日期分组依赖 FROM_UNIXTIME

```sql
DATE(FROM_UNIXTIME(created_at + %s)) AS day
```

### 正确：数学分组

```sql
DATE('1970-01-01') + INTERVAL FLOOR((created_at + %s) / 86400) DAY AS day
```

---

## 11. 改动后验证建议

涉及日期筛选或统计的改动，至少搜索确认：

```text
CURDATE
UNIX_TIMESTAMP
FROM_UNIXTIME
T23:59:59
setHours(23
created_at <=
deleted_at <=
timestamp <=
```

如果搜索结果是业务时间范围查询，应优先改为 epoch 半开区间。

---

## 12. 当前项目已统一的范围

截至 2026-06-29，本项目已统一以下模块：

- 系统统计 `gen_stats`
- 生图排行榜 `gen_leaderboard`
- 生图日志筛选 / 清理 / 孤儿扫描
- 删除日志筛选 / 清理
- 图片按日期条件删除
- 邮件日志筛选
- GC 日志筛选

以上模块不再依赖 MySQL 时区。

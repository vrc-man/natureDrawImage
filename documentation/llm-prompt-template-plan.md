# LLM 系统提示词模板库 — 实施计划

## 目标
管理员可后台维护多套“LLM 提示词规则模板”（针对 Anima / Pony / 写实等不同工作流/模型）。
用户生图时手动选择模板，LLM 按模板规则生成最终正负提示词。
**复用原 tags 模式的全部数据流与正负拆分机制，只替换 system prompt 的规则内容。**

## 硬边界（绝不触碰）
- 不动 `gen_logs` 表 / 生图日志写入/查询/展示/fork 逻辑
- 不动 `GenLogSection.vue`、`creator_ips`、`user_images`、路径记录、GC、孤儿扫描
- 不给日志加 template_id / 模板名 / 快照
- 不动 `schema.py` / `operations.py`（模板不进主 SQLite）
- 不改原 tags / natural 两个内置模式（保留并存）

## 存储
JSON 文件：`web/llm_prompt_templates.json`（数组）。带线程锁 + 原子写 + 损坏不自动清空。
字段：id, name, description, system_generate, system_rewrite, enabled, sort_order, created_at, updated_at。

## 改动清单

### 新增（外挂）
1. `web/features/llm_prompt_templates.py`
   - JSON 读写（_load / _save_atomic / _lock，损坏抛错不清空）
   - CRUD：list_all / list_enabled / get_enabled(id) / create / update / delete
   - admin router：`/api/admin/features/llm-templates` GET/POST/PUT/DELETE
   - public router：`GET /api/features/llm-templates`（仅 enabled，给用户下拉）
   - 导出 `get_enabled_template(id)` 供主流程调用
2. `web/features/__init__.py`：register_all 加一行挂载（routers.append）
3. `frontend/src/components/admin/LlmPromptTemplateSection.vue`：CRUD 界面（名称/说明/generate规则/rewrite规则/启用/排序）

### 老代码最小打孔
4. `web/app.py` `RunRequest`（L5270）：加字段 `llm_template_id: Optional[int] = None`
5. `web/app.py` `translate_prompt`（L3043）：加参数 `template_id=None` + 一个分支：
   - 有 template_id：system = NSFW + (rewrite时 system_rewrite or system_generate / 否则 system_generate) + _LLM_OUTPUT_RULE；走 _parse_pos_neg
   - 无 template_id：完全走原 tags/natural 逻辑（不变）
   - 模板查询用 try/except，查不到/禁用则回退原逻辑
6. `web/app.py` 两处调用（L6430 / L6436）：透传 `template_id=req.llm_template_id`

### 前端用户端
7. `frontend/src/pages/Home.vue`：
   - 新增 `llmTemplateId` ref + localStorage 持久化
   - 模式下拉旁新增独立“提示词模板”下拉（默认“不使用”，列 enabled 模板）
   - payload 加 `llm_template_id`
8. `frontend/src/pages/Admin.vue`：system 组里新增 `{ key:'llmtpl', title:'🧩 LLM 提示词模板', comp: LlmPromptTemplateSection }`

## 验证
- `.venv\Scripts\python.exe -m py_compile web/app.py web/features/llm_prompt_templates.py`
- `cd frontend; npm run build`
- 不传 template_id 时行为与现状完全一致（向后兼容）

## 已决定
- 输出格式系统统一追加 POSITIVE/NEGATIVE（管理员只写规则，方案A）
- 用户端独立模板下拉，内置 tags/natural 保留并存
- 模板手动选，不绑定工作流
- 第一版只做标签型自定义模板（不做 is_natural / 自定义分隔符 / 工作流绑定）

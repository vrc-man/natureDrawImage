# AI 聊天技能开发指南（Skills）

给 AI 聊天（ai_chat）扩展工具能力。**加技能 = 建一个目录**，像 ComfyUI custom_nodes 一样自动发现，无需改主文件。

## 目录结构

```
web/features/ai_chat_skills/
├── SKILLS.md                    # 本文档
├── skill_template/              # 模板（复制它改）
├── new_skill.py                 # 脚手架：python new_skill.py 技能名 "描述"
├── search_characters/           # 已有技能示例
│   ├── skill.json
│   ├── main.py
│   └── data/
├── search_styles/
├── search_workflows/
├── get_recommended_dimensions/
└── trigger_generation/
```

## 一个技能最少要有什么

每个技能是一个目录，含：
1. **`skill.json`** —— 说明书（LLM 看到的名称/描述/参数 schema）+ 入口声明
2. **`main.py`** —— 实现 `execute(args, ctx) -> str`
3. **`data/`**（可选）—— 技能自己的私有数据（json/sqlite 随便，技能自管）
4. 其他辅助 py / 子目录随便放，只要 skill.json 入口指向能用的函数

## skill.json 字段

```json
{
  "name": "技能名（小写下划线，唯一）",
  "description": "一句话：做什么 + 什么时候调用（LLM 据此决定是否调用）",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "参数说明" }
    },
    "required": ["query"]
  },
  "entry": "main.py:execute",      // 入口：文件:函数
  "data_dir": "data",              // 技能私有数据目录（相对技能目录）
  "shared": { "characters": "characters.json" }   // 引用的全局共享文件（相对 web/）
}
```

## main.py 约定

```python
def execute(args: dict, ctx) -> str:
    # args: LLM 按 parameters 传的参数
    # ctx.data_dir: 技能私有数据目录绝对路径
    # ctx.shared: {别名: 共享文件绝对路径}
    # ctx.ai_config: ai_chat.json 配置（含 llms/searxng 等）
    return "工具结果文本（回填给 LLM）"
```

- execute 可以是 **同步或 async**（加载器自动处理）
- 返回 `str`，会作为 tool 结果回填给 LLM
- 数据优先放自己 `data/`（自包含、可拷贝分享）
- **全局共享数据**（多端要用）用 `shared` 声明，加载器注入路径

## 加技能步骤

1. `python web/features/ai_chat_skills/new_skill.py 我的技能 "描述"`
   （或复制 `skill_template/` 改名为技能名）
2. 编辑 `skill.json`：改 description / parameters
3. 实现 `main.py` 的 `execute(args, ctx)`
4. 重启后端 → 自动发现，AI 就能调用

## 调试

```bash
# 列出已发现的技能
python -c "import sys; sys.path.insert(0,'web'); import features.ai_chat as a; print(a._SKILLS.keys())"

# 单独测一个技能
python -c "import sys,asyncio,json; sys.path.insert(0,'web'); import features.ai_chat as a; c={'function':{'name':'search_characters','arguments':json.dumps({'query':'甘雨'})}}; print(asyncio.run(a._exec_search_tool(c,[])))"
```

## 约定

- 目录名 = skill.json 的 `name`（小写下划线）
- `skill_template/`、`__pycache__/`、`.`/`_` 开头目录会被跳过，不会被加载
- 技能执行异常不会影响主流程（返回错误文本给 LLM）

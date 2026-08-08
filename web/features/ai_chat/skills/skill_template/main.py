"""技能模板：新技能从这里复制。

execute(args, ctx) 是唯一入口。
- args: dict，来自 LLM 的 function calling 参数（按 skill.json 的 parameters 定义）
- ctx: SkillContext，提供 data_dir（技能自己的数据目录）和 shared（共享文件路径映射）
返回: str（工具结果文本，会回填给 LLM）
"""


def execute(args: dict, ctx) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "（参数为空）"
    # 读技能自己的数据
    # import json, os
    # with open(os.path.join(ctx.data_dir, "my.json"), encoding="utf-8") as f: ...
    # 读共享文件
    # chars_path = ctx.shared.get("characters")
    return f"技能执行结果：{query}"

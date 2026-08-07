"""trigger_generation 技能：生图参数提交占位。

参数由 ai_chat.py 的 agent 循环捕获（gen_card），这里只是确认接收。
execute 不会被真正用于生成，返回值告知 LLM 继续输出卡片。
"""


def execute(args: dict, ctx) -> str:
    return "生图参数已接收，请直接向用户输出最终生图卡片。"

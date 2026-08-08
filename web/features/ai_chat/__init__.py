"""AI 聊天生图助手插件。

兼容旧引用：SKILLS.md 测试脚本用 `features.ai_chat._SKILLS` / `_exec_search_tool`。
"""

from .main import *
from .main import (
    router,
    CONFIG_DIR,
    JSON_PATH,
    _SKILLS,
    _CHAR_MEM,
    _ALIAS_MEM,
    _exec_search_tool,
    _call_llm,
    _call_llm_stream,
    _build_workflow_cache,
    _workflow_rule_name,
    _prompt_instruction_for_workflow,
    _prompt_style_for_workflow,
)

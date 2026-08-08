"""LLM 提示词模板插件。

兼容旧引用：app.py 里 `from features.llm_prompt_templates import get_enabled_template`。
"""

from .main import router
from .main import (
    get_enabled_template,
    list_all,
    create_template,
    update_template,
    delete_template,
)

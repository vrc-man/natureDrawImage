#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新建 AI 聊天技能骨架。

内置 YAML 模板，第一次运行时自动释放到技能目录，不依赖外部模板文件
（*.yaml 被 .gitignore 忽略，可能不在仓库里）。

用法：
    python new_skill.py 技能名 "技能描述"
示例：
    python new_skill.py get_weather "查询天气。用户问天气时调用。"
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE

# 内置 YAML 模板（首次自动释放）。{NAME} / {DESC} 会被替换。
YAML_TEMPLATE = """\
# 技能定义（说明 + schema + 入口）。yaml 可写注释，比 json 好维护。
# 注意：本文件默认被 .gitignore 忽略（*.yaml），不进 git。想分享技能需另发定义。
name: {NAME}

# 用一句话说明这个技能做什么、什么时候被调用。会作为 LLM 的 function calling 描述。
description: {DESC}

# LLM 调用参数定义（OpenAI function calling 的 parameters）
parameters:
  type: object
  properties:
    query:
      type: string
      description: 参数说明
  required:
    - query

# 入口：文件:函数
entry: main.py:execute

# 技能私有数据目录（相对技能目录）
data_dir: data

# 引用的全局共享文件（相对 web/）
shared: {}
"""

# 内置 main.py 模板（首次自动释放）
PY_TEMPLATE = '''"""{NAME} 技能。实现 execute(args, ctx)。

- args: dict，来自 LLM 的 function calling 参数（按 skill.yaml 的 parameters 定义）
- ctx: SkillContext，提供 data_dir（技能私有数据目录）和 shared（共享文件路径映射）
返回: str（工具结果文本，会回填给 LLM）
"""


def execute(args: dict, ctx) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "（参数为空）"
    # 读技能自己的数据：ctx.data_dir
    # 读共享文件：ctx.shared.get("xxx")
    return f"技能执行结果：{query}"
'''


def to_snake(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip()).strip("_").lower() or "my_skill"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    name = sys.argv[1].strip()
    desc = sys.argv[2].strip() if len(sys.argv) > 2 else "用一句话说明这个技能做什么、什么时候被调用。"
    if not name:
        print("需要技能名")
        return 1
    dir_name = to_snake(name)
    target = SKILLS_DIR / dir_name
    if target.exists():
        print(f"技能目录已存在: {target}")
        return 1

    target.mkdir(parents=True)
    data_dir = target / "data"
    data_dir.mkdir(exist_ok=True)

    # 释放内置模板（不依赖外部 skill_template 文件）
    (target / "skill.yaml").write_text(
        YAML_TEMPLATE.replace("{NAME}", dir_name).replace("{DESC}", desc), encoding="utf-8"
    )
    (target / "main.py").write_text(PY_TEMPLATE.replace("{NAME}", dir_name), encoding="utf-8")

    print(f"已创建技能: {target}")
    print("改 skill.yaml 的参数定义，再实现 main.py 的 execute(args, ctx) 即可。")
    print("重启后端后自动加载，AI 就能调用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

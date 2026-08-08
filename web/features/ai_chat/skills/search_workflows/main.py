"""search_workflows 技能：读取 ai_chat.py 重启时生成的工作流清单缓存。

缓存文件：本技能 data/workflows.json（由 ai_chat.py 每次重启扫描生成）。
"""
import json
import os


def execute(args: dict, ctx) -> str:
    cache = os.path.join(ctx.data_dir, "workflows.json")
    if not os.path.isfile(cache):
        return "（工作流清单缓存未生成，请重启后端刷新）"
    try:
        wfs = json.load(open(cache, encoding="utf-8"))
    except Exception:
        return "（工作流清单缓存读取失败，请重启后端刷新）"
    q = str(args.get("query", "")).strip().lower()
    hits = [w for w in wfs if not q or q in w.get("name", "").lower() or q in w.get("category", "").lower() or q in w.get("path", "").lower()]
    if not hits:
        return "（未找到匹配工作流，可沿用当前工作流）"
    lines = [f"- {w.get('name')}（分类：{w.get('category')}）：{w.get('path')}" for w in hits[:12]]
    return "工作流候选：\n" + "\n".join(lines)

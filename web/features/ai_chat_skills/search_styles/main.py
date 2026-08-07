"""search_styles 技能：按关键词搜画风库，返回前 10 条。"""
import json


def _load_styles(ctx) -> list:
    try:
        # 优先 ai_chat.json 的 skill_data.styles_file，缺省回退 skill.json shared
        p = ctx.data.get("styles_file") or ctx.shared.get("styles") or ""
        if not p:
            return []
        d = json.load(open(p, encoding="utf-8"))
        return [s for s in d if isinstance(s, dict) and str(s.get("name", "")).strip()]
    except Exception:
        return []


def execute(args: dict, ctx) -> str:
    styles = _load_styles(ctx)
    q = str(args.get("query", "")).strip().lower()
    if not q:
        return "（画风库为空或未匹配）"
    hits = [s for s in styles if q in str(s.get("name", "")).lower() or q in str(s.get("category", "")).lower() or q in str(s.get("tags", "")).lower()]
    if not hits:
        return "（未找到匹配画风，可直接用自然语言描述画风）"
    lines = [f"- {s.get('name')}（{s.get('category', '未分类')}）：{s.get('tags', '')[:80]}" for s in hits[:10]]
    return "画风候选：\n" + "\n".join(lines)

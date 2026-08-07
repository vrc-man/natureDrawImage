"""get_recommended_dimensions 技能：按宽高比返回推荐尺寸。"""

_DIMS = {
    "1:1": "1024x1024", "2:3": "832x1216", "3:2": "1216x832",
    "3:4": "896x1152", "4:3": "1152x896", "9:16": "768x1344",
    "16:9": "1344x768", "2:1": "1216x608", "1:2": "608x1216",
}
_ALIASES = {
    "竖屏": "3:4", "横屏": "16:9", "方图": "1:1", "方形": "1:1",
    "竖版": "3:4", "横版": "16:9", "手机": "9:16", "壁纸竖": "9:16", "壁纸横": "16:9",
}


def execute(args: dict, ctx) -> str:
    ar = str(args.get("aspect_ratio", "3:4")).strip()
    if not ar:
        ar = "3:4"
    ar = _ALIASES.get(ar.lower(), ar)
    if ar in _DIMS:
        return f"推荐尺寸 {_DIMS[ar]}"
    # 尝试解析 "WxH"
    try:
        import re
        m = re.match(r"(\d+)[xX×](\d+)", ar)
        if m:
            return f"推荐尺寸 {m.group(1)}x{m.group(2)}"
    except Exception:
        pass
    return "推荐尺寸 896x1152"

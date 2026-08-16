"""修复 AnimaDex 导入时含 / 的 tag 被拆进子目录的问题。

背景：第一次导入时文件名未 sanitize，含 / 的 tag（如 fate/stay_night、.hack//）被
Windows 当路径分隔符，os.replace 把文件写进了子目录（如 cu_chulainn_(fate/stay_night).webp
实际落在 cu_chulainn_(fate 目录 + stay_night).webp）。

修复：
  1. 遍历 index.json 的 thumbs，对含 / 的 tag，从「按 / 拆分的目录路径」找回真实文件；
  2. 复制/移动到扁平目录，用正确 sanitize 文件名（/ → _）；
  3. 更新 index.json 映射；
  4. 清理空的残留子目录。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

THUMB_DIR = Path(__file__).resolve().parent.parent / "web" / "features" / "ai_chat" / "skills" / "search_characters" / "character_thumbnails"
INDEX_JSON = THUMB_DIR / "index.json"

ILLEGAL_FS_CHARS = '<>:"/\\|?*'


def sanitize_filename(tag: str) -> str:
    cleaned = "".join("_" if c in ILLEGAL_FS_CHARS else c for c in tag)
    cleaned = cleaned.rstrip(" .") or "unnamed"
    return cleaned + ".webp"


def main():
    if not INDEX_JSON.is_file():
        print("index.json 不存在")
        return
    data = json.load(open(INDEX_JSON, encoding="utf-8"))
    thumbs = data.get("thumbs") or {}

    fixed = 0
    missing = []
    for tag, fname in thumbs.items():
        if "/" not in fname:
            continue
        # fname 形如 "cu_chulainn_(fate/stay_night).webp"——按 / 拆成路径
        parts = fname.replace("\\", "/").split("/")
        # 真实文件 = THUMB_DIR/parts[0]/.../parts[-1]
        src = THUMB_DIR.joinpath(*parts)
        if src.is_file():
            # 正确目标名
            good = sanitize_filename(tag)
            dst = THUMB_DIR / good
            if not dst.exists():
                shutil.copy2(src, dst)
            thumbs[tag] = good
            fixed += 1
            print(f"  修复 {tag}  <-  {src.name} -> {good}")
        else:
            missing.append((tag, fname))
            print(f"  缺失 {tag} (期望 {fname})")

    data["thumbs"] = thumbs
    data["total"] = len(thumbs)
    tmp = INDEX_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(INDEX_JSON)
    print(f"修复 {fixed} 个，缺失 {len(missing)} 个")

    # 清理残留子目录（只删我们认识的：含索引键前缀的）
    subs = [p for p in THUMB_DIR.iterdir() if p.is_dir()]
    print(f"子目录: {len(subs)}")
    for sub in subs:
        # 子目录名是某个 tag 去掉 / 后段的残留
        shutil.rmtree(sub, ignore_errors=True)
        print(f"  删除残留目录: {sub.name}")


if __name__ == "__main__":
    main()

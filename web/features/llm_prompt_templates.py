"""
外挂功能：LLM 系统提示词模板库（JSON 存储，不进主 SQLite，不碰生图日志）。

设计：
  - 模板数据存 web/llm_prompt_templates.json（数组），带线程锁 + 原子写。
  - JSON 损坏时**抛错**，绝不自动清空（避免后台一保存把模板全清掉）。
  - 复用原 tags 模式机制：模板只提供 system prompt 规则；NSFW 绕过 + 输出格式
    POSITIVE/NEGATIVE 由主流程（app.translate_prompt）统一包头尾，本模块不管解析。

接口：
  GET    /api/admin/features/llm-templates          列表（管理，全部）
  POST   /api/admin/features/llm-templates          新增
  PUT    /api/admin/features/llm-templates/{tid}     编辑
  DELETE /api/admin/features/llm-templates/{tid}     删除
  GET    /api/features/llm-templates                 用户端：仅 enabled（下拉用，公开只读）

供主流程调用：
  get_enabled_template(tid) -> dict | None
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, HTTPException

from features._deps import require_admin

# 数据文件：与 styles.json / characters.json 同级（web/ 目录）
_WEB_DIR = Path(__file__).resolve().parent.parent          # .../web
JSON_PATH = _WEB_DIR / "llm_prompt_templates.json"

_lock = threading.Lock()

FEATURE_VERSION = "1.0.0"

# 字段长度上限（防滥用 / 防 JSON 膨胀）
_MAX_NAME = 100
_MAX_DESC = 500
_MAX_PROMPT = 20000


# ────────────────────────── JSON 读写 ──────────────────────────

def _load() -> List[Dict[str, Any]]:
    """读取模板列表。文件不存在返回空；**内容损坏抛错（不自动清空）**。"""
    if not JSON_PATH.exists():
        return []
    try:
        with JSON_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        # 关键：损坏时不要返回 []，否则一次保存就会覆盖掉损坏文件丢失全部模板
        raise RuntimeError(f"llm_prompt_templates.json 解析失败，已停止写入以防丢失: {e}")
    if not isinstance(data, list):
        raise RuntimeError("llm_prompt_templates.json 根节点必须是数组")
    return data


def _save_atomic(items: List[Dict[str, Any]]) -> None:
    """原子写入（tmp + os.replace），UTF-8、不转义中文。"""
    tmp = JSON_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, JSON_PATH)


def _next_id(items: List[Dict[str, Any]]) -> int:
    mx = 0
    for it in items:
        try:
            mx = max(mx, int(it.get("id", 0)))
        except Exception:
            pass
    return mx + 1


def _normalize(it: Dict[str, Any]) -> Dict[str, Any]:
    """规整单条模板（截断、补默认值、类型修正）。"""
    name = str(it.get("name", "")).strip()[:_MAX_NAME]
    desc = str(it.get("description", "")).strip()[:_MAX_DESC]
    sg = str(it.get("system_generate", ""))[:_MAX_PROMPT]
    sr = str(it.get("system_rewrite", ""))[:_MAX_PROMPT]
    try:
        sort_order = int(it.get("sort_order", 0))
    except Exception:
        sort_order = 0
    return {
        "id": int(it.get("id", 0)),
        "name": name,
        "description": desc,
        "system_generate": sg,
        "system_rewrite": sr,
        "enabled": bool(it.get("enabled", True)),
        "sort_order": sort_order,
        "created_at": float(it.get("created_at", 0) or 0),
        "updated_at": float(it.get("updated_at", 0) or 0),
    }


def _public_view(it: Dict[str, Any]) -> Dict[str, Any]:
    """用户端下拉只需要 id / name / description，不暴露完整 system prompt。"""
    return {"id": it["id"], "name": it["name"], "description": it["description"]}


# ────────────────────────── 业务函数 ──────────────────────────

def list_all() -> List[Dict[str, Any]]:
    with _lock:
        items = [_normalize(x) for x in _load()]
    items.sort(key=lambda x: (x["sort_order"], x["id"]))
    return items


def list_enabled() -> List[Dict[str, Any]]:
    return [x for x in list_all() if x["enabled"]]


def get_enabled_template(tid: Optional[int]) -> Optional[Dict[str, Any]]:
    """供主流程调用：取启用模板。查不到 / 禁用 / 异常 → None（主流程回退原逻辑）。"""
    if tid is None:
        return None
    try:
        tid_int = int(tid)
    except Exception:
        return None
    try:
        with _lock:
            items = _load()
        for raw in items:
            it = _normalize(raw)
            if it["id"] == tid_int and it["enabled"]:
                return it
    except Exception as e:
        print(f"[llm-templates] 读取模板失败，回退默认逻辑: {type(e).__name__}: {e}")
    return None


def create_template(data: Dict[str, Any]) -> Dict[str, Any]:
    name = str(data.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "模板名称不能为空")
    sg = str(data.get("system_generate", "")).strip()
    if not sg:
        raise HTTPException(400, "不改写规则（system_generate）不能为空")
    with _lock:
        items = _load()
        now = time.time()
        new = _normalize({
            "id": _next_id(items),
            "name": name,
            "description": data.get("description", ""),
            "system_generate": data.get("system_generate", ""),
            "system_rewrite": data.get("system_rewrite", ""),
            "enabled": data.get("enabled", True),
            "sort_order": data.get("sort_order", 0),
            "created_at": now,
            "updated_at": now,
        })
        items.append(new)
        _save_atomic(items)
    return new


def update_template(tid: int, data: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        items = _load()
        target = None
        for i, raw in enumerate(items):
            if int(raw.get("id", 0)) == tid:
                target = i
                break
        if target is None:
            raise HTTPException(404, "模板不存在")
        cur = _normalize(items[target])
        # 仅覆盖传入字段
        for k in ("name", "description", "system_generate", "system_rewrite",
                  "enabled", "sort_order"):
            if k in data:
                cur[k] = data[k]
        if not str(cur.get("name", "")).strip():
            raise HTTPException(400, "模板名称不能为空")
        if not str(cur.get("system_generate", "")).strip():
            raise HTTPException(400, "不改写规则（system_generate）不能为空")
        cur["id"] = tid
        cur["updated_at"] = time.time()
        items[target] = _normalize(cur)
        _save_atomic(items)
        return items[target]


def delete_template(tid: int) -> None:
    with _lock:
        items = _load()
        new_items = [x for x in items if int(x.get("id", 0)) != tid]
        if len(new_items) == len(items):
            raise HTTPException(404, "模板不存在")
        _save_atomic(new_items)


# ────────────────────────── 路由 ──────────────────────────

router = APIRouter(tags=["llm-templates"])


@router.get("/api/admin/features/llm-templates")
async def admin_list(request: Request):
    require_admin(request)
    return {"templates": list_all(), "version": FEATURE_VERSION}


@router.post("/api/admin/features/llm-templates")
async def admin_create(request: Request):
    require_admin(request)
    body = await request.json()
    return {"ok": True, "template": create_template(body)}


@router.put("/api/admin/features/llm-templates/{tid}")
async def admin_update(tid: int, request: Request):
    require_admin(request)
    body = await request.json()
    return {"ok": True, "template": update_template(tid, body)}


@router.delete("/api/admin/features/llm-templates/{tid}")
async def admin_delete(tid: int, request: Request):
    require_admin(request)
    delete_template(tid)
    return {"ok": True}


@router.get("/api/features/llm-templates")
async def public_list(request: Request):
    """用户端下拉：仅返回启用模板的 id/name/description（公开只读）。"""
    try:
        items = list_enabled()
    except Exception as e:
        print(f"[llm-templates] 公开列表读取失败: {type(e).__name__}: {e}")
        items = []
    return {"templates": [_public_view(x) for x in items]}

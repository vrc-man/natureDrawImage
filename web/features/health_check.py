"""
试水模块 A：图片目录健康检查（纯只读统计，不改任何数据）。

验证外挂架构是否打通：APIRouter 注册、中间件鉴权继承、db / _deps 单向依赖。

接口：
  GET /api/admin/features/health/ping       —— 探活，确认模块已挂载
  POST /api/admin/features/health/scan      —— 后台扫描 OUTPUT_DIR，统计健康状况
  GET /api/admin/features/health/scan/status —— 轮询扫描进度/结果

统计内容（只读）：
  - total_images          OUTPUT_DIR 下图片总数
  - total_size_bytes      图片总占用字节
  - missing_thumb         原图存在但 thumb_cache 缺缩略图的数量
  - orphan_files          不在任何 gen_logs 记录中的"无主"原图数量
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Request

from db import operations as db
from features._deps import (
    require_admin,
    OUTPUT_DIR,
    OUTPUT_IMAGE_EXTS,
    thumb_exists,
)

router = APIRouter(prefix="/api/admin/features/health", tags=["health-check"])

# 模块自管状态 + 锁（不污染 app.py 的全局区）
_scan_status: Dict[str, Any] = {}
_scan_lock = asyncio.Lock()

FEATURE_VERSION = "1.0.0"


@router.get("/ping")
async def ping(request: Request):
    """探活：确认外挂模块已正确挂载、鉴权链路通畅。"""
    require_admin(request)
    return {
        "ok": True,
        "feature": "health-check",
        "version": FEATURE_VERSION,
        "output_dir": str(OUTPUT_DIR),
        "output_dir_exists": OUTPUT_DIR.exists(),
    }


@router.post("/scan")
async def start_scan(request: Request):
    """启动后台健康检查扫描（单例，已在跑则拒绝）。"""
    require_admin(request)
    global _scan_status
    async with _scan_lock:
        if _scan_status.get("status") == "running":
            return {"ok": False, "error": "已有健康检查任务运行中"}
        _scan_status = {"status": "running", "scanned": 0,
                        "total_images": 0, "total_size_bytes": 0,
                        "missing_thumb": 0, "orphan_files": 0}
    _spawn(_run_scan())
    return {"ok": True}


@router.get("/scan/status")
async def scan_status(request: Request):
    """查询扫描进度 / 结果。"""
    require_admin(request)
    global _scan_status
    if not _scan_status:
        return {"status": "idle"}
    return dict(_scan_status)


def _spawn(coro):
    """轻量后台任务启动（不依赖 app._safe_task）。"""
    loop = asyncio.get_event_loop()
    task = loop.create_task(coro)

    def _done(t):
        try:
            t.result()
        except Exception as e:  # 不让异常无声消失
            print(f"[health-check] 后台任务异常: {type(e).__name__}: {e}")

    task.add_done_callback(_done)
    return task


def _collect_gen_log_stems() -> set:
    """取所有 gen_logs 引用的原图（去扩展名的相对路径 key），用于判定孤儿。"""
    stems = set()
    try:
        rows = db.load_gen_logs_raw()
    except Exception:
        rows = []
    for r in rows:
        try:
            fps = json.loads(r.get("file_paths", "[]"))
        except Exception:
            fps = []
        for fp in fps:
            key = Path(str(fp or "").replace("\\", "/")).with_suffix("").as_posix()
            if key:
                stems.add(key)
    return stems


def _scan_blocking() -> Dict[str, int]:
    """同步扫描（在线程里跑，避免阻塞事件循环）。"""
    result = {"total_images": 0, "total_size_bytes": 0,
              "missing_thumb": 0, "orphan_files": 0, "scanned": 0}
    if not OUTPUT_DIR.exists():
        return result
    base = OUTPUT_DIR.resolve()
    gen_stems = _collect_gen_log_stems()
    for p in OUTPUT_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in OUTPUT_IMAGE_EXTS:
            continue
        try:
            rel = p.resolve().relative_to(base).as_posix()
        except Exception:
            continue
        result["total_images"] += 1
        try:
            result["total_size_bytes"] += p.stat().st_size
        except Exception:
            pass
        # 缺缩略图？
        if not thumb_exists(rel):
            result["missing_thumb"] += 1
        # 孤儿（不在任何 gen_logs）？
        stem = Path(rel).with_suffix("").as_posix()
        if stem not in gen_stems:
            result["orphan_files"] += 1
        result["scanned"] += 1
    return result


async def _run_scan():
    global _scan_status
    try:
        res = await asyncio.to_thread(_scan_blocking)
        async with _scan_lock:
            _scan_status.update(res)
            _scan_status["status"] = "done"
        print(f"[health-check] 扫描完成: 图片 {res['total_images']}, "
              f"缺缩略图 {res['missing_thumb']}, 孤儿 {res['orphan_files']}")
    except Exception as e:
        async with _scan_lock:
            _scan_status["status"] = "error"
            _scan_status["error"] = str(e)

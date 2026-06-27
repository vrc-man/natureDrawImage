"""
生图排行榜外挂特征模块（只读，不修改任何数据）。

统计规则：
  - 按 login 分组，SUM(count) 计算总张数
  - 只统计 status='success' 的记录
  - 60 秒内存缓存，避免重复计算

接口：
  GET /api/admin/features/gen-leaderboard?range=today
    range: today | weekly | monthly | all
"""

import time
import math
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request

from db import operations as db
from features._deps import require_admin

router = APIRouter(prefix="/api/admin/features/gen-leaderboard", tags=["gen-leaderboard"])

# ── 60 秒内存缓存 ──
_cache: Dict[str, dict] = {}
_CACHE_TTL = 60


def _get_cached(key: str, date_from: float, date_to: float, tz_offset: float = 0) -> dict:
    now = time.time()
    entry = _cache.get(key)
    if entry and now - entry["cached_at"] < _CACHE_TTL:
        return entry["data"]
    data = db.get_gen_leaderboard(limit=3, date_from=date_from, date_to=date_to, tz_offset=tz_offset)
    _cache[key] = {"data": data, "cached_at": now}
    return data


def _clear_cache():
    _cache.clear()


@router.get("")
async def gen_leaderboard(request: Request, range: str = "today"):
    """生图排行榜。"""
    require_admin(request)
    now = time.time()
    date_from = 0.0
    date_to = 0.0
    # 前端传的 tz_offset（默认东八区）
    tz_offset = 8

    if range == "today":
        # 当天 0 点（本地时区）
        lt = time.localtime(now)
        date_from = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        date_to = now
    elif range == "weekly":
        date_from = now - 7 * 86400
        date_to = now
    elif range == "monthly":
        date_from = now - 30 * 86400
        date_to = now
    # all: date_from=0, date_to=0 表示全部

    key = f"{range}:{int(date_from)}:{int(date_to)}"
    data = _get_cached(key, date_from, date_to, tz_offset)
    return {"range": range, **data}

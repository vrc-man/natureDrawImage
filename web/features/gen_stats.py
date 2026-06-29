"""
外挂功能：生图统计（只读，不修改任何数据）。

从 web/app.py 迁出，纯查询统计，不写任何表。

接口：
  GET /api/admin/features/gen-stats/generation?date_from=...&date_to=...&login=...
"""

from fastapi import APIRouter, Request, HTTPException

from db import operations as db
from features._deps import require_admin

router = APIRouter(prefix="/api/admin/features/gen-stats", tags=["gen-stats"])


@router.get("/generation")
async def gen_stats_generation(request: Request, date_from: float = 0, date_to: float = 0, login: str = "", tz_offset: float = 0):
    """系统统计：今日生图总数、每小时分布、每日分布。支持 date_from/date_to (epoch秒)/login/tz_offset 筛选。"""
    require_admin(request)
    login = login.strip()
    if date_from and date_to:
        return {
            "today_total": db.count_gen_logs_range(date_from, date_to, login),
            "hourly": db.get_gen_logs_hourly_range(date_from, date_to, tz_offset, login),
            "daily": db.get_gen_logs_daily_range(date_from, date_to, tz_offset, login),
        }
    return {
        "today_total": db.count_gen_logs_today(tz_offset, login),
        "hourly": db.get_gen_logs_hourly_today(tz_offset, login),
        "daily": db.get_gen_logs_daily_7days(tz_offset, login),
    }

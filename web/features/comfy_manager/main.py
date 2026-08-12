"""
外挂功能：ComfyUI 启动器远程管理（可选）。

配置文件 config.yaml（本目录，*.yaml 已被 .gitignore 忽略）：
    manager:
      url: http://127.0.0.1:18808      # 启动器管理地址
      api_key: xxx                      # 管理密钥（X-Key）
      confirm_key: xxx                  # 停止/重启确认密钥（X-Confirm）

未配置/缺文件时所有端点返回 {enabled: false}，不影响项目使用。
配置后，管理员可在管理面板远程启动/停止/重启/查看 ComfyUI（转发到启动器本地管理 API）。
"""

from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from features._deps import require_admin

router = APIRouter(prefix="/api/admin/comfy-manager", tags=["comfy-manager"])

_YAML_PATH = Path(__file__).resolve().parent / "config.yaml"


def _load_manager_conf() -> Dict[str, str]:
    """读取 config.yaml 的 manager 段。缺文件/解析失败/缺 url 时返回空。"""
    try:
        import yaml as _yaml
    except ImportError:
        return {}
    try:
        if not _YAML_PATH.is_file():
            return {}
        data = _yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8")) or {}
        m = (data or {}).get("manager") or {}
        if not m.get("url"):
            return {}
        return {
            "url": str(m["url"]).strip().rstrip("/"),
            "api_key": str(m.get("api_key", "") or "").strip(),
            "confirm_key": str(m.get("confirm_key", "") or "").strip(),
        }
    except Exception:
        return {}


_conf = _load_manager_conf()
MANAGER_URL = _conf.get("url", "")
MANAGER_KEY = _conf.get("api_key", "")
MANAGER_CONFIRM_KEY = _conf.get("confirm_key", "")
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def _enabled() -> bool:
    return bool(MANAGER_URL)


async def _forward(method: str, path: str, confirm: bool = False) -> Dict[str, Any]:
    """转发到启动器管理 API。请求头携带 X-Key（停止/重启另带 X-Confirm）。"""
    headers = {"X-Key": MANAGER_KEY}
    if confirm:
        headers["X-Confirm"] = MANAGER_CONFIRM_KEY
    url = f"{MANAGER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.request(method, url, headers=headers)
            try:
                data = r.json()
            except Exception:
                data = {"ok": False, "error": r.text[:300]}
            if r.status_code >= 400:
                data = {"ok": False, "error": data.get("detail") or data.get("error") or f"HTTP {r.status_code}"}
            return data
    except httpx.ConnectError:
        return {"ok": False, "error": "无法连接启动器（未运行？）"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "启动器响应超时"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@router.get("/status")
async def api_status(request: Request):
    require_admin(request)
    if not _enabled():
        return {"enabled": False}
    data = await _forward("GET", "/api/status")
    return {"enabled": True, **data}


@router.get("/logs")
async def api_logs(request: Request, tail: int = 200, source: str = "launcher"):
    require_admin(request)
    if not _enabled():
        return {"enabled": False}
    tail = max(1, min(tail, 500))
    src = "comfy" if (source or "").strip().lower() == "comfy" else "launcher"
    data = await _forward("GET", f"/api/logs?tail={tail}&source={src}")
    return {"enabled": True, **data}


@router.post("/start")
async def api_start(request: Request):
    require_admin(request)
    if not _enabled():
        return {"enabled": False}
    data = await _forward("POST", "/api/start")
    return {"enabled": True, **data}


@router.post("/stop")
async def api_stop(request: Request):
    require_admin(request)
    if not _enabled():
        return {"enabled": False}
    data = await _forward("POST", "/api/stop", confirm=True)
    return {"enabled": True, **data}


@router.post("/restart")
async def api_restart(request: Request):
    require_admin(request)
    if not _enabled():
        return {"enabled": False}
    data = await _forward("POST", "/api/restart", confirm=True)
    return {"enabled": True, **data}

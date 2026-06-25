from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.adapters.base import SourceQuery, SourceStatus
from app.adapters.maimai import MaimaiAdapter
from app.adapters.xiaohongshu import XiaohongshuAdapter
from app.config import settings
from app.runtime.source_auth import GLOBAL_SOURCE_AUTH, SourceAuthManager
from app.runtime.source_health import GLOBAL_SOURCE_HEALTH


router = APIRouter(prefix="/api/source-auth", tags=["source-auth"])

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
AUTH_FAILURE_STATUSES = {SourceStatus.AUTH_REQUIRED, SourceStatus.UNAUTHORIZED, SourceStatus.CONFIG_ERROR}
SAVE_ALLOWED_STATUSES = {
    SourceStatus.OK,
    SourceStatus.EMPTY,
    SourceStatus.RATE_LIMITED,
    SourceStatus.TIMEOUT,
}
# 全局单例，与 cookie 导入/校验流程共享 last_validated_at 状态。
# 测试可通过替换 GLOBAL_SOURCE_AUTH 注入 mock。
_MANAGER = GLOBAL_SOURCE_AUTH


class MaimaiCookieImportRequest(BaseModel):
    model_config = {"populate_by_name": True}

    cookie: str = Field(min_length=8, max_length=20000)
    should_validate: bool = Field(default=True, alias="validate")


def _ensure_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    url_host = request.url.hostname or ""
    if client_host in LOCAL_HOSTS or url_host in LOCAL_HOSTS:
        return
    raise HTTPException(status_code=403, detail="Source auth import is only available from localhost")


def _normalize_cookie(cookie: str) -> str:
    value = " ".join(cookie.strip().split())
    if not value or "=" not in value:
        raise HTTPException(status_code=400, detail="Cookie must be a browser Cookie header")

    parsed = SimpleCookie()
    try:
        parsed.load(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Cookie format is invalid") from exc

    if not parsed:
        raise HTTPException(status_code=400, detail="Cookie must contain at least one key=value pair")

    return "; ".join(f"{key}={morsel.value}" for key, morsel in parsed.items() if morsel.value)


def _latest_runtime_auth_status(source: str) -> dict:
    latest = GLOBAL_SOURCE_HEALTH.current_status(source)
    if not latest:
        return {
            "runtimeStatus": None,
            "runtimeReason": None,
            "needsLogin": False,
        }
    return {
        "runtimeStatus": latest.get("status"),
        "runtimeReason": latest.get("reason"),
        "needsLogin": latest.get("nextAction") == "login",
    }


@router.get("/maimai/status")
async def get_maimai_auth_status(request: Request):
    _ensure_local_request(request)
    manager = _MANAGER
    return {
        "source": "maimai",
        "enabled": settings.maimai_enabled,
        "hasCookieState": manager.has_cookie_state("maimai", domains=("maimai.cn",)),
        "hasConfiguredCookie": bool(settings.maimai_cookie),
        "autoRefreshEnabled": settings.source_auth_auto_refresh_enabled,
        "revalidateIntervalHours": settings.source_auth_revalidate_interval_hours,
        "lastValidatedAt": manager.last_validated_at("maimai"),
        **_latest_runtime_auth_status("maimai"),
    }


@router.post("/maimai/cookie")
async def import_maimai_cookie(payload: MaimaiCookieImportRequest, request: Request):
    _ensure_local_request(request)
    cookie = _normalize_cookie(payload.cookie)
    manager = _MANAGER

    if not payload.should_validate:
        manager.save_cookie("maimai", cookie)
        manager.mark_validated("maimai")
        return {
            "source": "maimai",
            "saved": True,
            "validationStatus": "not_validated",
            "reason": None,
            "count": 0,
            "lastValidatedAt": manager.last_validated_at("maimai"),
        }

    adapter = MaimaiAdapter(cookie=cookie, auth_manager=manager)
    result = await adapter.search(SourceQuery(query="面经", limit=1))
    status = result.status

    if status in AUTH_FAILURE_STATUSES:
        return {
            "source": "maimai",
            "saved": False,
            "validationStatus": status.value,
            "reason": result.reason or "Cookie is not authorized",
            "count": result.count,
            "lastValidatedAt": manager.last_validated_at("maimai"),
        }

    saved = status in SAVE_ALLOWED_STATUSES
    if saved:
        manager.save_cookie("maimai", adapter.current_cookie or cookie)
        manager.mark_validated("maimai")

    return {
        "source": "maimai",
        "saved": saved,
        "validationStatus": status.value,
        "reason": result.reason,
        "count": result.count,
        "lastValidatedAt": manager.last_validated_at("maimai"),
    }


class XhsCookieImportRequest(BaseModel):
    model_config = {"populate_by_name": True}

    cookie: str = Field(min_length=8, max_length=20000)
    should_validate: bool = Field(default=True, alias="validate")


@router.get("/xhs/status")
async def get_xhs_auth_status(request: Request):
    _ensure_local_request(request)
    manager = _MANAGER
    return {
        "source": "xiaohongshu",
        "enabled": settings.xhs_enabled,
        "hasCookieState": manager.has_cookie_state("xiaohongshu", domains=("xiaohongshu.com", "xhslink.com")),
        "hasConfiguredCookie": bool(settings.xhs_cookie),
        "autoRefreshEnabled": settings.source_auth_auto_refresh_enabled,
        "revalidateIntervalHours": settings.source_auth_revalidate_interval_hours,
        "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
        **_latest_runtime_auth_status("xiaohongshu"),
    }


@router.post("/xhs/cookie")
async def import_xhs_cookie(payload: XhsCookieImportRequest, request: Request):
    _ensure_local_request(request)
    cookie = _normalize_cookie(payload.cookie)
    manager = _MANAGER

    if not payload.should_validate:
        manager.save_cookie("xiaohongshu", cookie)
        manager.mark_validated("xiaohongshu")
        return {
            "source": "xiaohongshu",
            "saved": True,
            "validationStatus": "not_validated",
            "reason": None,
            "count": 0,
            "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
        }

    adapter = XiaohongshuAdapter(mcp_command=settings.xhs_mcp_command)
    result = await adapter.search(SourceQuery(query="面经", limit=1))
    status = result.status

    if status in AUTH_FAILURE_STATUSES:
        return {
            "source": "xiaohongshu",
            "saved": False,
            "validationStatus": status.value,
            "reason": result.reason or "Cookie is not authorized",
            "count": result.count,
            "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
        }

    saved = status in SAVE_ALLOWED_STATUSES
    if saved:
        manager.save_cookie("xiaohongshu", cookie)
        manager.mark_validated("xiaohongshu")

    return {
        "source": "xiaohongshu",
        "saved": saved,
        "validationStatus": status.value,
        "reason": result.reason,
        "count": result.count,
        "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
    }


class ValidateAllRequest(BaseModel):
    sources: Optional[list[str]] = None


async def _validate_maimai(manager: SourceAuthManager) -> dict:
    if not settings.maimai_enabled:
        return {
            "source": "maimai",
            "validationStatus": SourceStatus.DISABLED.value,
            "reason": "Disabled in settings",
            "lastValidatedAt": manager.last_validated_at("maimai"),
        }

    if not manager.has_cookie_state("maimai", domains=("maimai.cn",)) and not settings.maimai_cookie:
        return {
            "source": "maimai",
            "validationStatus": SourceStatus.CONFIG_ERROR.value,
            "reason": "Cookie is missing in configuration",
            "lastValidatedAt": manager.last_validated_at("maimai"),
        }

    adapter = MaimaiAdapter(cookie=settings.maimai_cookie, auth_manager=manager)
    result = await adapter.search(SourceQuery(query="面经", limit=1))
    status = result.status

    if status in AUTH_FAILURE_STATUSES:
        return {
            "source": "maimai",
            "validationStatus": status.value,
            "reason": result.reason or "Cookie is not authorized",
            "lastValidatedAt": manager.last_validated_at("maimai"),
        }

    if status in SAVE_ALLOWED_STATUSES:
        manager.mark_validated("maimai")

    return {
        "source": "maimai",
        "validationStatus": status.value,
        "reason": result.reason,
        "lastValidatedAt": manager.last_validated_at("maimai"),
    }


async def _validate_xhs(manager: SourceAuthManager) -> dict:
    if not settings.xhs_enabled:
        return {
            "source": "xiaohongshu",
            "validationStatus": SourceStatus.DISABLED.value,
            "reason": "Disabled in settings",
            "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
        }

    adapter = XiaohongshuAdapter(mcp_command=settings.xhs_mcp_command)
    result = await adapter.search(SourceQuery(query="面经", limit=1))
    status = result.status

    if status in AUTH_FAILURE_STATUSES:
        return {
            "source": "xiaohongshu",
            "validationStatus": status.value,
            "reason": result.reason or "Cookie is not authorized",
            "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
        }

    if status in SAVE_ALLOWED_STATUSES:
        manager.mark_validated("xiaohongshu")

    return {
        "source": "xiaohongshu",
        "validationStatus": status.value,
        "reason": result.reason,
        "lastValidatedAt": manager.last_validated_at("xiaohongshu"),
    }


@router.post("/validate-all")
async def validate_all_sources(payload: ValidateAllRequest, request: Request):
    """Re-validate saved cookies for multiple sources. Used by frontend 24h auto-revalidation."""
    _ensure_local_request(request)
    manager = _MANAGER

    requested = payload.sources or ["maimai", "xiaohongshu"]
    results: list[dict] = []
    for source in requested:
        if source == "maimai":
            results.append(await _validate_maimai(manager))
        elif source == "xiaohongshu":
            results.append(await _validate_xhs(manager))
        else:
            results.append({
                "source": source,
                "validationStatus": "unknown_source",
                "reason": f"Unknown source: {source}",
                "lastValidatedAt": None,
            })

    return {"results": results}

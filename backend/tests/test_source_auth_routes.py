from app.adapters.base import SourceSearchResult, SourceStatus
from app.runtime.source_auth import SourceAuthManager
import app.api.routes_source_auth as source_auth_routes
import pytest


class _ValidatingMaimaiAdapter:
    def __init__(self, cookie: str = "", auth_manager=None):
        self.current_cookie = f"{cookie}; rotated=1"

    async def search(self, query):
        return SourceSearchResult(
            source="maimai",
            status=SourceStatus.OK,
            count=1,
            reason=None,
        )


class _UnauthorizedMaimaiAdapter:
    def __init__(self, cookie: str = "", auth_manager=None):
        self.current_cookie = cookie

    async def search(self, query):
        return SourceSearchResult(
            source="maimai",
            status=SourceStatus.UNAUTHORIZED,
            count=0,
            reason="Cookie expired",
        )


class _ValidatingXhsAdapter:
    def __init__(self, mcp_command: str = ""):
        pass

    async def search(self, query):
        return SourceSearchResult(
            source="xiaohongshu",
            status=SourceStatus.OK,
            count=1,
            reason=None,
        )


@pytest.fixture
def isolated_manager(monkeypatch, tmp_path):
    """Replace _MANAGER with a fresh SourceAuthManager pointed at tmp_path."""
    fresh = SourceAuthManager(state_dir=tmp_path / "auth")
    monkeypatch.setattr(source_auth_routes, "_MANAGER", fresh)
    return fresh


@pytest.mark.asyncio
async def test_import_maimai_cookie_saves_validated_cookie(client, monkeypatch, tmp_path, isolated_manager):
    monkeypatch.setattr(source_auth_routes.settings, "maimai_enabled", True)
    monkeypatch.setattr(source_auth_routes, "MaimaiAdapter", _ValidatingMaimaiAdapter)

    response = await client.post(
        "/api/source-auth/maimai/cookie",
        json={"cookie": "sid=fresh; csrftoken=token", "validate": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is True
    assert body["validationStatus"] == "ok"
    assert (tmp_path / "auth" / "maimai_cookie.txt").read_text(encoding="utf-8") == (
        "sid=fresh; csrftoken=token; rotated=1"
    )


@pytest.mark.asyncio
async def test_import_maimai_cookie_does_not_save_unauthorized_cookie(client, monkeypatch, tmp_path, isolated_manager):
    monkeypatch.setattr(source_auth_routes.settings, "maimai_enabled", True)
    monkeypatch.setattr(source_auth_routes, "MaimaiAdapter", _UnauthorizedMaimaiAdapter)

    response = await client.post(
        "/api/source-auth/maimai/cookie",
        json={"cookie": "sid=expired; csrftoken=token", "validate": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is False
    assert body["validationStatus"] == "unauthorized"
    assert not (tmp_path / "auth" / "maimai_cookie.txt").exists()


@pytest.mark.asyncio
async def test_maimai_status_reports_latest_runtime_login_failure(client, monkeypatch, tmp_path, isolated_manager):
    monkeypatch.setattr(source_auth_routes.settings, "maimai_enabled", True)
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "maimai_cookie.txt").write_text("sid=expired", encoding="utf-8")

    source_auth_routes.GLOBAL_SOURCE_HEALTH.reset("maimai")
    source_auth_routes.GLOBAL_SOURCE_HEALTH.record_status(
        "maimai",
        SourceStatus.UNAUTHORIZED,
        "Cookie expired",
    )

    response = await client.get("/api/source-auth/maimai/status")

    source_auth_routes.GLOBAL_SOURCE_HEALTH.reset("maimai")
    assert response.status_code == 200
    body = response.json()
    assert body["hasCookieState"] is True
    assert body["runtimeStatus"] == "unauthorized"
    assert body["runtimeReason"] == "Cookie expired"
    assert body["needsLogin"] is True


@pytest.mark.asyncio
async def test_maimai_status_returns_last_validated_at(client, monkeypatch, tmp_path, isolated_manager):
    """status endpoint should surface lastValidatedAt from the shared SourceAuthManager."""
    monkeypatch.setattr(source_auth_routes.settings, "maimai_enabled", True)

    source_auth_routes.GLOBAL_SOURCE_HEALTH.reset("maimai")
    isolated_manager.mark_validated("maimai")
    expected_ts = isolated_manager.last_validated_at("maimai")

    response = await client.get("/api/source-auth/maimai/status")
    body = response.json()
    assert body["lastValidatedAt"] == expected_ts
    assert body["revalidateIntervalHours"] == source_auth_routes.settings.source_auth_revalidate_interval_hours


@pytest.mark.asyncio
async def test_validate_all_endpoint_returns_status_for_each_source(client, monkeypatch, tmp_path, isolated_manager):
    """POST /api/source-auth/validate-all runs validation for each source."""
    monkeypatch.setattr(source_auth_routes.settings, "maimai_enabled", True)
    monkeypatch.setattr(source_auth_routes.settings, "xhs_enabled", True)
    monkeypatch.setattr(source_auth_routes, "MaimaiAdapter", _ValidatingMaimaiAdapter)
    monkeypatch.setattr(source_auth_routes, "XiaohongshuAdapter", _ValidatingXhsAdapter)

    response = await client.post(
        "/api/source-auth/validate-all",
        json={"sources": ["maimai", "xiaohongshu"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert len(body["results"]) == 2

    by_source = {r["source"]: r for r in body["results"]}
    assert by_source["maimai"]["validationStatus"] == "ok"
    assert by_source["maimai"]["lastValidatedAt"] is not None
    assert by_source["xiaohongshu"]["validationStatus"] == "ok"
    assert by_source["xiaohongshu"]["lastValidatedAt"] is not None


@pytest.mark.asyncio
async def test_validate_all_endpoint_rejects_remote_request(client, monkeypatch):
    """Non-localhost requests should be rejected with 403."""
    from fastapi import HTTPException
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/source-auth/validate-all",
        "headers": [],
        "query_string": b"",
        "client": ("203.0.113.5", 12345),
        "server": ("203.0.113.5", 8000),
        "url": {"scheme": "http", "host": "203.0.113.5", "path": "/", "query": b""},
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        source_auth_routes._ensure_local_request(request)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_import_xhs_cookie_marks_validated_on_success(client, monkeypatch, tmp_path, isolated_manager):
    """successful xhs cookie import should populate lastValidatedAt."""
    monkeypatch.setattr(source_auth_routes.settings, "xhs_enabled", True)
    monkeypatch.setattr(source_auth_routes, "XiaohongshuAdapter", _ValidatingXhsAdapter)

    response = await client.post(
        "/api/source-auth/xhs/cookie",
        json={"cookie": "web_session=abc; xhsappid=xyz", "validate": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is True
    assert body["validationStatus"] == "ok"
    assert body["lastValidatedAt"] is not None

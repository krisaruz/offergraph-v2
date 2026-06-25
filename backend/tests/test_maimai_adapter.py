from __future__ import annotations

import httpx
import pytest

import app.adapters.maimai as maimai_module
from app.adapters.base import SourceQuery, SourceStatus
from app.adapters.maimai import MaimaiAdapter
from app.config import Settings
from app.runtime.source_auth import SourceAuthManager


class _FakeMaimaiResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = httpx.Headers(headers or {})

    def json(self) -> dict:
        return self._payload


class _FakeMaimaiClient:
    captured_cookies: list[str] = []

    def __init__(self, *args, headers=None, **kwargs):
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, params: dict):
        cookie = self.headers.get("Cookie", "")
        self.__class__.captured_cookies.append(cookie)
        if "sid=fresh" not in cookie:
            return _FakeMaimaiResponse(302, headers={"location": "https://maimai.cn/login"})
        return _FakeMaimaiResponse(
            200,
            {
                "data": {
                    "feeds": [
                        {
                            "fid": "feed-1",
                            "feed": {
                                "text": "阿里 自动化测试 社招 面经，问了测试平台设计。",
                                "crtime": 1760000000,
                            },
                        }
                    ]
                }
            },
            headers={"set-cookie": "sid=fresh_rotated; Path=/; HttpOnly"},
        )


@pytest.mark.asyncio
async def test_maimai_refreshes_cookie_from_authorized_project_state(monkeypatch, tmp_path):
    state_dir = tmp_path / "auth"
    state_dir.mkdir()
    (state_dir / "maimai_cookie.txt").write_text("sid=fresh", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        maimai_enabled=True,
        source_auth_state_dir=str(state_dir),
        search_timeout_platform=1,
    )
    monkeypatch.setattr(maimai_module, "settings", settings)
    monkeypatch.setattr(maimai_module.httpx, "AsyncClient", _FakeMaimaiClient)
    _FakeMaimaiClient.captured_cookies = []

    adapter = MaimaiAdapter(
        cookie="sid=expired",
        auth_manager=SourceAuthManager(state_dir=state_dir),
    )
    result = await adapter.search(SourceQuery(query="阿里 自动化测试", limit=5))

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert _FakeMaimaiClient.captured_cookies == ["sid=expired", "sid=fresh"]
    assert (state_dir / "maimai_cookie.txt").read_text(encoding="utf-8") == "sid=fresh_rotated"

from __future__ import annotations

import pytest

import app.adapters.xiaohongshu as xhs_module
from app.adapters.base import SourceQuery, SourceStatus
from app.adapters.xiaohongshu import XiaohongshuAdapter
from app.config import Settings
from app.runtime.source_health import GLOBAL_SOURCE_HEALTH


class _FakeSearxngResponse:
    status_code = 200

    def json(self):
        return {
            "results": [
                {
                    "url": "https://www.xiaohongshu.com/explore/abc123",
                    "title": "Kimi Eval 面试记录",
                    "content": "分享大模型评测方向面试，问了 benchmark 和指标设计。",
                    "publishedDate": "2026-05-10",
                },
                {
                    "url": "https://www.xiaohongshu.com/search_result?keyword=Kimi",
                    "title": "search page",
                    "content": "not detail",
                },
            ]
        }


class _FakeSearxngClient:
    captured_params: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, params: dict):
        self.__class__.captured_params = params
        return _FakeSearxngResponse()


@pytest.mark.asyncio
async def test_xhs_falls_back_to_searxng_url_discovery_when_mcp_missing(monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None,
        xhs_enabled=True,
        searxng_base_url="http://127.0.0.1:8080",
    )
    monkeypatch.setattr(xhs_module, "settings", settings)
    monkeypatch.setattr(xhs_module.httpx, "AsyncClient", _FakeSearxngClient)

    adapter = XiaohongshuAdapter(mcp_command=str(tmp_path / "missing-mcp"))
    result = await adapter.search(SourceQuery(query="Kimi 大模型 Eval", limit=5))

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.reason and "fell back to SearXNG URL discovery" in result.reason
    assert result.items[0].source_url == "https://www.xiaohongshu.com/explore/abc123"
    assert result.items[0].raw["evidence_status"] == "url_snippet_only"
    assert result.items[0].raw["requires_authorized_detail"] is True
    assert _FakeSearxngClient.captured_params["q"] == (
        "Kimi 大模型 Eval 小红书 面经 site:xiaohongshu.com/explore"
    )


class _FakeClientRaisingAuthRequired:
    """Stands in for XhsMcpClient; raises ValueError(auth_required) on get_note_content."""

    async def get_note_content(self, url: str):
        raise ValueError("auth_required")


async def _fake_get_client_factory():
    """Async factory returning the fake client (matches _get_client signature)."""
    return _FakeClientRaisingAuthRequired()


@pytest.mark.asyncio
async def test_xhs_fetch_detects_auth_required_and_reports_unauthorized(monkeypatch):
    """fetch() should catch auth_required from MCP and record UNAUTHORIZED on source_health."""
    settings = Settings(_env_file=None, xhs_enabled=True)
    monkeypatch.setattr(xhs_module, "settings", settings)

    adapter = XiaohongshuAdapter(mcp_command="")
    monkeypatch.setattr(adapter, "_get_client", _fake_get_client_factory)

    GLOBAL_SOURCE_HEALTH.reset("xiaohongshu")
    result = await adapter.fetch("https://www.xiaohongshu.com/explore/abc")

    assert result is None

    latest = GLOBAL_SOURCE_HEALTH.current_status("xiaohongshu")
    assert latest is not None, "fetch should have recorded UNAUTHORIZED on source_health"
    assert latest["status"] == SourceStatus.UNAUTHORIZED.value
    assert latest["nextAction"] == "login"
    GLOBAL_SOURCE_HEALTH.reset("xiaohongshu")


@pytest.mark.asyncio
async def test_xhs_fetch_does_not_reset_client_on_auth_required(monkeypatch):
    """On auth_required we should NOT tear down the browser; only cookie is invalid."""
    settings = Settings(_env_file=None, xhs_enabled=True)
    monkeypatch.setattr(xhs_module, "settings", settings)

    adapter = XiaohongshuAdapter(mcp_command="")
    monkeypatch.setattr(adapter, "_get_client", _fake_get_client_factory)

    reset_calls: list[None] = []
    original_reset = adapter._reset_client

    async def _track_reset():
        reset_calls.append(None)
        await original_reset()

    monkeypatch.setattr(adapter, "_reset_client", _track_reset)

    await adapter.fetch("https://www.xiaohongshu.com/explore/abc")

    assert reset_calls == [], "_reset_client should NOT be called for auth_required"
    GLOBAL_SOURCE_HEALTH.reset("xiaohongshu")

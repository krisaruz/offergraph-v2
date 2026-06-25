from __future__ import annotations

import pytest

import app.adapters.xiaohongshu as xhs_module
from app.adapters.base import SourceQuery, SourceStatus
from app.adapters.free_web_search import FreeWebSearchOutcome
from app.adapters.xiaohongshu import XiaohongshuAdapter
from app.config import Settings


@pytest.mark.asyncio
async def test_xhs_falls_back_to_free_rss_url_discovery_when_searxng_missing(monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None,
        xhs_enabled=True,
        searxng_base_url="",
    )
    monkeypatch.setattr(xhs_module, "settings", settings)

    async def fake_search_bing_rss(query: str, *, limit: int, timeout_s: int, language: str):
        assert "site:xiaohongshu.com/explore" in query
        return FreeWebSearchOutcome(
            status=SourceStatus.OK,
            results=[
                {
                    "url": "https://www.xiaohongshu.com/explore/rss123",
                    "title": "Kimi Eval interview note",
                    "content": "public snippet",
                    "provider": "bing_rss",
                    "discovery": "bing_rss_url_fallback",
                }
            ],
        )

    monkeypatch.setattr(xhs_module, "search_bing_rss", fake_search_bing_rss)

    adapter = XiaohongshuAdapter(mcp_command=str(tmp_path / "missing-mcp"))
    result = await adapter.search(SourceQuery(query="Kimi Eval", limit=5))

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.reason and "fell back to free web URL discovery" in result.reason
    assert result.items[0].source_url == "https://www.xiaohongshu.com/explore/rss123"
    assert result.items[0].raw["discovery"] == "bing_rss_url_fallback"
    assert result.items[0].raw["evidence_status"] == "url_snippet_only"

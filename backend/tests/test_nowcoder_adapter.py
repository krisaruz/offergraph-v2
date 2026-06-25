from __future__ import annotations

import httpx
import pytest

import app.adapters.nowcoder as nowcoder_module
from app.adapters.base import SourceQuery, SourceSearchResult, SourceStatus
from app.adapters.free_web_search import FreeWebSearchOutcome
from app.adapters.nowcoder import NowcoderAdapter
from app.config import Settings


class _FakeSearxngResponse:
    status_code = 200

    def json(self):
        return {
            "results": [
                {
                    "url": "https://www.nowcoder.com/discuss/12345",
                    "title": "阿里 自动化测试 面经 - 牛客网",
                    "content": "一面问了测试平台、Java 基础和数据库。",
                    "publishedDate": "2026-05-01",
                },
                {
                    "url": "https://example.com/not-nowcoder",
                    "title": "not used",
                    "content": "ignore",
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
async def test_nowcoder_uses_searxng_site_fallback_when_api_is_empty(monkeypatch):
    settings = Settings(
        _env_file=None,
        nowcoder_enabled=True,
        searxng_base_url="http://127.0.0.1:8080",
    )
    monkeypatch.setattr(nowcoder_module, "settings", settings)
    monkeypatch.setattr(nowcoder_module.httpx, "AsyncClient", _FakeSearxngClient)

    async def _empty_api(self, query, start_time):
        return SourceSearchResult(
            source="nowcoder",
            status=SourceStatus.EMPTY,
            items=[],
            reason="No items matched query",
        )

    monkeypatch.setattr(NowcoderAdapter, "_search_api", _empty_api)

    result = await NowcoderAdapter().search(SourceQuery(query="阿里 自动化测试", limit=5))

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.reason and "fell back to SearXNG" in result.reason
    assert result.items[0].source_url == "https://www.nowcoder.com/discuss/12345"
    assert result.items[0].raw["evidence_status"] == "snippet_only"
    assert _FakeSearxngClient.captured_params["q"] == (
        "阿里 自动化测试 牛客 面经 site:nowcoder.com"
    )


@pytest.mark.asyncio
async def test_nowcoder_uses_free_rss_fallback_when_searxng_missing(monkeypatch):
    settings = Settings(
        _env_file=None,
        nowcoder_enabled=True,
        searxng_base_url=None,
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(nowcoder_module, "settings", settings)

    async def _empty_api(self, query, start_time):
        return SourceSearchResult(
            source="nowcoder",
            status=SourceStatus.EMPTY,
            items=[],
            reason="No items matched query",
        )

    async def _fake_bing_rss(query, *, limit, timeout_s, language):
        captured.update(
            {
                "query": query,
                "limit": limit,
                "timeout_s": timeout_s,
                "language": language,
            }
        )
        return FreeWebSearchOutcome(
            status=SourceStatus.OK,
            results=[
                {
                    "url": "https://www.nowcoder.com/discuss/67890",
                    "title": "Alibaba automation testing interview - Nowcoder",
                    "content": "Interview questions about test platform and SQL.",
                    "date": "2026-06-01",
                },
                {
                    "url": "https://example.com/not-nowcoder",
                    "title": "not used",
                    "content": "ignore",
                },
            ],
        )

    monkeypatch.setattr(NowcoderAdapter, "_search_api", _empty_api)
    monkeypatch.setattr(nowcoder_module, "search_bing_rss", _fake_bing_rss)

    result = await NowcoderAdapter().search(SourceQuery(query="Alibaba automation testing", limit=5))

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.reason and "free Bing RSS" in result.reason
    assert result.items[0].source_url == "https://www.nowcoder.com/discuss/67890"
    assert result.items[0].raw["evidence_status"] == "snippet_only"
    assert captured["query"] == "Alibaba automation testing 牛客 面经 site:nowcoder.com"

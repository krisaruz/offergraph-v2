"""Tests for the free SearXNG-backed search engine adapter."""

from __future__ import annotations

import json

import httpx
import pytest

import app.adapters.search_engine as search_module
from app.adapters.base import SourceQuery, SourceStatus
from app.adapters.free_web_search import FreeWebSearchOutcome
from app.adapters.search_engine import SearchEngineAdapter
from app.config import Settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, json_error: bool = False):
        self.status_code = status_code
        self._payload = payload or {}
        self._json_error = json_error

    def json(self) -> dict:
        if self._json_error:
            raise json.JSONDecodeError("not json", "html", 0)
        return self._payload


class _FakeAsyncClient:
    response: _FakeResponse
    captured_url: str | None = None
    captured_params: dict | None = None
    raised_exception: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, params: dict):
        self.__class__.captured_url = url
        self.__class__.captured_params = params
        if self.__class__.raised_exception:
            raise self.__class__.raised_exception
        return self.__class__.response


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides):
    settings = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(search_module, "settings", settings)
    return settings


def _patch_client(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse):
    _FakeAsyncClient.response = response
    _FakeAsyncClient.captured_url = None
    _FakeAsyncClient.captured_params = None
    _FakeAsyncClient.raised_exception = None
    monkeypatch.setattr(search_module.httpx, "AsyncClient", _FakeAsyncClient)


@pytest.mark.asyncio
async def test_search_engine_uses_free_rss_fallback_when_searxng_base_url_missing(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="")

    async def fake_search_bing_rss(query: str, *, limit: int, timeout_s: int, language: str):
        return FreeWebSearchOutcome(
            status=SourceStatus.OK,
            results=[
                {
                    "url": "https://example.com/kimi-eval",
                    "title": "Kimi Eval interview",
                    "content": "Public snippet",
                    "date": "2026-06-01",
                    "provider": "bing_rss",
                    "fallback": True,
                }
            ],
        )

    monkeypatch.setattr(search_module, "search_bing_rss", fake_search_bing_rss)

    result = await SearchEngineAdapter().search(SourceQuery(query="字节 自动化测试"))

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.reason == "SEARXNG_BASE_URL missing; used free Bing RSS fallback"
    assert result.items[0].source_url == "https://example.com/kimi-eval"
    assert result.items[0].raw["provider"] == "bing_rss"


@pytest.mark.asyncio
async def test_search_engine_rejects_paid_or_unsupported_provider(monkeypatch):
    _patch_settings(
        monkeypatch,
        search_api_provider="serpapi",
        searxng_base_url="http://127.0.0.1:8080",
    )

    result = await SearchEngineAdapter().search(SourceQuery(query="Kimi Eval"))

    assert result.status == SourceStatus.CONFIG_ERROR
    assert result.items == []
    assert result.reason == "Only free self-hosted SearXNG is supported"


@pytest.mark.asyncio
async def test_search_engine_calls_searxng_json_api_without_api_key(monkeypatch):
    _patch_settings(
        monkeypatch,
        searxng_base_url="http://127.0.0.1:8080",
        searxng_language="zh-CN",
        searxng_safe_search=0,
    )
    _patch_client(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "results": [
                    {
                        "url": "https://jobs.bytedance.com/experienced/position/1/detail",
                        "title": "AI 应用测试开发工程师",
                        "content": "负责 AI 产品自动化测试和质量保障",
                        "publishedDate": "2026-05-01",
                    },
                    {
                        "url": "https://jobs.bytedance.com/experienced/position/2/detail",
                        "title": "不应超过 limit 的结果",
                        "content": "第二条结果应被本地截断",
                    }
                ]
            },
        ),
    )

    result = await SearchEngineAdapter().search(
        SourceQuery(query="字节 自动化测试 site:jobs.bytedance.com", limit=1)
    )

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.items[0].source_url == "https://jobs.bytedance.com/experienced/position/1/detail"
    assert result.items[0].title == "AI 应用测试开发工程师"
    assert result.items[0].snippet == "负责 AI 产品自动化测试和质量保障"
    assert result.items[0].published_at == "2026-05-01"
    assert _FakeAsyncClient.captured_url == "http://127.0.0.1:8080/search"
    assert _FakeAsyncClient.captured_params == {
        "q": "字节 自动化测试 site:jobs.bytedance.com",
        "format": "json",
        "language": "zh-CN",
        "safesearch": 0,
        "pageno": 1,
    }
    assert "api_key" not in _FakeAsyncClient.captured_params


@pytest.mark.asyncio
async def test_search_engine_reports_json_format_disabled(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="http://127.0.0.1:8080")
    _patch_client(monkeypatch, _FakeResponse(403))

    result = await SearchEngineAdapter().search(SourceQuery(query="Kimi Eval"))

    assert result.status == SourceStatus.CONFIG_ERROR
    assert result.reason == "SearXNG JSON format is disabled or forbidden"


@pytest.mark.asyncio
async def test_search_engine_reports_timeout(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="http://127.0.0.1:8080")
    _FakeAsyncClient.response = _FakeResponse(200)
    _FakeAsyncClient.raised_exception = httpx.TimeoutException("timeout")
    monkeypatch.setattr(search_module.httpx, "AsyncClient", _FakeAsyncClient)

    result = await SearchEngineAdapter().search(SourceQuery(query="Kimi Eval"))

    assert result.status == SourceStatus.TIMEOUT
    assert result.reason == "Timeout calling SearXNG API"

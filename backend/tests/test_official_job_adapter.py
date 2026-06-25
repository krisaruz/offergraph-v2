"""Tests for official company job source discovery."""

from __future__ import annotations

import json

import httpx
import pytest

import app.adapters.official_job as job_module
from app.adapters.base import SourceQuery, SourceStatus
from app.adapters.free_web_search import FreeWebSearchOutcome
from app.adapters.official_job import OfficialJobAdapter
from app.config import Settings


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, json_error: bool = False):
        self.status_code = status_code
        self._payload = payload or {}
        self._json_error = json_error
        self.headers = {"content-type": "text/html"}
        self.text = "<html><title>JD</title><body>岗位职责：负责自动化测试。任职要求：Python。</body></html>"
        self.url = "https://jobs.bytedance.com/experienced/position/1/detail"

    def json(self) -> dict:
        if self._json_error:
            raise json.JSONDecodeError("not json", "html", 0)
        return self._payload


class _FakeAsyncClient:
    response: _FakeResponse
    captured_calls: list[tuple[str, dict]] = []
    raised_exception: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, params: dict | None = None):
        self.__class__.captured_calls.append((url, params or {}))
        if self.__class__.raised_exception:
            raise self.__class__.raised_exception
        return self.__class__.response


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides):
    settings = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(job_module, "settings", settings)
    return settings


def _patch_client(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse):
    _FakeAsyncClient.response = response
    _FakeAsyncClient.captured_calls = []
    _FakeAsyncClient.raised_exception = None
    monkeypatch.setattr(job_module.httpx, "AsyncClient", _FakeAsyncClient)


@pytest.mark.asyncio
async def test_official_job_uses_free_rss_fallback_when_searxng_base_url_missing(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="")

    async def fake_search_bing_rss(query: str, *, limit: int, timeout_s: int, language: str):
        return FreeWebSearchOutcome(
            status=SourceStatus.OK,
            results=[
                {
                    "url": "https://jobs.bytedance.com/experienced/position/1/detail",
                    "title": "AI test engineer",
                    "content": "job responsibilities and requirements",
                    "provider": "bing_rss",
                },
                {
                    "url": "https://example-jobs.test/bytedance/1",
                    "title": "Copied job",
                    "content": "third party job repost",
                    "provider": "bing_rss",
                },
            ],
        )

    monkeypatch.setattr(job_module, "search_bing_rss", fake_search_bing_rss)

    result = await OfficialJobAdapter().search(
        SourceQuery(query="字节 自动化测试", company="字节跳动", position="自动化测试")
    )

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.reason == "SEARXNG_BASE_URL missing; used free Bing RSS fallback"
    assert result.items[0].source_url == "https://jobs.bytedance.com/experienced/position/1/detail"
    assert result.items[0].raw["provider"] == "bing_rss"


@pytest.mark.asyncio
async def test_official_job_filters_to_known_official_domains(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="http://127.0.0.1:8080")
    _patch_client(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "results": [
                    {
                        "url": "https://jobs.bytedance.com/experienced/position/1/detail",
                        "title": "AI 应用测试开发工程师",
                        "content": "岗位职责：负责 AI 产品自动化测试和质量保障。",
                        "publishedDate": "2026-05-01",
                    },
                    {
                        "url": "https://example-jobs.test/bytedance/1",
                        "title": "字节跳动 自动化测试工程师",
                        "content": "第三方搬运职位，不应进入官方 JD。",
                    },
                ]
            },
        ),
    )

    result = await OfficialJobAdapter().search(
        SourceQuery(
            query="字节 自动化测试 面经",
            company="字节跳动",
            position="自动化测试工程师",
            limit=5,
        )
    )

    assert result.status == SourceStatus.OK
    assert result.count == 1
    assert result.items[0].source == "official_job"
    assert result.items[0].source_url == "https://jobs.bytedance.com/experienced/position/1/detail"
    assert result.items[0].raw["company"] == "字节跳动"
    assert result.items[0].raw["evidence_type"] == "jd_fact"
    assert any("site:jobs.bytedance.com" in call[1]["q"] for call in _FakeAsyncClient.captured_calls)


@pytest.mark.asyncio
async def test_official_job_supports_kimi_moonshot_official_board(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="http://127.0.0.1:8080")
    _patch_client(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "results": [
                    {
                        "url": "https://jobs.ashbyhq.com/moonshot-ai/abc",
                        "title": "Eval Engineer - Moonshot AI",
                        "content": "Open Positions for evaluation and agent quality.",
                    }
                ]
            },
        ),
    )

    result = await OfficialJobAdapter().search(
        SourceQuery(query="Kimi 大模型 Eval 评测方向", company="Kimi", position="大模型 Eval")
    )

    assert result.status == SourceStatus.OK
    assert result.items[0].source_url == "https://jobs.ashbyhq.com/moonshot-ai/abc"
    assert result.items[0].raw["company"] == "月之暗面"


@pytest.mark.asyncio
async def test_official_job_returns_empty_for_unsupported_company(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="http://127.0.0.1:8080")

    result = await OfficialJobAdapter().search(
        SourceQuery(query="未知公司 自动化测试", company="未知公司", position="自动化测试")
    )

    assert result.status == SourceStatus.EMPTY
    assert result.items == []
    assert result.reason == "No supported official job source matched query company"


@pytest.mark.asyncio
async def test_official_job_reports_timeout(monkeypatch):
    _patch_settings(monkeypatch, searxng_base_url="http://127.0.0.1:8080")
    _FakeAsyncClient.response = _FakeResponse(200)
    _FakeAsyncClient.captured_calls = []
    _FakeAsyncClient.raised_exception = httpx.TimeoutException("timeout")
    monkeypatch.setattr(job_module.httpx, "AsyncClient", _FakeAsyncClient)

    result = await OfficialJobAdapter().search(
        SourceQuery(query="阿里 自动化测试", company="阿里", position="自动化测试")
    )

    assert result.status == SourceStatus.TIMEOUT
    assert result.reason == "Timeout calling SearXNG API for official JD search"

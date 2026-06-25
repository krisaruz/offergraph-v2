from __future__ import annotations

import pytest

import app.adapters.free_web_search as free_search_module
from app.adapters.base import SourceStatus


class _FakeResponse:
    status_code = 200
    text = """
    <rss>
      <channel>
        <item>
          <title>Kimi Eval interview</title>
          <link>https://example.com/kimi-eval</link>
          <description><![CDATA[<b>Public</b> snippet&nbsp;text]]></description>
          <pubDate>Mon, 01 Jun 2026 00:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """


class _FakeAsyncClient:
    captured_params: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str, params: dict):
        self.__class__.captured_params = params
        return _FakeResponse()


@pytest.mark.asyncio
async def test_search_bing_rss_parses_public_rss_results(monkeypatch):
    monkeypatch.setattr(free_search_module.httpx, "AsyncClient", _FakeAsyncClient)

    outcome = await free_search_module.search_bing_rss(
        "Kimi Eval interview",
        limit=3,
        timeout_s=1,
        language="zh-CN",
    )

    assert outcome.status == SourceStatus.OK
    assert outcome.results[0]["url"] == "https://example.com/kimi-eval"
    assert outcome.results[0]["content"] == "Public snippet text"
    assert outcome.results[0]["provider"] == "bing_rss"
    assert _FakeAsyncClient.captured_params == {
        "q": "Kimi Eval interview",
        "format": "rss",
        "setlang": "zh-CN",
    }

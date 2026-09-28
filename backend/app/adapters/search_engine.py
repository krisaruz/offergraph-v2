"""
搜索引擎适配器 — 通过 SerpAPI 或类似服务补充长尾结果。
支持 site: 限定搜索范围。
"""

import logging
from typing import List, Optional

import httpx

from app.adapters.base import (
    SourceAdapter,
    SourceDocument,
    SourceQuery,
    SourceSearchItem,
    SourceSearchResult,
    SourceStatus,
)
from app.adapters.free_web_search import search_bing_rss
from app.config import settings
from app.utils.text_clean import clean_html, content_hash, normalize_text

logger = logging.getLogger(__name__)

SUPPORTED_SITES = [
    "nowcoder.com",
    "maimai.cn",
    "xiaohongshu.com",
    "zhihu.com",
    "juejin.cn",
    "cnblogs.com",
]


class SearchEngineAdapter(SourceAdapter):
    id = "search_engine"
    display_name = "搜索引擎"

    @property
    def capabilities(self) -> dict:
        return {
            "search": True,
            "fetchDetail": True,
            "requiresLogin": False,
            "supportsDateFilter": True,
        }

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        if not settings.searxng_base_url:
            outcome = await search_bing_rss(
                query.query,
                limit=query.limit,
                timeout_s=settings.search_timeout_search_engine,
                language=settings.searxng_language,
            )
            return SourceSearchResult(
                source="search_engine",
                status=outcome.status,
                items=[self._item_from_web_result(item) for item in outcome.results[: query.limit]],
                count=len(outcome.results[: query.limit]),
                reason=(
                    "SEARXNG_BASE_URL missing; used free Bing RSS fallback"
                    if outcome.status == SourceStatus.OK
                    else outcome.reason
                ),
            )

        provider_was_explicit = "search_api_provider" in settings.model_fields_set
        if provider_was_explicit and settings.search_api_provider != "searxng":
            return SourceSearchResult(
                source="search_engine",
                status=SourceStatus.CONFIG_ERROR,
                items=[],
                count=0,
                reason="Only free self-hosted SearXNG is supported",
            )

        timeout = httpx.Timeout(settings.search_timeout_search_engine)
        params = {
            "q": query.query,
            "format": "json",
            "language": settings.searxng_language,
            "safesearch": settings.searxng_safe_search,
            "pageno": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(settings.searxng_base_url.rstrip("/") + "/search", params=params)
                if resp.status_code == 403:
                    return SourceSearchResult(
                        source="search_engine",
                        status=SourceStatus.CONFIG_ERROR,
                        count=0,
                        reason="SearXNG JSON format is disabled or forbidden",
                    )
                if resp.status_code == 429:
                    return SourceSearchResult(
                        source="search_engine",
                        status=SourceStatus.RATE_LIMITED,
                        count=0,
                        reason="Rate limited by SearXNG",
                    )
                if resp.status_code != 200:
                    return SourceSearchResult(
                        source="search_engine",
                        status=SourceStatus.ERROR,
                        count=0,
                        reason=f"HTTP Error {resp.status_code}",
                    )
                data = resp.json()
                items = [
                    self._item_from_web_result(item)
                    for item in (data.get("results") or [])[: query.limit]
                    if item.get("url") or item.get("link")
                ]
                return SourceSearchResult(
                    source="search_engine",
                    status=SourceStatus.OK if items else SourceStatus.EMPTY,
                    items=items,
                    count=len(items),
                )

        except httpx.TimeoutException:
            logger.warning("SearchEngine search timeout")
            return SourceSearchResult(
                source="search_engine",
                status=SourceStatus.TIMEOUT,
                count=0,
                reason="Timeout calling SearXNG API",
            )
        except ValueError:
            return SourceSearchResult(
                source="search_engine",
                status=SourceStatus.CONFIG_ERROR,
                count=0,
                reason="SearXNG did not return JSON; enable search.formats=json",
            )
        except Exception as e:
            logger.error(f"SearchEngine search error: {e}")
            return SourceSearchResult(
                source="search_engine",
                status=SourceStatus.ERROR,
                count=0,
                reason=str(e),
            )

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        """通用网页抓取，提取正文"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        timeout = httpx.Timeout(settings.webfetch_timeout)

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return None

                html = resp.text
                text = clean_html(html)

                if not text or len(text) < 50:
                    return None

                title = self._extract_title(html)

                return SourceDocument(
                    source="search_engine",
                    source_url=str(resp.url),
                    title=title,
                    full_text=normalize_text(text),
                    content_hash=content_hash(text),
                )

        except Exception as e:
            logger.error(f"SearchEngine fetch error: {url} - {e}")
            return None

    @staticmethod
    def _item_from_web_result(item: dict) -> SourceSearchItem:
        return SourceSearchItem(
            source="search_engine",
            source_url=item.get("url") or item.get("link") or "",
            title=item.get("title") or item.get("url") or item.get("link") or "",
            snippet=item.get("content") or item.get("snippet") or "",
            published_at=item.get("publishedDate") or item.get("date") or item.get("published_at"),
            raw=item,
        )

    @staticmethod
    def _extract_title(html: str) -> Optional[str]:
        import re
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:100]
        return None

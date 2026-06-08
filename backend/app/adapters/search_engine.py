"""
搜索引擎适配器 — 通过 SerpAPI 或类似服务补充长尾结果。
支持 site: 限定搜索范围。
"""

import logging
from typing import List, Optional

import httpx

from app.adapters.base import SourceAdapter, SourceDocument, SourceQuery, SourceSearchResult
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

    async def search(self, query: SourceQuery) -> List[SourceSearchResult]:
        if not settings.search_api_key:
            logger.info("SearchEngine: no API key configured, skipping")
            return []

        results: List[SourceSearchResult] = []
        timeout = httpx.Timeout(settings.search_timeout_search_engine)

        search_query = query.query
        # SerpAPI Google Search
        params = {
            "q": search_query,
            "api_key": settings.search_api_key,
            "engine": "google",
            "num": query.limit,
            "hl": "zh-CN",
            "gl": "cn",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                if resp.status_code != 200:
                    logger.warning(f"SerpAPI failed: status={resp.status_code}")
                    return []

                data = resp.json()
                organic = data.get("organic_results", [])

                for item in organic:
                    link = item.get("link", "")
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")

                    if not link:
                        continue

                    results.append(SourceSearchResult(
                        source="search_engine",
                        source_url=link,
                        title=title,
                        snippet=snippet,
                        published_at=item.get("date"),
                        raw=item,
                    ))

        except httpx.TimeoutException:
            logger.warning("SearchEngine search timeout")
        except Exception as e:
            logger.error(f"SearchEngine search error: {e}")

        return results

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
    def _extract_title(html: str) -> Optional[str]:
        import re
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:100]
        return None

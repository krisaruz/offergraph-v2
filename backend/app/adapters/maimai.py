"""
脉脉面经适配器 — 异步版本
需要 Cookie 才能搜索，MVP 阶段做公开搜索尝试，Cookie 失效则标记 disabled。
"""

import logging
from datetime import datetime
from typing import List, Optional

import httpx

from app.adapters.base import SourceAdapter, SourceDocument, SourceQuery, SourceSearchResult
from app.config import settings
from app.utils.text_clean import clean_html

logger = logging.getLogger(__name__)

API_BASE = "https://maimai.cn"


class MaimaiAdapter(SourceAdapter):
    id = "maimai"
    display_name = "脉脉"

    def __init__(self, cookie: str = ""):
        self._cookie = cookie

    @property
    def capabilities(self) -> dict:
        return {
            "search": True,
            "fetchDetail": False,
            "requiresLogin": True,
            "supportsDateFilter": False,
        }

    async def search(self, query: SourceQuery) -> List[SourceSearchResult]:
        if not self._cookie:
            logger.info("Maimai: no cookie configured, skipping")
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://maimai.cn/",
            "Origin": "https://maimai.cn",
            "Cookie": self._cookie,
            "X-Requested-With": "XMLHttpRequest",
        }

        csrf = self._extract_csrf(self._cookie)
        if csrf:
            headers["X-CSRFToken"] = csrf

        url = f"{API_BASE}/web/search_center"
        params = {
            "type": "feed",
            "query": query.query,
            "jsononly": 1,
            "page": 0,
            "count": query.limit,
        }

        timeout = httpx.Timeout(settings.search_timeout_platform)
        results: List[SourceSearchResult] = []

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                resp = await client.get(url, params=params)

                if resp.status_code in {403, 401}:
                    logger.warning("Maimai: cookie expired or blocked (403/401)")
                    return []
                if resp.status_code == 429:
                    logger.warning("Maimai: rate limited (429)")
                    return []
                if resp.status_code != 200:
                    return []

                data = resp.json()
                inner = data.get("data") or data
                items = inner.get("feeds") or inner.get("list") or []

                for item in items:
                    result = self._parse_search_item(item)
                    if result:
                        results.append(result)

        except httpx.TimeoutException:
            logger.warning("Maimai search timeout")
        except Exception as e:
            logger.error(f"Maimai search error: {e}")

        return results

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        return None

    def _parse_search_item(self, item: dict) -> Optional[SourceSearchResult]:
        feed = item.get("feed") or item
        post_id = str(item.get("fid") or feed.get("id") or feed.get("fid", ""))
        if not post_id:
            return None

        text = feed.get("text", "") or feed.get("content", "")
        if "<" in text:
            text = clean_html(text)

        title = text[:80] if text else ""
        snippet = text[:200] if text else ""

        crtime = feed.get("crtime") or feed.get("create_time")
        published_at = self._format_time(crtime)

        return SourceSearchResult(
            source="maimai",
            source_url=f"https://maimai.cn/web/feed_detail?fid={post_id}",
            title=title,
            snippet=snippet,
            published_at=published_at,
            raw=item,
        )

    @staticmethod
    def _extract_csrf(cookie_str: str) -> str:
        for part in cookie_str.split(";"):
            part = part.strip()
            if part.startswith("csrftoken="):
                return part.split("=", 1)[1]
        return ""

    @staticmethod
    def _format_time(ts) -> Optional[str]:
        if not ts:
            return None
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                ts = ts / 1000
            try:
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                return None
        return None

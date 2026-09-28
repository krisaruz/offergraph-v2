"""
脉脉面经适配器 — 异步版本
需要 Cookie 才能搜索，MVP 阶段做公开搜索尝试，Cookie 失效则标记 disabled。
"""

import logging
from datetime import datetime
from typing import Iterable, Optional

import httpx

from app.adapters.base import (
    SourceAdapter,
    SourceDocument,
    SourceQuery,
    SourceSearchItem,
    SourceSearchResult,
    SourceStatus,
)
from app.config import settings
from app.runtime.source_auth import GLOBAL_SOURCE_AUTH, SourceAuthManager
from app.utils.text_clean import clean_html

logger = logging.getLogger(__name__)

API_BASE = "https://maimai.cn"


class MaimaiAdapter(SourceAdapter):
    id = "maimai"
    display_name = "脉脉"

    def __init__(self, cookie: str = "", auth_manager: SourceAuthManager | None = None):
        self._cookie = cookie
        self._auth_manager = auth_manager or GLOBAL_SOURCE_AUTH

    @property
    def capabilities(self) -> dict:
        return {
            "search": True,
            "fetchDetail": False,
            "requiresLogin": True,
            "supportsDateFilter": False,
        }

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        if not self._cookie:
            refreshed_cookie = self._auth_manager.refresh_cookie(
                "maimai",
                current_cookie="",
                domains=("maimai.cn",),
            )
            if refreshed_cookie:
                self._cookie = refreshed_cookie

        if not self._cookie:
            logger.info("Maimai: no cookie configured, skipping")
            return SourceSearchResult(
                source="maimai",
                status=SourceStatus.AUTH_REQUIRED,
                count=0,
                reason="Maimai cookie is not configured",
            )

        first = await self._search_with_cookie(query, self._cookie)
        if first.status != SourceStatus.UNAUTHORIZED:
            return first

        refreshed_cookie = self._auth_manager.refresh_cookie(
            "maimai",
            current_cookie=self._cookie,
            domains=("maimai.cn",),
        )
        if not refreshed_cookie:
            return first

        self._cookie = refreshed_cookie
        return await self._search_with_cookie(query, refreshed_cookie)

    async def _search_with_cookie(self, query: SourceQuery, cookie: str) -> SourceSearchResult:
        headers = self._build_headers(cookie)
        url = f"{API_BASE}/web/search_center"
        params = {
            "type": "feed",
            "query": query.query,
            "jsononly": 1,
            "page": 0,
            "count": query.limit,
        }

        timeout = httpx.Timeout(settings.search_timeout_platform)

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                resp = await client.get(url, params=params)

                if self._is_unauthorized_response(resp):
                    logger.warning("Maimai: cookie expired or login required")
                    return SourceSearchResult(
                        source="maimai",
                        status=SourceStatus.UNAUTHORIZED,
                        count=0,
                        reason="Maimai cookie expired or login required",
                    )
                if resp.status_code == 429:
                    logger.warning("Maimai: rate limited (429)")
                    return SourceSearchResult(
                        source="maimai",
                        status=SourceStatus.RATE_LIMITED,
                        count=0,
                        reason="Maimai rate limited the request",
                    )
                if resp.status_code != 200:
                    return SourceSearchResult(
                        source="maimai",
                        status=SourceStatus.ERROR,
                        count=0,
                        reason=f"Maimai returned HTTP {resp.status_code}",
                    )

                self._update_cookie_from_response(cookie, resp.headers.get_list("set-cookie"))

                data = resp.json()
                inner = data.get("data") or data
                raw_items = inner.get("feeds") or inner.get("list") or []
                items = [item for raw in raw_items if (item := self._parse_search_item(raw))]
                self._auth_manager.mark_validated("maimai")

                return SourceSearchResult(
                    source="maimai",
                    status=SourceStatus.OK if items else SourceStatus.EMPTY,
                    items=items,
                    count=len(items),
                )

        except httpx.TimeoutException:
            logger.warning("Maimai search timeout")
            return SourceSearchResult(
                source="maimai",
                status=SourceStatus.TIMEOUT,
                count=0,
                reason="Maimai search timeout",
            )
        except Exception as e:
            logger.error(f"Maimai search error: {e}")
            return SourceSearchResult(
                source="maimai",
                status=SourceStatus.ERROR,
                count=0,
                reason=str(e),
            )

    def _build_headers(self, cookie: str) -> dict[str, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://maimai.cn/",
            "Origin": "https://maimai.cn",
            "Cookie": cookie,
            "X-Requested-With": "XMLHttpRequest",
        }

        csrf = self._extract_csrf(cookie)
        if csrf:
            headers["X-CSRFToken"] = csrf
        return headers

    def _update_cookie_from_response(self, current_cookie: str, set_cookie_headers: Iterable[str]) -> None:
        updated_cookie = self._auth_manager.update_from_set_cookie(
            "maimai",
            current_cookie,
            set_cookie_headers,
        )
        if updated_cookie:
            self._cookie = updated_cookie

    @staticmethod
    def _is_unauthorized_response(resp: httpx.Response) -> bool:
        location = resp.headers.get("location", "").lower()
        return resp.status_code in {401, 403} or (resp.status_code in {301, 302, 303, 307, 308} and "login" in location)

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        return None

    def _parse_search_item(self, item: dict) -> Optional[SourceSearchItem]:
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

        return SourceSearchItem(
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

"""
牛客面经适配器 — 异步版本
通过搜索 API 采集公开面经数据，无需登录。
"""

import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import httpx

from app.adapters.base import SourceAdapter, SourceDocument, SourceQuery, SourceSearchResult
from app.config import settings
from app.utils.text_clean import clean_html, normalize_text

logger = logging.getLogger(__name__)

GATEWAY_BASE = "https://gw-c.nowcoder.com/api/sparta"
TAG_ID_INTERVIEW = 81


class NowcoderAdapter(SourceAdapter):
    id = "nowcoder"
    display_name = "牛客"

    @property
    def capabilities(self) -> dict:
        return {
            "search": True,
            "fetchDetail": True,
            "requiresLogin": False,
            "supportsDateFilter": False,
        }

    async def search(self, query: SourceQuery) -> List[SourceSearchResult]:
        url = f"{GATEWAY_BASE}/pc/search"
        payload = {
            "query": query.query,
            "type": "post",
            "page": 1,
            "pageSize": query.limit,
            "tagId": TAG_ID_INTERVIEW,
            "order": "time",
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nowcoder.com/",
            "Origin": "https://www.nowcoder.com",
        }

        results: List[SourceSearchResult] = []
        timeout = httpx.Timeout(settings.search_timeout_platform)

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning(f"Nowcoder search failed: status={resp.status_code}")
                    return []

                data = resp.json()
                inner = data.get("data") or {}
                items = inner.get("records") or inner.get("list") or []

                for item in items:
                    result = self._parse_search_item(item)
                    if result:
                        results.append(result)

        except httpx.TimeoutException:
            logger.warning("Nowcoder search timeout")
        except Exception as e:
            logger.error(f"Nowcoder search error: {e}")

        return results

    async def fetch(self, url: str) -> Optional[SourceDocument]:
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

                html = resp.text
                text = self._extract_content_from_html(html)
                title = self._extract_title_from_html(html)

                if not text or len(text) < 50:
                    return None

                from app.utils.text_clean import content_hash
                return SourceDocument(
                    source="nowcoder",
                    source_url=url,
                    title=title,
                    full_text=text,
                    content_hash=content_hash(text),
                )

        except Exception as e:
            logger.error(f"Nowcoder fetch error: {url} - {e}")
            return None

    def _parse_search_item(self, item: dict) -> Optional[SourceSearchResult]:
        moment = item.get("momentData") or {}
        user_brief = item.get("userBrief") or {}

        post_id = moment.get("uuid") or str(moment.get("id") or "")
        if not post_id:
            post_id = item.get("uuid") or str(item.get("id") or "")
        if not post_id:
            return None

        title = moment.get("title") or moment.get("newTitle") or ""
        content_raw = moment.get("content") or moment.get("newContent") or ""
        snippet = clean_html(content_raw)[:200] if content_raw else ""

        is_uuid = self._is_uuid(post_id)
        if is_uuid:
            source_url = f"https://www.nowcoder.com/feed/main/detail/{post_id}"
        else:
            source_url = f"https://www.nowcoder.com/discuss/{post_id}"

        created_at = moment.get("createdAt") or moment.get("createTime")
        published_at = self._format_time(created_at)

        return SourceSearchResult(
            source="nowcoder",
            source_url=source_url,
            title=title or snippet[:50],
            snippet=snippet,
            published_at=published_at,
            raw=item,
        )

    @staticmethod
    def _is_uuid(post_id: str) -> bool:
        clean = post_id.replace("-", "")
        return len(clean) == 32 and all(c in "0123456789abcdef" for c in clean.lower())

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
        if isinstance(ts, str):
            return ts[:10]
        return None

    @staticmethod
    def _extract_content_from_html(html: str) -> str:
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        if match:
            try:
                next_data = json.loads(match.group(1))
                page_props = next_data.get("props", {}).get("pageProps", {})
                state = page_props.get("dehydratedState", {})
                for query in state.get("queries", []):
                    qdata = query.get("state", {}).get("data") or {}
                    if isinstance(qdata, dict):
                        content = qdata.get("content") or qdata.get("newContent") or ""
                        if content and len(content) > 50:
                            return clean_html(content) if "<" in content else content
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        return clean_html(html)

    @staticmethod
    def _extract_title_from_html(html: str) -> str:
        og_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
        if og_match:
            return og_match.group(1)
        title_match = re.search(r"<title>(.*?)</title>", html)
        if title_match:
            title = title_match.group(1)
            for suffix in [" - 牛客网", "_牛客网", " | 牛客"]:
                title = title.replace(suffix, "")
            return title.strip()
        return ""

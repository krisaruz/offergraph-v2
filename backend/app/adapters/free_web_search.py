"""No-key public web search fallback helpers.

The fallback is intentionally limited to URL/snippet discovery. It avoids paid
search APIs and does not promote snippets to high-confidence source evidence.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from app.adapters.base import SourceStatus
from app.utils.text_clean import normalize_text

logger = logging.getLogger(__name__)

BING_RSS_SEARCH_URL = "https://www.bing.com/search"
BING_RSS_PROVIDER = "bing_rss"


@dataclass(frozen=True)
class FreeWebSearchOutcome:
    status: SourceStatus
    results: list[dict]
    reason: str | None = None


async def search_bing_rss(
    query: str,
    *,
    limit: int,
    timeout_s: int,
    language: str = "zh-CN",
) -> FreeWebSearchOutcome:
    """Search Bing RSS without an API key and return normalized result dicts."""
    if limit <= 0:
        return FreeWebSearchOutcome(
            status=SourceStatus.EMPTY,
            results=[],
            reason="Search limit is zero",
        )

    params = {
        "q": query,
        "format": "rss",
        "setlang": language,
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        ),
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers=headers,
            follow_redirects=True,
        ) as client:
            resp = await client.get(BING_RSS_SEARCH_URL, params=params)
    except httpx.TimeoutException:
        logger.warning("Bing RSS fallback timeout")
        return FreeWebSearchOutcome(
            status=SourceStatus.TIMEOUT,
            results=[],
            reason="Timeout calling free Bing RSS fallback",
        )
    except Exception as exc:
        logger.warning("Bing RSS fallback error: %s", exc)
        return FreeWebSearchOutcome(
            status=SourceStatus.ERROR,
            results=[],
            reason=str(exc),
        )

    if resp.status_code == 429:
        return FreeWebSearchOutcome(
            status=SourceStatus.RATE_LIMITED,
            results=[],
            reason="Rate limited by free Bing RSS fallback",
        )
    if resp.status_code != 200:
        return FreeWebSearchOutcome(
            status=SourceStatus.ERROR,
            results=[],
            reason=f"Free Bing RSS fallback HTTP Error {resp.status_code}",
        )

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        logger.warning("Bing RSS fallback returned non-XML response")
        return FreeWebSearchOutcome(
            status=SourceStatus.ERROR,
            results=[],
            reason="Free Bing RSS fallback did not return valid RSS XML",
        )

    results: list[dict] = []
    for item in root.findall(".//item")[:limit]:
        title = normalize_text(_node_text(item, "title"))
        link = normalize_text(_node_text(item, "link"))
        description = _clean_description(_node_text(item, "description"))
        published_at = normalize_text(_node_text(item, "pubDate"))
        if not link:
            continue
        results.append(
            {
                "url": link,
                "link": link,
                "title": title or link,
                "content": description,
                "snippet": description,
                "date": published_at or None,
                "provider": BING_RSS_PROVIDER,
                "discovery": "bing_rss_url_fallback",
                "fallback": True,
                "query": query,
            }
        )

    if not results:
        return FreeWebSearchOutcome(
            status=SourceStatus.EMPTY,
            results=[],
            reason="No items matched query from free Bing RSS fallback",
        )

    return FreeWebSearchOutcome(status=SourceStatus.OK, results=results)


def _node_text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    if node is None or node.text is None:
        return ""
    return node.text


def _clean_description(value: str) -> str:
    text = html.unescape(value or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_text(text)

"""
小红书面经适配器 — MCP 版本
通过 xiaohongshu-mcp-server（Playwright 浏览器自动化）获取搜索结果和笔记内容。
比直接 HTTP 请求更可靠，走真实客户端会话。
"""

import asyncio
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
from app.adapters.xhs_mcp_client import XhsMcpClient
from app.config import settings
from app.runtime.source_health import GLOBAL_SOURCE_HEALTH
from app.utils.text_clean import content_hash, normalize_text

logger = logging.getLogger(__name__)


class XiaohongshuAdapter(SourceAdapter):
    id = "xiaohongshu"
    display_name = "小红书"

    def __init__(self, mcp_command: str = ""):
        self._mcp_command = mcp_command
        self._client: Optional[XhsMcpClient] = None
        self._warmup_task: Optional[asyncio.Task] = None

    def start_warmup(self):
        """
        在后台预热 MCP 连接（启动浏览器）。
        应在服务启动时调用，避免首次搜索时等 30+ 秒。
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._warmup_task = asyncio.ensure_future(self._warmup())
            else:
                loop.run_until_complete(self._warmup())
        except RuntimeError:
            pass

    async def _warmup(self):
        """预热连接"""
        try:
            client = await XhsMcpClient.get_instance(command=self._mcp_command)
            connected = await client.ensure_connected()
            if connected:
                logger.info("XHS MCP: warmup complete, browser ready")
            else:
                logger.warning("XHS MCP: warmup failed")
        except Exception as e:
            logger.warning(f"XHS MCP warmup error: {e}")

    async def _get_client(self) -> Optional[XhsMcpClient]:
        """获取 MCP Client 单例（如有预热 task 先等待）"""
        if self._warmup_task and not self._warmup_task.done():
            try:
                await asyncio.wait_for(self._warmup_task, timeout=50)
            except (asyncio.TimeoutError, Exception):
                pass

        if self._client is None:
            self._client = await XhsMcpClient.get_instance(
                command=self._mcp_command
            )
        return self._client

    @property
    def capabilities(self) -> dict:
        return {
            "search": True,
            "fetchDetail": True,
            "requiresLogin": True,
            "supportsDateFilter": False,
        }

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        """通过 MCP search_notes 工具搜索小红书笔记"""
        client = await self._get_client()
        if not client:
            logger.warning("XHS: MCP client unavailable")
            return await self._fallback_searxng_url_discovery(query)

        notes = await client.search_notes(
            keywords=query.query,
            limit=min(query.limit, 10),
        )

        if not notes:
            logger.info(f"XHS MCP: no results for '{query.query}'")
            return await self._fallback_searxng_url_discovery(query)

        results = []
        for note in notes:
            title = note.get("title", "小红书笔记")
            url = note.get("url", "")
            if not url:
                continue

            results.append(SourceSearchItem(
                source="xiaohongshu",
                source_url=url,
                title=title,
                snippet=title,
                published_at=None,
                raw=note,
            ))

        logger.info(f"XHS MCP: found {len(results)} results for '{query.query}'")
        return SourceSearchResult(
            source="xiaohongshu",
            status=SourceStatus.OK if results else SourceStatus.EMPTY,
            items=results,
            count=len(results),
        )

    async def _fallback_searxng_url_discovery(self, query: SourceQuery) -> SourceSearchResult:
        if not settings.searxng_base_url:
            fallback_query = f"{query.query} 小红书 面经 site:xiaohongshu.com/explore"
            outcome = await search_bing_rss(
                fallback_query,
                limit=query.limit,
                timeout_s=settings.search_timeout_search_engine,
                language=settings.searxng_language,
            )
            items = self._items_from_public_results(outcome.results, query.limit)
            return SourceSearchResult(
                source="xiaohongshu",
                status=SourceStatus.OK if items else outcome.status,
                items=items,
                count=len(items),
                reason=(
                    "XHS MCP unavailable; fell back to free web URL discovery"
                    if items else outcome.reason
                ),
            )

        params = {
            "q": f"{query.query} 小红书 面经 site:xiaohongshu.com/explore",
            "format": "json",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(settings.searxng_base_url.rstrip("/") + "/search", params=params)
            if resp.status_code != 200:
                return SourceSearchResult(
                    source="xiaohongshu",
                    status=SourceStatus.ERROR,
                    count=0,
                    reason=f"SearXNG fallback returned HTTP {resp.status_code}",
                )
            items = self._items_from_public_results(resp.json().get("results") or [], query.limit)
            return SourceSearchResult(
                source="xiaohongshu",
                status=SourceStatus.OK if items else SourceStatus.EMPTY,
                items=items[: query.limit],
                count=len(items[: query.limit]),
                reason="XHS MCP unavailable; fell back to SearXNG URL discovery",
            )
        except httpx.TimeoutException:
            return SourceSearchResult(
                source="xiaohongshu",
                status=SourceStatus.TIMEOUT,
                count=0,
                reason="SearXNG fallback timed out",
            )
        except Exception as exc:
            return SourceSearchResult(
                source="xiaohongshu",
                status=SourceStatus.ERROR,
                count=0,
                reason=str(exc),
            )

    @staticmethod
    def _items_from_public_results(results: list[dict], limit: int) -> list[SourceSearchItem]:
        items: list[SourceSearchItem] = []
        for row in results:
            url = str(row.get("url") or row.get("link") or "")
            if "xiaohongshu.com/explore" not in url:
                continue
            title = str(row.get("title") or "小红书笔记")
            content = str(row.get("content") or row.get("snippet") or "")
            items.append(SourceSearchItem(
                source="xiaohongshu",
                source_url=url,
                title=title,
                snippet=content or title,
                published_at=row.get("publishedDate") or row.get("date"),
                raw={
                    **row,
                    "evidence_status": "url_snippet_only",
                    "requires_authorized_detail": True,
                },
            ))
            if len(items) >= limit:
                break
        return items

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        """通过 MCP get_note_content 工具获取笔记全文"""
        client = await self._get_client()
        if not client:
            return None

        try:
            note = await client.get_note_content(url)
        except ValueError as exc:
            if str(exc) == "auth_required":
                GLOBAL_SOURCE_HEALTH.record_status(
                    "xiaohongshu",
                    SourceStatus.UNAUTHORIZED,
                    "XHS authorized browser session is required",
                )
                return None
            raise
        if not note:
            logger.info(f"XHS MCP: failed to fetch {url}")
            return None

        title = note.get("title", "")
        content = note.get("content", "")
        author = note.get("author", "")

        full_text = ""
        if title:
            full_text += title + "\n\n"
        if author:
            full_text += f"作者: {author}\n\n"
        if content:
            full_text += content

        full_text = full_text.strip()

        if not full_text or len(full_text) < 20:
            return None

        return SourceDocument(
            source="xiaohongshu",
            source_url=url,
            title=title or None,
            full_text=normalize_text(full_text),
            content_hash=content_hash(full_text),
        )

    async def _reset_client(self) -> None:
        if self._client:
            await self._client.disconnect()
        self._client = None

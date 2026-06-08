"""
小红书面经适配器 — MCP 版本
通过 xiaohongshu-mcp-server（Playwright 浏览器自动化）获取搜索结果和笔记内容。
比直接 HTTP 请求更可靠，走真实客户端会话。
"""

import asyncio
import logging
from typing import List, Optional

from app.adapters.base import SourceAdapter, SourceDocument, SourceQuery, SourceSearchResult
from app.adapters.xhs_mcp_client import XhsMcpClient
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

    async def search(self, query: SourceQuery) -> List[SourceSearchResult]:
        """通过 MCP search_notes 工具搜索小红书笔记"""
        client = await self._get_client()
        if not client:
            logger.warning("XHS: MCP client unavailable")
            return []

        notes = await client.search_notes(
            keywords=query.query,
            limit=min(query.limit, 10),
        )

        if not notes:
            logger.info(f"XHS MCP: no results for '{query.query}'")
            return []

        results = []
        for note in notes:
            title = note.get("title", "小红书笔记")
            url = note.get("url", "")
            if not url:
                continue

            results.append(SourceSearchResult(
                source="xiaohongshu",
                source_url=url,
                title=title,
                snippet=title,
                published_at=None,
                raw=note,
            ))

        logger.info(f"XHS MCP: found {len(results)} results for '{query.query}'")
        return results

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        """通过 MCP get_note_content 工具获取笔记全文"""
        client = await self._get_client()
        if not client:
            return None

        note = await client.get_note_content(url)
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

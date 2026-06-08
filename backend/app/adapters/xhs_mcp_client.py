"""
小红书 MCP Client — 管理与 xiaohongshu-mcp-server 的 stdio 长连接。

直接启动 Python FastMCP Server 进程（跳过 Node.js 包装层以避免 stdout 污染），
维护单例连接，提供 search_notes / get_note_content 两个核心方法供 Adapter 调用。
"""

import asyncio
import logging
import os
import re
from contextlib import AsyncExitStack
from typing import List, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# MCP Server Python 入口所在目录（npm global 安装路径）
_DEFAULT_MCP_ROOT = os.path.join(
    os.environ.get("APPDATA", ""),
    "npm", "node_modules", "xiaohongshu-mcp-server"
)


class XhsMcpClient:
    """小红书 MCP Client 单例，管理与 MCP Server 的 stdio 连接。"""

    _instance: Optional["XhsMcpClient"] = None
    _lock = asyncio.Lock()

    def __init__(self, mcp_root: str = ""):
        self._mcp_root = mcp_root or _DEFAULT_MCP_ROOT
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._connected = False
        self._connect_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, command: str = "") -> "XhsMcpClient":
        """获取或创建单例实例"""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls(mcp_root=command)
            return cls._instance

    async def ensure_connected(self) -> bool:
        """确保 MCP 连接已建立"""
        if self._connected and self._session:
            return True

        async with self._connect_lock:
            if self._connected and self._session:
                return True
            return await self._connect()

    async def _connect(self) -> bool:
        """
        直接启动 Python FastMCP Server 进程（跳过 Node.js index.js）。
        Node.js 包装层会打印 emoji 启动信息到 stdout 污染 MCP JSON-RPC 通道。
        整个连接流程有 30s 超时保护，防止子进程挂起阻塞事件循环。
        """
        try:
            server_py = os.path.join(
                self._mcp_root, "src", "interfaces", "mcp", "server.py"
            )
            if not os.path.exists(server_py):
                logger.error(f"XHS MCP server.py not found: {server_py}")
                return False

            logger.info(f"Starting XHS MCP Server (Python direct): {self._mcp_root}")

            server_params = StdioServerParameters(
                command="python",
                args=["-m", "src.interfaces.mcp.server"],
                env={
                    **os.environ,
                    "PYTHONPATH": self._mcp_root,
                    "PYTHONIOENCODING": "utf-8",
                },
                cwd=self._mcp_root,
            )

            self._exit_stack = AsyncExitStack()

            async def _do_connect():
                transport = await self._exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                read, write = transport
                self._session = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                await self._session.initialize()
                tools = await self._session.list_tools()
                return [t.name for t in tools.tools]

            tool_names = await asyncio.wait_for(_do_connect(), timeout=30)
            logger.info(f"XHS MCP connected, available tools: {tool_names}")

            self._connected = True
            return True

        except asyncio.TimeoutError:
            logger.error("XHS MCP connection timed out after 30s")
            await self._cleanup()
            return False
        except Exception as e:
            logger.error(f"XHS MCP connection failed: {e}")
            await self._cleanup()
            return False

    async def _cleanup(self):
        """清理连接资源"""
        self._connected = False
        self._session = None
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._exit_stack = None

    async def disconnect(self):
        """断开连接"""
        await self._cleanup()

    async def call_tool(self, name: str, arguments: dict, timeout: float = 30) -> Optional[str]:
        """调用 MCP tool，返回文本结果。单次调用有 timeout 秒超时保护。"""
        if not await self.ensure_connected():
            return None

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, arguments=arguments),
                timeout=timeout,
            )
            if result.content:
                return result.content[0].text
            return None
        except asyncio.TimeoutError:
            logger.error(f"XHS MCP call_tool({name}) timed out after {timeout}s")
            self._connected = False
            return None
        except Exception as e:
            logger.error(f"XHS MCP call_tool({name}) failed: {e}")
            self._connected = False
            return None

    async def search_notes(
        self, keywords: str, limit: int = 5
    ) -> List[dict]:
        """
        搜索笔记，解析 MCP 返回的文本为结构化数据。

        Returns:
            [{"title": "...", "url": "..."}, ...]
        """
        text = await self.call_tool("search_notes", {
            "keywords": keywords,
            "limit": limit,
        })

        if not text:
            return []

        return self._parse_search_results(text)

    async def get_note_content(self, url: str) -> Optional[dict]:
        """
        获取笔记内容。

        Returns:
            {"title": "...", "author": "...", "content": "..."} or None
        """
        text = await self.call_tool("get_note_content", {"url": url})

        if not text:
            return None

        return self._parse_note_content(text)

    @staticmethod
    def _parse_search_results(text: str) -> List[dict]:
        """
        解析 search_notes 返回的文本格式：
        找到 N 条与 'xxx' 相关的笔记：

        1. 标题: xxx
           链接: https://...

        2. 标题: xxx
           链接: https://...
        """
        results = []

        # 匹配每条结果：序号 + 标题 + 链接
        pattern = re.compile(
            r'\d+\.\s*标题:\s*(.+?)\s*\n\s*链接:\s*(https?://\S+)',
            re.MULTILINE
        )

        for match in pattern.finditer(text):
            title = match.group(1).strip()
            url = match.group(2).strip()
            results.append({"title": title, "url": url})

        return results

    @staticmethod
    def _parse_note_content(text: str) -> Optional[dict]:
        """
        解析 get_note_content 返回的文本格式：
        标题: xxx
        作者: xxx
        内容: xxx
        """
        if not text or "失败" in text[:20]:
            return None

        result = {}

        # 提取标题
        title_match = re.search(r'^标题:\s*(.+?)$', text, re.MULTILINE)
        if title_match:
            result["title"] = title_match.group(1).strip()

        # 提取作者
        author_match = re.search(r'^作者:\s*(.+?)$', text, re.MULTILINE)
        if author_match:
            result["author"] = author_match.group(1).strip()

        # 提取内容（从 "内容:" 开始到文本结尾）
        content_match = re.search(r'^内容:\s*(.+)', text, re.MULTILINE | re.DOTALL)
        if content_match:
            result["content"] = content_match.group(1).strip()

        return result if result.get("content") or result.get("title") else None

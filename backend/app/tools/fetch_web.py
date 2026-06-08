"""WebFetch 工具 — 统一网页抓取并写入 source_documents"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import SourceAdapter
from app.config import settings
from app.models.source_document import SourceDocumentModel
from app.runtime.permission_guard import PermissionGuard
from app.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class FetchWebTool(BaseTool):
    """
    抓取 URL 正文，写入 source_documents。
    抓取前检查 PermissionGuard。
    """

    name = "fetch_web"
    tool_type = "fetch"

    def __init__(self, db: AsyncSession, adapters: Dict[str, SourceAdapter]):
        self._db = db
        self._adapters = adapters
        self._permission_guard = PermissionGuard()

    async def run(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        url = input_data.get("url", "")
        source = input_data.get("source", "search_engine")

        if not url:
            return ToolResult(status="error", error_message="No URL provided")

        # 权限检查
        perm = self._permission_guard.can_fetch_url(url, source)
        if not perm.allowed:
            return ToolResult(
                status="skipped",
                error_message=f"Blocked: {perm.reason}",
                metadata={"policy": perm.policy.value},
            )

        # 尝试通过对应 adapter fetch
        adapter = self._adapters.get(source)
        doc = None

        if adapter and hasattr(adapter, "fetch"):
            doc = await adapter.fetch(url)

        # fallback: 通过搜索引擎 adapter 的通用 fetch
        if not doc and "search_engine" in self._adapters:
            doc = await self._adapters["search_engine"].fetch(url)

        if not doc:
            return ToolResult(status="error", error_message="Fetch returned empty")

        # 写入 source_documents
        source_doc = SourceDocumentModel(
            id=str(uuid.uuid4()),
            source=doc.source,
            source_url=doc.source_url,
            title=doc.title,
            snippet=doc.snippet,
            full_text=doc.full_text,
            content_hash=doc.content_hash,
            fetched_at=datetime.utcnow(),
            fetch_policy=perm.policy.value,
            extraction_status="pending",
        )
        self._db.add(source_doc)
        await self._db.flush()

        return ToolResult(
            status="success",
            data={
                "source_document_id": source_doc.id,
                "title": source_doc.title,
                "text_length": len(doc.full_text) if doc.full_text else 0,
                "content_hash": doc.content_hash,
            },
        )

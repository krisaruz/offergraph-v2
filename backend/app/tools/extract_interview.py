"""面经抽取工具 — 对 source_document 执行 LLM 结构化抽取"""

import logging
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.structured_extract import extract_interview
from app.models.source_document import SourceDocumentModel
from app.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ExtractInterviewTool(BaseTool):
    """调用 LLM 对 source_document 执行结构化抽取"""

    name = "extract_interview"
    tool_type = "extract"

    def __init__(self, db: AsyncSession):
        self._db = db

    async def run(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        source_document_id = input_data.get("source_document_id", "")
        if not source_document_id:
            return ToolResult(status="error", error_message="No source_document_id provided")

        stmt = select(SourceDocumentModel).where(SourceDocumentModel.id == source_document_id)
        result = await self._db.execute(stmt)
        source_doc = result.scalar_one_or_none()

        if not source_doc:
            return ToolResult(status="error", error_message="Source document not found")

        if source_doc.extraction_status == "extracted":
            return ToolResult(status="skipped", data={"reason": "already_extracted"})

        try:
            extract_result = await extract_interview(
                db=self._db,
                source_doc=source_doc,
                profile_context=input_data.get("profile_context"),
            )
            return ToolResult(status="success", data=extract_result)

        except Exception as e:
            logger.error(f"Extraction failed for {source_document_id}: {e}")
            return ToolResult(status="error", error_message=str(e))

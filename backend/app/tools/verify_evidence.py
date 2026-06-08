"""Evidence 验证工具 — 检查证据链完整性"""

import logging
from typing import Any, Dict

from app.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class VerifyEvidenceTool(BaseTool):
    """
    检查抽取结果的证据完整性：
    - 每个 real_interview 问题是否有 evidence_quote
    - evidence_quote 是否能在 full_text 中找到
    - 计算 evidence_coverage
    """

    name = "verify_evidence"
    tool_type = "verify"

    async def run(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        full_text = input_data.get("full_text", "")
        questions = input_data.get("questions", [])

        if not questions:
            return ToolResult(status="success", data={"coverage": 0.0, "total": 0})

        real_questions = [q for q in questions if q.get("source_type") == "real_interview"]
        if not real_questions:
            return ToolResult(status="success", data={"coverage": 0.0, "total": 0})

        verified_count = 0
        issues = []

        for q in real_questions:
            quote = q.get("evidence_quote", "")
            if not quote:
                issues.append(f"Missing evidence: {q.get('text', '')[:40]}")
                continue

            if full_text and quote in full_text:
                verified_count += 1
            elif full_text and self._fuzzy_match(quote, full_text):
                verified_count += 1
            else:
                issues.append(f"Evidence not found in text: {quote[:40]}")

        coverage = verified_count / len(real_questions) if real_questions else 0.0

        return ToolResult(
            status="success",
            data={
                "coverage": round(coverage, 3),
                "total": len(real_questions),
                "verified": verified_count,
                "issues": issues,
            },
        )

    @staticmethod
    def _fuzzy_match(quote: str, full_text: str) -> bool:
        """宽松匹配：去除空白后检查子串"""
        clean_quote = "".join(quote.split())[:50]
        clean_text = "".join(full_text.split())
        return clean_quote in clean_text

"""LLM 结构化抽取 — 面经 → 结构化面试情报"""

import json
import logging
import uuid
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import llm_client, LLMClient
from app.models.source_document import SourceDocumentModel
from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.evidence import QuestionEvidence

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是一个面经结构化抽取助手。

任务：从用户提供的面经文本中抽取结构化信息。

严格规则：
1. 你只能从原文中抽取真实出现的面试问题。
2. 如果问题没有在原文中出现，不要作为 real_interview 输出。
3. 如果你基于上下文扩展了可能追问，必须标记为 ai_extension。
4. 每个 real_interview 问题必须返回 evidence_quote（原文短片段）。
5. 不要编造公司、岗位、轮次、时间。如果信息不明确，返回 null 或 unknown。
6. 输出必须是合法 JSON。

输出 JSON 结构：
{{
  "events": [
    {{
      "company": "string | null",
      "position": "string | null",
      "candidate_type": "social | campus | intern | unknown",
      "round": "string | null",
      "interview_date": "YYYY-MM-DD | null",
      "region": "string | null",
      "summary": "string",
      "difficulty": 1-5,
      "tags": ["string"],
      "confidence": 0.0-1.0,
      "questions": [
        {{
          "text": "原始问题文本",
          "category": "project | fundamentals | algorithm | system_design | ai | behavioral | other",
          "difficulty": 1-5,
          "tags": ["string"],
          "followups": ["追问文本"],
          "source_type": "real_interview | ai_extension",
          "evidence_quote": "原文中的证据片段",
          "confidence": 0.0-1.0
        }}
      ]
    }}
  ]
}}

面经文本：
{text}
"""


async def extract_interview(
    db: AsyncSession,
    source_doc: SourceDocumentModel,
    profile_context: Optional[dict] = None,
) -> dict:
    """
    对 source_document 执行 LLM 结构化抽取，
    将结果写入 interview_events / interview_questions / question_evidence。
    返回抽取概要。
    """
    if not source_doc.full_text or len(source_doc.full_text) < 50:
        source_doc.extraction_status = "skipped"
        await db.flush()
        return {"status": "skipped", "reason": "text_too_short"}

    prompt = EXTRACTION_PROMPT.format(text=source_doc.full_text[:8000])

    messages = [
        {"role": "system", "content": "你是一个面经结构化抽取助手。只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]

    try:
        result = await llm_client.chat_json(messages, temperature=0.1)
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        source_doc.extraction_status = "failed"
        await db.flush()
        return {"status": "failed", "error": str(e)}

    if "error" in result:
        source_doc.extraction_status = "failed"
        await db.flush()
        return {"status": "failed", "error": result["error"]}

    events = result.get("events", [])
    if not events:
        source_doc.extraction_status = "extracted"
        source_doc.extraction_confidence = 0.0
        await db.flush()
        return {"status": "extracted", "event_count": 0, "question_count": 0}

    total_questions = 0
    total_with_evidence = 0
    representative_questions = []

    for event_data in events:
        event_id = str(uuid.uuid4())
        event = InterviewEvent(
            id=event_id,
            source_document_id=source_doc.id,
            company=event_data.get("company"),
            position=event_data.get("position"),
            candidate_type=event_data.get("candidate_type", "unknown"),
            round=event_data.get("round"),
            region=event_data.get("region"),
            summary=event_data.get("summary", ""),
            difficulty=event_data.get("difficulty"),
            tags_json=json.dumps(event_data.get("tags", []), ensure_ascii=False),
        )
        db.add(event)

        questions = event_data.get("questions", [])
        event_evidence_count = 0

        for q_data in questions:
            q_id = str(uuid.uuid4())
            source_type = q_data.get("source_type", "real_interview")

            question = InterviewQuestion(
                id=q_id,
                interview_event_id=event_id,
                question_text=q_data.get("text", ""),
                normalized_question=q_data.get("text", ""),
                category=q_data.get("category", "other"),
                difficulty=q_data.get("difficulty"),
                tags_json=json.dumps(q_data.get("tags", []), ensure_ascii=False),
                followups_json=json.dumps(q_data.get("followups", []), ensure_ascii=False),
                source_type=source_type,
                confidence=q_data.get("confidence", 0.0),
            )
            db.add(question)
            total_questions += 1

            # 写入证据
            evidence_quote = q_data.get("evidence_quote")
            if evidence_quote and source_type == "real_interview":
                start_offset = source_doc.full_text.find(evidence_quote) if evidence_quote else -1
                evidence = QuestionEvidence(
                    id=str(uuid.uuid4()),
                    question_id=q_id,
                    source_document_id=source_doc.id,
                    quote=evidence_quote,
                    start_offset=start_offset if start_offset >= 0 else None,
                    end_offset=(start_offset + len(evidence_quote)) if start_offset >= 0 else None,
                    confidence=q_data.get("confidence", 0.0),
                )
                db.add(evidence)
                event_evidence_count += 1
                total_with_evidence += 1
                if len(representative_questions) < 5:
                    representative_questions.append({
                        "text": q_data.get("text", ""),
                        "category": q_data.get("category", "other"),
                        "evidence_quote": evidence_quote,
                        "source_type": source_type,
                        "confidence": q_data.get("confidence", 0.0),
                    })

        real_count = sum(1 for q in questions if q.get("source_type") == "real_interview")
        coverage = event_evidence_count / real_count if real_count > 0 else 0.0
        event.evidence_coverage = coverage

    overall_confidence = sum(e.get("confidence", 0) for e in events) / len(events) if events else 0.0
    source_doc.extraction_status = "extracted"
    source_doc.extraction_confidence = overall_confidence
    await db.flush()

    return {
        "status": "extracted",
        "event_count": len(events),
        "question_count": total_questions,
        "evidence_count": total_with_evidence,
        "confidence": overall_confidence,
        "representative_questions": representative_questions,
    }


async def extract_interview_streaming(
    db: AsyncSession,
    source_doc: SourceDocumentModel,
    on_token: Callable[[str], None],
    profile_context: Optional[dict] = None,
) -> dict:
    """
    流式版本的 extract_interview：边生成边推送 token。
    on_token 回调在每次收到 LLM chunk 时调用。
    完成后解析 JSON 并写入数据库，返回抽取概要。
    """
    if not source_doc.full_text or len(source_doc.full_text) < 50:
        source_doc.extraction_status = "skipped"
        await db.flush()
        return {"status": "skipped", "reason": "text_too_short"}

    prompt = EXTRACTION_PROMPT.format(text=source_doc.full_text[:8000])

    messages = [
        {"role": "system", "content": "你是一个面经结构化抽取助手。只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]

    collected_content = ""
    try:
        async for token in llm_client.chat_stream(messages, temperature=0.1, max_tokens=4096):
            collected_content += token
            on_token(token)
    except Exception as e:
        logger.error(f"LLM streaming extraction failed: {e}")
        source_doc.extraction_status = "failed"
        await db.flush()
        return {"status": "failed", "error": str(e)}

    # Parse collected JSON
    parsed = LLMClient._extract_json(collected_content)
    if parsed is None:
        source_doc.extraction_status = "failed"
        await db.flush()
        return {"status": "failed", "error": "JSON parse failed"}

    if "error" in parsed:
        source_doc.extraction_status = "failed"
        await db.flush()
        return {"status": "failed", "error": parsed["error"]}

    events = parsed.get("events", [])
    if not events:
        source_doc.extraction_status = "extracted"
        source_doc.extraction_confidence = 0.0
        await db.flush()
        return {"status": "extracted", "event_count": 0, "question_count": 0}

    total_questions = 0
    total_with_evidence = 0
    representative_questions = []

    for event_data in events:
        event_id = str(uuid.uuid4())
        event = InterviewEvent(
            id=event_id,
            source_document_id=source_doc.id,
            company=event_data.get("company"),
            position=event_data.get("position"),
            candidate_type=event_data.get("candidate_type", "unknown"),
            round=event_data.get("round"),
            region=event_data.get("region"),
            summary=event_data.get("summary", ""),
            difficulty=event_data.get("difficulty"),
            tags_json=json.dumps(event_data.get("tags", []), ensure_ascii=False),
        )
        db.add(event)

        questions = event_data.get("questions", [])
        event_evidence_count = 0

        for q_data in questions:
            q_id = str(uuid.uuid4())
            source_type = q_data.get("source_type", "real_interview")

            question = InterviewQuestion(
                id=q_id,
                interview_event_id=event_id,
                question_text=q_data.get("text", ""),
                normalized_question=q_data.get("text", ""),
                category=q_data.get("category", "other"),
                difficulty=q_data.get("difficulty"),
                tags_json=json.dumps(q_data.get("tags", []), ensure_ascii=False),
                followups_json=json.dumps(q_data.get("followups", []), ensure_ascii=False),
                source_type=source_type,
                confidence=q_data.get("confidence", 0.0),
            )
            db.add(question)
            total_questions += 1

            evidence_quote = q_data.get("evidence_quote")
            if evidence_quote and source_type == "real_interview":
                start_offset = source_doc.full_text.find(evidence_quote) if evidence_quote else -1
                evidence = QuestionEvidence(
                    id=str(uuid.uuid4()),
                    question_id=q_id,
                    source_document_id=source_doc.id,
                    quote=evidence_quote,
                    start_offset=start_offset if start_offset >= 0 else None,
                    end_offset=(start_offset + len(evidence_quote)) if start_offset >= 0 else None,
                    confidence=q_data.get("confidence", 0.0),
                )
                db.add(evidence)
                event_evidence_count += 1
                total_with_evidence += 1
                if len(representative_questions) < 5:
                    representative_questions.append({
                        "text": q_data.get("text", ""),
                        "category": q_data.get("category", "other"),
                        "evidence_quote": evidence_quote,
                        "source_type": source_type,
                        "confidence": q_data.get("confidence", 0.0),
                    })

        real_count = sum(1 for q in questions if q.get("source_type") == "real_interview")
        coverage = event_evidence_count / real_count if real_count > 0 else 0.0
        event.evidence_coverage = coverage

    overall_confidence = sum(e.get("confidence", 0) for e in events) / len(events) if events else 0.0
    source_doc.extraction_status = "extracted"
    source_doc.extraction_confidence = overall_confidence
    await db.flush()

    # Build human-readable summary
    categories = {}
    for ev in events:
        for q in ev.get("questions", []):
            cat = q.get("category", "other")
            categories[cat] = categories.get(cat, 0) + 1

    category_summary = "、".join(
        f"{_category_label(k)}({v})" for k, v in sorted(categories.items(), key=lambda x: -x[1])[:4]
    )

    return {
        "status": "extracted",
        "event_count": len(events),
        "question_count": total_questions,
        "evidence_count": total_with_evidence,
        "confidence": overall_confidence,
        "summary": f"提取了 {total_questions} 个面试问题，涵盖{category_summary}",
        "representative_questions": representative_questions,
    }


def _category_label(cat: str) -> str:
    labels = {
        "fundamentals": "基础",
        "system_design": "系统设计",
        "algorithm": "算法",
        "project": "项目",
        "ai": "AI",
        "behavioral": "行为面试",
        "other": "其他",
    }
    return labels.get(cat, cat)

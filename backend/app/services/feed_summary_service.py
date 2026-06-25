"""Feed-facing summaries built from archived interview questions."""

from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import QuestionEvidence
from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.source_document import SourceDocumentModel
from app.services.question_quality import (
    is_specific_interview_question,
    question_specificity_score,
)


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _dedupe(values: Iterable[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


async def build_feed_summary(
    db: AsyncSession,
    source_doc: SourceDocumentModel,
    preview_limit: int = 3,
) -> dict[str, Any]:
    """Return question-first metadata for one archived source document."""
    events_result = await db.execute(
        select(InterviewEvent).where(InterviewEvent.source_document_id == source_doc.id)
    )
    events = events_result.scalars().all()
    event_ids = [event.id for event in events]

    questions: list[InterviewQuestion] = []
    if event_ids:
        questions_result = await db.execute(
            select(InterviewQuestion).where(
                InterviewQuestion.interview_event_id.in_(event_ids)
            )
        )
        questions = questions_result.scalars().all()

    question_ids = [question.id for question in questions]
    evidence_by_question: dict[str, QuestionEvidence] = {}
    if question_ids:
        evidence_result = await db.execute(
            select(QuestionEvidence).where(QuestionEvidence.question_id.in_(question_ids))
        )
        for evidence in evidence_result.scalars().all():
            evidence_by_question.setdefault(evidence.question_id, evidence)

    event_tags = [
        tag
        for event in events
        for tag in _json_list(event.tags_json)
    ]
    question_tags = [
        tag
        for question in questions
        for tag in _json_list(question.tags_json)
    ]
    tags = _dedupe([*event_tags, *question_tags], limit=6)

    real_questions = [
        question for question in questions
        if question.source_type == "real_interview"
    ]
    specific_real_questions = [
        question for question in real_questions
        if is_specific_interview_question(question.question_text, question.category)
    ]
    real_with_evidence = [
        question for question in specific_real_questions if question.id in evidence_by_question
    ]

    coverage_values = [
        event.evidence_coverage for event in events if event.evidence_coverage is not None
    ]
    if coverage_values:
        evidence_coverage = sum(coverage_values) / len(coverage_values)
    elif specific_real_questions:
        evidence_coverage = len(real_with_evidence) / len(specific_real_questions)
    else:
        evidence_coverage = None

    def preview_sort_key(question: InterviewQuestion) -> tuple[int, int, int, float, int]:
        evidence = evidence_by_question.get(question.id)
        confidence = float(question.confidence or 0.0)
        difficulty = int(question.difficulty or 0)
        specificity = question_specificity_score(
            question,
            evidence_quote=evidence.quote if evidence else None,
        )
        return (*specificity, confidence, difficulty)

    preview_questions = sorted(
        specific_real_questions,
        key=preview_sort_key,
        reverse=True,
    )[:preview_limit]

    representative_questions: list[dict[str, Any]] = []
    for question in preview_questions:
        evidence = evidence_by_question.get(question.id)
        representative_questions.append({
            "id": question.id,
            "text": question.question_text,
            "category": question.category,
            "difficulty": question.difficulty,
            "source_type": question.source_type,
            "confidence": question.confidence,
            "evidence_quote": evidence.quote if evidence else None,
        })

    first_event = events[0] if events else None
    return {
        "question_count": len(questions),
        "real_question_count": len(real_questions),
        "evidence_count": len(evidence_by_question),
        "representative_questions": representative_questions,
        "tags": tags,
        "evidence_coverage": evidence_coverage,
        "extraction_status": source_doc.extraction_status,
        "extraction_confidence": source_doc.extraction_confidence,
        "event_count": len(events),
        "company": first_event.company if first_event else None,
        "position": first_event.position if first_event else None,
        "difficulty": first_event.difficulty if first_event else None,
    }

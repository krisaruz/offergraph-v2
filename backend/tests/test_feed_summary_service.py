"""Tests for Feed-facing question summaries."""

import uuid
from datetime import datetime

import pytest

from app.models.evidence import QuestionEvidence
from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.source_document import SourceDocumentModel
from app.services.feed_summary_service import build_feed_summary


@pytest.mark.asyncio
async def test_feed_summary_skips_generic_representative_questions(db_session):
    doc_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    generic_id = str(uuid.uuid4())
    specific_id = str(uuid.uuid4())

    doc = SourceDocumentModel(
        id=doc_id,
        source="nowcoder",
        source_url="https://nowcoder.com/discuss/summary-quality",
        title="阿里后端面经",
        full_text="面试官问了项目经历，也问 Redis 和 MySQL 如何保证一致性。" * 3,
        extraction_status="extracted",
        fetched_at=datetime.utcnow(),
    )
    event = InterviewEvent(
        id=event_id,
        source_document_id=doc_id,
        company="阿里巴巴",
        position="后端",
        candidate_type="social",
        summary="缓存一致性",
        evidence_coverage=1.0,
    )
    generic = InterviewQuestion(
        id=generic_id,
        interview_event_id=event_id,
        question_text="项目经历相关问题",
        normalized_question="项目经历相关问题",
        category="project",
        source_type="real_interview",
        confidence=0.9,
    )
    specific = InterviewQuestion(
        id=specific_id,
        interview_event_id=event_id,
        question_text="Redis 和 MySQL 如何保证一致性？",
        normalized_question="Redis 和 MySQL 如何保证一致性？",
        category="fundamentals",
        source_type="real_interview",
        confidence=0.8,
    )
    db_session.add_all([
        doc,
        event,
        generic,
        specific,
        QuestionEvidence(
            id=str(uuid.uuid4()),
            question_id=generic_id,
            source_document_id=doc_id,
            quote="面试官问了项目经历",
            confidence=0.9,
        ),
        QuestionEvidence(
            id=str(uuid.uuid4()),
            question_id=specific_id,
            source_document_id=doc_id,
            quote="问 Redis 和 MySQL 如何保证一致性",
            confidence=0.8,
        ),
    ])
    await db_session.flush()

    summary = await build_feed_summary(db_session, doc)

    assert summary["question_count"] == 2
    assert [
        q["text"] for q in summary["representative_questions"]
    ] == ["Redis 和 MySQL 如何保证一致性？"]

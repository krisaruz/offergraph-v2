"""Tests for LLM structured interview extraction."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.llm import structured_extract
from app.llm.structured_extract import extract_interview

# EXTRACTION_PROMPT contains JSON braces; use a minimal template in tests.
_TEST_EXTRACTION_PROMPT = "面经文本：{text}"
from app.models.evidence import QuestionEvidence
from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.source_document import SourceDocumentModel


@pytest.mark.asyncio
async def test_extract_interview_skips_short_text(db_session):
    doc = SourceDocumentModel(
        id=str(uuid.uuid4()),
        source="nowcoder",
        source_url="https://nowcoder.com/short",
        full_text="too short",
        extraction_status="pending",
    )
    db_session.add(doc)
    await db_session.flush()

    result = await extract_interview(db_session, doc)

    assert result == {"status": "skipped", "reason": "text_too_short"}
    assert doc.extraction_status == "skipped"


@pytest.mark.asyncio
async def test_extract_interview_skips_empty_text(db_session):
    doc = SourceDocumentModel(
        id=str(uuid.uuid4()),
        source="nowcoder",
        source_url="https://nowcoder.com/empty",
        full_text=None,
        extraction_status="pending",
    )
    db_session.add(doc)
    await db_session.flush()

    result = await extract_interview(db_session, doc)

    assert result["status"] == "skipped"
    assert doc.extraction_status == "skipped"


@pytest.mark.asyncio
async def test_extract_interview_writes_events_questions_and_evidence(db_session):
    evidence_quote = "面试官问了红黑树和项目架构"
    full_text = (
        f"腾讯后端一面面经：{evidence_quote}，"
        "还追问了缓存一致性，属于典型校招面经，难度中等，"
        "整体内容超过最小长度阈值，便于触发结构化抽取流程。"
    )

    doc = SourceDocumentModel(
        id=str(uuid.uuid4()),
        source="nowcoder",
        source_url="https://nowcoder.com/discuss/extract-1",
        title="腾讯 后端 面经",
        full_text=full_text,
        extraction_status="pending",
        fetched_at=datetime.utcnow(),
    )
    db_session.add(doc)
    await db_session.flush()

    llm_payload = {
        "events": [
            {
                "company": "腾讯",
                "position": "后端",
                "candidate_type": "campus",
                "round": "一面",
                "summary": "红黑树和项目",
                "difficulty": 3,
                "tags": ["算法"],
                "confidence": 0.85,
                "questions": [
                    {
                        "text": "请解释红黑树的性质",
                        "category": "algorithm",
                        "difficulty": 3,
                        "tags": ["数据结构"],
                        "followups": ["如何旋转"],
                        "source_type": "real_interview",
                        "evidence_quote": evidence_quote,
                        "confidence": 0.9,
                    },
                    {
                        "text": "可能的系统设计追问",
                        "category": "system_design",
                        "source_type": "ai_extension",
                        "confidence": 0.5,
                    },
                ],
            }
        ]
    }

    with (
        patch.object(structured_extract, "EXTRACTION_PROMPT", _TEST_EXTRACTION_PROMPT),
        patch("app.llm.structured_extract.llm_client") as mock_llm,
    ):
        mock_llm.chat_json = AsyncMock(return_value=llm_payload)
        result = await extract_interview(db_session, doc)

    assert result["status"] == "extracted"
    assert result["event_count"] == 1
    assert result["question_count"] == 2
    assert result["evidence_count"] == 1
    assert result["confidence"] == 0.85
    assert doc.extraction_status == "extracted"
    assert doc.extraction_confidence == 0.85

    events = (await db_session.execute(select(InterviewEvent))).scalars().all()
    questions = (await db_session.execute(select(InterviewQuestion))).scalars().all()
    evidences = (await db_session.execute(select(QuestionEvidence))).scalars().all()

    assert len(events) == 1
    assert events[0].company == "腾讯"
    assert events[0].evidence_coverage == 1.0

    assert len(questions) == 2
    real_questions = [q for q in questions if q.source_type == "real_interview"]
    assert len(real_questions) == 1
    assert real_questions[0].question_text == "请解释红黑树的性质"

    assert len(evidences) == 1
    assert evidences[0].quote == evidence_quote
    assert evidences[0].source_document_id == doc.id
    assert evidences[0].start_offset == full_text.find(evidence_quote)


@pytest.mark.asyncio
async def test_extract_interview_handles_llm_error_payload(db_session):
    doc = SourceDocumentModel(
        id=str(uuid.uuid4()),
        source="nowcoder",
        source_url="https://nowcoder.com/discuss/error",
        full_text="这是一段足够长的面经文本，用于触发 LLM 抽取流程。" * 3,
        extraction_status="pending",
    )
    db_session.add(doc)
    await db_session.flush()

    with (
        patch.object(structured_extract, "EXTRACTION_PROMPT", _TEST_EXTRACTION_PROMPT),
        patch("app.llm.structured_extract.llm_client") as mock_llm,
    ):
        mock_llm.chat_json = AsyncMock(return_value={"error": "LLM failed", "confidence": 0})
        result = await extract_interview(db_session, doc)

    assert result["status"] == "failed"
    assert result["error"] == "LLM failed"
    assert doc.extraction_status == "failed"


@pytest.mark.asyncio
async def test_extract_interview_handles_empty_events(db_session):
    doc = SourceDocumentModel(
        id=str(uuid.uuid4()),
        source="nowcoder",
        source_url="https://nowcoder.com/discuss/no-events",
        full_text="这是一段足够长的面经文本，但模型没有抽到任何事件。" * 3,
        extraction_status="pending",
    )
    db_session.add(doc)
    await db_session.flush()

    with (
        patch.object(structured_extract, "EXTRACTION_PROMPT", _TEST_EXTRACTION_PROMPT),
        patch("app.llm.structured_extract.llm_client") as mock_llm,
    ):
        mock_llm.chat_json = AsyncMock(return_value={"events": []})
        result = await extract_interview(db_session, doc)

    assert result == {"status": "extracted", "event_count": 0, "question_count": 0}
    assert doc.extraction_status == "extracted"
    assert doc.extraction_confidence == 0.0

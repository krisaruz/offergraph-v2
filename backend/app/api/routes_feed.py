"""Feed 详情 API + 搜索会话 API + 公司画像 API + 流式搜索 SSE"""

import json
import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import SourceAdapter
from app.database import get_db
from app.models.search_session import SearchSession
from app.models.tool_run import ToolRun
from app.models.source_document import SourceDocumentModel
from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.evidence import QuestionEvidence
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.streaming_coordinator import StreamingCoordinator
from app.schemas.feed import (
    FeedItem,
    FeedSearchRequest,
    FeedSearchResponse,
    QualityReport,
    SearchSessionResponse,
)
from app.services.company_profile_service import CompanyProfileService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feed", tags=["feed"])


def _get_adapters() -> Dict[str, SourceAdapter]:
    from app.adapters import get_registered_adapters
    return get_registered_adapters()


@router.get("/cached")
async def feed_cached(
    db: AsyncSession = Depends(get_db),
    company: str = None,
    position: str = None,
    limit: int = 20,
):
    """从数据库返回已有的面经数据（无需外部搜索）"""
    from sqlalchemy.orm import selectinload

    conditions = []
    if company:
        conditions.append(SourceDocumentModel.title.contains(company))

    # 优化：使用 selectinload 批量加载关联数据，避免 N+1 查询
    stmt = select(SourceDocumentModel).where(
        SourceDocumentModel.extraction_status == "extracted"
    )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(SourceDocumentModel.fetched_at.desc()).limit(limit)

    result = await db.execute(stmt)
    docs = result.scalars().all()

    # 批量查询所有关联的 events
    doc_ids = [doc.id for doc in docs]
    events_stmt = select(InterviewEvent).where(
        InterviewEvent.source_document_id.in_(doc_ids)
    )
    events_result = await db.execute(events_stmt)
    all_events = events_result.scalars().all()

    # 按 doc_id 分组 events
    events_by_doc = {}
    for event in all_events:
        events_by_doc.setdefault(event.source_document_id, []).append(event)

    # 批量查询所有关联的 questions
    event_ids = [event.id for event in all_events]
    questions_by_event = {}
    if event_ids:
        questions_stmt = select(InterviewQuestion).where(
            InterviewQuestion.interview_event_id.in_(event_ids)
        )
        questions_result = await db.execute(questions_stmt)
        all_questions = questions_result.scalars().all()

        for q in all_questions:
            questions_by_event.setdefault(q.interview_event_id, []).append(q)

    # 组装结果
    items = []
    total_questions = 0
    confidence_sum = 0.0
    confidence_count = 0

    for doc in docs:
        events = events_by_doc.get(doc.id, [])
        company_name = events[0].company if events else None
        position_name = events[0].position if events else None
        difficulty = events[0].difficulty if events else None

        event_question_count = 0
        for event in events:
            event_question_count += len(questions_by_event.get(event.id, []))

        total_questions += event_question_count

        if doc.extraction_confidence:
            confidence_sum += doc.extraction_confidence
            confidence_count += 1

        items.append({
            "id": doc.id,
            "source": doc.source,
            "sourceUrl": doc.source_url,
            "title": doc.title,
            "snippet": doc.snippet[:200] if doc.snippet else "",
            "company": company_name,
            "position": position_name,
            "difficulty": difficulty,
            "trustLabel": "high" if doc.extraction_confidence and doc.extraction_confidence > 0.7 else "medium",
            "hasFullText": bool(doc.full_text),
            "finalScore": doc.extraction_confidence or 0.0,
            "fetchedAt": doc.fetched_at.isoformat() if doc.fetched_at else None,
            "eventCount": len(events),
            "questionCount": event_question_count,
        })

    avg_confidence = (confidence_sum / confidence_count) if confidence_count > 0 else None

    return {
        "items": items,
        "total": len(items),
        "source": "database_cache",
        "cachedCount": len(items),
        "freshCount": 0,
        "totalQuestions": total_questions,
        "avgConfidence": avg_confidence,
    }


@router.post("/search", response_model=FeedSearchResponse)
async def feed_search(
    request: FeedSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """基于用户画像执行面试情报搜索"""
    profile = {
        "identity": request.identity,
        "directions": request.directions,
        "target_companies": request.target_companies,
        "regions": request.regions or [],
        "custom_needs": request.custom_needs or "",
    }

    adapters = _get_adapters()
    runtime = AgentRuntime(db=db, adapters=adapters)
    result = await runtime.run_search(profile)

    items = [
        FeedItem(
            source=item.get("source", ""),
            source_url=item.get("source_url", ""),
            title=item.get("title"),
            snippet=item.get("snippet"),
            published_at=item.get("published_at"),
            trust_label=item.get("trust_label"),
            has_full_text=item.get("has_full_text", False),
            final_score=item.get("final_score"),
        )
        for item in result.get("items", [])
    ]

    quality = result.get("qualityReport", {})

    return FeedSearchResponse(
        sessionId=result["sessionId"],
        status=result["status"],
        items=items,
        total=result["total"],
        sourcesStatus=result.get("sourcesStatus", {}),
        cachedCount=result.get("cachedCount", 0),
        freshCount=result.get("freshCount", 0),
        searchDuration=result.get("searchDuration", 0),
        qualityReport=QualityReport(
            filteredCount=quality.get("filteredCount", 0),
            duplicateCount=quality.get("duplicateCount", 0),
            hookWarnings=quality.get("hookWarnings", []),
            evidenceCoverageAvg=quality.get("evidenceCoverageAvg"),
            fetchedCount=quality.get("fetchedCount", 0),
        ),
        error=result.get("error"),
    )


@router.get("/detail/{source_document_id}")
async def feed_detail(
    source_document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取 Feed 详情：展示结构化面试问题 + 证据引用。
    """
    # 获取 source_document
    stmt = select(SourceDocumentModel).where(SourceDocumentModel.id == source_document_id)
    result = await db.execute(stmt)
    source_doc = result.scalar_one_or_none()

    if not source_doc:
        raise HTTPException(status_code=404, detail="Source document not found")

    # 批量查询所有关联的 events
    events_stmt = select(InterviewEvent).where(
        InterviewEvent.source_document_id == source_document_id
    )
    events_result = await db.execute(events_stmt)
    events = events_result.scalars().all()

    # 批量查询所有关联的 questions
    event_ids = [event.id for event in events]
    questions_by_event = {}
    if event_ids:
        questions_stmt = select(InterviewQuestion).where(
            InterviewQuestion.interview_event_id.in_(event_ids)
        )
        questions_result = await db.execute(questions_stmt)
        all_questions = questions_result.scalars().all()

        for q in all_questions:
            questions_by_event.setdefault(q.interview_event_id, []).append(q)

    # 批量查询所有关联的 evidences
    question_ids = [q.id for q in all_questions]
    evidences_by_question = {}
    if question_ids:
        evidences_stmt = select(QuestionEvidence).where(
            QuestionEvidence.question_id.in_(question_ids)
        )
        evidences_result = await db.execute(evidences_stmt)
        all_evidences = evidences_result.scalars().all()

        for ev in all_evidences:
            evidences_by_question.setdefault(ev.question_id, []).append(ev)

    # 组装结果
    structured_events = []
    for event in events:
        questions = questions_by_event.get(event.id, [])

        structured_questions = []
        for q in questions:
            evidences = evidences_by_question.get(q.id, [])
            evidence_data = None
            if evidences:
                ev = evidences[0]
                evidence_data = {
                    "quote": ev.quote,
                    "confidence": ev.confidence,
                    "sourceUrl": source_doc.source_url,
                }

            followups = []
            if q.followups_json:
                try:
                    followups = json.loads(q.followups_json)
                except json.JSONDecodeError:
                    pass

            tags = []
            if q.tags_json:
                try:
                    tags = json.loads(q.tags_json)
                except json.JSONDecodeError:
                    pass

            structured_questions.append({
                "id": q.id,
                "text": q.question_text,
                "category": q.category,
                "difficulty": q.difficulty,
                "sourceType": q.source_type,
                "confidence": q.confidence,
                "evidence": evidence_data,
                "followUps": followups,
                "tags": tags,
            })

        event_tags = []
        if event.tags_json:
            try:
                event_tags = json.loads(event.tags_json)
            except json.JSONDecodeError:
                pass

        structured_events.append({
            "id": event.id,
            "company": event.company,
            "position": event.position,
            "candidateType": event.candidate_type,
            "round": event.round,
            "region": event.region,
            "summary": event.summary,
            "difficulty": event.difficulty,
            "evidenceCoverage": event.evidence_coverage,
            "tags": event_tags,
            "questions": structured_questions,
        })

    return {
        "id": source_doc.id,
        "source": source_doc.source,
        "sourceUrl": source_doc.source_url,
        "title": source_doc.title,
        "snippet": source_doc.snippet,
        "extractionStatus": source_doc.extraction_status,
        "extractionConfidence": source_doc.extraction_confidence,
        "fetchedAt": source_doc.fetched_at.isoformat() if source_doc.fetched_at else None,
        "structured": {
            "events": structured_events,
        },
    }


@router.post("/search/stream")
async def feed_search_stream(
    request: FeedSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """基于用户画像执行面试情报搜索（SSE 流式输出）。

    事件类型:
      session_created, phase_start, query_plan_ready, phase_completed,
      search_started, source_results, source_completed, source_error, source_timeout,
      ranking_completed, fetch_completed, extract_completed, search_completed, search_error
    """
    profile = {
        "identity": request.identity,
        "directions": request.directions,
        "target_companies": request.target_companies,
        "regions": request.regions or [],
        "custom_needs": request.custom_needs or "",
    }

    adapters = _get_adapters()
    coordinator = StreamingCoordinator(db=db, adapters=adapters)

    async def event_generator():
        try:
            async for sse_chunk in coordinator.run_stream(profile):
                yield sse_chunk
        finally:
            await db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/search-sessions/{session_id}", response_model=SearchSessionResponse)
async def get_search_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取搜索会话详情，包含运行轨迹"""
    stmt = select(SearchSession).where(SearchSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    runs_stmt = select(ToolRun).where(ToolRun.session_id == session_id)
    runs_result = await db.execute(runs_stmt)
    tool_runs = runs_result.scalars().all()

    tool_runs_data = [
        {
            "id": run.id,
            "toolName": run.tool_name,
            "toolType": run.tool_type,
            "status": run.status,
            "durationMs": run.duration_ms,
            "errorMessage": run.error_message,
            "startedAt": run.started_at.isoformat() if run.started_at else None,
            "endedAt": run.ended_at.isoformat() if run.ended_at else None,
        }
        for run in tool_runs
    ]

    return SearchSessionResponse(
        id=session.id,
        status=session.status,
        profileSnapshot=json.loads(session.profile_snapshot_json) if session.profile_snapshot_json else None,
        queryPlan=json.loads(session.query_plan_json) if session.query_plan_json else None,
        sourceStatus=json.loads(session.source_status_json) if session.source_status_json else None,
        toolRuns=tool_runs_data,
        qualityReport=json.loads(session.quality_report_json) if session.quality_report_json else None,
        createdAt=session.created_at.isoformat() if session.created_at else None,
    )

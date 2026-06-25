"""End-to-end reasoning checks for source-specific Feed conclusions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import select

import app.llm.structured_extract as structured_extract
import app.runtime.streaming_coordinator as streaming_module
from app.adapters.base import SourceDocument, SourceSearchItem
from app.models.source_document import SourceDocumentModel
from app.runtime.source_health import SourceHealthRegistry
from app.runtime.streaming_coordinator import StreamingCoordinator
from app.services.feed_summary_service import build_feed_summary
from tests.conftest import MockSourceAdapter


def _parse_sse(chunk: str) -> tuple[str, dict[str, Any]] | None:
    event_type = ""
    data_lines: list[str] = []
    for raw_line in chunk.splitlines():
        line = raw_line.strip()
        if line.startswith("event:"):
            event_type = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())

    if not event_type or not data_lines:
        return None
    return event_type, json.loads("\n".join(data_lines))


class _ReusableSessionContext:
    """Give StreamingCoordinator isolated-session call sites the test session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _interview_item(source: str, url: str, title: str, snippet: str) -> SourceSearchItem:
    return SourceSearchItem(
        source=source,
        source_url=url,
        title=title,
        snippet=snippet,
        published_at=datetime.utcnow().isoformat(),
    )


def _document(source: str, url: str, title: str, text: str) -> SourceDocument:
    return SourceDocument(
        source=source,
        source_url=url,
        title=title,
        snippet=text[:120],
        full_text=text,
        content_hash=f"hash-{source}-{abs(hash(url))}",
    )


def _llm_payload(
    *,
    company: str,
    position: str,
    question: str,
    evidence_quote: str,
    category: str,
    tags: list[str],
) -> dict[str, Any]:
    return {
        "events": [
            {
                "company": company,
                "position": position,
                "candidate_type": "social",
                "round": "一面",
                "interview_date": None,
                "region": "北京",
                "summary": f"{company}{position}一面，问题集中在{tags[0]}。",
                "difficulty": 3,
                "tags": tags,
                "confidence": 0.92,
                "questions": [
                    {
                        "text": question,
                        "category": category,
                        "difficulty": 3,
                        "tags": tags,
                        "followups": [],
                        "source_type": "real_interview",
                        "evidence_quote": evidence_quote,
                        "confidence": 0.9,
                    }
                ],
            }
        ]
    }


def _mock_llm_stream(payload: dict[str, Any]):
    async def _chat_stream(*_args, **_kwargs):
        raw = json.dumps(payload, ensure_ascii=False)
        midpoint = max(len(raw) // 2, 1)
        yield raw[:midpoint]
        yield raw[midpoint:]

    return _chat_stream


async def _unexpected_llm_stream(*_args, **_kwargs):
    raise AssertionError("LLM should not be called for non-interview content")
    yield ""


async def _run_stream_case(
    db_session,
    monkeypatch,
    adapter: MockSourceAdapter,
    *,
    llm_payload: dict[str, Any] | None,
    target_companies: list[str],
    directions: list[str],
) -> list[tuple[str, dict[str, Any]]]:
    monkeypatch.setattr(
        streaming_module,
        "async_session_factory",
        lambda: _ReusableSessionContext(db_session),
    )
    monkeypatch.setattr(
        structured_extract.llm_client,
        "chat_stream",
        _mock_llm_stream(llm_payload) if llm_payload is not None else _unexpected_llm_stream,
    )

    coordinator = StreamingCoordinator(
        db_session,
        {adapter.id: adapter},
        source_health_registry=SourceHealthRegistry(),
    )

    events: list[tuple[str, dict[str, Any]]] = []
    async for chunk in coordinator.run_stream(
        {
            "identity": "working_switch",
            "target_companies": target_companies,
            "directions": directions,
            "regions": ["北京"],
        }
    ):
        parsed = _parse_sse(chunk)
        if parsed:
            events.append(parsed)
    return events


def _events(events: list[tuple[str, dict[str, Any]]], event_type: str) -> list[dict[str, Any]]:
    return [data for current_type, data in events if current_type == event_type]


async def _summary_for_doc(db_session, source_document_id: str) -> dict[str, Any]:
    result = await db_session.execute(
        select(SourceDocumentModel).where(SourceDocumentModel.id == source_document_id)
    )
    source_doc = result.scalar_one()
    return await build_feed_summary(db_session, source_doc)


async def _assert_extracted_conclusion(
    db_session,
    events: list[tuple[str, dict[str, Any]]],
    *,
    expected_company: str,
    expected_position: str,
    expected_question: str,
    expected_evidence: str,
):
    extract_events = _events(events, "extract_completed")
    assert extract_events
    latest = extract_events[-1]
    assert latest["status"] == "extracted"
    assert latest["question_count"] == 1
    assert latest["representative_questions"]
    assert latest["representative_questions"][0]["text"] == expected_question
    assert latest["representative_questions"][0]["evidence_quote"] == expected_evidence

    summary = await _summary_for_doc(db_session, latest["source_document_id"])
    assert summary["company"] == expected_company
    assert summary["position"] == expected_position
    assert summary["question_count"] == 1
    assert summary["evidence_count"] == 1
    assert summary["representative_questions"][0]["text"] == expected_question
    assert summary["representative_questions"][0]["evidence_quote"] == expected_evidence


@pytest.mark.asyncio
async def test_nowcoder_source_e2e_outputs_evidenced_feed_summary(db_session, monkeypatch):
    source = "nowcoder"
    url = "https://www.nowcoder.com/discuss/1001"
    evidence = "面试官问了 Redis 缓存一致性如何保证"
    question = "Redis 缓存一致性如何保证？"
    text = (
        "阿里巴巴后端一面面经。"
        f"{evidence}，还追问了数据库事务隔离级别和索引优化，整体偏社招。"
    )
    adapter = MockSourceAdapter(
        adapter_id=source,
        search_results=[
            _interview_item(
                source,
                "https://www.nowcoder.com/discuss/off-target",
                "百度大模型一面-实习面经",
                "百度大模型实习面经，面试官问了 RAG、Agent 和评测。",
            ),
            _interview_item(source, url, "阿里巴巴 后端 社招 一面面经", text),
        ],
        fetch_document=_document(source, url, "阿里巴巴 后端 社招 一面面经", text),
    )

    events = await _run_stream_case(
        db_session,
        monkeypatch,
        adapter,
        llm_payload=_llm_payload(
            company="阿里巴巴",
            position="后端开发",
            question=question,
            evidence_quote=evidence,
            category="system_design",
            tags=["Redis", "缓存一致性"],
        ),
        target_companies=["阿里巴巴"],
        directions=["后端开发"],
    )

    ranked = _events(events, "ranking_completed")[-1]["final_items"]
    assert [item["source_url"] for item in ranked] == [url]

    await _assert_extracted_conclusion(
        db_session,
        events,
        expected_company="阿里巴巴",
        expected_position="后端开发",
        expected_question=question,
        expected_evidence=evidence,
    )


@pytest.mark.asyncio
async def test_maimai_source_e2e_outputs_evidenced_feed_summary(db_session, monkeypatch):
    source = "maimai"
    url = "https://maimai.cn/article/2002"
    evidence = "面试官问如何设计订单系统的幂等和补偿流程"
    question = "如何设计订单系统的幂等和补偿流程？"
    text = (
        "腾讯后端社招面经，一面主要围绕项目和系统设计。"
        f"{evidence}，继续追问消息队列重复消费和数据库事务。"
    )
    adapter = MockSourceAdapter(
        adapter_id=source,
        search_results=[_interview_item(source, url, "腾讯 后端 社招 一面 面经", text)],
        fetch_document=_document(source, url, "腾讯 后端 社招 一面 面经", text),
    )

    events = await _run_stream_case(
        db_session,
        monkeypatch,
        adapter,
        llm_payload=_llm_payload(
            company="腾讯",
            position="后端开发",
            question=question,
            evidence_quote=evidence,
            category="system_design",
            tags=["幂等", "消息队列"],
        ),
        target_companies=["腾讯"],
        directions=["后端开发"],
    )

    await _assert_extracted_conclusion(
        db_session,
        events,
        expected_company="腾讯",
        expected_position="后端开发",
        expected_question=question,
        expected_evidence=evidence,
    )


@pytest.mark.asyncio
async def test_xiaohongshu_source_e2e_outputs_evidenced_feed_summary(db_session, monkeypatch):
    source = "xiaohongshu"
    url = "https://www.xiaohongshu.com/explore/3003"
    evidence = "面试官问接口自动化用例失败时如何定位是环境问题还是代码问题"
    question = "接口自动化用例失败时如何定位是环境问题还是代码问题？"
    text = (
        "小红书笔记：Kimi 自动化测试一面面经。"
        f"{evidence}，还聊到质量平台、用例分层和失败重试策略。"
    )
    adapter = MockSourceAdapter(
        adapter_id=source,
        search_results=[_interview_item(source, url, "Kimi 自动化测试 一面面经", text)],
        fetch_document=_document(source, url, "Kimi 自动化测试 一面面经", text),
    )

    events = await _run_stream_case(
        db_session,
        monkeypatch,
        adapter,
        llm_payload=_llm_payload(
            company="Kimi",
            position="自动化测试",
            question=question,
            evidence_quote=evidence,
            category="project",
            tags=["接口自动化", "质量平台"],
        ),
        target_companies=["Kimi"],
        directions=["自动化测试"],
    )

    await _assert_extracted_conclusion(
        db_session,
        events,
        expected_company="Kimi",
        expected_position="自动化测试",
        expected_question=question,
        expected_evidence=evidence,
    )


@pytest.mark.asyncio
async def test_search_engine_e2e_filters_product_page_and_outputs_interview_summary(db_session, monkeypatch):
    source = "search_engine"
    product_url = "https://www.kimi.com/k2"
    interview_url = "https://example.com/kimi-eval-interview"
    evidence = "面试官问如何设计大模型 Eval 的数据集版本管理"
    question = "如何设计大模型 Eval 的数据集版本管理？"
    text = (
        "Kimi 大模型 Eval 评测方向面经。"
        f"{evidence}，后续追问评测指标、坏例归因和线上回归。"
    )
    adapter = MockSourceAdapter(
        adapter_id=source,
        search_results=[
            _interview_item(
                source,
                product_url,
                "Kimi AI with K2.6 | Better Coding, Smarter Agents",
                "Try Kimi K2.6 to build full-stack websites and use Agent Swarm.",
            ),
            _interview_item(
                source,
                interview_url,
                "Kimi 大模型 Eval 一面面经",
                text,
            ),
        ],
        fetch_document=_document(source, interview_url, "Kimi 大模型 Eval 一面面经", text),
    )

    events = await _run_stream_case(
        db_session,
        monkeypatch,
        adapter,
        llm_payload=_llm_payload(
            company="Kimi",
            position="大模型 Eval",
            question=question,
            evidence_quote=evidence,
            category="ai",
            tags=["大模型", "Eval"],
        ),
        target_companies=["Kimi"],
        directions=["大模型 Eval"],
    )

    ranked = _events(events, "ranking_completed")[-1]["final_items"]
    assert [item["source_url"] for item in ranked] == [interview_url]
    assert product_url not in {item["source_url"] for item in ranked}

    await _assert_extracted_conclusion(
        db_session,
        events,
        expected_company="Kimi",
        expected_position="大模型 Eval",
        expected_question=question,
        expected_evidence=evidence,
    )


@pytest.mark.asyncio
async def test_official_job_e2e_skips_question_extraction_for_jd(db_session, monkeypatch):
    source = "official_job"
    url = "https://talent.example.com/kimi/eval"
    text = (
        "职位名称：大模型 Eval 评测工程师。岗位职责：建设评测数据集、"
        "维护评测平台、分析模型效果。任职要求：熟悉 Python、数据分析和质量评估，"
        "具备良好的工程协作能力。"
    )
    adapter = MockSourceAdapter(
        adapter_id=source,
        search_results=[
            _interview_item(source, url, "Kimi 大模型 Eval 评测工程师招聘", text)
        ],
        fetch_document=_document(source, url, "Kimi 大模型 Eval 评测工程师招聘", text),
    )

    events = await _run_stream_case(
        db_session,
        monkeypatch,
        adapter,
        llm_payload=None,
        target_companies=["Kimi"],
        directions=["大模型 Eval"],
    )

    extract_events = _events(events, "extract_completed")
    assert extract_events
    latest = extract_events[-1]
    assert latest["status"] == "skipped"
    assert latest["question_count"] == 0
    assert latest["representative_questions"] == []
    assert not _events(events, "llm_chunk")

    summary = await _summary_for_doc(db_session, latest["source_document_id"])
    assert summary["question_count"] == 0
    assert summary["representative_questions"] == []

    result = await db_session.execute(
        select(SourceDocumentModel).where(SourceDocumentModel.id == latest["source_document_id"])
    )
    source_doc = result.scalar_one()
    assert source_doc.source == "official_job"
    assert source_doc.extraction_status == "skipped"

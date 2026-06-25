"""Tests for the SSE streaming search coordinator."""

import json
from datetime import datetime, timedelta

import pytest

from app.adapters.base import SourceSearchItem
import app.runtime.streaming_coordinator as streaming_module
from app.runtime.streaming_coordinator import StreamingCoordinator
from tests.conftest import MockSourceAdapter


def _parse_sse(chunk: str) -> tuple[str, dict] | None:
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


@pytest.mark.asyncio
async def test_streaming_source_results_filter_expired_candidates(db_session):
    recent = SourceSearchItem(
        source="mock_source",
        source_url="https://example.com/recent",
        title="阿里巴巴 后端 社招 面经",
        snippet="近期一面二面问题记录",
        published_at=(datetime.utcnow() - timedelta(days=7)).isoformat(),
    )
    expired = SourceSearchItem(
        source="mock_source",
        source_url="https://example.com/expired",
        title="阿里巴巴 后端 旧面经",
        snippet="很久以前的面试记录",
        published_at=(datetime.utcnow() - timedelta(days=400)).isoformat(),
    )
    coordinator = StreamingCoordinator(
        db_session,
        {
            "mock_source": MockSourceAdapter(
                adapter_id="mock_source",
                search_results=[expired, recent],
            )
        },
    )

    events: list[tuple[str, dict]] = []
    async for chunk in coordinator.run_stream(
        {
            "identity": "working_switch",
            "target_companies": ["阿里巴巴"],
            "directions": ["后端开发"],
        }
    ):
        parsed = _parse_sse(chunk)
        if parsed:
            events.append(parsed)

    source_results = [
        data for event_type, data in events if event_type == "source_results"
    ]
    assert source_results
    assert [
        item["source_url"] for item in source_results[0]["items"]
    ] == ["https://example.com/recent"]

    ranking_events = [
        data for event_type, data in events if event_type == "ranking_completed"
    ]
    assert ranking_events
    assert [
        item["source_url"] for item in ranking_events[0]["final_items"]
    ] == ["https://example.com/recent"]


@pytest.mark.asyncio
async def test_streaming_source_results_filter_non_interview_search_engine_candidates(db_session):
    product_page = SourceSearchItem(
        source="search_engine",
        source_url="https://www.kimi.com/k2",
        title="Kimi AI with K2.6 | Better Coding, Smarter Agents",
        snippet="Try Kimi K2.6 to build full-stack websites and use Agent Swarm.",
        published_at=datetime.utcnow().isoformat(),
    )
    real_interview = SourceSearchItem(
        source="search_engine",
        source_url="https://example.com/kimi-interview",
        title="Kimi 自动化测试 面经",
        snippet="面试官问了自动化框架、接口测试和质量平台建设。",
        published_at=datetime.utcnow().isoformat(),
    )
    coordinator = StreamingCoordinator(
        db_session,
        {
            "search_engine": MockSourceAdapter(
                adapter_id="search_engine",
                search_results=[product_page, real_interview],
            )
        },
    )

    events: list[tuple[str, dict]] = []
    async for chunk in coordinator.run_stream(
        {
            "identity": "working_switch",
            "target_companies": ["kimi"],
            "directions": ["自动化测试"],
        }
    ):
        parsed = _parse_sse(chunk)
        if parsed:
            events.append(parsed)

    source_results = [
        data for event_type, data in events if event_type == "source_results"
    ]
    assert source_results
    assert [
        item["source_url"] for item in source_results[0]["items"]
    ] == ["https://example.com/kimi-interview"]


@pytest.mark.asyncio
async def test_extract_failure_emits_terminal_status(db_session, source_document, monkeypatch):
    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _raise_extract_error(**kwargs):
        raise RuntimeError("llm unavailable")

    import app.llm.structured_extract as structured_extract

    monkeypatch.setattr(streaming_module, "async_session_factory", lambda: _SessionContext())
    monkeypatch.setattr(structured_extract, "extract_interview_streaming", _raise_extract_error)

    coordinator = StreamingCoordinator(db_session, {})
    events: list[tuple[str, dict]] = []

    await coordinator._extract_doc_task_isolated(
        "session-test",
        source_document.id,
        0,
        1,
        lambda event_type, data: events.append((event_type, data)),
    )

    extract_events = [data for event_type, data in events if event_type == "extract_completed"]
    assert extract_events
    assert extract_events[-1]["status"] == "failed"
    assert extract_events[-1]["extraction_status"] == "failed"
    assert extract_events[-1]["question_count"] == 0

    await db_session.refresh(source_document)
    assert source_document.extraction_status == "failed"

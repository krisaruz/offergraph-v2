"""Tests for FastAPI route handlers."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.base import SourceSearchResult
from app.runtime.agent_runtime import AgentRuntime


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "offergraph-agent-runtime"


@pytest.mark.asyncio
async def test_feed_search_with_mock_runtime(client):
    mock_result = {
        "sessionId": "session-123",
        "status": "success",
        "items": [
            {
                "source": "nowcoder",
                "source_url": "https://nowcoder.com/discuss/1",
                "title": "字节 后端 面经",
                "snippet": "一面算法题",
                "published_at": datetime.utcnow().isoformat(),
                "trust_label": "真实来源 / 近期内容",
                "has_full_text": True,
                "final_score": 0.82,
            }
        ],
        "total": 1,
        "sourcesStatus": {"mock_source": "ok"},
        "cachedCount": 0,
        "freshCount": 1,
        "searchDuration": 120,
        "qualityReport": {
            "filteredCount": 0,
            "duplicateCount": 0,
            "hookWarnings": [],
            "fetchedCount": 1,
        },
    }

    with patch.object(AgentRuntime, "run_search", new=AsyncMock(return_value=mock_result)):
        response = await client.post(
            "/api/feed/search",
            json={
                "identity": "working_switch",
                "directions": ["后端开发"],
                "target_companies": ["字节跳动"],
                "regions": ["北京"],
                "custom_needs": "系统设计",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["sessionId"] == "session-123"
    assert data["status"] == "success"
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["source"] == "nowcoder"
    assert data["qualityReport"]["fetchedCount"] == 1


@pytest.mark.asyncio
async def test_feed_search_integration_with_mock_adapter(client, mock_adapters):
    with (
        patch("app.api.routes_feed._get_adapters", return_value=mock_adapters),
        patch("app.llm.structured_extract.llm_client") as mock_llm,
    ):
        mock_llm.chat_json = AsyncMock(return_value={"events": []})

        response = await client.post(
            "/api/feed/search",
            json={
                "identity": "student_autumn",
                "directions": ["后端"],
                "target_companies": ["字节跳动"],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"success", "partial_success"}
    assert data["total"] >= 1
    assert data["items"][0]["source_url"].startswith("https://")


@pytest.mark.asyncio
async def test_feed_detail_returns_structured_data(client, extracted_feed_detail):
    doc_id = extracted_feed_detail["source_document_id"]

    response = await client.get(f"/api/feed/detail/{doc_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["source"] == "nowcoder"
    assert data["structured"]["events"]
    event = data["structured"]["events"][0]
    assert event["company"] == "腾讯"
    assert event["questions"]
    question = event["questions"][0]
    assert question["text"] == "请解释红黑树的性质"
    assert question["evidence"]["quote"] == "面试官问了红黑树和项目架构"


@pytest.mark.asyncio
async def test_feed_detail_not_found(client):
    response = await client.get(f"/api/feed/detail/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source document not found"


@pytest.mark.asyncio
async def test_company_profile_insufficient_data(client):
    response = await client.get("/api/company-profile/不存在公司")

    assert response.status_code == 200
    data = response.json()
    assert data["company"] == "不存在公司"
    assert data["sufficient_data"] is False
    assert data["event_count"] == 0


@pytest.mark.asyncio
async def test_company_profile_with_sufficient_data(db_session, client):
    import json

    from app.models.evidence import QuestionEvidence
    from app.models.interview_event import InterviewEvent
    from app.models.question import InterviewQuestion
    from app.models.source_document import SourceDocumentModel

    company = "高可信测试公司"

    for index in range(5):
        doc_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        question_id = str(uuid.uuid4())

        doc = SourceDocumentModel(
            id=doc_id,
            source="nowcoder",
            source_url=f"https://nowcoder.com/discuss/profile-{index}",
            title=f"{company} 面经 {index}",
            full_text="面经内容" * 20,
            fetched_at=datetime.utcnow(),
        )
        event = InterviewEvent(
            id=event_id,
            source_document_id=doc_id,
            company=company,
            position="后端",
            candidate_type="campus",
            summary="summary",
            difficulty=3,
            evidence_coverage=0.9,
        )
        question = InterviewQuestion(
            id=question_id,
            interview_event_id=event_id,
            question_text=f"问题{index % 2}",
            normalized_question=f"问题{index % 2}",
            category="algorithm",
            source_type="real_interview",
            confidence=0.9,
            difficulty=3,
        )
        evidence = QuestionEvidence(
            id=str(uuid.uuid4()),
            question_id=question_id,
            source_document_id=doc_id,
            quote=f"证据{index}",
            confidence=0.9,
        )

        db_session.add_all([doc, event, question, evidence])

    await db_session.flush()

    response = await client.get(
        f"/api/company-profile/{company}",
        params={"position": "后端", "candidateType": "campus"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["sufficient_data"] is True
    assert data["eventCount"] == 5
    assert data["questionCount"] == 5
    assert data["highFreqQuestions"]
    assert data["categoryDistribution"]["algorithm"] == 5

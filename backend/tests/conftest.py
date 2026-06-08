"""Shared pytest fixtures for OfferGraph v2 backend tests."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.base import SourceAdapter, SourceDocument, SourceQuery, SourceSearchResult
from app.config import Settings
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Override application settings for the test environment."""
    return Settings(
        database_url=TEST_DATABASE_URL,
        search_api_key="",
        nowcoder_enabled=False,
        maimai_enabled=False,
        xhs_enabled=False,
        search_timeout_platform=1,
        search_timeout_search_engine=1,
        webfetch_timeout=1,
        webfetch_max_urls=3,
        llm_api_base="http://test-llm.local/api/v3",
        llm_api_key="test-key",
        llm_model="test/model",
        llm_gateway_uid="test-uid",
        llm_gateway_product="test-product",
        llm_gateway_intention="test-intention",
        host="127.0.0.1",
        port=8000,
    )


@pytest_asyncio.fixture
async def test_engine(test_settings: Settings):
    """Create an in-memory SQLite async engine and schema."""
    engine = create_async_engine(test_settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session rolled back after each test."""
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLM client with async chat methods."""
    client = MagicMock()
    client.chat = AsyncMock(return_value="mock response")
    client.chat_json = AsyncMock(return_value={"events": []})
    client.chat_stream = AsyncMock()
    return client


class MockSourceAdapter(SourceAdapter):
    """Minimal source adapter for runtime/API tests."""

    def __init__(
        self,
        adapter_id: str = "mock_source",
        search_results: list[SourceSearchResult] | None = None,
        fetch_document: SourceDocument | None = None,
    ):
        self.id = adapter_id
        self.display_name = f"Mock {adapter_id}"
        self._search_results = search_results or []
        self._fetch_document = fetch_document

    @property
    def capabilities(self) -> dict:
        return {"search": True, "fetch": self._fetch_document is not None}

    async def search(self, query: SourceQuery) -> list[SourceSearchResult]:
        return self._search_results

    async def fetch(self, url: str) -> SourceDocument | None:
        return self._fetch_document


@pytest.fixture
def mock_adapter() -> MockSourceAdapter:
    """Adapter returning a single interview search result."""
    return MockSourceAdapter(
        adapter_id="mock_source",
        search_results=[
            SourceSearchResult(
                source="mock_source",
                source_url="https://example.com/interview/1",
                title="字节跳动 后端 一面 面经",
                snippet="面试官问了算法题和项目经历，整体难度中等。",
                published_at=datetime.utcnow().isoformat(),
            )
        ],
        fetch_document=SourceDocument(
            source="mock_source",
            source_url="https://example.com/interview/1",
            title="字节跳动 后端 一面 面经",
            snippet="面试官问了算法题",
            full_text=(
                "今天参加了字节跳动后端一面，面试官问了算法题和项目经历，"
                "还追问了分布式系统设计，整体是标准校招面经。"
            ),
            content_hash="abc123",
        ),
    )


@pytest.fixture
def mock_adapters(mock_adapter: MockSourceAdapter) -> dict[str, SourceAdapter]:
    return {mock_adapter.id: mock_adapter}


@pytest_asyncio.fixture
async def test_app(db_session: AsyncSession, test_settings: Settings):
    """FastAPI app with overridden DB dependency and test settings."""
    import app.config as config_module

    config_module.settings = test_settings

    from app.main import app as fastapi_app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for API route tests."""
    async with test_app.router.lifespan_context(test_app):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def source_document(db_session: AsyncSession) -> "SourceDocumentModel":
    """Persist a source document with extractable interview text."""
    from app.models.source_document import SourceDocumentModel

    doc = SourceDocumentModel(
        id=str(uuid.uuid4()),
        source="nowcoder",
        source_url="https://nowcoder.com/discuss/12345",
        title="腾讯 后端 面经",
        snippet="一面问了红黑树",
        full_text=(
            "腾讯后端一面面经：面试官问了红黑树和项目架构，"
            "还追问了缓存一致性，属于典型校招面经。"
        ),
        extraction_status="pending",
        fetched_at=datetime.utcnow(),
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


@pytest_asyncio.fixture
async def extracted_feed_detail(db_session: AsyncSession, source_document) -> dict:
    """Source document with structured interview event, question, and evidence."""
    import json

    from app.models.evidence import QuestionEvidence
    from app.models.interview_event import InterviewEvent
    from app.models.question import InterviewQuestion

    event_id = str(uuid.uuid4())
    question_id = str(uuid.uuid4())
    evidence_quote = "面试官问了红黑树和项目架构"

    event = InterviewEvent(
        id=event_id,
        source_document_id=source_document.id,
        company="腾讯",
        position="后端",
        candidate_type="campus",
        round="一面",
        summary="红黑树和项目",
        difficulty=3,
        evidence_coverage=1.0,
        tags_json=json.dumps(["算法"], ensure_ascii=False),
    )
    question = InterviewQuestion(
        id=question_id,
        interview_event_id=event_id,
        question_text="请解释红黑树的性质",
        normalized_question="请解释红黑树的性质",
        category="algorithm",
        difficulty=3,
        source_type="real_interview",
        confidence=0.9,
        tags_json=json.dumps(["数据结构"], ensure_ascii=False),
        followups_json=json.dumps(["如何旋转"], ensure_ascii=False),
    )
    evidence = QuestionEvidence(
        id=str(uuid.uuid4()),
        question_id=question_id,
        source_document_id=source_document.id,
        quote=evidence_quote,
        start_offset=source_document.full_text.find(evidence_quote),
        end_offset=source_document.full_text.find(evidence_quote) + len(evidence_quote),
        confidence=0.9,
    )

    db_session.add_all([event, question, evidence])
    await db_session.flush()

    return {
        "source_document_id": source_document.id,
        "event_id": event_id,
        "question_id": question_id,
    }

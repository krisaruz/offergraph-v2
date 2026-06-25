"""Tests for AgentRuntime orchestration edge cases."""

from datetime import datetime, timedelta

import pytest

from app.adapters.base import (
    SourceAdapter,
    SourceDocument,
    SourceQuery,
    SourceSearchItem,
    SourceSearchResult,
    SourceStatus,
)
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.source_health import SourceHealthRegistry


class CountingFetchAdapter(SourceAdapter):
    def __init__(self, adapter_id: str, items: list[SourceSearchItem]):
        self.id = adapter_id
        self.display_name = f"Mock {adapter_id}"
        self.items = items
        self.fetch_calls = 0

    @property
    def capabilities(self) -> dict:
        return {"search": True, "fetch": True}

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        return SourceSearchResult(
            source=self.id,
            status=SourceStatus.OK,
            items=self.items,
            count=len(self.items),
        )


class StatusAdapter(SourceAdapter):
    def __init__(self, adapter_id: str, status: SourceStatus, reason: str | None = None):
        self.id = adapter_id
        self.display_name = f"Mock {adapter_id}"
        self.status = status
        self.reason = reason
        self.search_calls = 0

    @property
    def capabilities(self) -> dict:
        return {"search": True}

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        self.search_calls += 1
        return SourceSearchResult(
            source=self.id,
            status=self.status,
            items=[],
            count=0,
            reason=self.reason,
        )

    async def fetch(self, url: str) -> SourceDocument | None:
        self.fetch_calls += 1
        return SourceDocument(
            source=self.id,
            source_url=url,
            title="should not be fetched",
            full_text="expired content should not reach fetch",
            published_at=(datetime.utcnow() - timedelta(days=400)).isoformat(),
        )


@pytest.mark.asyncio
async def test_runtime_filters_expired_candidates_before_fetch(db_session):
    adapter = CountingFetchAdapter(
        "xiaohongshu",
        [
            SourceSearchItem(
                source="xiaohongshu",
                source_url="https://example.com/expired",
                title="阿里巴巴 后端 旧面经",
                snippet="过期面试记录",
                published_at=(datetime.utcnow() - timedelta(days=400)).isoformat(),
            )
        ]
    )
    runtime = AgentRuntime(db_session, {"xiaohongshu": adapter})

    result = await runtime.run_search(
        {
            "identity": "working_switch",
            "target_companies": ["阿里巴巴"],
            "directions": ["后端开发"],
        }
    )

    assert result["total"] == 0
    assert result["qualityReport"]["expiredFilteredCount"] == 1
    assert result["qualityReport"]["fetchedCount"] == 0
    assert adapter.fetch_calls == 0


@pytest.mark.asyncio
async def test_runtime_enriches_auth_failure_status(db_session):
    adapter = StatusAdapter("maimai", SourceStatus.UNAUTHORIZED, "Cookie expired")
    runtime = AgentRuntime(
        db_session,
        {"maimai": adapter},
        source_health_registry=SourceHealthRegistry(),
    )

    result = await runtime.run_search(
        {
            "identity": "working_switch",
            "target_companies": ["阿里巴巴"],
            "directions": ["自动化测试"],
        }
    )

    assert result["status"] == "failed"
    assert result["sourcesStatus"]["maimai"]["status"] == "unauthorized"
    assert result["sourcesStatus"]["maimai"]["nextAction"] == "login"
    assert result["sourcesStatus"]["maimai"]["recoverable"] is True
    assert result["sourcesStatus"]["maimai"]["failureCount"] == 1


@pytest.mark.asyncio
async def test_runtime_skips_source_during_transient_cooldown(db_session):
    adapter = StatusAdapter("xiaohongshu", SourceStatus.OK)
    registry = SourceHealthRegistry()
    registry.record_status("xiaohongshu", SourceStatus.TIMEOUT, "Previous timeout")
    runtime = AgentRuntime(
        db_session,
        {"xiaohongshu": adapter},
        source_health_registry=registry,
    )

    result = await runtime.run_search(
        {
            "identity": "working_switch",
            "target_companies": ["Kimi"],
            "directions": ["大模型 Eval"],
        }
    )

    assert adapter.search_calls == 0
    assert result["status"] == "failed"
    assert result["sourcesStatus"]["xiaohongshu"]["status"] == "timeout"
    assert result["sourcesStatus"]["xiaohongshu"]["nextAction"] == "retry_later"
    assert result["sourcesStatus"]["xiaohongshu"]["cooldownSeconds"] > 0

from __future__ import annotations

import pytest

from app.adapters.base import (
    SourceAdapter,
    SourceQuery,
    SourceSearchItem,
    SourceSearchResult,
    SourceStatus,
)
from app.runtime.report_runtime import ReportRuntime
from app.schemas.report import SourceHealth, TargetBrief


class ReportAdapter(SourceAdapter):
    def __init__(self, adapter_id: str, items: list[SourceSearchItem] | None = None):
        self.id = adapter_id
        self.display_name = adapter_id
        self.items = items or []

    @property
    def capabilities(self) -> dict:
        return {"search": True}

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        return SourceSearchResult(
            source=self.id,
            status=SourceStatus.OK,
            items=self.items,
            count=len(self.items),
        )


class FixedSourceConnections:
    def __init__(self, health: list[SourceHealth]):
        self.health = health

    async def validate_required(self) -> list[SourceHealth]:
        return self.health


def _target() -> TargetBrief:
    return TargetBrief(
        company="字节跳动",
        roleDirection="后端开发",
        experienceStage="social",
    )


def _ready_health() -> list[SourceHealth]:
    return [
        SourceHealth(source="xiaohongshu", status="ready"),
        SourceHealth(source="maimai", status="ready"),
        SourceHealth(source="nowcoder", status="ready"),
    ]


def _items(source: str, count: int, title: str = "Redis 一致性怎么保证") -> list[SourceSearchItem]:
    return [
        SourceSearchItem(
            source=source,
            source_url=f"https://example.com/{source}/{index}",
            title=title,
            snippet="面试官追问了 Redis 缓存一致性和项目深挖",
        )
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_report_runtime_blocks_when_required_source_unready():
    runtime = ReportRuntime(
        adapters={},
        source_connection_manager=FixedSourceConnections([
            SourceHealth(source="xiaohongshu", status="ready"),
            SourceHealth(source="maimai", status="expired", reason="Cookie expired", nextAction="relogin"),
            SourceHealth(source="nowcoder", status="ready"),
        ]),
    )

    result = await runtime.run(_target())

    assert result.status == "blocked_source_unready"
    assert result.diagnostic is not None
    assert [source.source for source in result.diagnostic.blockedSources] == ["maimai"]
    assert result.intelligenceReport is None


@pytest.mark.asyncio
async def test_report_runtime_marks_sample_insufficient_without_advice():
    runtime = ReportRuntime(
        adapters={
            "xiaohongshu": ReportAdapter("xiaohongshu", _items("xiaohongshu", 2)),
            "maimai": ReportAdapter("maimai", []),
            "nowcoder": ReportAdapter("nowcoder", []),
        },
        source_connection_manager=FixedSourceConnections(_ready_health()),
    )

    result = await runtime.run(_target())

    assert result.status == "sample_insufficient"
    assert result.sampleQuality.meetsFormalReportThreshold is False
    assert result.intelligenceReport is not None
    assert result.intelligenceReport.clusters == []
    assert result.intelligenceReport.preparationAdvice == []


@pytest.mark.asyncio
async def test_report_runtime_generates_ready_report_when_gates_pass():
    runtime = ReportRuntime(
        adapters={
            "xiaohongshu": ReportAdapter("xiaohongshu", _items("xiaohongshu", 4)),
            "maimai": ReportAdapter("maimai", _items("maimai", 4)),
            "nowcoder": ReportAdapter("nowcoder", _items("nowcoder", 1, title="项目深挖怎么回答")),
        },
        source_connection_manager=FixedSourceConnections(_ready_health()),
    )

    result = await runtime.run(_target())

    assert result.status == "ready"
    assert result.sampleQuality.validInterviewCount == 9
    assert result.sampleQuality.participatingKeySourceCount == 3
    assert result.sampleQuality.evidenceQuestionCount == 9
    assert result.intelligenceReport is not None
    assert result.intelligenceReport.clusters
    assert result.intelligenceReport.preparationAdvice
    assert all(advice.clusterId for advice in result.intelligenceReport.preparationAdvice)

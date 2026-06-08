"""Tests for HookEngine and default quality hooks."""

import pytest

from app.runtime.hook_engine import (
    HookEngine,
    HookResult,
    HookType,
    create_default_hook_engine,
    post_fetch_hook,
    post_search_hook,
    pre_search_hook,
)


@pytest.fixture
def engine() -> HookEngine:
    return create_default_hook_engine()


@pytest.mark.asyncio
async def test_default_hooks_are_registered(engine):
    assert len(engine._hooks[HookType.PRE_SEARCH]) == 1
    assert len(engine._hooks[HookType.POST_SEARCH]) == 1
    assert len(engine._hooks[HookType.POST_FETCH]) == 1


@pytest.mark.asyncio
async def test_pre_search_blocks_when_no_queries():
    result = await pre_search_hook({"queries": []})

    assert result.passed is False
    assert result.blocked_reason == "No queries provided"


@pytest.mark.asyncio
async def test_pre_search_passes_with_valid_queries():
    result = await pre_search_hook(
        {
            "queries": [
                {"query": "字节跳动 后端 面经"},
                {"query": "腾讯 算法 校招 面经"},
            ]
        }
    )

    assert result.passed is True
    assert result.blocked_reason is None


@pytest.mark.asyncio
async def test_pre_search_warns_on_short_queries():
    result = await pre_search_hook({"queries": [{"query": "ab"}]})

    assert result.passed is True
    assert any("too short" in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_post_search_warns_on_empty_results():
    result = await post_search_hook({"results": []})

    assert result.passed is True
    assert any("0 results" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_post_search_warns_on_high_duplicate_ratio():
    results = [
        {"source_url": "https://example.com/a"},
        {"source_url": "https://example.com/a"},
        {"source_url": "https://example.com/a"},
        {"source_url": "https://example.com/a"},
        {"source_url": "https://example.com/b"},
    ]

    result = await post_search_hook({"results": results})

    assert result.passed is True
    assert any("duplicate" in warning.lower() for warning in result.warnings)


@pytest.mark.asyncio
async def test_post_fetch_warns_on_non_interview_content():
    result = await post_fetch_hook(
        {"full_text": "这是一篇普通旅游攻略，没有任何技术面试相关内容。" * 3}
    )

    assert result.passed is True
    assert any("interview-related keywords" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_post_fetch_passes_for_interview_content():
    result = await post_fetch_hook(
        {
            "full_text": (
                "今天参加了字节后端一面，面试官追问了算法题和项目经历，"
                "最后还问了反问环节，整体是典型面经，内容足够长用于质量检查。"
            )
        }
    )

    assert result.passed is True
    assert result.warnings == []


@pytest.mark.asyncio
async def test_run_hooks_stops_on_first_block(engine):
    async def blocking_hook(_context):
        return HookResult(passed=False, blocked_reason="blocked by test")

    engine.register(HookType.PRE_SEARCH, blocking_hook)

    result = await engine.run_hooks(
        HookType.PRE_SEARCH,
        {"queries": [{"query": "valid query here"}]},
    )

    assert result.passed is False
    assert result.blocked_reason == "blocked by test"


@pytest.mark.asyncio
async def test_run_hooks_aggregates_warnings(engine):
    async def warning_hook(_context):
        return HookResult(passed=True, warnings=["warning one"])

    engine.register(HookType.POST_SEARCH, warning_hook)

    result = await engine.run_hooks(
        HookType.POST_SEARCH,
        {"results": [{"source_url": "https://example.com/1"}]},
    )

    assert result.passed is True
    assert "warning one" in result.warnings


@pytest.mark.asyncio
async def test_run_hooks_handles_hook_exception(engine):
    async def failing_hook(_context):
        raise RuntimeError("hook crashed")

    engine.register(HookType.POST_FETCH, failing_hook)

    result = await engine.run_hooks(HookType.POST_FETCH, {"full_text": "x" * 60})

    assert result.passed is True
    assert any("hook crashed" in warning for warning in result.warnings)

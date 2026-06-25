from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.xhs_mcp_client import XhsMcpClient, _MAX_CONCURRENT_CALLS, _MAX_HEALTH_FAILURES


def _make_session_stub(*, call_tool_side_effect=None, call_tool_return: str = ""):
    session = MagicMock()
    session.initialize = AsyncMock(return_value=None)
    tools_stub = MagicMock()
    tools_stub.tools = [MagicMock(name="search_notes"), MagicMock(name="get_note_content")]
    session.list_tools = AsyncMock(return_value=tools_stub)

    if call_tool_side_effect is not None:
        session.call_tool = AsyncMock(side_effect=call_tool_side_effect)
    else:
        content_item = MagicMock()
        content_item.text = call_tool_return
        result_obj = MagicMock()
        result_obj.content = [content_item]
        session.call_tool = AsyncMock(return_value=result_obj)

    return session


def _wire_client_with_session(client: XhsMcpClient, session) -> XhsMcpClient:
    client._session = session
    client._connected = True
    client._healthy = True
    client._health_failures = 0
    client._exit_stack = None
    client._heartbeat_task = None
    client.start_heartbeat = MagicMock()
    return client


@pytest.mark.asyncio
async def test_call_tool_uses_semaphore_concurrency(monkeypatch):
    client = XhsMcpClient()

    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def _track_call(*args, **kwargs):
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        content_item = MagicMock()
        content_item.text = "ok"
        result_obj = MagicMock()
        result_obj.content = [content_item]
        return result_obj

    session = _make_session_stub(call_tool_side_effect=_track_call)
    _wire_client_with_session(client, session)

    async def _bypass_connect():
        return True

    monkeypatch.setattr(client, "ensure_connected", AsyncMock(side_effect=_bypass_connect))

    tasks = [client.call_tool("get_note_content", {"url": f"https://xhs.com/{i}"}) for i in range(5)]
    await asyncio.gather(*tasks)

    assert peak <= _MAX_CONCURRENT_CALLS, f"peak concurrency {peak} exceeded {_MAX_CONCURRENT_CALLS}"
    assert peak >= 2, f"expected parallel execution, peak={peak}"


@pytest.mark.asyncio
async def test_call_tool_timeout_does_not_disconnect(monkeypatch):
    client = XhsMcpClient()

    async def _timeout_call(*args, **kwargs):
        await asyncio.sleep(0.5)
        return MagicMock()

    session = _make_session_stub(call_tool_side_effect=_timeout_call)
    _wire_client_with_session(client, session)

    async def _bypass_connect():
        return True

    monkeypatch.setattr(client, "ensure_connected", AsyncMock(side_effect=_bypass_connect))

    result = await client.call_tool("get_note_content", {"url": "x"}, timeout=0.05)

    assert result is None
    assert client._connected is True, "single timeout should NOT mark disconnected"
    assert client._health_failures == 1
    assert client._healthy is True, "should not be unhealthy after single failure"


@pytest.mark.asyncio
async def test_call_tool_timeout_triggers_unhealthy_after_3_failures(monkeypatch):
    client = XhsMcpClient()

    async def _timeout_call(*args, **kwargs):
        await asyncio.sleep(0.5)
        return MagicMock()

    session = _make_session_stub(call_tool_side_effect=_timeout_call)
    _wire_client_with_session(client, session)

    async def _bypass_connect():
        return True

    monkeypatch.setattr(client, "ensure_connected", AsyncMock(side_effect=_bypass_connect))

    for _ in range(_MAX_HEALTH_FAILURES):
        await client.call_tool("get_note_content", {"url": "x"}, timeout=0.05)

    assert client._health_failures >= _MAX_HEALTH_FAILURES
    assert client._healthy is False, "should be unhealthy after 3 consecutive timeouts"


@pytest.mark.asyncio
async def test_get_note_content_detects_auth_required(monkeypatch):
    client = XhsMcpClient()

    content_item = MagicMock()
    content_item.text = "请先登录后再查看笔记内容"
    result_obj = MagicMock()
    result_obj.content = [content_item]
    session = _make_session_stub()
    session.call_tool = AsyncMock(return_value=result_obj)
    _wire_client_with_session(client, session)

    async def _bypass_connect():
        return True

    monkeypatch.setattr(client, "ensure_connected", AsyncMock(side_effect=_bypass_connect))

    with pytest.raises(ValueError, match="auth_required"):
        await client.get_note_content("https://www.xiaohongshu.com/explore/abc")

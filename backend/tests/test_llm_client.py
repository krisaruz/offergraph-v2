"""Tests for LLMClient JSON extraction and retry behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.client import LLMClient


class TestExtractJson:
    def test_extract_json_plain_object(self):
        result = LLMClient._extract_json('{"company": "字节", "count": 2}')
        assert result == {"company": "字节", "count": 2}

    def test_extract_json_from_markdown_fence(self):
        content = 'Here is the result:\n```json\n{"status": "ok"}\n```'
        result = LLMClient._extract_json(content)
        assert result == {"status": "ok"}

    def test_extract_json_embedded_in_text(self):
        content = 'Analysis complete. {"events": [{"company": "腾讯"}]} Done.'
        result = LLMClient._extract_json(content)
        assert result == {"events": [{"company": "腾讯"}]}

    def test_extract_json_array(self):
        content = '["a", "b", "c"]'
        result = LLMClient._extract_json(content)
        assert result == ["a", "b", "c"]

    def test_extract_json_invalid_returns_none(self):
        result = LLMClient._extract_json("not json at all")
        assert result is None


class TestChatJson:
    @pytest.fixture
    def llm_client(self):
        with patch("app.llm.client.AsyncOpenAI"):
            return LLMClient()

    @pytest.mark.asyncio
    async def test_chat_json_success(self, llm_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"answer": 42}'))]
        llm_client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await llm_client.chat_json([{"role": "user", "content": "test"}])

        assert result == {"answer": 42}
        call_kwargs = llm_client._client.chat.completions.create.await_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_chat_json_retries_on_parse_failure(self, llm_client):
        bad_response = MagicMock()
        bad_response.choices = [MagicMock(message=MagicMock(content="not valid json"))]

        good_response = MagicMock()
        good_response.choices = [MagicMock(message=MagicMock(content='{"retried": true}'))]

        llm_client._client.chat.completions.create = AsyncMock(
            side_effect=[bad_response, good_response]
        )

        result = await llm_client.chat_json([{"role": "user", "content": "test"}])

        assert result == {"retried": True}
        assert llm_client._client.chat.completions.create.await_count == 2

    @pytest.mark.asyncio
    async def test_chat_json_fallback_when_json_object_not_supported(self, llm_client):
        json_object_error = Exception("response_format json_object is not supported")
        fallback_response = MagicMock()
        fallback_response.choices = [
            MagicMock(message=MagicMock(content='{"fallback": true}'))
        ]

        llm_client._client.chat.completions.create = AsyncMock(
            side_effect=[json_object_error, fallback_response]
        )

        result = await llm_client.chat_json([{"role": "user", "content": "test"}])

        assert result == {"fallback": True}
        assert llm_client._client.chat.completions.create.await_count == 2

        second_call_kwargs = llm_client._client.chat.completions.create.await_args_list[1].kwargs
        assert "response_format" not in second_call_kwargs

    @pytest.mark.asyncio
    async def test_chat_json_exhausted_retries_return_error(self, llm_client):
        llm_client._client.chat.completions.create = AsyncMock(
            side_effect=Exception("persistent API failure")
        )

        result = await llm_client.chat_json([{"role": "user", "content": "test"}])

        assert result["error"] == "persistent API failure"
        assert result["confidence"] == 0
        assert llm_client._client.chat.completions.create.await_count == 3

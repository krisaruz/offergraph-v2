"""LLM 客户端 — OpenAI 兼容接口（WPS AI Gateway）"""

import json
import logging
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI 兼容 LLM 客户端，支持普通对话和 JSON 输出"""

    def __init__(self):
        self._client = AsyncOpenAI(
            base_url=settings.llm_api_base,
            api_key=settings.llm_api_key,
            default_headers={
                "AI-Gateway-Uid": settings.llm_gateway_uid,
                "AI-Gateway-Product-Name": settings.llm_gateway_product,
                "AI-Gateway-Intention-Code": settings.llm_gateway_intention,
            },
        )
        self._model = settings.llm_model

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """JSON 输出，带重试和降级逻辑"""
        max_retries = 3
        last_error = None
        use_json_format = True

        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if use_json_format:
                    kwargs["response_format"] = {"type": "json_object"}

                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or "{}"

                parsed = self._extract_json(content)
                if parsed is not None:
                    return parsed
                return json.loads(content)

            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                if ("json_object" in error_msg or "not supported" in error_msg) and use_json_format:
                    logger.warning("Model doesn't support json_object format, falling back")
                    use_json_format = False
                    continue

                logger.warning(f"JSON parse failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    messages = messages + [
                        {"role": "assistant", "content": str(e)},
                        {"role": "user", "content": "请重新输出合法的 JSON，不要包含任何其他文本。"},
                    ]

        logger.error(f"JSON output retries exhausted: {last_error}")
        return {"error": str(last_error), "confidence": 0}

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    @staticmethod
    def _extract_json(content: str) -> dict | None:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
            match = re.search(pattern, content)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        return None


llm_client = LLMClient()

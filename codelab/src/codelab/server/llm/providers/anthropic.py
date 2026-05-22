"""Anthropic LLM провайдер.

Использует Anthropic Messages API, не наследуется от OpenAICompatibleProvider.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from codelab.server.llm.base import (
    LLMCapabilities,
    LLMConfig,
    LLMProvider,
)
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMMessage,
    LLMToolCall,
    StopReason,
)

logger = structlog.get_logger()


class AnthropicProvider(LLMProvider):
    """Провайдер для Anthropic Claude API.

    Использует Messages API вместо Chat Completions.
    Отличия:
    - max_tokens обязателен в запросе
    - Tool format: input_schema вместо parameters
    - Stop reason mapping
    """

    def __init__(self) -> None:
        """Инициализация."""
        self._client: AsyncAnthropic | None = None
        self._config: LLMConfig | None = None

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "anthropic"

    @property
    def capabilities(self) -> LLMCapabilities:
        """Возможности провайдера."""
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=True,
            supports_system_prompt=True,
            max_context_window=200000,
        )

    async def initialize(self, config: LLMConfig) -> None:
        """Инициализировать провайдер.

        Args:
            config: Конфигурация провайдера
        """
        self._config = config
        self._client = AsyncAnthropic(api_key=config.api_key)

        logger.info(
            "anthropic provider initialized",
            model=config.model,
        )

    async def create_completion(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Получить завершение от Anthropic API.

        Args:
            request: Запрос к провайдеру

        Returns:
            CompletionResponse с ответом модели
        """
        if self._client is None:
            msg = "Provider not initialized"
            raise RuntimeError(msg)

        system_message = self._extract_system_message(request.messages)
        messages = self._convert_to_anthropic_format(request.messages)

        model = request.model or (self._config.model if self._config else "claude-sonnet-4")

        request_params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if system_message:
            request_params["system"] = system_message

        if request.tools:
            request_params["tools"] = self._convert_tools_for_anthropic(request.tools)

        response = await self._client.messages.create(**request_params)

        return self._parse_response(response, model)

    async def stream_completion(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionResponse, None]:
        """Потоковое получение ответа.

        Args:
            request: Запрос к провайдеру

        Yields:
            Промежуточные CompletionResponse
        """
        if self._client is None:
            msg = "Provider not initialized"
            raise RuntimeError(msg)

        system_message = self._extract_system_message(request.messages)
        messages = self._convert_to_anthropic_format(request.messages)

        model = request.model or (self._config.model if self._config else "claude-sonnet-4")

        request_params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if system_message:
            request_params["system"] = system_message

        if request.tools:
            request_params["tools"] = self._convert_tools_for_anthropic(request.tools)

        buffer = ""
        async with self._client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                buffer += text
                yield CompletionResponse(
                    text=buffer,
                    stop_reason=StopReason.STREAMING,
                    model=model,
                )

    def _extract_system_message(self, messages: list[LLMMessage]) -> str | None:
        """Извлечь system message из списка.

        Args:
            messages: Список сообщений

        Returns:
            Текст system message или None
        """
        for msg in messages:
            if msg.role == "system":
                return msg.content or ""
        return None

    def _convert_to_anthropic_format(
        self,
        messages: list[LLMMessage],
    ) -> list[dict[str, Any]]:
        """Преобразовать LLMMessage в формат Anthropic API.

        Args:
            messages: Список LLMMessage

        Returns:
            Список словарей в формате Anthropic API
        """
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                continue  # System message обрабатывается отдельно

            anthropic_msg: dict[str, Any] = {"role": msg.role}

            if msg.role == "assistant" and msg.tool_calls:
                content: list[dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})

                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })

                anthropic_msg["content"] = content
            elif msg.role == "tool":
                anthropic_msg["content"] = [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                }]
            else:
                anthropic_msg["content"] = msg.content or ""

            anthropic_messages.append(anthropic_msg)

        return anthropic_messages

    def _convert_tools_for_anthropic(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Преобразовать инструменты в формат Anthropic.

        Args:
            tools: Инструменты в OpenAI формате

        Returns:
            Инструменты в Anthropic формате
        """
        anthropic_tools: list[dict[str, Any]] = []

        for tool in tools:
            anthropic_tools.append({
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
            })

        return anthropic_tools

    def _parse_response(
        self,
        response: Any,
        model: str,
    ) -> CompletionResponse:
        """Преобразовать ответ Anthropic в CompletionResponse.

        Args:
            response: Ответ от Anthropic API
            model: Имя модели

        Returns:
            CompletionResponse
        """
        text = ""
        tool_calls: list[LLMToolCall] = []

        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    LLMToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        stop_reason = StopReason.END_TURN
        if response.stop_reason == "tool_use":
            stop_reason = StopReason.TOOL_USE
        elif response.stop_reason == "max_tokens":
            stop_reason = StopReason.MAX_TOKENS
        elif response.stop_reason == "stop_sequence":
            stop_reason = StopReason.STOP_SEQUENCE

        usage = {}
        if hasattr(response, "usage"):
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model=model,
            usage=usage,
        )

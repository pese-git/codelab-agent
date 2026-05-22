"""OpenAI LLM провайдер (legacy wrapper).

Обёртка для обратной совместимости.
Основная реализация: codelab.server.llm.providers.openai.OpenAIProvider
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from codelab.server.llm.base import (
    LLMConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMToolCall,
)
from codelab.server.llm.models import StopReason

logger = structlog.get_logger()


class OpenAIProvider(LLMProvider):
    """Провайдер для взаимодействия с OpenAI API.

    Legacy wrapper для обратной совместимости.
    """

    def __init__(self) -> None:
        """Инициализация провайдера."""
        self._client: AsyncOpenAI | None = None
        self._model: str = "gpt-4o"
        self._temperature: float = 0.7
        self._max_tokens: int = 8192

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "openai"

    @property
    def capabilities(self):
        """Возможности провайдера."""
        from codelab.server.llm.base import LLMCapabilities

        return LLMCapabilities()

    async def initialize(self, config: dict[str, Any] | LLMConfig) -> None:
        """Инициализировать провайдер с конфигурацией.

        Поддерживает как dict (legacy), так и LLMConfig.
        """
        logger.debug("initializing openai provider")

        if isinstance(config, LLMConfig):
            api_key = config.api_key
            self._model = config.model
            self._temperature = config.temperature
            self._max_tokens = config.max_tokens
            base_url = config.base_url
        else:
            api_key = config.get("api_key")
            self._model = config.get("model", "gpt-4o")
            self._temperature = config.get("temperature", 0.7)
            self._max_tokens = config.get("max_tokens", 8192)
            base_url = config.get("base_url")

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        logger.info(
            "openai provider initialized",
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            has_base_url=bool(base_url),
        )

    async def create_completion(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Получить завершение от OpenAI API."""
        if self._client is None:
            msg = "Провайдер не инициализирован"
            raise RuntimeError(msg)

        openai_messages = self._convert_to_openai_format(messages)
        self._validate_message_history(openai_messages)

        request_params = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
        }

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"

        response: ChatCompletion = await self._client.chat.completions.create(**request_params)
        return self._parse_completion(response)

    async def stream_completion(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Потоковое получение ответа."""
        if self._client is None:
            msg = "Провайдер не инициализирован"
            raise RuntimeError(msg)

        openai_messages = self._convert_to_openai_format(messages)

        request_params = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "stream": True,
        }

        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**request_params)
        buffer = ""
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                buffer += chunk.choices[0].delta.content
                yield LLMResponse(
                    text=buffer,
                    tool_calls=[],
                    stop_reason=StopReason.STREAMING,
                )

    def _parse_completion(self, response: ChatCompletion) -> LLMResponse:
        """Преобразовать ответ OpenAI в LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        text = message.content or ""
        tool_calls: list[LLMToolCall] = []

        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.type == "function":
                    func = tool_call.function
                    args: dict[str, Any] = {}
                    if isinstance(func.arguments, str):
                        try:
                            args = json.loads(func.arguments)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    elif isinstance(func.arguments, dict):
                        args = func.arguments

                    tool_calls.append(
                        LLMToolCall(
                            id=tool_call.id,
                            name=func.name,
                            arguments=args,
                        )
                    )

        stop_reason = StopReason.END_TURN
        if choice.finish_reason == "tool_calls":
            stop_reason = StopReason.TOOL_USE
        elif choice.finish_reason == "length":
            stop_reason = StopReason.MAX_TOKENS

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
        )

    def _convert_to_openai_format(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Преобразовать LLMMessage в формат OpenAI API."""
        openai_messages: list[dict[str, Any]] = []

        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role}

            if msg.content is not None:
                openai_msg["content"] = msg.content

            if msg.role == "assistant" and msg.tool_calls:
                openai_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            if msg.role == "tool":
                if msg.tool_call_id:
                    openai_msg["tool_call_id"] = msg.tool_call_id
                if msg.name:
                    openai_msg["name"] = msg.name

            openai_messages.append(openai_msg)

        return openai_messages

    def _validate_message_history(self, messages: list[dict[str, Any]]) -> None:
        """Валидация истории сообщений."""
        last_assistant_tool_call_ids: set[str] = set()

        for i, msg in enumerate(messages):
            role = msg.get("role")

            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    last_assistant_tool_call_ids = {tc["id"] for tc in tool_calls}
                else:
                    last_assistant_tool_call_ids = set()

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")

                if not tool_call_id:
                    raise ValueError(f"Tool message at index {i} missing tool_call_id")

                if not last_assistant_tool_call_ids:
                    raise ValueError(
                        f"Tool message at index {i} (tool_call_id={tool_call_id}) "
                        "must follow an assistant message with tool_calls"
                    )

"""Базовый класс для OpenAI-compatible провайдеров.

Все провайдеры с OpenAI-compatible API наследуются от этого класса:
- OpenAIProvider
- OpenRouterProvider
- ZenProvider
- GoProvider
- OllamaProvider
- LMStudioProvider
"""

from __future__ import annotations

import json
from abc import abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

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


class OpenAICompatibleProvider(LLMProvider):
    """Базовый класс для всех OpenAI-compatible провайдеров.

    Содержит всю логику работы с OpenAI SDK.
    Наследники переопределяют только:
    - name property
    - default_model property
    - base_url (опционально)
    """

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str = "gpt-4o",
    ) -> None:
        """Инициализация.

        Args:
            base_url: Base URL API (None для стандартного OpenAI)
            default_model: Модель по умолчанию
        """
        self._client: AsyncOpenAI | None = None
        self._base_url = base_url
        self._default_model = default_model
        self._config: LLMConfig | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя провайдера."""
        ...

    @property
    def capabilities(self) -> LLMCapabilities:
        """Возможности провайдера."""
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=False,
            supports_system_prompt=True,
        )

    async def initialize(self, config: LLMConfig) -> None:
        """Инициализировать провайдер.

        Args:
            config: Конфигурация провайдера
        """
        self._config = config

        # Создаём настраиваемый таймаут для HTTP-вызовов
        timeout = httpx.Timeout(
            connect=config.timeout.connect,
            read=config.timeout.read,
            write=config.timeout.write,
            pool=config.timeout.pool,
        )

        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=self._base_url or config.base_url,
            timeout=timeout,
        )

        logger.info(
            "openai-compatible provider initialized",
            provider=self.name,
            model=config.model,
            has_base_url=bool(self._base_url or config.base_url),
        )

    async def create_completion(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Получить завершение от LLM.

        Args:
            request: Запрос к провайдеру

        Returns:
            CompletionResponse с ответом модели
        """
        if self._client is None:
            msg = "Provider not initialized"
            raise RuntimeError(msg)

        logger.debug(
            "create_completion request starting",
            provider=self.name,
            num_messages=len(request.messages),
            has_tools=bool(request.tools),
        )

        openai_messages = self._convert_to_openai_format(request.messages)
        self._validate_message_history(openai_messages)

        model = request.model or self._config.model if self._config else self._default_model
        model = self._normalize_model_id(model)

        request_params: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.tools:
            request_params["tools"] = request.tools
            request_params["tool_choice"] = "auto"

        if request.stop:
            request_params["stop"] = request.stop

        response: ChatCompletion = await self._client.chat.completions.create(**request_params)

        return self._parse_completion(response, model)

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

        openai_messages = self._convert_to_openai_format(request.messages)

        model = request.model or self._config.model if self._config else self._default_model
        model = self._normalize_model_id(model)

        request_params: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if request.tools:
            request_params["tools"] = request.tools
            request_params["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**request_params)

        buffer = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                buffer += chunk.choices[0].delta.content
                yield CompletionResponse(
                    text=buffer,
                    stop_reason=StopReason.STREAMING,
                    model=model,
                )

    def _convert_to_openai_format(
        self,
        messages: list[LLMMessage],
    ) -> list[dict[str, Any]]:
        """Преобразовать LLMMessage в формат OpenAI API.

        Args:
            messages: Список LLMMessage

        Returns:
            Список словарей в формате OpenAI API
        """
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

    def _parse_completion(
        self,
        response: ChatCompletion,
        model: str,
    ) -> CompletionResponse:
        """Преобразовать ответ OpenAI в CompletionResponse.

        Args:
            response: Ответ от OpenAI API
            model: Имя модели

        Returns:
            CompletionResponse
        """
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
        elif choice.finish_reason == "stop":
            stop_reason = StopReason.STOP_SEQUENCE

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model=model,
            usage=usage,
        )

    def _validate_message_history(self, messages: list[dict[str, Any]]) -> None:
        """Валидация истории сообщений.

        Args:
            messages: Список сообщений в формате OpenAI

        Raises:
            ValueError: Если история некорректна
        """
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
                    logger.error("tool message without tool_call_id", message_index=i)
                    raise ValueError(f"Tool message at index {i} missing tool_call_id")

                if not last_assistant_tool_call_ids:
                    logger.error(
                        "tool message without preceding assistant tool_calls",
                        message_index=i,
                    )
                    raise ValueError(
                        f"Tool message at index {i} must follow an assistant message with tool_calls"
                    )

    def _normalize_model_id(self, model: str) -> str:
        """Нормализовать model ID для отправки в API.

        Strip-ает префикс внутреннего провайдера (например, 'openrouter/')
        чтобы получить model ID, который ожидает внешнее API.

        Args:
            model: Model ID во внутреннем формате (например, 'openrouter/gpt-4o')

        Returns:
            Model ID для внешнего API (например, 'gpt-4o')
        """
        if not model:
            return model

        prefix = f"{self.name}/"
        if model.startswith(prefix):
            return model[len(prefix):]

        return model

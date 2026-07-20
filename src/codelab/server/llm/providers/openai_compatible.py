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
from codelab.server.llm.errors import map_provider_exception
from codelab.server.llm.formatting import (
    accumulate_tool_call_fragment,
    assemble_tool_calls,
    content_part_to_openai,
    content_parts_to_openai,
    extract_openai_usage,
    finish_reason_to_stop_reason,
    messages_to_openai_dict,
    parse_openai_tool_calls,
    validate_openai_message_history,
)
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMMessage,
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
            supports_vision=True,
            supports_audio=True,
            supports_system_prompt=True,
            supports_structured_output=True,
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

        model = self._resolve_model(request)

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

        try:
            response: ChatCompletion = await self._client.chat.completions.create(
                **request_params
            )
        except Exception as e:
            raise map_provider_exception(e, self.name) from e

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

        model = self._resolve_model(request)

        request_params = self._build_stream_request_params(request, model)
        try:
            stream = await self._client.chat.completions.create(**request_params)
        except Exception as e:
            raise map_provider_exception(e, self.name) from e

        # Контракт стрима:
        # - промежуточные chunk'и: stop_reason=STREAMING, text = ДЕЛЬТА (инкремент);
        # - финальный chunk: полный text + собранные tool_calls + реальный
        #   stop_reason + usage. Потребитель эмитит дельты вживую и НЕ должен
        #   повторно эмитить text финального chunk'а.
        full_text = ""
        # Фрагменты tool_calls по index: id/name приходят в первом фрагменте,
        # arguments — по кускам строки в последующих.
        tool_frags: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage: dict[str, int] = {}

        async for chunk in stream:
            chunk_usage = extract_openai_usage(getattr(chunk, "usage", None))
            if chunk_usage:
                usage = chunk_usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if delta is None:
                continue
            if delta.content:
                full_text += delta.content
                yield CompletionResponse(
                    text=delta.content,
                    stop_reason=StopReason.STREAMING,
                    model=model,
                )
            for tc in delta.tool_calls or []:
                accumulate_tool_call_fragment(tool_frags, tc)

        tool_calls = assemble_tool_calls(tool_frags)
        yield CompletionResponse(
            text=full_text,
            tool_calls=tool_calls,
            stop_reason=finish_reason_to_stop_reason(
                finish_reason, has_tool_calls=bool(tool_calls)
            ),
            model=model,
            usage=usage,
        )

    def _resolve_model(self, request: CompletionRequest) -> str:
        """Определить эффективную модель: request > config > default, + нормализация."""
        model = request.model or self._config.model if self._config else self._default_model
        return self._normalize_model_id(model)

    def _build_stream_request_params(
        self, request: CompletionRequest, model: str
    ) -> dict[str, Any]:
        """Собрать параметры запроса для streaming chat.completions."""
        params: dict[str, Any] = {
            "model": model,
            "messages": self._convert_to_openai_format(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            # usage приходит отдельным финальным chunk'ом только с этим флагом
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            params["tools"] = request.tools
            params["tool_choice"] = "auto"
        return params

    def _convert_to_openai_format(
        self,
        messages: list[LLMMessage],
    ) -> list[dict[str, Any]]:
        """Преобразовать LLMMessage в формат OpenAI API.

        Делегирует общей `messages_to_openai_dict`, пробрасывая vision/audio
        capabilities провайдера для graceful degradation мультимодального
        контента.

        Args:
            messages: Список LLMMessage

        Returns:
            Список словарей в формате OpenAI API
        """
        return messages_to_openai_dict(
            messages,
            supports_vision=self.capabilities.supports_vision,
            supports_audio=self.capabilities.supports_audio,
        )

    def _convert_content_parts_to_openai(
        self,
        parts: list[Any],
    ) -> list[dict[str, Any]]:
        """Конвертировать ContentPart-ы в формат OpenAI content."""
        return content_parts_to_openai(
            parts,
            supports_vision=self.capabilities.supports_vision,
            supports_audio=self.capabilities.supports_audio,
        )

    def _content_part_to_openai(self, part: Any) -> dict[str, Any] | None:
        """Конвертировать один ContentPart в формат OpenAI."""
        return content_part_to_openai(
            part,
            supports_vision=self.capabilities.supports_vision,
            supports_audio=self.capabilities.supports_audio,
        )

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
        tool_calls = parse_openai_tool_calls(message.tool_calls or [])

        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=finish_reason_to_stop_reason(
                choice.finish_reason, has_tool_calls=bool(tool_calls)
            ),
            model=model,
            usage=extract_openai_usage(response.usage),
        )

    def _validate_message_history(self, messages: list[dict[str, Any]]) -> None:
        """Валидация истории сообщений (делегирует общей formatting-функции).

        Args:
            messages: Список сообщений в формате OpenAI

        Raises:
            ValueError: Если история некорректна
        """
        validate_openai_message_history(messages)

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
            return model[len(prefix) :]

        return model

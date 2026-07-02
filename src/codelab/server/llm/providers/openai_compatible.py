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


def _extract_audio_format(mime_type: str) -> str:
    """Извлечь формат из MIME типа (audio/wav → wav)."""
    if "/" in mime_type:
        return mime_type.split("/", 1)[1]
    return mime_type


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
            # usage приходит отдельным финальным chunk'ом только с этим флагом
            "stream_options": {"include_usage": True},
        }

        if request.tools:
            request_params["tools"] = request.tools
            request_params["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**request_params)

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
            if getattr(chunk, "usage", None):
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
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
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    frag = tool_frags.setdefault(
                        tc.index, {"id": None, "name": None, "args": ""}
                    )
                    if tc.id:
                        frag["id"] = tc.id
                    if tc.function is not None:
                        if tc.function.name:
                            frag["name"] = tc.function.name
                        if tc.function.arguments:
                            frag["args"] += tc.function.arguments

        tool_calls: list[LLMToolCall] = []
        for idx in sorted(tool_frags):
            frag = tool_frags[idx]
            if not frag["name"]:
                continue  # неполный фрагмент без имени — пропускаем
            args: dict[str, Any] = {}
            if frag["args"]:
                try:
                    args = json.loads(frag["args"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
            tool_calls.append(
                LLMToolCall(id=frag["id"] or "", name=frag["name"], arguments=args)
            )

        yield CompletionResponse(
            text=full_text,
            tool_calls=tool_calls,
            stop_reason=self._finish_reason_to_stop_reason(
                finish_reason, has_tool_calls=bool(tool_calls)
            ),
            model=model,
            usage=usage,
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
                if isinstance(msg.content, list):
                    openai_msg["content"] = self._convert_content_parts_to_openai(
                        msg.content
                    )
                else:
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

    def _convert_content_parts_to_openai(
        self,
        parts: list[Any],
    ) -> list[dict[str, Any]]:
        """Конвертировать ContentPart-ы в формат OpenAI content."""
        result: list[dict[str, Any]] = []
        for part in parts:
            converted = self._content_part_to_openai(part)
            if converted is not None:
                result.append(converted)
        return result

    def _content_part_to_openai(self, part: Any) -> dict[str, Any] | None:
        """Конвертировать один ContentPart в формат OpenAI."""
        if part.type == "text":
            return {"type": "text", "text": part.text or ""}
        if part.type == "image":
            if not self.capabilities.supports_vision:
                logger.warning("provider does not support vision, skipping image")
                return None
            data = part.data or ""
            mime_type = part.mime_type or "image/png"
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{data}"},
            }
        if part.type == "audio":
            if not self.capabilities.supports_audio:
                logger.warning("provider does not support audio, skipping audio")
                return None
            mime_type = part.mime_type or "audio/wav"
            fmt = _extract_audio_format(mime_type)
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": part.data or "",
                    "format": fmt,
                },
            }
        return None

    @staticmethod
    def _finish_reason_to_stop_reason(
        finish_reason: str | None, *, has_tool_calls: bool
    ) -> StopReason:
        """Маппинг OpenAI finish_reason → StopReason.

        В стриме finish_reason может отсутствовать (None), но при собранных
        tool_calls всё равно нужен TOOL_USE — поэтому has_tool_calls имеет
        приоритет.
        """
        if finish_reason == "tool_calls" or has_tool_calls:
            return StopReason.TOOL_USE
        if finish_reason == "length":
            return StopReason.MAX_TOKENS
        if finish_reason == "stop":
            return StopReason.STOP_SEQUENCE
        return StopReason.END_TURN

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

        stop_reason = self._finish_reason_to_stop_reason(
            choice.finish_reason, has_tool_calls=bool(tool_calls)
        )

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
                        f"Tool message at index {i} must follow an assistant "
                        f"message with tool_calls"
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

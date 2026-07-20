"""LiteLLM провайдер — универсальный прокси через litellm.acompletion.

Поддерживает 100+ endpoint'ов (openai, anthropic, bedrock, vertex,
together, groq, mistral, cohere, и т.д.) через единый litellm-интерфейс.

Использует общие formatting-функции из codelab.server.llm.formatting
для конвертации LLMMessage/ContentPart в OpenAI-формат, который
принимает litellm.

Не наследуется от OpenAICompatibleProvider: litellm acompletion —
функция, а не объект, и capabilities зависят от выбранной модели.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import structlog
from litellm import acompletion

from codelab.server.llm.base import (
    LLMCapabilities,
    LLMConfig,
    LLMProvider,
)
from codelab.server.llm.errors import ProviderError, map_provider_exception
from codelab.server.llm.formatting import (
    accumulate_tool_call_fragment,
    assemble_tool_calls,
    extract_openai_usage,
    finish_reason_to_stop_reason,
    messages_to_openai_dict,
    parse_openai_tool_calls,
    validate_openai_message_history,
)
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    StopReason,
)

logger = structlog.get_logger()


_DEFAULT_MODEL = "gpt-4o"


@dataclass
class _StreamState:
    """Аккумулятор состояния по ходу потребления stream-чанков.

    Выделен из stream_completion для снижения цикломатической
    сложности hot-loop (mccabe <= 10).
    """

    full_text: str = ""
    tool_frags: dict[int, dict[str, Any]] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class _StreamChunkUpdate:
    """Snapshot релевантных полей одного stream-чанка.

    Возвращается _inspect_stream_chunk и обрабатывается в hot-loop
    stream_completion: чистая декомпозиция inspection vs accumulation.
    """

    usage: dict[str, int]
    finish_reason: str | None
    delta_content: str | None
    delta_tool_calls: tuple[Any, ...]


class LiteLLMProvider(LLMProvider):
    """Провайдер через litellm.acompletion."""

    def __init__(self) -> None:
        self._config: LLMConfig | None = None

    @property
    def name(self) -> str:
        return "litellm"

    @property
    def capabilities(self) -> LLMCapabilities:
        # Конкретные фичи зависят от выбранной модели; на уровне
        # провайдера заявляем максимум, graceful degradation делает
        # litellm + content_parts_to_openai.
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=True,
            supports_audio=True,
            supports_system_prompt=True,
        )

    async def initialize(self, config: LLMConfig) -> None:
        self._config = config
        logger.info(
            "litellm provider initialized",
            model=config.model,
            has_base_url=bool(config.base_url),
        )

    def _resolve_model(self, request_model: str) -> str:
        if request_model:
            return self._normalize_model_id(request_model)
        if self._config is not None and self._config.model:
            return self._normalize_model_id(self._config.model)
        return _DEFAULT_MODEL

    def _normalize_model_id(self, model: str) -> str:
        """Срезать внутренний префикс провайдера ("litellm/") из model ID.

        Основной путь (di/llm.py) кладёт в config.model полную ссылку
        "litellm/<litellm-model>" без ModelRef.parse. litellm.acompletion
        ожидает model в своём формате (напр. "openai/MiniMax-M3",
        "anthropic/claude-..."), поэтому селектор "litellm/" нужно срезать.
        Остаток (в т.ч. с бэкенд-префиксом litellm) передаётся как есть.
        """
        prefix = f"{self.name}/"
        if model.startswith(prefix):
            return model[len(prefix) :]
        return model

    def _build_call_kwargs(
        self,
        *,
        request: CompletionRequest,
        model: str,
        stream: bool,
    ) -> dict[str, Any]:
        messages = messages_to_openai_dict(request.messages)
        validate_openai_message_history(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }

        if self._config is not None and self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._config is not None and self._config.base_url:
            kwargs["api_base"] = self._config.base_url

        if request.tools:
            kwargs["tools"] = request.tools
            kwargs["tool_choice"] = "auto"

        if request.stop:
            kwargs["stop"] = request.stop

        if self._config is not None:
            kwargs["timeout"] = self._config.timeout.read

        return kwargs

    async def create_completion(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        if self._config is None:
            msg = "Provider not initialized"
            raise RuntimeError(msg)

        model = self._resolve_model(request.model)
        kwargs = self._build_call_kwargs(request=request, model=model, stream=False)

        logger.debug(
            "litellm create_completion",
            model=model,
            num_messages=len(request.messages),
            has_tools=bool(request.tools),
        )

        try:
            response = await acompletion(**kwargs)
        except Exception as e:
            raise self._map_exception(e) from e

        return self._parse_response(response, model)

    async def stream_completion(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionResponse, None]:
        if self._config is None:
            msg = "Provider not initialized"
            raise RuntimeError(msg)

        model = self._resolve_model(request.model)
        kwargs = self._build_call_kwargs(request=request, model=model, stream=True)

        try:
            response = await acompletion(**kwargs)
        except Exception as e:
            raise self._map_exception(e) from e

        state = _StreamState()

        async for chunk in response:
            update = self._inspect_stream_chunk(chunk)
            if update.usage:
                state.usage = update.usage
            if update.finish_reason:
                state.finish_reason = update.finish_reason
            if update.delta_content:
                state.full_text += update.delta_content
                yield CompletionResponse(
                    text=update.delta_content,
                    stop_reason=StopReason.STREAMING,
                    model=model,
                )
            for tc in update.delta_tool_calls:
                accumulate_tool_call_fragment(state.tool_frags, tc)

        tool_calls = assemble_tool_calls(state.tool_frags)
        yield CompletionResponse(
            text=state.full_text,
            tool_calls=tool_calls,
            stop_reason=finish_reason_to_stop_reason(
                state.finish_reason, has_tool_calls=bool(tool_calls)
            ),
            model=model,
            usage=state.usage,
        )

    def _inspect_stream_chunk(self, chunk: Any) -> _StreamChunkUpdate:
        """Извлечь из chunk'а стрима все релевантные поля для аккумуляции.

        Декомпозиция stream_completion: выделение inspection-логики из горячего
        цикла снижает цикломатическую сложность до <=10 (mccabe).
        """
        usage: dict[str, int] = {}
        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage:
            usage = extract_openai_usage(chunk_usage)

        choices = getattr(chunk, "choices", None)
        if not choices:
            return _StreamChunkUpdate(
                usage=usage,
                finish_reason=None,
                delta_content=None,
                delta_tool_calls=(),
            )

        choice = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        delta = getattr(choice, "delta", None)
        if delta is None:
            return _StreamChunkUpdate(
                usage=usage,
                finish_reason=finish_reason,
                delta_content=None,
                delta_tool_calls=(),
            )

        return _StreamChunkUpdate(
            usage=usage,
            finish_reason=finish_reason,
            delta_content=getattr(delta, "content", None),
            delta_tool_calls=getattr(delta, "tool_calls", None) or (),
        )

    def _parse_response(
        self,
        response: Any,
        model: str,
    ) -> CompletionResponse:
        choice = response.choices[0]
        message = choice.message

        text = getattr(message, "content", None) or ""
        raw_tool_calls = getattr(message, "tool_calls", None)
        tool_calls = parse_openai_tool_calls(raw_tool_calls or [])

        return CompletionResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=finish_reason_to_stop_reason(
                getattr(choice, "finish_reason", None),
                has_tool_calls=bool(tool_calls),
            ),
            model=model,
            usage=extract_openai_usage(getattr(response, "usage", None)),
        )

    def _map_exception(self, exc: BaseException) -> ProviderError:
        """Маппинг litellm-исключений в ProviderError.

        Делегирует общему SDK-агностичному map_provider_exception:
        litellm-исключения экспонируют status_code / имеют распознаваемые
        имена классов (AuthenticationError, RateLimitError, Timeout, ...).
        """
        return map_provider_exception(exc, self.name)

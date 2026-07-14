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

import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from litellm import acompletion

from codelab.server.llm.base import (
    LLMCapabilities,
    LLMConfig,
    LLMProvider,
)
from codelab.server.llm.errors import ProviderError, ProviderErrorType
from codelab.server.llm.formatting import (
    extract_openai_usage,
    finish_reason_to_stop_reason,
    messages_to_openai_dict,
    parse_openai_tool_calls,
    validate_openai_message_history,
)
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMToolCall,
    StopReason,
)

logger = structlog.get_logger()


_DEFAULT_MODEL = "gpt-4o"


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
            return request_model
        if self._config is not None and self._config.model:
            return self._config.model
        return _DEFAULT_MODEL

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

        full_text = ""
        tool_frags: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage: dict[str, int] = {}

        async for chunk in response:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage:
                usage = extract_openai_usage(chunk_usage)

            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            choice = choices[0]
            chunk_finish = getattr(choice, "finish_reason", None)
            if chunk_finish:
                finish_reason = chunk_finish
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue

            content = getattr(delta, "content", None)
            if content:
                full_text += content
                yield CompletionResponse(
                    text=content,
                    stop_reason=StopReason.STREAMING,
                    model=model,
                )

            delta_tool_calls = getattr(delta, "tool_calls", None)
            if delta_tool_calls:
                for tc in delta_tool_calls:
                    idx = getattr(tc, "index", 0) or 0
                    frag = tool_frags.setdefault(
                        idx, {"id": None, "name": None, "args": ""}
                    )
                    tc_id = getattr(tc, "id", None)
                    if tc_id:
                        frag["id"] = tc_id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        fn_name = getattr(fn, "name", None)
                        fn_args = getattr(fn, "arguments", None)
                        if fn_name:
                            frag["name"] = fn_name
                        if fn_args:
                            frag["args"] += fn_args

        tool_calls = self._assemble_tool_calls(tool_frags)
        yield CompletionResponse(
            text=full_text,
            tool_calls=tool_calls,
            stop_reason=finish_reason_to_stop_reason(
                finish_reason, has_tool_calls=bool(tool_calls)
            ),
            model=model,
            usage=usage,
        )

    def _assemble_tool_calls(
        self,
        frags: dict[int, dict[str, Any]],
    ) -> list[LLMToolCall]:
        result: list[LLMToolCall] = []
        for idx in sorted(frags):
            frag = frags[idx]
            if not frag["name"]:
                continue
            args: dict[str, Any] = {}
            if frag["args"]:
                try:
                    args = json.loads(frag["args"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
            result.append(
                LLMToolCall(id=frag["id"] or "", name=frag["name"], arguments=args)
            )
        return result

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

        Импорт модуля litellm.exceptions лениво — избегаем жёсткой
        зависимости от точных классов исключений litellm.
        """
        try:
            from litellm.exceptions import (
                AuthenticationError,
                BadRequestError,
                RateLimitError,
                ServiceUnavailableError,
            )
            from litellm.exceptions import (
                Timeout as LiteLLMTimeout,
            )
        except ImportError:
            return ProviderError(
                message=str(exc),
                error_type=ProviderErrorType.UNKNOWN,
                provider_id=self.name,
            )

        if isinstance(exc, AuthenticationError):
            return ProviderError(
                message=str(exc),
                error_type=ProviderErrorType.AUTH_ERROR,
                provider_id=self.name,
                retryable=False,
            )
        if isinstance(exc, RateLimitError):
            return ProviderError(
                message=str(exc),
                error_type=ProviderErrorType.RATE_LIMIT,
                provider_id=self.name,
                retryable=True,
            )
        if isinstance(exc, LiteLLMTimeout):
            return ProviderError(
                message=str(exc),
                error_type=ProviderErrorType.TIMEOUT,
                provider_id=self.name,
                retryable=True,
            )
        if isinstance(exc, ServiceUnavailableError):
            return ProviderError(
                message=str(exc),
                error_type=ProviderErrorType.SERVICE_UNAVAILABLE,
                provider_id=self.name,
                retryable=True,
            )
        if isinstance(exc, BadRequestError):
            return ProviderError(
                message=str(exc),
                error_type=ProviderErrorType.INVALID_REQUEST,
                provider_id=self.name,
                retryable=False,
            )

        return ProviderError(
            message=str(exc),
            error_type=ProviderErrorType.UNKNOWN,
            provider_id=self.name,
        )

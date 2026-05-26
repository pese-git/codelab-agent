"""Mock LLM провайдер для тестирования.

Использует новые модели (CompletionRequest/Response вместо dict).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog

from codelab.server.llm.base import (
    LLMCapabilities,
    LLMConfig,
    LLMProvider,
)
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMToolCall,
    StopReason,
)

logger = structlog.get_logger()


class MockLLMProvider(LLMProvider):
    """Mock провайдер для unit-тестирования.

    Возвращает предсказуемые ответы для тестирования логики агента
    без обращения к реальному API.
    """

    def __init__(
        self,
        response: str = "Mock response",
        tool_calls: list[LLMToolCall] | None = None,
    ) -> None:
        """Инициализация mock провайдера.

        Args:
            response: Текст ответа, который будет возвращен
            tool_calls: Список tool calls для возврата
        """
        self._response = response
        self._tool_calls = tool_calls or []
        self._config: LLMConfig | None = None
        self.last_request: CompletionRequest | None = None

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "mock"

    @property
    def capabilities(self) -> LLMCapabilities:
        """Возможности провайдера."""
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_function_calling=True,
        )

    async def initialize(self, config: LLMConfig) -> None:
        """Mock инициализация."""
        self._config = config
        logger.debug("mock llm provider initialized", config=config)

    async def create_completion(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Вернуть mock ответ."""
        self.last_request = request

        logger.debug(
            "mock llm create_completion called",
            num_messages=len(request.messages),
            num_tools=len(request.tools) if request.tools else 0,
        )

        return CompletionResponse(
            text=self._response,
            tool_calls=self._tool_calls,
            stop_reason=StopReason.END_TURN if not self._tool_calls else StopReason.TOOL_USE,
            model=request.model,
        )

    async def stream_completion(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionResponse, None]:
        """Вернуть mock потоковый ответ."""
        self.last_request = request

        logger.debug(
            "mock llm stream_completion called",
            num_messages=len(request.messages),
        )

        yield CompletionResponse(
            text=self._response,
            tool_calls=self._tool_calls,
            stop_reason=StopReason.END_TURN if not self._tool_calls else StopReason.TOOL_USE,
            model=request.model,
        )

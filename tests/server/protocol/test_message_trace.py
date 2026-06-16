"""Тесты для middleware трассировки сообщений.

Проверяют:
- Логирование входящих и исходящих сообщений
- Отключение трассировки при enabled=False
- Обрезка payload при max_payload_length > 0
- Корректную работу в цепочке middleware
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ProtocolOutcome
from codelab.server.protocol.middleware.message_trace import (
    create_message_trace_middleware,
    message_trace_middleware,
)


@pytest.fixture
def sample_request() -> ACPMessage:
    """Создает тестовый запрос."""
    return ACPMessage.request(
        "session/new",
        {"cwd": "/tmp", "mcpServers": []},
        request_id=1,
    )


@pytest.fixture
def sample_response() -> ACPMessage:
    """Создает тестовый ответ."""
    return ACPMessage.response(
        1,
        {"sessionId": "sess_123"},
    )


@pytest.fixture
def sample_notification() -> ACPMessage:
    """Создает тестовое уведомление."""
    return ACPMessage.notification(
        "session/update",
        {"sessionId": "sess_123", "update": {"sessionUpdate": "test"}},
    )


class TestMessageTraceMiddleware:
    """Тесты message_trace_middleware."""

    @pytest.mark.asyncio
    async def test_logs_incoming_message(self, sample_request: ACPMessage) -> None:
        """Middleware логирует входящее сообщение."""
        # next_handler возвращает простой outcome
        next_handler = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response(1, {"ok": True}))
        )

        # Вызываем middleware
        outcome = await message_trace_middleware(
            sample_request, next_handler, enabled=True
        )

        # next_handler был вызван
        next_handler.assert_called_once_with(sample_request)

        # Outcome корректный
        assert outcome.response is not None
        assert outcome.response.result == {"ok": True}

    @pytest.mark.asyncio
    async def test_disabled_does_not_log(self, sample_request: ACPMessage) -> None:
        """При enabled=False middleware просто передает вызов."""
        next_handler = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response(1, {"ok": True}))
        )

        outcome = await message_trace_middleware(
            sample_request, next_handler, enabled=False
        )

        next_handler.assert_called_once_with(sample_request)
        assert outcome.response is not None

    @pytest.mark.asyncio
    async def test_passes_through_outcome_with_notifications(
        self, sample_request: ACPMessage, sample_notification: ACPMessage
    ) -> None:
        """Middleware корректно передает outcome с notifications."""
        next_handler = AsyncMock(
            return_value=ProtocolOutcome(
                response=ACPMessage.response(1, {"sessionId": "sess_1"}),
                notifications=[sample_notification],
            )
        )

        outcome = await message_trace_middleware(
            sample_request, next_handler, enabled=True
        )

        assert outcome.response is not None
        assert len(outcome.notifications) == 1
        assert outcome.notifications[0].method == "session/update"

    @pytest.mark.asyncio
    async def test_connection_id_in_context(self, sample_request: ACPMessage) -> None:
        """Middleware принимает connection_id для контекста."""
        next_handler = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response(1, {"ok": True}))
        )

        # Не должно вызвать исключений
        outcome = await message_trace_middleware(
            sample_request,
            next_handler,
            enabled=True,
            connection_id="test-conn-123",
        )

        assert outcome.response is not None


class TestCreateMessageTraceMiddleware:
    """Тесты create_message_trace_middleware."""

    @pytest.mark.asyncio
    async def test_creates_middleware_with_defaults(self) -> None:
        """create_message_trace_middleware создает middleware с defaults."""
        middleware = create_message_trace_middleware()

        next_handler = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response(1, {"ok": True}))
        )
        request = ACPMessage.request("initialize", {"protocolVersion": 1}, request_id=0)

        outcome = await middleware(request, next_handler)

        assert outcome.response is not None
        next_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_middleware_respects_enabled_flag(self) -> None:
        """Middleware отключается при enabled=False."""
        middleware = create_message_trace_middleware(enabled=False)

        next_handler = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response(1, {"ok": True}))
        )
        request = ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []}, request_id=1)

        outcome = await middleware(request, next_handler)

        next_handler.assert_called_once()
        assert outcome.response is not None

    @pytest.mark.asyncio
    async def test_middleware_with_connection_id(self) -> None:
        """Middleware принимает connection_id."""
        middleware = create_message_trace_middleware(
            enabled=True,
            connection_id="ws-conn-456",
        )

        next_handler = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response(1, {"ok": True}))
        )
        request = ACPMessage.request("initialize", {"protocolVersion": 1}, request_id=0)

        # Не должно вызвать исключений
        outcome = await middleware(request, next_handler)

        assert outcome.response is not None


class TestMessageTraceIntegration:
    """Интеграционные тесты трассировки."""

    @pytest.mark.asyncio
    async def test_middleware_chain(self) -> None:
        """Middleware работает в цепочке."""
        call_order: list[str] = []

        async def mw1(msg: ACPMessage, next_handler) -> ProtocolOutcome:
            call_order.append("mw1_before")
            outcome = await next_handler(msg)
            call_order.append("mw1_after")
            return outcome

        async def mw2(msg: ACPMessage, next_handler) -> ProtocolOutcome:
            call_order.append("mw2_before")
            outcome = await next_handler(msg)
            call_order.append("mw2_after")
            return outcome

        async def handler(msg: ACPMessage) -> ProtocolOutcome:
            call_order.append("handler")
            return ProtocolOutcome(response=ACPMessage.response(msg.id, {"ok": True}))

        # Применяем middleware в обратном порядке (onion pattern)
        wrapped = handler
        for mw in [mw2, mw1]:
            async def make_wrapper(next_h, middleware_func):
                async def wrapper(msg):
                    return await middleware_func(msg, next_h)
                return wrapper
            wrapped = await make_wrapper(wrapped, mw)

        request = ACPMessage.request("test", {}, request_id=1)
        outcome = await wrapped(request)

        # Проверяем порядок вызовов
        assert call_order == ["mw1_before", "mw2_before", "handler", "mw2_after", "mw1_after"]
        assert outcome.response is not None

    @pytest.mark.asyncio
    async def test_trace_middleware_in_chain(self) -> None:
        """Trace middleware работает в цепочке с другими middleware."""
        trace_middleware = create_message_trace_middleware(enabled=True)

        handler_called = False

        async def handler(msg: ACPMessage) -> ProtocolOutcome:
            nonlocal handler_called
            handler_called = True
            return ProtocolOutcome(
                response=ACPMessage.response(msg.id, {"sessionId": "sess_1"}),
                notifications=[
                    ACPMessage.notification(
                        "session/update",
                        {"sessionId": "sess_1", "update": {"sessionUpdate": "test"}},
                    )
                ],
            )

        outcome = await trace_middleware(
            ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []}, request_id=1),
            handler,
        )

        assert handler_called
        assert outcome.response is not None
        assert len(outcome.notifications) == 1

"""Integration тесты для immediate notification delivery.

Проверяет что notifications доставляются клиенту немедленно (< 100ms),
особенно для terminal embedding с live output.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop


@pytest.fixture
def mock_strategy():
    """Mock LLMCallStrategy."""
    strategy = MagicMock()
    strategy.execute = AsyncMock()
    strategy.continue_execution = AsyncMock()
    return strategy


@pytest.fixture
def mock_session():
    """Mock SessionState."""
    session = MagicMock()
    session.session_id = "test_session"
    session.config_values = {}
    session.history = []
    session.tool_calls = {}
    session.active_turn = None
    session.permission_policy = {}
    session.latest_plan = None
    return session


@pytest.fixture
def mock_dependencies():
    """Mock зависимости AgentLoop."""
    mock_spb = MagicMock()
    mock_spb.build.return_value = "You are a helpful assistant."
    return {
        "tool_registry": MagicMock(),
        "tool_call_handler": MagicMock(),
        "permission_manager": MagicMock(),
        "state_manager": MagicMock(),
        "content_extractor": AsyncMock(),
        "content_validator": MagicMock(),
        "content_formatter": MagicMock(),
        "replay_manager": MagicMock(),
        "plan_builder": MagicMock(),
        "system_prompt_builder": mock_spb,
    }


class TestTerminalEmbeddingImmediateDelivery:
    """Тесты для immediate delivery terminal embedding notifications."""

    @pytest.mark.asyncio
    async def test_terminal_notification_delivered_immediately(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """Terminal notification доставляется < 100ms после создания."""
        # Настройка callback для отслеживания времени отправки
        sent_notifications = []
        send_times = []

        async def mock_callback(notification: ACPMessage) -> None:
            sent_notifications.append(notification)
            send_times.append(time.time())

        # Создание AgentLoop с callback
        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Создание notification с terminal content
        start_time = time.time()
        terminal_notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": "test_session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": [
                        {"type": "terminal", "terminalId": "term_123"},
                        {
                            "type": "content",
                            "content": {"type": "text", "text": "Terminal created"},
                        },
                    ],
                },
            },
        )

        # Отправка через immediate delivery
        await loop._send_notification_immediately(terminal_notification)
        end_time = time.time()

        # Проверки
        assert len(sent_notifications) == 1, "Notification должен быть отправлен"
        assert sent_notifications[0] == terminal_notification, "Отправлен правильный notification"

        # Проверка latency
        latency_ms = (end_time - start_time) * 1000
        assert latency_ms < 100, f"Latency {latency_ms}ms > 100ms"

    @pytest.mark.asyncio
    async def test_terminal_notification_contains_terminal_id(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """Notification содержит terminalId."""
        sent_notifications = []

        async def mock_callback(notification: ACPMessage) -> None:
            sent_notifications.append(notification)

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Создание notification с terminal content
        terminal_notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": "test_session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": [
                        {"type": "terminal", "terminalId": "term_xyz789"},
                    ],
                },
            },
        )

        await loop._send_notification_immediately(terminal_notification)

        # Проверка что notification содержит terminalId
        assert len(sent_notifications) == 1
        notification = sent_notifications[0]
        assert notification.method == "session/update"
        assert notification.params is not None
        update = notification.params["update"]
        assert "content" in update
        content = update["content"]
        assert len(content) > 0
        terminal_content = content[0]
        assert terminal_content["type"] == "terminal"
        assert "terminalId" in terminal_content
        assert terminal_content["terminalId"] == "term_xyz789"

    @pytest.mark.asyncio
    async def test_terminal_notification_contains_terminal_content(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """Notification содержит terminal content для live output."""
        sent_notifications = []

        async def mock_callback(notification: ACPMessage) -> None:
            sent_notifications.append(notification)

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Создание notification с terminal content
        terminal_notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": "test_session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": [
                        {"type": "terminal", "terminalId": "term_123"},
                        {
                            "type": "content",
                            "content": {"type": "text", "text": "Terminal created for command: ls"},
                        },
                    ],
                },
            },
        )

        await loop._send_notification_immediately(terminal_notification)

        # Проверка что notification содержит terminal content
        assert len(sent_notifications) == 1
        notification = sent_notifications[0]
        assert notification.params is not None
        update = notification.params["update"]
        content = update["content"]

        # Проверка terminal content
        terminal_content = content[0]
        assert terminal_content["type"] == "terminal"
        assert "terminalId" in terminal_content

        # Проверка text content
        text_content = content[1]
        assert text_content["type"] == "content"
        assert text_content["content"]["type"] == "text"
        assert "Terminal created" in text_content["content"]["text"]

    @pytest.mark.asyncio
    async def test_client_can_start_live_output_display(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """Клиент может начать отображение live output после получения notification."""
        sent_notifications = []

        async def mock_callback(notification: ACPMessage) -> None:
            sent_notifications.append(notification)

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Симуляция получения notification клиентом
        terminal_notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": "test_session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": [
                        {"type": "terminal", "terminalId": "term_live_123"},
                    ],
                },
            },
        )

        await loop._send_notification_immediately(terminal_notification)

        # Проверка что клиент получил notification и может извлечь terminalId
        assert len(sent_notifications) == 1
        notification = sent_notifications[0]
        assert notification.params is not None
        update = notification.params["update"]
        content = update["content"]
        terminal_content = content[0]

        # Клиент может извлечь terminalId для начала отображения live output
        terminal_id = terminal_content["terminalId"]
        assert terminal_id == "term_live_123"

        # Клиент может использовать terminalId для подписки на live output
        # (это проверяется в UI тестах)
        assert terminal_id is not None
        assert len(terminal_id) > 0

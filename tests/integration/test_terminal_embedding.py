"""Integration тест для terminal embedding.

Проверяет полный pipeline:
1. TerminalToolExecutor создаёт терминал и возвращает terminal content
2. ContentExtractor извлекает content из результата
3. ContentValidator валидирует content
4. AgentLoop передаёт content в notification
5. Клиентский ToolCallHandler сохраняет content
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.state import SessionState
from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker


@pytest.fixture
def session() -> SessionState:
    """Создает тестовую сессию."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        config_values={},
    )


@pytest.fixture
def executor() -> TerminalToolExecutor:
    """Создает executor с mock зависимостями."""
    mock_bridge = MagicMock(spec=ClientRPCBridge)
    mock_checker = MagicMock(spec=PermissionChecker)
    return TerminalToolExecutor(mock_bridge, mock_checker)


class TestTerminalEmbeddingIntegration:
    """Integration тесты для terminal embedding."""

    @pytest.mark.asyncio
    async def test_terminal_tool_full_pipeline(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """Полный pipeline: executor → extractor → validator → notification."""
        # Arrange: Mock bridge возвращает terminal_id
        executor._bridge.create_terminal = AsyncMock(return_value="term_integration")

        # Act 1: Executor создаёт терминал
        result = await executor.execute_create(
            session=session,
            command="npm test",
        )

        # Assert 1: Результат содержит terminal content
        assert result.success is True
        assert result.content is not None
        assert len(result.content) == 2
        assert result.content[0]["type"] == "terminal"
        assert result.content[0]["terminalId"] == "term_integration"

        # Act 2: ContentExtractor извлекает content
        extractor = ContentExtractor()
        extracted = await extractor.extract_from_result("tc_001", result)

        # Assert 2: Extracted content содержит terminal items
        assert extracted.has_content is True
        assert extracted.content_items == result.content

        # Act 3: ContentValidator валидирует content
        validator = ContentValidator()
        is_valid, errors = validator.validate_content_list(extracted.content_items)

        # Assert 3: Content проходит валидацию
        assert is_valid is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_terminal_content_preserved_through_client_handler(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """Terminal content сохраняется в клиентском ToolCallHandler."""
        # Arrange
        executor._bridge.create_terminal = AsyncMock(return_value="term_client")

        # Act 1: Executor создаёт терминал
        result = await executor.execute_create(
            session=session,
            command="ls -la",
        )

        # Act 2: Имитируем notification от сервера
        notification_content = result.content

        # Act 3: Клиентский handler обрабатывает notification
        handler = ToolCallHandler()
        mock_context = MagicMock()
        mock_context.session_id = "test_session"
        mock_context.state = MagicMock()
        mock_context.state.add_tool_call = MagicMock()
        mock_context.state.update_tool_call = MagicMock()
        mock_context.state.tool_calls = []
        mock_context.sink = None
        mock_context.logger = MagicMock()

        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tc_client",
                    "title": "terminal/create",
                    "status": "completed",
                    "kind": "execute",
                    "content": notification_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Assert: Content сохранён в состоянии
        mock_context.state.add_tool_call.assert_called_once()
        tool_call = mock_context.state.add_tool_call.call_args[0][0]
        assert "content" in tool_call
        assert tool_call["content"] == notification_content
        assert tool_call["content"][0]["type"] == "terminal"
        assert tool_call["content"][0]["terminalId"] == "term_client"

    @pytest.mark.asyncio
    async def test_terminal_content_update_preserved(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """Terminal content обновляется в клиентском ToolCallHandler."""
        # Arrange
        handler = ToolCallHandler()
        mock_context = MagicMock()
        mock_context.session_id = "test_session"
        mock_context.state = MagicMock()
        mock_context.state.add_tool_call = MagicMock()
        mock_context.state.update_tool_call = MagicMock()
        mock_context.state.tool_calls = []
        mock_context.sink = None
        mock_context.logger = MagicMock()

        # Act: Обновление с terminal content
        terminal_content = [
            {"type": "terminal", "terminalId": "term_update"},
        ]
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "tc_update",
                    "status": "completed",
                    "content": terminal_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Assert: Content обновлён
        mock_context.state.update_tool_call.assert_called_once()
        call_kwargs = mock_context.state.update_tool_call.call_args[1]
        assert "content" in call_kwargs
        assert call_kwargs["content"] == terminal_content

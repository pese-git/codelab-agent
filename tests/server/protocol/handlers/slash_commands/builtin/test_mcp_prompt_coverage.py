"""Дополнительные тесты покрытия для MCPPromptCommandHandler.

Покрывает sync-версию execute, fallback при отсутствии event loop
и конвертацию объектных MCP-сообщений.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from codelab.server.protocol.handlers.slash_commands.builtin.mcp_prompt import (
    MCPPromptCommandHandler,
)


class DummyMessage:
    """MCP-сообщение-объект с role и content."""

    def __init__(self, role: str, content: object) -> None:
        self.role = role
        self.content = content


@pytest.fixture
def handler() -> MCPPromptCommandHandler:
    """Создает handler с mock-менеджером."""
    return MCPPromptCommandHandler(
        server_id="server1",
        prompt_name="test_prompt",
        mcp_manager=MagicMock(),
        description="Test prompt",
    )


class TestMCPPromptCommandHandlerExecute:
    """Тесты sync-метода execute."""

    def test_execute_sync_returns_async_required(self, handler: MCPPromptCommandHandler) -> None:
        """_execute_sync возвращает предупреждение о необходимости async."""
        result = handler._execute_sync([])

        assert len(result.content) == 1
        assert "async" in result.content[0]["text"].lower()
        assert result.stop_reason == "end_turn"

    def test_execute_runtime_error_uses_sync_fallback(
        self,
        handler: MCPPromptCommandHandler,
    ) -> None:
        """При RuntimeError execute переходит к sync fallback."""
        with patch.object(asyncio, "get_event_loop", side_effect=RuntimeError):
            result = handler.execute([], MagicMock())

        assert "async" in result.content[0]["text"].lower()

    def test_execute_without_running_loop_runs_async(
        self,
        handler: MCPPromptCommandHandler,
    ) -> None:
        """Если loop не запущен, execute запускает _execute_async через run_until_complete."""
        loop = MagicMock()
        loop.is_running.return_value = False
        async_result = MagicMock()
        loop.run_until_complete.return_value = async_result

        with patch.object(asyncio, "get_event_loop", return_value=loop):
            result = handler.execute(["arg"], MagicMock())

        assert result is async_result
        loop.run_until_complete.assert_called_once()
        call_arg = loop.run_until_complete.call_args[0][0]
        # run_until_complete получает coroutine от _execute_async
        assert call_arg.__name__ == handler._execute_async.__name__

    async def test_execute_with_running_loop_uses_executor(
        self,
        handler: MCPPromptCommandHandler,
    ) -> None:
        """Если loop запущен, execute использует run_in_executor и fallback."""
        result = handler.execute([], MagicMock())

        assert len(result.content) == 1
        assert "async" in result.content[0]["text"].lower()


class TestMCPPromptCommandHandlerConvertObjectMessages:
    """Тесты конвертации объектных MCP-сообщений."""

    def test_convert_object_message_with_string_content(self) -> None:
        """Сообщение-объект с не-dict content конвертируется через str."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        messages = [
            DummyMessage("assistant", "plain text"),
            DummyMessage("user", 42),
        ]

        content = handler._convert_messages_to_content(messages)

        assert len(content) == 2
        assert content[0]["text"] == "plain text"
        assert "**User:**" in content[1]["text"]
        assert "42" in content[1]["text"]

    def test_convert_object_message_with_dict_content(self) -> None:
        """Сообщение-объект с dict content извлекает text."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        messages = [DummyMessage("assistant", {"text": "nested text"})]

        content = handler._convert_messages_to_content(messages)

        assert len(content) == 1
        assert content[0]["text"] == "nested text"

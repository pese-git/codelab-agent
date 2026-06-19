"""Integration тесты для ToolCallHandler с FollowAlongService."""

import asyncio
from unittest.mock import MagicMock

import pytest

from codelab.client.infrastructure.services.follow_along import (
    FollowAlongService,
    StubFileOpener,
)
from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler


class TestToolCallHandlerWithFollowAlong:
    """Тесты интеграции ToolCallHandler с FollowAlongService."""

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Создать mock контекст."""
        context = MagicMock()
        context.session_id = "test-session"
        context.state = MagicMock()
        context.state.add_tool_call = MagicMock()
        context.state.update_tool_call = MagicMock()
        context.sink = None
        context.logger = MagicMock()
        return context

    @pytest.fixture
    def stub_opener(self) -> StubFileOpener:
        """Создать stub file opener."""
        return StubFileOpener()

    @pytest.fixture
    def follow_along_service(self, stub_opener: StubFileOpener) -> FollowAlongService:
        """Создать follow-along сервис."""
        return FollowAlongService(stub_opener, enabled=True)

    @pytest.fixture
    def handler_with_follow_along(
        self, follow_along_service: FollowAlongService
    ) -> ToolCallHandler:
        """Создать handler с follow-along сервисом."""
        return ToolCallHandler(follow_along=follow_along_service)

    @pytest.fixture
    def handler_without_follow_along(self) -> ToolCallHandler:
        """Создать handler без follow-along сервиса."""
        return ToolCallHandler()

    def test_tool_call_created_saves_locations(
        self, handler_with_follow_along: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """Tool call created сохраняет locations."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_001",
                    "title": "Read file",
                    "status": "pending",
                    "kind": "read",
                    "locations": [{"path": "/tmp/test.py", "line": 10}],
                    "rawInput": {"path": "/tmp/test.py"},
                }
            }
        }

        handler_with_follow_along.handle(update_data, mock_context)

        # Проверяем, что add_tool_call был вызван с locations
        mock_context.state.add_tool_call.assert_called_once()
        tool_call = mock_context.state.add_tool_call.call_args[0][0]
        assert tool_call["locations"] == [{"path": "/tmp/test.py", "line": 10}]
        assert tool_call["rawInput"] == {"path": "/tmp/test.py"}

    @pytest.mark.asyncio
    async def test_tool_call_updated_triggers_follow_along(
        self,
        handler_with_follow_along: ToolCallHandler,
        stub_opener: StubFileOpener,
        mock_context: MagicMock,
    ) -> None:
        """Tool call updated вызывает follow-along сервис."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "locations": [{"path": "/tmp/test.py", "line": 42}],
                }
            }
        }

        handler_with_follow_along.handle(update_data, mock_context)

        # Даем время для выполнения asyncio task
        await asyncio.sleep(0.01)

        # Проверяем, что file opener был вызван
        assert len(stub_opener.calls) == 1
        assert stub_opener.calls[0]["path"] == "/tmp/test.py"
        assert stub_opener.calls[0]["line"] == 42

    @pytest.mark.asyncio
    async def test_tool_call_updated_without_locations_does_not_trigger_follow_along(
        self,
        handler_with_follow_along: ToolCallHandler,
        stub_opener: StubFileOpener,
        mock_context: MagicMock,
    ) -> None:
        """Tool call updated без locations не вызывает follow-along."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                }
            }
        }

        handler_with_follow_along.handle(update_data, mock_context)

        # Даем время для выполнения asyncio task
        await asyncio.sleep(0.01)

        # Проверяем, что file opener не был вызван
        assert len(stub_opener.calls) == 0

    @pytest.mark.asyncio
    async def test_handler_without_follow_along_does_not_crash(
        self, handler_without_follow_along: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """Handler без follow-along не падает при tool call updated."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "locations": [{"path": "/tmp/test.py", "line": 10}],
                }
            }
        }

        # Не должно вызвать исключение
        handler_without_follow_along.handle(update_data, mock_context)

        # Даем время для выполнения asyncio task (если бы они были)
        await asyncio.sleep(0.01)

        # Проверяем, что update_tool_call был вызван
        mock_context.state.update_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_call_updated_with_multiple_locations_opens_first(
        self,
        handler_with_follow_along: ToolCallHandler,
        stub_opener: StubFileOpener,
        mock_context: MagicMock,
    ) -> None:
        """Tool call updated с несколькими locations открывает первый файл."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "locations": [
                        {"path": "/tmp/first.py", "line": 10},
                        {"path": "/tmp/second.py", "line": 20},
                    ],
                }
            }
        }

        handler_with_follow_along.handle(update_data, mock_context)

        # Даем время для выполнения asyncio task
        await asyncio.sleep(0.01)

        # Проверяем, что был открыт только первый файл
        assert len(stub_opener.calls) == 1
        assert stub_opener.calls[0]["path"] == "/tmp/first.py"
        assert stub_opener.calls[0]["line"] == 10

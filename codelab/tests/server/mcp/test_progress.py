"""Тесты для MCP progress notifications.

Покрывают:
- MCPProgressNotification модель
- Progress notification обработку в MCPClient
- Progress callback регистрацию и вызов
- Progress notification проксирование через MCPManager
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.mcp.client import MCPClient
from codelab.server.mcp.manager import MCPManager
from codelab.server.mcp.models import MCPProgressNotification, MCPServerConfig


class TestMCPProgressNotification:
    """Тесты модели MCPProgressNotification."""

    def test_create_basic_progress(self) -> None:
        """Базовое создание progress notification."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=50.0,
        )

        assert progress.progress_token == "token-123"
        assert progress.progress == 50.0
        assert progress.total is None
        assert progress.message is None

    def test_create_progress_with_total(self) -> None:
        """Progress notification с total."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=2.0,
            total=5.0,
        )

        assert progress.progress == 2.0
        assert progress.total == 5.0

    def test_create_progress_with_message(self) -> None:
        """Progress notification с message."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=1.0,
            total=10.0,
            message="Processing files...",
        )

        assert progress.message == "Processing files..."

    def test_percentage_with_total(self) -> None:
        """Вычисление percentage с total."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=2.0,
            total=5.0,
        )

        assert progress.percentage == 40.0

    def test_percentage_without_total_normalized(self) -> None:
        """Вычисление percentage без total (нормализованное 0-1)."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=0.5,
        )

        assert progress.percentage == 50.0

    def test_percentage_without_total_not_normalized(self) -> None:
        """Progress больше 1.0 без total возвращает None."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=50.0,
        )

        assert progress.percentage is None

    def test_percentage_capped_at_100(self) -> None:
        """Percentage не превышает 100%."""
        progress = MCPProgressNotification(
            progress_token="token-123",
            progress=10.0,
            total=5.0,
        )

        assert progress.percentage == 100.0

    def test_deserialization_from_camel_case(self) -> None:
        """Десериализация из camelCase (от MCP сервера)."""
        data = {
            "progressToken": "token-abc",
            "progress": 3.0,
            "total": 10.0,
            "message": "Working...",
        }

        progress = MCPProgressNotification.model_validate(data)

        assert progress.progress_token == "token-abc"
        assert progress.progress == 3.0
        assert progress.total == 10.0
        assert progress.message == "Working..."

    def test_serialization_to_camel_case(self) -> None:
        """Сериализация в camelCase."""
        progress = MCPProgressNotification(
            progress_token="token-xyz",
            progress=1.0,
            total=2.0,
            message="Done",
        )

        data = progress.model_dump(by_alias=True)

        assert "progressToken" in data
        assert data["progressToken"] == "token-xyz"


class TestMCPClientProgressCallbacks:
    """Тесты progress callbacks в MCPClient."""

    @pytest.mark.asyncio
    async def test_register_progress_callback(self) -> None:
        """Регистрация progress callback."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="test",
        )
        client = MCPClient(config)

        callback = AsyncMock()
        client.register_progress_callback(callback)

        assert callback in client._progress_callbacks

    @pytest.mark.asyncio
    async def test_handle_progress_notification_calls_callbacks(self) -> None:
        """_handle_progress_notification вызывает callbacks."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="test",
        )
        client = MCPClient(config)

        callback = AsyncMock()
        client.register_progress_callback(callback)

        progress_params = {
            "progressToken": "token-123",
            "progress": 5.0,
            "total": 10.0,
        }

        await client._handle_progress_notification(progress_params)

        callback.assert_called_once()
        call_arg = callback.call_args[0][0]
        assert isinstance(call_arg, MCPProgressNotification)
        assert call_arg.progress_token == "token-123"
        assert call_arg.progress == 5.0

    @pytest.mark.asyncio
    async def test_handle_progress_notification_sync_callback(self) -> None:
        """_handle_progress_notification поддерживает sync callbacks."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="test",
        )
        client = MCPClient(config)

        callback = MagicMock()
        client.register_progress_callback(callback)

        progress_params = {
            "progressToken": "token-456",
            "progress": 1.0,
        }

        await client._handle_progress_notification(progress_params)

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_progress_notification_invalid_params(self) -> None:
        """_handle_progress_notification обрабатывает невалидные params."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="test",
        )
        client = MCPClient(config)

        callback = AsyncMock()
        client.register_progress_callback(callback)

        # Невалидные params (нет progressToken)
        invalid_params = {"progress": 1.0}

        # Не должно вызвать callback, но и не должно упасть
        await client._handle_progress_notification(invalid_params)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_progress_notification_callback_error(self) -> None:
        """_handle_progress_notification обрабатывает ошибки в callback."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="test",
        )
        client = MCPClient(config)

        callback = AsyncMock(side_effect=Exception("Callback error"))
        client.register_progress_callback(callback)

        progress_params = {
            "progressToken": "token-789",
            "progress": 1.0,
        }

        # Не должно упасть
        await client._handle_progress_notification(progress_params)

        callback.assert_called_once()


class TestMCPManagerProgressCallbacks:
    """Тесты progress callbacks в MCPManager."""

    @pytest.mark.asyncio
    async def test_register_progress_callback(self) -> None:
        """Регистрация progress callback в manager."""
        manager = MCPManager("session-123")

        callback = AsyncMock()
        manager.register_progress_callback(callback)

        assert callback in manager._progress_callbacks

    @pytest.mark.asyncio
    async def test_on_progress_calls_callbacks(self) -> None:
        """_on_progress вызывает callbacks с server_id."""
        manager = MCPManager("session-123")

        callback = AsyncMock()
        manager.register_progress_callback(callback)

        progress = MCPProgressNotification(
            progress_token="token-mgr",
            progress=3.0,
            total=10.0,
        )

        await manager._on_progress("test-server", progress)

        callback.assert_called_once_with("test-server", progress)

    @pytest.mark.asyncio
    async def test_on_progress_multiple_callbacks(self) -> None:
        """_on_progress вызывает все зарегистрированные callbacks."""
        manager = MCPManager("session-123")

        callback1 = AsyncMock()
        callback2 = AsyncMock()
        manager.register_progress_callback(callback1)
        manager.register_progress_callback(callback2)

        progress = MCPProgressNotification(
            progress_token="token-multi",
            progress=1.0,
        )

        await manager._on_progress("server-a", progress)

        callback1.assert_called_once()
        callback2.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_progress_callback_error(self) -> None:
        """_on_progress обрабатывает ошибки в callback."""
        manager = MCPManager("session-123")

        callback1 = AsyncMock(side_effect=Exception("Error 1"))
        callback2 = AsyncMock()
        manager.register_progress_callback(callback1)
        manager.register_progress_callback(callback2)

        progress = MCPProgressNotification(
            progress_token="token-err",
            progress=1.0,
        )

        # Не должно упасть
        await manager._on_progress("server-x", progress)

        callback1.assert_called_once()
        callback2.assert_called_once()

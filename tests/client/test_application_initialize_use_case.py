"""Тесты для InitializeUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.use_cases import InitializeUseCase


class TestInitializeUseCase:
    """Проверки сценария инициализации соединения с сервером."""

    @pytest.mark.asyncio
    async def test_execute_connects_and_sends_initialize_request(self) -> None:
        """UseCase подключается и отправляет initialize запрос."""
        transport = AsyncMock()
        transport.connect = AsyncMock()
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {
                "protocolVersion": "1.0",
                "serverCapabilities": {"sessionCapabilities": {"create": True}},
                "authMethods": [],
            },
        })
        transport.set_server_capabilities = Mock()

        use_case = InitializeUseCase(transport=transport)
        response = await use_case.execute()

        transport.connect.assert_awaited_once()
        transport.send.assert_awaited_once()
        transport.receive.assert_awaited_once()
        transport.set_server_capabilities.assert_called_once_with(
            {"sessionCapabilities": {"create": True}}
        )
        assert response.protocol_version == "1.0"
        assert response.server_capabilities == {"sessionCapabilities": {"create": True}}
        assert response.available_auth_methods == []

    @pytest.mark.asyncio
    async def test_execute_raises_on_server_error(self) -> None:
        """UseCase поднимает ошибку при server error."""
        transport = AsyncMock()
        transport.connect = AsyncMock()
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "error": {
                "code": -32600,
                "message": "Invalid Request",
            },
        })
        transport.disconnect = AsyncMock()

        use_case = InitializeUseCase(transport=transport)

        with pytest.raises(RuntimeError, match="Initialize failed"):
            await use_case.execute()

        transport.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_disconnects_on_connection_error(self) -> None:
        """UseCase отключается при ошибке подключения."""
        transport = AsyncMock()
        transport.connect = AsyncMock(side_effect=ConnectionError("Connection refused"))
        transport.disconnect = AsyncMock()

        use_case = InitializeUseCase(transport=transport)

        with pytest.raises(RuntimeError, match="Failed to initialize"):
            await use_case.execute()

        transport.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_handles_unexpected_exception(self) -> None:
        """UseCase обрабатывает непредвиденные исключения."""
        transport = AsyncMock()
        transport.connect = AsyncMock(side_effect=RuntimeError("Unexpected"))
        transport.disconnect = AsyncMock()

        use_case = InitializeUseCase(transport=transport)

        with pytest.raises(RuntimeError, match="Unexpected"):
            await use_case.execute()

    @pytest.mark.asyncio
    async def test_execute_extracts_auth_methods(self) -> None:
        """UseCase извлекает auth methods из ответа."""
        transport = AsyncMock()
        transport.connect = AsyncMock()
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {
                "protocolVersion": "1.0",
                "serverCapabilities": {},
                "authMethods": ["api_key", "oauth"],
            },
        })
        transport.set_server_capabilities = Mock()

        use_case = InitializeUseCase(transport=transport)
        response = await use_case.execute()

        assert response.available_auth_methods == ["api_key", "oauth"]

    @pytest.mark.asyncio
    async def test_execute_handles_missing_result(self) -> None:
        """UseCase обрабатывает отсутствие result в ответе."""
        transport = AsyncMock()
        transport.connect = AsyncMock()
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": None,
        })
        transport.set_server_capabilities = Mock()

        use_case = InitializeUseCase(transport=transport)
        response = await use_case.execute()

        assert response.server_capabilities == {}
        assert response.available_auth_methods == []

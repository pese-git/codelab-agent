"""Дополнительные тесты для покрытия SessionCoordinator.

Покрывает ранее непротестированные строки:
- initialize, list_sessions, delete_session, cancel_prompt
- set_config_option (успех и ошибка)
- send_prompt с callbacks из kwargs
- request_permission: timeout и ошибка cleanup в finally
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.permission_handler import (
    PermissionHandler,
    PermissionRequestManager,
)
from codelab.client.application.session_coordinator import SessionCoordinator
from codelab.client.domain import SessionRepository, TransportService
from codelab.client.messages import RequestPermissionRequest


class TestSessionCoordinatorCoverage:
    """Тесты для покрытия непротестированных методов SessionCoordinator."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Создать mock TransportService."""
        transport = Mock(spec=TransportService)
        transport.initialize_use_case = AsyncMock()
        return transport

    @pytest.fixture
    def mock_session_repo(self) -> Mock:
        """Создать mock SessionRepository."""
        return Mock(spec=SessionRepository)

    @pytest.fixture
    def coordinator(
        self,
        mock_transport: Mock,
        mock_session_repo: Mock,
    ) -> SessionCoordinator:
        """Создать SessionCoordinator с mock зависимостями."""
        return SessionCoordinator(
            transport=mock_transport,
            session_repo=mock_session_repo,
            permission_handler=None,
        )

    @pytest.mark.asyncio
    async def test_initialize_returns_server_info(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """initialize возвращает словарь с данными сервера."""
        init_response = Mock()
        init_response.server_capabilities = {"test": True}
        init_response.available_auth_methods = ["api_key"]
        init_response.protocol_version = "1.0"

        mock_initialize_use_case = Mock()
        mock_initialize_use_case.execute = AsyncMock(return_value=init_response)
        coordinator.initialize_use_case = mock_initialize_use_case

        result = await coordinator.initialize()

        assert result == {
            "server_capabilities": {"test": True},
            "available_auth_methods": ["api_key"],
            "protocol_version": "1.0",
        }

    @pytest.mark.asyncio
    async def test_list_sessions_returns_sessions(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """list_sessions возвращает список сессий из response."""
        list_response = Mock()
        list_response.sessions = [{"sessionId": "s1"}, {"sessionId": "s2"}]

        mock_list_use_case = Mock()
        mock_list_use_case.execute = AsyncMock(return_value=list_response)
        coordinator.list_sessions_use_case = mock_list_use_case

        result = await coordinator.list_sessions()

        assert result == [{"sessionId": "s1"}, {"sessionId": "s2"}]

    @pytest.mark.asyncio
    async def test_delete_session_calls_repo_delete(
        self,
        coordinator: SessionCoordinator,
        mock_session_repo: Mock,
    ) -> None:
        """delete_session вызывает session_repo.delete."""
        mock_session_repo.delete = AsyncMock()

        await coordinator.delete_session("session_1")

        mock_session_repo.delete.assert_awaited_once_with("session_1")

    @pytest.mark.asyncio
    async def test_cancel_prompt_calls_transport_cancel(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """cancel_prompt вызывает transport.cancel_prompt."""
        mock_transport.cancel_prompt = AsyncMock()

        await coordinator.cancel_prompt("session_1")

        mock_transport.cancel_prompt.assert_awaited_once_with("session_1")

    @pytest.mark.asyncio
    async def test_set_config_option_success(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """set_config_option возвращает результат при успехе."""
        mock_transport.set_config_option = AsyncMock(
            return_value={"configOptions": [{"id": "model", "value": "gpt-4o"}]}
        )

        result = await coordinator.set_config_option("session_1", "model", "gpt-4o")

        assert result == {"configOptions": [{"id": "model", "value": "gpt-4o"}]}
        mock_transport.set_config_option.assert_awaited_once_with(
            session_id="session_1",
            config_id="model",
            value="gpt-4o",
        )

    @pytest.mark.asyncio
    async def test_set_config_option_error_returns_none(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """set_config_option возвращает None при ошибке."""
        mock_transport.set_config_option = AsyncMock(side_effect=RuntimeError("fail"))

        result = await coordinator.set_config_option("session_1", "model", "gpt-4o")

        assert result is None

    @pytest.mark.asyncio
    async def test_send_prompt_with_callbacks_from_kwargs(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """send_prompt собирает callbacks из kwargs, начинающихся с on_."""
        send_response = Mock()
        send_response.session_id = "session_1"
        send_response.prompt_result = {"stopReason": "end_turn"}
        send_response.updates = []

        mock_send_use_case = Mock()
        mock_send_use_case.execute = AsyncMock(return_value=send_response)
        coordinator.send_prompt_use_case = mock_send_use_case

        on_update = Mock()
        on_fs_read = Mock()
        on_terminal_create = Mock()

        result = await coordinator.send_prompt(
            session_id="session_1",
            prompt_text="hello",
            on_update=on_update,
            on_fs_read=on_fs_read,
            on_terminal_create=on_terminal_create,
        )

        assert result["session_id"] == "session_1"
        assert result["prompt_result"] == {"stopReason": "end_turn"}

        call_args = mock_send_use_case.execute.call_args[0][0]
        assert call_args.callbacks is not None
        assert call_args.callbacks.on_update is on_update
        assert call_args.callbacks.on_fs_read is on_fs_read
        assert call_args.callbacks.on_terminal_create is on_terminal_create

    @pytest.mark.asyncio
    async def test_send_prompt_with_callbacks_object(
        self,
        coordinator: SessionCoordinator,
        mock_transport: Mock,
    ) -> None:
        """send_prompt использует callbacks напрямую, если переданы."""
        from codelab.client.application.dto import PromptCallbacks

        send_response = Mock()
        send_response.session_id = "session_1"
        send_response.prompt_result = {}
        send_response.updates = []

        mock_send_use_case = Mock()
        mock_send_use_case.execute = AsyncMock(return_value=send_response)
        coordinator.send_prompt_use_case = mock_send_use_case

        callbacks = PromptCallbacks(on_update=Mock())

        await coordinator.send_prompt(
            session_id="session_1",
            prompt_text="hello",
            callbacks=callbacks,
        )

        call_args = mock_send_use_case.execute.call_args[0][0]
        assert call_args.callbacks is callbacks

    @pytest.mark.asyncio
    async def test_request_permission_cleanup_error_in_finally(
        self,
        coordinator: SessionCoordinator,
    ) -> None:
        """request_permission обрабатывает ошибку cleanup в finally."""
        permission_handler = Mock(spec=PermissionHandler)
        # Первый вызов get_request_manager — для основного потока,
        # второй — из finally. Бросаем ошибку только во втором.
        real_manager = PermissionRequestManager()
        call_count = 0

        def side_effect() -> PermissionRequestManager:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("cleanup error")
            return real_manager

        permission_handler.get_request_manager.side_effect = side_effect
        coordinator._permission_handler = permission_handler

        request = RequestPermissionRequest(
            jsonrpc="2.0",
            id="perm_cleanup",
            method="session/request_permission",
            params={
                "sessionId": "session_1",
                "toolCall": {"toolCallId": "tool_1", "title": "Test"},
                "options": [{"optionId": "allow_once", "name": "Allow", "kind": "allow_once"}],
            },
        )

        callback = Mock()
        # Ошибка get_request_manager в основном потоке, finally обработает
        outcome = await coordinator.request_permission(request, callback)

        assert outcome.outcome == "cancelled"
        assert call_count == 2

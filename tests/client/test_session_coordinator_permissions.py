"""Тесты для SessionCoordinator методов управления permissions.

Проверяет:
- request_permission: запрос разрешения у пользователя
- resolve_permission: разрешение pending request
- cancel_permission: отмену pending request
- Обработку ошибок и edge cases
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from codelab.client.application.permission_handler import (
    PermissionHandler,
    PermissionRequest,
    PermissionRequestManager,
)
from codelab.client.application.session_coordinator import SessionCoordinator
from codelab.client.domain import SessionRepository, TransportService
from codelab.client.messages import (
    CancelledPermissionOutcome,
    PermissionOption,
    PermissionToolCall,
    RequestPermissionRequest,
    SelectedPermissionOutcome,
)

# Все тесты в этом модуле - async
pytestmark = pytest.mark.asyncio


class TestSessionCoordinatorPermissions:
    """Тесты для методов permission в SessionCoordinator."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        """Создать mock TransportService."""
        return Mock(spec=TransportService)

    @pytest.fixture
    def mock_session_repo(self) -> Mock:
        """Создать mock SessionRepository."""
        return Mock(spec=SessionRepository)

    @pytest.fixture
    def mock_permission_handler(self) -> Mock:
        """Создать mock PermissionHandler."""
        handler = Mock(spec=PermissionHandler)
        # Создать настоящий PermissionRequestManager для более реалистичных тестов
        handler.get_request_manager.return_value = PermissionRequestManager()
        return handler

    @pytest.fixture
    def coordinator_without_handler(
        self,
        mock_transport: Mock,
        mock_session_repo: Mock,
    ) -> SessionCoordinator:
        """Создать SessionCoordinator без permission_handler."""
        return SessionCoordinator(
            transport=mock_transport,
            session_repo=mock_session_repo,
            permission_handler=None,
        )

    @pytest.fixture
    def coordinator_with_handler(
        self,
        mock_transport: Mock,
        mock_session_repo: Mock,
        mock_permission_handler: Mock,
    ) -> SessionCoordinator:
        """Создать SessionCoordinator с permission_handler."""
        return SessionCoordinator(
            transport=mock_transport,
            session_repo=mock_session_repo,
            permission_handler=mock_permission_handler,
        )

    @pytest.fixture
    def sample_permission_request(self) -> RequestPermissionRequest:
        """Создать sample RequestPermissionRequest."""
        return RequestPermissionRequest(
            jsonrpc="2.0",
            id="perm_1",
            method="session/request_permission",
            params={
                "sessionId": "session_1",
                "toolCall": {
                    "toolCallId": "tool_1",
                    "title": "File Write",
                },
                "options": [
                    {
                        "optionId": "allow_once",
                        "name": "Allow once",
                        "kind": "allow_once",
                    },
                    {
                        "optionId": "reject_once",
                        "name": "Reject",
                        "kind": "reject_once",
                    },
                ],
            },
        )

    @pytest.mark.asyncio
    async def test_request_permission_without_handler(
        self,
        coordinator_without_handler: SessionCoordinator,
        sample_permission_request: RequestPermissionRequest,
    ) -> None:
        """request_permission возвращает CancelledPermissionOutcome если нет handler."""
        callback = Mock()

        outcome = await coordinator_without_handler.request_permission(
            request=sample_permission_request,
            callback=callback,
        )

        assert isinstance(outcome, CancelledPermissionOutcome)
        assert outcome.outcome == "cancelled"
        # Callback не должен быть вызван
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_permission_with_handler_success(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
        sample_permission_request: RequestPermissionRequest,
    ) -> None:
        """request_permission успешно обрабатывает запрос и возвращает outcome."""
        manager = PermissionRequestManager()
        mock_permission_handler.get_request_manager.return_value = manager
        callback = Mock()

        # Запустить запрос разрешения и сразу разрешить его
        async def test_flow() -> None:
            # Запустить request_permission в background
            import asyncio

            task = asyncio.create_task(
                coordinator_with_handler.request_permission(
                    request=sample_permission_request,
                    callback=callback,
                )
            )

            # Дать время на создание запроса
            await asyncio.sleep(0.1)

            # Получить созданный запрос и разрешить его
            perm_request = manager.get_request("perm_1")
            assert perm_request is not None

            perm_request.resolve_with_option("allow_once")

            # Дождаться результата
            outcome = await task

            assert isinstance(outcome, SelectedPermissionOutcome)
            assert outcome.outcome == "selected"
            assert outcome.optionId == "allow_once"
            # Проверить что callback был вызван с правильными аргументами
            callback.assert_called_once()
            call_args = callback.call_args
            assert call_args[0][0] == "perm_1"  # request_id
            assert call_args[0][1].toolCallId == "tool_1"  # tool_call
            assert len(call_args[0][2]) == 2  # options

        await test_flow()

    @pytest.mark.asyncio
    async def test_request_permission_timeout(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
        sample_permission_request: RequestPermissionRequest,
    ) -> None:
        """request_permission возвращает CancelledOutcome при timeout."""
        manager = PermissionRequestManager()
        mock_permission_handler.get_request_manager.return_value = manager
        callback = Mock()

        # Модифицировать запрос с очень коротким timeout
        modified_request = sample_permission_request.model_copy()

        async def test_with_short_timeout() -> None:
            # Patch create_request чтобы установить очень короткий timeout
            original_create = manager.create_request

            def patched_create(*args, **kwargs) -> PermissionRequest:
                kwargs["timeout"] = 0.05  # 50ms
                return original_create(*args, **kwargs)

            manager.create_request = patched_create  # type: ignore[method-assign]

            outcome = await coordinator_with_handler.request_permission(
                request=modified_request,
                callback=callback,
            )

            # После timeout должно вернуть cancelled
            assert isinstance(outcome, CancelledPermissionOutcome)
            assert outcome.outcome == "cancelled"

        await test_with_short_timeout()

    @pytest.mark.asyncio
    async def test_request_permission_handler_error(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
        sample_permission_request: RequestPermissionRequest,
    ) -> None:
        """request_permission возвращает CancelledOutcome при ошибке handler."""
        # Сконфигурировать mock чтобы бросать исключение при первом вызове,
        # но возвращать валидный manager при вызове из finally
        call_count = 0

        def side_effect_handler() -> PermissionRequestManager:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Handler error")
            return PermissionRequestManager()

        mock_permission_handler.get_request_manager.side_effect = side_effect_handler
        callback = Mock()

        outcome = await coordinator_with_handler.request_permission(
            request=sample_permission_request,
            callback=callback,
        )

        assert isinstance(outcome, CancelledPermissionOutcome)
        assert outcome.outcome == "cancelled"

    def test_resolve_permission_without_handler(
        self,
        coordinator_without_handler: SessionCoordinator,
    ) -> None:
        """resolve_permission логирует warning если нет handler."""
        coordinator_without_handler.resolve_permission(
            request_id="perm_1",
            option_id="allow_once",
        )
        # Не должно бросать исключение

    @pytest.mark.asyncio
    async def test_resolve_permission_success(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
    ) -> None:
        """resolve_permission успешно разрешает pending request."""
        manager = PermissionRequestManager()
        mock_permission_handler.get_request_manager.return_value = manager

        # Создать pending request
        tool_call = PermissionToolCall(
            toolCallId="tool_1",
            title="File Write",
        )
        option = PermissionOption(
            optionId="allow_once",
            name="Allow once",
            kind="allow_once",
        )
        perm_request = manager.create_request(
            request_id="perm_1",
            session_id="session_1",
            tool_call=tool_call,
            options=[option],
        )

        # Разрешить request
        coordinator_with_handler.resolve_permission(
            request_id="perm_1",
            option_id="allow_once",
        )

        # Проверить что request был разрешен
        assert perm_request.future.done()
        outcome = perm_request.future.result()
        assert isinstance(outcome, SelectedPermissionOutcome)
        assert outcome.optionId == "allow_once"

    def test_resolve_permission_not_found(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
    ) -> None:
        """resolve_permission логирует warning если request не найден."""
        manager = PermissionRequestManager()
        mock_permission_handler.get_request_manager.return_value = manager

        # Попытаться разрешить несуществующий request
        coordinator_with_handler.resolve_permission(
            request_id="nonexistent",
            option_id="allow_once",
        )
        # Не должно бросать исключение

    def test_resolve_permission_error(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
    ) -> None:
        """resolve_permission ловит и логирует ошибки handler."""
        mock_permission_handler.get_request_manager.side_effect = RuntimeError(
            "Handler error"
        )

        coordinator_with_handler.resolve_permission(
            request_id="perm_1",
            option_id="allow_once",
        )
        # Не должно бросать исключение

    def test_cancel_permission_without_handler(
        self,
        coordinator_without_handler: SessionCoordinator,
    ) -> None:
        """cancel_permission логирует warning если нет handler."""
        coordinator_without_handler.cancel_permission(request_id="perm_1")
        # Не должно бросать исключение

    @pytest.mark.asyncio
    async def test_cancel_permission_success(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
    ) -> None:
        """cancel_permission успешно отменяет pending request."""
        manager = PermissionRequestManager()
        mock_permission_handler.get_request_manager.return_value = manager

        # Создать pending request
        tool_call = PermissionToolCall(
            toolCallId="tool_1",
            title="File Write",
        )
        option = PermissionOption(
            optionId="allow_once",
            name="Allow once",
            kind="allow_once",
        )
        manager.create_request(
            request_id="perm_1",
            session_id="session_1",
            tool_call=tool_call,
            options=[option],
        )

        # Отменить request
        coordinator_with_handler.cancel_permission(request_id="perm_1")

        # Проверить что request был отменен (удален из manager)
        assert manager.get_request("perm_1") is None

    def test_cancel_permission_not_found(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
    ) -> None:
        """cancel_permission логирует info если request не найден."""
        manager = PermissionRequestManager()
        mock_permission_handler.get_request_manager.return_value = manager

        # Попытаться отменить несуществующий request
        # Не должно бросать исключение
        coordinator_with_handler.cancel_permission(request_id="nonexistent")

    def test_cancel_permission_error(
        self,
        coordinator_with_handler: SessionCoordinator,
        mock_permission_handler: Mock,
    ) -> None:
        """cancel_permission ловит и логирует ошибки handler."""
        mock_permission_handler.get_request_manager.side_effect = RuntimeError(
            "Handler error"
        )

        coordinator_with_handler.cancel_permission(request_id="perm_1")
        # Не должно бросать исключение

    async def test_handle_permission_deprecated(
        self,
        coordinator_with_handler: SessionCoordinator,
    ) -> None:
        """handle_permission оставлен для backward compatibility."""
        # Метод должен просто логировать, не выбрасывая исключение
        await coordinator_with_handler.handle_permission(
            session_id="session_1",
            permission_id="perm_1",
            approved=True,
        )
        # Не должно бросать исключение

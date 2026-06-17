"""Тесты покрытия для PermissionChecker.

Покрывает делегирование вызовов PermissionManager и логирование проверок прав.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.state import SessionState
from codelab.server.tools.integrations.permission_checker import PermissionChecker


@pytest.fixture
def mock_manager() -> MagicMock:
    """Мок PermissionManager."""
    return MagicMock(spec=PermissionManager)


@pytest.fixture
def checker(mock_manager: MagicMock) -> PermissionChecker:
    """PermissionChecker с мок-менеджером."""
    return PermissionChecker(mock_manager)


@pytest.fixture
def session() -> SessionState:
    """Базовая сессия."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestShouldRequestPermission:
    """Тесты should_request_permission."""

    def test_delegates_and_returns_true(
        self,
        checker: PermissionChecker,
        mock_manager: MagicMock,
        session: SessionState,
    ) -> None:
        """Делегирует менеджеру и возвращает True."""
        mock_manager.should_request_permission.return_value = True

        result = checker.should_request_permission(session, "execute")

        assert result is True
        mock_manager.should_request_permission.assert_called_once_with(session, "execute")

    def test_delegates_and_returns_false(
        self,
        checker: PermissionChecker,
        mock_manager: MagicMock,
        session: SessionState,
    ) -> None:
        """Делегирует менеджеру и возвращает False."""
        mock_manager.should_request_permission.return_value = False

        result = checker.should_request_permission(session, "read")

        assert result is False
        mock_manager.should_request_permission.assert_called_once_with(session, "read")


class TestGetRememberedPermission:
    """Тесты get_remembered_permission."""

    def test_returns_allow(
        self,
        checker: PermissionChecker,
        mock_manager: MagicMock,
        session: SessionState,
    ) -> None:
        """Возвращает 'allow' от менеджера."""
        mock_manager.get_remembered_permission.return_value = "allow"

        result = checker.get_remembered_permission(session, "write")

        assert result == "allow"
        mock_manager.get_remembered_permission.assert_called_once_with(session, "write")

    def test_returns_reject(
        self,
        checker: PermissionChecker,
        mock_manager: MagicMock,
        session: SessionState,
    ) -> None:
        """Возвращает 'reject' от менеджера."""
        mock_manager.get_remembered_permission.return_value = "reject"

        result = checker.get_remembered_permission(session, "delete")

        assert result == "reject"
        mock_manager.get_remembered_permission.assert_called_once_with(session, "delete")

    def test_returns_ask(
        self,
        checker: PermissionChecker,
        mock_manager: MagicMock,
        session: SessionState,
    ) -> None:
        """Возвращает 'ask' от менеджера."""
        mock_manager.get_remembered_permission.return_value = "ask"

        result = checker.get_remembered_permission(session, "execute")

        assert result == "ask"
        mock_manager.get_remembered_permission.assert_called_once_with(session, "execute")

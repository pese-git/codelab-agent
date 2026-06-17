"""Дополнительные тесты для покрытия SessionViewModel.

Покрывает:
- обработку ImportError при инициализации
- ошибки создания и удаления сессии
- обработчики событий создания/инициализации сессии
- _extract_session_id для dict и объектов с разными атрибутами
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from codelab.client.presentation.session_view_model import SessionViewModel


class TestSessionViewModelInitCoverage:
    """Тесты для покрытия __init__."""

    def test_init_handles_import_error(self) -> None:
        """SessionViewModel обрабатывает ImportError при подписке на события."""
        coordinator = AsyncMock()
        with patch.dict("sys.modules", {"codelab.client.domain.events": None}):
            vm = SessionViewModel(coordinator, event_bus=Mock(), logger=None)

        assert vm.sessions.value == []


class TestSessionViewModelCreateSessionErrors:
    """Тесты для ошибок создания сессии."""

    @pytest.fixture
    def vm(self) -> SessionViewModel:
        """Создать SessionViewModel с mock coordinator."""
        coordinator = AsyncMock()
        return SessionViewModel(coordinator, event_bus=Mock(), logger=None)

    @pytest.mark.asyncio
    async def test_create_session_error_sets_message(self, vm: SessionViewModel) -> None:
        """Ошибка создания сессии устанавливает error_message."""
        vm.coordinator.create_session.side_effect = RuntimeError("Connection failed")

        await vm.create_session_cmd.execute("localhost", 8080)

        assert vm.is_loading_sessions.value is False
        assert vm.error_message.value is not None
        assert "Failed to create session" in vm.error_message.value


class TestSessionViewModelDeleteSessionErrors:
    """Тесты для ошибок удаления сессии."""

    @pytest.fixture
    def vm(self) -> SessionViewModel:
        """Создать SessionViewModel с mock coordinator."""
        coordinator = AsyncMock()
        return SessionViewModel(coordinator, event_bus=Mock(), logger=None)

    @pytest.mark.asyncio
    async def test_delete_session_error_sets_message(self, vm: SessionViewModel) -> None:
        """Ошибка удаления сессии устанавливает error_message."""
        session = MagicMock(id="s1")
        vm.sessions.value = [session]
        vm.coordinator.delete_session.side_effect = RuntimeError("Delete failed")

        await vm.delete_session_cmd.execute("s1")

        assert vm.error_message.value is not None
        assert "Failed to delete session" in vm.error_message.value


class TestSessionViewModelEventHandlers:
    """Тесты для обработчиков событий."""

    @pytest.fixture
    def vm(self) -> SessionViewModel:
        """Создать SessionViewModel с mock coordinator."""
        coordinator = AsyncMock()
        return SessionViewModel(coordinator, event_bus=Mock(), logger=None)

    def test_handle_session_created(self, vm: SessionViewModel) -> None:
        """_handle_session_created логирует событие."""
        event = MagicMock(session_id="s1")

        # Не должно бросать исключение
        vm._handle_session_created(event)

    def test_handle_session_initialized(self, vm: SessionViewModel) -> None:
        """_handle_session_initialized логирует событие."""
        event = MagicMock(session_id="s1")
        event.capabilities = {"test": True}

        # Не должно бросать исключение
        vm._handle_session_initialized(event)


class TestSessionViewModelExtractSessionId:
    """Тесты для _extract_session_id."""

    def test_extract_from_dict_with_session_id(self) -> None:
        """_extract_session_id извлекает sessionId из dict."""
        result = SessionViewModel._extract_session_id({"sessionId": "abc123"})
        assert result == "abc123"

    def test_extract_from_dict_with_non_string_id(self) -> None:
        """_extract_session_id возвращает None для нестрокового id в dict."""
        result = SessionViewModel._extract_session_id({"id": 123})
        assert result is None

    def test_extract_from_object_with_session_id_attribute(self) -> None:
        """_extract_session_id извлекает sessionId из атрибута объекта."""
        obj = Mock()
        obj.sessionId = "obj123"
        obj.id = "other"

        result = SessionViewModel._extract_session_id(obj)
        assert result == "obj123"

    def test_extract_from_object_with_non_string_attribute(self) -> None:
        """_extract_session_id возвращает None для нестрокового атрибута."""
        obj = Mock()
        obj.sessionId = 123

        result = SessionViewModel._extract_session_id(obj)
        assert result is None

    def test_extract_from_object_without_attributes(self) -> None:
        """_extract_session_id возвращает None для объекта без id."""
        result = SessionViewModel._extract_session_id(object())
        assert result is None

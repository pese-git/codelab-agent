"""Дополнительные тесты для покрытия UIViewModel.

Покрывает:
- обработку ImportError при инициализации
- show_error, show_info, show_warning, clear_messages
- set_connection_status, set_loading, show_modal, hide_modal
- is_modal_open, increment/reset retry_count, set_auto_reconnect
- _handle_error_event, reset_connection_state
- toggle_active_sidebar_section для SETTINGS
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from codelab.client.presentation.ui_view_model import (
    ConnectionStatus,
    SidebarTab,
    UIViewModel,
)


class TestUIViewModelInitCoverage:
    """Тесты для покрытия __init__."""

    def test_init_handles_import_error(self) -> None:
        """UIViewModel обрабатывает ImportError при подписке на события."""
        with patch.dict("sys.modules", {"codelab.client.domain.events": None}):
            vm = UIViewModel(event_bus=Mock(), logger=None)

        assert vm.connection_status.value == ConnectionStatus.DISCONNECTED


class TestUIViewModelMessagesCoverage:
    """Тесты для покрытия методов сообщений."""

    def test_show_error_sets_message(self) -> None:
        """show_error устанавливает error_message."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.show_error("Connection failed", error_type="network")

        assert vm.error_message.value == "Connection failed"

    def test_show_info_sets_message(self) -> None:
        """show_info устанавливает info_message."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.show_info("Session loaded")

        assert vm.info_message.value == "Session loaded"

    def test_show_warning_sets_message(self) -> None:
        """show_warning устанавливает warning_message."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.show_warning("Low disk space")

        assert vm.warning_message.value == "Low disk space"

    def test_clear_messages_clears_all(self) -> None:
        """clear_messages очищает все сообщения."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        vm.show_error("Error")
        vm.show_info("Info")
        vm.show_warning("Warning")

        vm.clear_messages()

        assert vm.error_message.value is None
        assert vm.info_message.value is None
        assert vm.warning_message.value is None


class TestUIViewModelConnectionCoverage:
    """Тесты для покрытия методов соединения."""

    def test_set_connection_status_updates_offline_flag(self) -> None:
        """set_connection_status обновляет is_offline."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.set_connection_status(ConnectionStatus.CONNECTED)
        assert vm.is_offline.value is False

        vm.set_connection_status(ConnectionStatus.DISCONNECTED)
        assert vm.is_offline.value is True

        vm.set_connection_status(ConnectionStatus.ERROR)
        assert vm.is_offline.value is True

    def test_reset_connection_state(self) -> None:
        """reset_connection_state сбрасывает состояние."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        vm.set_connection_status(ConnectionStatus.CONNECTED)
        vm.increment_retry_count()
        vm.show_error("Error")

        vm.reset_connection_state()

        assert vm.connection_status.value == ConnectionStatus.DISCONNECTED
        assert vm.is_offline.value is True
        assert vm.retry_count.value == 0
        assert vm.error_message.value is None

    def test_increment_retry_count(self) -> None:
        """increment_retry_count увеличивает счётчик."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.increment_retry_count()
        vm.increment_retry_count()

        assert vm.retry_count.value == 2

    def test_reset_retry_count(self) -> None:
        """reset_retry_count сбрасывает счётчик."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        vm.increment_retry_count()

        vm.reset_retry_count()

        assert vm.retry_count.value == 0

    def test_set_auto_reconnect(self) -> None:
        """set_auto_reconnect устанавливает флаг."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.set_auto_reconnect(False)
        assert vm.auto_reconnect_enabled.value is False

        vm.set_auto_reconnect(True)
        assert vm.auto_reconnect_enabled.value is True


class TestUIViewModelLoadingAndModalCoverage:
    """Тесты для покрытия loading и modal методов."""

    def test_set_loading_with_message(self) -> None:
        """set_loading устанавливает is_loading и loading_message."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.set_loading(True, "Loading sessions...")

        assert vm.is_loading.value is True
        assert vm.loading_message.value == "Loading sessions..."

    def test_set_loading_false_clears_message(self) -> None:
        """set_loading(False) очищает loading_message."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        vm.set_loading(True, "Loading...")

        vm.set_loading(False)

        assert vm.is_loading.value is False
        assert vm.loading_message.value is None

    def test_show_modal(self) -> None:
        """show_modal устанавливает active_modal и modal_data."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.show_modal("permission", {"request_id": "123"})

        assert vm.active_modal.value == "permission"
        assert vm.modal_data.value == {"request_id": "123"}

    def test_show_modal_without_data(self) -> None:
        """show_modal работает без данных."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.show_modal("settings")

        assert vm.active_modal.value == "settings"
        assert vm.modal_data.value == {}

    def test_hide_modal(self) -> None:
        """hide_modal скрывает модальное окно."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        vm.show_modal("permission")

        vm.hide_modal()

        assert vm.active_modal.value is None
        assert vm.modal_data.value == {}

    def test_is_modal_open(self) -> None:
        """is_modal_open проверяет состояние модалов."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        assert vm.is_modal_open() is False
        assert vm.is_modal_open("permission") is False

        vm.show_modal("permission")

        assert vm.is_modal_open() is True
        assert vm.is_modal_open("permission") is True
        assert vm.is_modal_open("settings") is False


class TestUIViewModelSidebarCoverage:
    """Тесты для покрытия sidebar методов."""

    def test_set_sidebar_tab(self) -> None:
        """set_sidebar_tab меняет активную вкладку."""
        vm = UIViewModel(event_bus=Mock(), logger=None)

        vm.set_sidebar_tab(SidebarTab.SETTINGS)

        assert vm.sidebar_tab.value == SidebarTab.SETTINGS

    def test_toggle_active_sidebar_section_settings_returns_true(self) -> None:
        """toggle_active_sidebar_section возвращает True для SETTINGS."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        vm.set_sidebar_tab(SidebarTab.SETTINGS)

        result = vm.toggle_active_sidebar_section()

        assert result is True


class TestUIViewModelEventHandlersCoverage:
    """Тесты для покрытия обработчиков событий."""

    def test_handle_error_event(self) -> None:
        """_handle_error_event вызывает show_error."""
        vm = UIViewModel(event_bus=Mock(), logger=None)
        event = Mock()
        event.error_message = "Test error"
        event.error_type = "test"

        vm._handle_error_event(event)

        assert vm.error_message.value == "Test error"

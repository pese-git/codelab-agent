"""UIViewModel для управления глобальным UI состоянием.

Отвечает за:
- Статус соединения
- Глобальные загрузки
- Ошибки и уведомления
- Модальные окна
"""

from enum import Enum
from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class ConnectionStatus(Enum):
    """Статус соединения с сервером."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class SidebarTab(Enum):
    """Доступные вкладки левой панели."""

    SESSIONS = "sessions"
    FILES = "files"
    SETTINGS = "settings"


class UIViewModel(BaseViewModel):
    """ViewModel для управления глобальным UI состоянием.

    Отвечает за состояние, которое влияет на весь интерфейс:
    - connection_status: текущий статус соединения
    - is_loading: флаг глобальной загрузки
    - error_message: последняя ошибка
    - info_message: информационное сообщение
    - active_modal: активное модальное окно

    Пример использования:
        >>> vm = UIViewModel(event_bus)
        >>>
        >>> # Подписаться на изменения
        >>> vm.connection_status.subscribe(lambda s: print(f"Status: {s}"))
        >>> vm.error_message.subscribe(lambda e: show_error_dialog(e))
        >>>
        >>> # Показать ошибку
        >>> vm.show_error("Connection failed")
        >>>
        >>> # Показать модальное окно
        >>> vm.show_modal("permission")
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать UIViewModel.

        Args:
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для логирования
        """
        super().__init__(event_bus, logger)

        # Observable свойства
        self.connection_status: Observable[ConnectionStatus] = Observable(
            ConnectionStatus.DISCONNECTED
        )
        self.sidebar_tab: Observable[SidebarTab] = Observable(SidebarTab.SESSIONS)
        self.sidebar_collapsed: Observable[bool] = Observable(False)
        self.sessions_expanded: Observable[bool] = Observable(True)
        self.files_expanded: Observable[bool] = Observable(True)
        self.is_loading: Observable[bool] = Observable(False)
        self.loading_message: Observable[str | None] = Observable(None)
        self.error_message: Observable[str | None] = Observable(None)
        self.info_message: Observable[str | None] = Observable(None)
        self.warning_message: Observable[str | None] = Observable(None)
        # Тип активного модала или None
        self.active_modal: Observable[str | None] = Observable(None)
        self.modal_data: Observable[dict[str, Any]] = Observable({})  # Данные для модального окна

        # Флаги для offline режима
        self.is_offline: Observable[bool] = Observable(False)
        self.retry_count: Observable[int] = Observable(0)
        self.auto_reconnect_enabled: Observable[bool] = Observable(True)

        # Подписываемся на события (если EventBus доступен)
        try:
            from codelab.client.domain.events import ErrorOccurredEvent

            self.on_event(ErrorOccurredEvent, self._handle_error_event)
        except ImportError:
            self.logger.debug("DomainEvents not available, skipping event subscriptions")

    def show_error(self, message: str, error_type: str | None = None) -> None:
        """Показать сообщение об ошибке.

        Args:
            message: Текст ошибки
            error_type: Тип ошибки (optional, для категоризации)
        """
        self.error_message.value = message
        self.logger.error("UI Error", message=message, error_type=error_type or "unknown")

    def show_info(self, message: str) -> None:
        """Показать информационное сообщение.

        Args:
            message: Информационный текст
        """
        self.info_message.value = message
        self.logger.info("UI Info", message=message)

    def show_warning(self, message: str) -> None:
        """Показать предупреждение.

        Args:
            message: Текст предупреждения
        """
        self.warning_message.value = message
        self.logger.warning("UI Warning", message=message)

    def clear_messages(self) -> None:
        """Очистить все сообщения (ошибки, инфо, предупреждения)."""
        self.error_message.value = None
        self.info_message.value = None
        self.warning_message.value = None
        self.logger.debug("All messages cleared")

    def set_connection_status(self, status: ConnectionStatus) -> None:
        """Установить статус соединения.

        Args:
            status: Новый статус соединения
        """
        self.connection_status.value = status

        # Обновить флаг offline режима
        is_offline = status in (ConnectionStatus.DISCONNECTED, ConnectionStatus.ERROR)
        self.is_offline.value = is_offline

        self.logger.info("Connection status changed", status=status.value)

    def set_sidebar_tab(self, tab: SidebarTab) -> None:
        """Сделать активной указанную вкладку левой панели."""

        self.sidebar_tab.value = tab
        self.logger.debug("Sidebar tab changed", tab=tab.value)

    def cycle_sidebar_tab(self, *, reverse: bool = False) -> SidebarTab:
        """Переключить вкладку sidebar по кругу и вернуть новое значение."""

        tabs = [SidebarTab.SESSIONS, SidebarTab.FILES, SidebarTab.SETTINGS]
        current_index = tabs.index(self.sidebar_tab.value)
        step = -1 if reverse else 1
        next_index = (current_index + step) % len(tabs)
        next_tab = tabs[next_index]
        self.set_sidebar_tab(next_tab)
        return next_tab

    def toggle_active_sidebar_section(self) -> bool:
        """Свернуть/развернуть активную секцию sidebar при необходимости."""

        active_tab = self.sidebar_tab.value
        if active_tab == SidebarTab.SESSIONS:
            next_value = not self.sessions_expanded.value
            self.sessions_expanded.value = next_value
            self.logger.debug("Sessions section toggled", expanded=next_value)
            return next_value
        if active_tab == SidebarTab.FILES:
            next_value = not self.files_expanded.value
            self.files_expanded.value = next_value
            self.logger.debug("Files section toggled", expanded=next_value)
            return next_value
        return True

    def set_loading(self, is_loading: bool, message: str | None = None) -> None:
        """Установить флаг глобальной загрузки.

        Args:
            is_loading: True если идет загрузка, False если завершена
        """
        self.is_loading.value = is_loading
        self.loading_message.value = message if is_loading else None
        self.logger.debug("Global loading status changed", is_loading=is_loading)

    def show_modal(self, modal_type: str, data: dict | None = None) -> None:
        """Показать модальное окно.

        Args:
            modal_type: Тип модального окна ("permission", "settings", "about", etc.)
            data: Данные для передачи в модальное окно
        """
        self.active_modal.value = modal_type
        self.modal_data.value = data or {}
        self.logger.debug("Modal shown", modal_type=modal_type)

    def hide_modal(self) -> None:
        """Скрыть текущее модальное окно."""
        self.active_modal.value = None
        self.modal_data.value = {}
        self.logger.debug("Modal hidden")

    def is_modal_open(self, modal_type: str | None = None) -> bool:
        """Проверить открыто ли модальное окно.

        Args:
            modal_type: Если указан, проверить конкретный тип модала.
                       Если None, проверить есть ли какой-нибудь открытый модал.

        Returns:
            True если модал открыт, False иначе
        """
        if modal_type is None:
            return self.active_modal.value is not None
        return self.active_modal.value == modal_type

    def increment_retry_count(self) -> None:
        """Увеличить счетчик попыток переподключения."""
        self.retry_count.value += 1
        self.logger.debug("Retry count incremented", count=self.retry_count.value)

    def reset_retry_count(self) -> None:
        """Сбросить счетчик попыток переподключения."""
        self.retry_count.value = 0
        self.logger.debug("Retry count reset")

    def set_auto_reconnect(self, enabled: bool) -> None:
        """Включить/отключить автоматическое переподключение.

        Args:
            enabled: True чтобы включить, False чтобы отключить
        """
        self.auto_reconnect_enabled.value = enabled
        self.logger.info("Auto-reconnect setting changed", enabled=enabled)

    # Event handlers
    def _handle_error_event(self, event: Any) -> None:
        """Обработать ErrorOccurredEvent из EventBus.

        Args:
            event: ErrorOccurredEvent
        """
        error_msg = getattr(event, "error_message", "Unknown error")
        error_type = getattr(event, "error_type", "unknown")
        self.show_error(error_msg, error_type)

    def reset_connection_state(self) -> None:
        """Сбросить состояние соединения в начальное."""
        self.connection_status.value = ConnectionStatus.DISCONNECTED
        self.is_offline.value = True
        self.reset_retry_count()
        self.clear_messages()
        self.logger.debug("Connection state reset")

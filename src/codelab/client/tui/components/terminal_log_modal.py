"""Модальное окно детального просмотра terminal output.

Интегрировано с TerminalLogViewModel для управления состоянием модального окна.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

if TYPE_CHECKING:
    from codelab.client.presentation.terminal_log_view_model import TerminalLogViewModel


class TerminalLogModal(ModalScreen[None]):
    """Показывает полный вывод терминала для выбранного tool call.

    Интегрирован с TerminalLogViewModel для управления состоянием:
    - log_entries: список записей логов
    - is_visible: видимость модального окна

    Все изменения UI синхронизируются с ViewModel через Observable паттерн.
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(
        self,
        *,
        terminal_log_vm: TerminalLogViewModel,
        title: str = "",
        terminal_id: str = "",
        output: Text | None = None,
    ) -> None:
        """Создает модальное окно просмотра логов терминала.

        Args:
            terminal_log_vm: TerminalLogViewModel для управления состоянием.
                Обязательный параметр для MVVM интеграции.
            title: Заголовок окна (опционально).
            terminal_id: ID терминала (опционально).
            output: Начальный вывод (опционально).
                Если указан, используется для инициализации.
        """

        super().__init__()
        self.terminal_log_vm = terminal_log_vm
        self._title = title
        self._terminal_id = terminal_id
        self._output = output or Text("")

        # Сохраняем unsubscribe функции для очистки при уничтожении
        self._unsubscribers: list[Callable[[], None]] = []

        # Подписываемся на изменения ViewModel сразу (не только при on_mount)
        self._subscribe_to_view_model()

    def compose(self) -> ComposeResult:
        """Рендерит заголовок и scrollable-блок вывода терминала."""

        with Vertical(id="terminal-log-modal"):
            # Рендерим заголовок с информацией о терминале
            header_text = self._title
            if self._terminal_id:
                header_text = f"{self._title} | terminal: {self._terminal_id}"
            yield Static(header_text, id="terminal-log-title")

            # Рендерим содержимое лога
            yield Static(self._output, id="terminal-log-content")

    def _subscribe_to_view_model(self) -> None:
        """Подписаться на изменения ViewModel.

        Устанавливает observers на все Observable свойства ViewModel
        для синхронизации UI при изменениях состояния.
        """
        # Подписываемся на изменение записей лога
        unsub_entries = self.terminal_log_vm.log_entries.subscribe(self._on_entries_changed)
        self._unsubscribers.append(unsub_entries)

    def _on_entries_changed(self, entries: list[str]) -> None:
        """Обработчик изменения записей логов в ViewModel.

        Args:
            entries: Новый список записей логов.
        """
        # Форматируем список строк в один текст
        content = "\n".join(entries)
        self._output = Text(content) if content else Text("")

        # Обновляем виджет если компонент смонтирован
        with suppress(Exception):
            content_widget = self.query_one("#terminal-log-content", Static)
            content_widget.update(self._output)

    def action_close(self) -> None:
        """Закрывает модальное окно по hotkey.

        Только обновляет ViewModel, NavigationManager сам удалит виджет.
        """
        self.terminal_log_vm.hide()

    def on_unmount(self) -> None:
        """Отписываемся от ViewModel при размонтировании."""
        # Отписываемся от всех наблюдателей
        for unsubscriber in self._unsubscribers:
            with suppress(Exception):
                unsubscriber()
        self._unsubscribers.clear()

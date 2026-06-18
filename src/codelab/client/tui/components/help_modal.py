"""Модальное окно встроенной справки и горячих клавиш."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpModal(ModalScreen[None]):
    """Показывает контекстную справку по текущему экрану TUI."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("enter", "close", "Close"),
    ]

    def __init__(self, *, context: str, show_hotkeys: bool = False) -> None:
        """Инициализировать модал с контекстным содержимым."""

        super().__init__()
        self._help_context = context
        self._show_hotkeys = show_hotkeys

    def compose(self) -> ComposeResult:
        """Отрисовать заголовок и содержание справки."""

        title = "Справка" if not self._show_hotkeys else "Горячие клавиши"
        with Vertical(id="help-modal"):
            yield Static(title, id="help-title")
            yield Static(self._content(), id="help-content")
            yield Static("[Esc/Enter] Закрыть", id="help-hint")

    def action_close(self) -> None:
        """Закрыть модальное окно справки."""

        self.dismiss(None)

    def _content(self) -> str:
        """Сформировать текст справки под текущий сценарий."""

        if self._show_hotkeys:
            return (
                "Global:\n"
                "- F1: контекстная справка\n"
                "- ?: список горячих клавиш\n"
                "- Ctrl+Tab: следующая вкладка sidebar\n"
                "- Ctrl+Shift+Tab: предыдущая вкладка sidebar\n"
                "- Ctrl+Q: выход\n\n"
                "Chat:\n"
                "- Ctrl+Enter: отправить промпт\n"
                "- Up/Down: история промптов"
            )

        context_map: dict[str, str] = {
            "sidebar": (
                "Sidebar:\n"
                "- Up/Down: выбрать сессию\n"
                "- Enter: загрузить сессию\n"
                "- Space: свернуть/развернуть секцию\n"
                "- Ctrl+Tab: переключить вкладку Sessions/Files/Settings"
            ),
            "file-tree": (
                "File Tree:\n"
                "- Up/Down: перемещение по дереву\n"
                "- Enter: открыть файл\n"
                "- Tab: перейти к следующей области"
            ),
            "prompt-input": (
                "Prompt Input:\n"
                "- Ctrl+Enter: отправка\n"
                "- Up/Down: история текущей сессии\n"
                "- Enter: новая строка"
            ),
        }
        return context_map.get(
            self._help_context,
            (
                "Общая справка:\n"
                "- Создайте или выберите сессию в sidebar\n"
                "- Введите промпт в нижнем поле ввода\n"
                "- Отправьте Ctrl+Enter\n"
                "- Нажмите ? для полного списка горячих клавиш"
            ),
        )

"""SearchInput - поле поиска с иконкой и очисткой.

Компонент поля поиска:
- Иконка поиска
- Clear button
- Debounce для input
- История поиска (опционально)
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Label


class SearchInput(Widget):
    """Поле поиска с иконкой и кнопкой очистки.

    Поддерживает debounce для уменьшения частоты событий поиска
    при быстром вводе текста.
    """

    DEFAULT_CSS = """
    SearchInput {
        width: 100%;
        height: 3;
        layout: horizontal;
    }

    SearchInput .search-container {
        width: 100%;
        height: 100%;
        layout: horizontal;
        border: solid $border;
        background: $surface;
    }

    SearchInput .search-container:focus-within {
        border: solid $primary;
    }

    SearchInput .search-icon {
        width: 3;
        height: 100%;
        content-align: center middle;
        color: $foreground-muted;
    }

    SearchInput .search-field {
        width: 1fr;
        height: 100%;
        border: none;
        background: transparent;
    }

    SearchInput .search-field:focus {
        border: none;
    }

    SearchInput .clear-button {
        width: 3;
        height: 1;
        min-width: 0;
        border: none;
        background: transparent;
        color: $foreground-muted;
    }

    SearchInput .clear-button:hover {
        color: $error;
        background: $error 20%;
    }

    SearchInput .clear-button.-hidden {
        display: none;
    }
    """

    # Иконка поиска
    SEARCH_ICON: ClassVar[str] = "🔍"

    class SearchChanged(Message):
        """Сообщение об изменении поискового запроса."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class SearchSubmitted(Message):
        """Сообщение о подтверждении поиска (Enter)."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class SearchCleared(Message):
        """Сообщение об очистке поиска."""

        pass

    # Текущее значение поиска
    value: reactive[str] = reactive("")

    def __init__(
        self,
        *,
        placeholder: str = "Поиск...",
        debounce: float = 0.3,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует поле поиска.

        Args:
            placeholder: Текст-подсказка
            debounce: Задержка debounce в секундах (0 = без debounce)
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "search-input", classes=classes)
        self._placeholder = placeholder
        self._debounce = debounce
        self._debounce_task: asyncio.Task | None = None
        self._history: list[str] = []
        self._history_index: int = -1

    def compose(self) -> ComposeResult:
        """Создаёт содержимое поля поиска."""
        with Horizontal(classes="search-container"):
            yield Label(self.SEARCH_ICON, classes="search-icon")
            yield Input(placeholder=self._placeholder, classes="search-field")
            yield Button("×", classes="clear-button -hidden", variant="default")

    @property
    def input(self) -> Input:
        """Возвращает виджет Input."""
        return self.query_one(".search-field", Input)

    @property
    def clear_button(self) -> Button:
        """Возвращает кнопку очистки."""
        return self.query_one(".clear-button", Button)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Обрабатывает изменение ввода."""
        event.stop()
        new_value = event.value

        # Показываем/скрываем кнопку очистки
        self.clear_button.set_class(not new_value, "-hidden")

        # Применяем debounce
        if self._debounce > 0:
            self._schedule_search(new_value)
        else:
            self._emit_search(new_value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Обрабатывает подтверждение ввода (Enter)."""
        event.stop()

        # Отменяем debounce
        if self._debounce_task:
            self._debounce_task.cancel()
            self._debounce_task = None

        value = event.value.strip()
        if value:
            # Добавляем в историю
            if not self._history or self._history[-1] != value:
                self._history.append(value)
            self._history_index = -1

        self.value = value
        self.post_message(self.SearchSubmitted(value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обрабатывает клик на кнопку очистки."""
        if "clear-button" in event.button.classes:
            event.stop()
            self.clear()

    def _schedule_search(self, value: str) -> None:
        """Планирует отправку события поиска с debounce."""
        if self._debounce_task:
            self._debounce_task.cancel()

        async def debounced_search() -> None:
            await asyncio.sleep(self._debounce)
            self._emit_search(value)

        self._debounce_task = asyncio.create_task(debounced_search())

    def _emit_search(self, value: str) -> None:
        """Отправляет событие изменения поиска."""
        self.value = value
        self.post_message(self.SearchChanged(value))

    def clear(self) -> None:
        """Очищает поле поиска."""
        self.input.value = ""
        self.value = ""
        self.clear_button.add_class("-hidden")
        self.post_message(self.SearchCleared())

    def focus_input(self) -> None:
        """Фокусирует поле ввода."""
        self.input.focus()

    def set_value(self, value: str) -> None:
        """Устанавливает значение поля поиска.

        Args:
            value: Новое значение
        """
        self.input.value = value
        self.value = value
        self.clear_button.set_class(not value, "-hidden")

    # Навигация по истории

    def previous_history(self) -> str | None:
        """Получает предыдущий элемент истории."""
        if not self._history:
            return None

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            value = self._history[-(self._history_index + 1)]
            self.set_value(value)
            return value
        return None

    def next_history(self) -> str | None:
        """Получает следующий элемент истории."""
        if self._history_index > 0:
            self._history_index -= 1
            value = self._history[-(self._history_index + 1)]
            self.set_value(value)
            return value
        elif self._history_index == 0:
            self._history_index = -1
            self.clear()
            return ""
        return None

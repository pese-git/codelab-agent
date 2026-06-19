"""ConfigOptionSelectorModal - универсальное модальное окно для выбора config option.

Поддерживает выбор любой config option:
- model (LLM модель)
- mode (режим сессии)
- _agent (агент)
- _active_strategy (стратегия выполнения)

Функциональность:
- Отображение списка доступных options
- Поиск по названию
- Отображение текущего выбранного значения
- Навигация клавиатурой (↑↓, Enter, Esc)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from .keyboard_manager import (
    KeyboardManager,
    get_keyboard_manager,
)

if TYPE_CHECKING:
    from codelab.client.presentation.config_option_selector_view_model import (
        ConfigOption,
        ConfigOptionSelectorViewModel,
    )


class ConfigOptionItem(Static):
    """Элемент списка config options.

    Отображает одну опцию с названием и описанием.
    """

    DEFAULT_CSS = """
    ConfigOptionItem {
        width: 100%;
        height: 3;
        padding: 0 2;
        background: transparent;
    }

    ConfigOptionItem:hover {
        background: $surface-lighten-1;
    }

    ConfigOptionItem.-selected {
        background: $primary 30%;
    }

    ConfigOptionItem.-current {
        border-left: solid $success;
    }

    ConfigOptionItem .option-name {
        width: 1fr;
        text-style: bold;
    }

    ConfigOptionItem .option-details {
        width: 100%;
        color: $text-muted;
        text-style: italic;
    }
    """

    class Selected(Message):
        """Сообщение о выборе опции."""

        def __init__(self, option: ConfigOption) -> None:
            self.option = option
            super().__init__()

    def __init__(
        self,
        option: ConfigOption,
        *,
        selected: bool = False,
        is_current: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует элемент опции.

        Args:
            option: Данные опции
            selected: Выбрана ли опция в списке
            is_current: Является ли текущей опцией
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._option = option
        self._selected = selected
        self._is_current = is_current

    @property
    def option(self) -> ConfigOption:
        """Возвращает данные опции."""
        return self._option

    def compose(self) -> ComposeResult:
        """Создаёт содержимое элемента."""
        if self._selected:
            self.add_class("-selected")
        if self._is_current:
            self.add_class("-current")

        # Основная строка: название
        yield Label(self._option.label, classes="option-name")

        # Детали: описание + extra (pricing и т.д.)
        details = []
        if self._option.description:
            details.append(self._option.description)
        if "pricing" in self._option.extra:
            details.append(self._option.extra["pricing"])

        if details:
            yield Label(" | ".join(details), classes="option-details")

    def on_click(self) -> None:
        """Обрабатывает клик по опции."""
        self.post_message(self.Selected(self._option))


class ConfigOptionSelectorModal(ModalScreen[str | None]):
    """Универсальное модальное окно выбора config option.

    Открывается по hotkey, позволяет выбрать опцию из списка.
    """

    DEFAULT_CSS = """
    ConfigOptionSelectorModal {
        align: center middle;
    }

    ConfigOptionSelectorModal > Container {
        width: 70;
        max-width: 85%;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $border;
        padding: 1;
    }

    ConfigOptionSelectorModal .modal-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    ConfigOptionSelectorModal .current-option {
        width: 100%;
        text-align: center;
        color: $success;
        text-style: italic;
        margin-bottom: 1;
    }

    ConfigOptionSelectorModal .search-container {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    ConfigOptionSelectorModal Input {
        width: 100%;
    }

    ConfigOptionSelectorModal .options-scroll {
        width: 100%;
        height: auto;
        max-height: 20;
    }

    ConfigOptionSelectorModal .no-results {
        width: 100%;
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    ConfigOptionSelectorModal .no-options {
        width: 100%;
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    ConfigOptionSelectorModal .hint {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Закрыть"),
        ("up", "previous", "Предыдущая"),
        ("down", "next", "Следующая"),
        ("enter", "select", "Выбрать"),
    ]

    def __init__(
        self,
        view_model: ConfigOptionSelectorViewModel,
        session_id: str,
        keyboard_manager: KeyboardManager | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует модальное окно выбора опции.

        Args:
            view_model: ConfigOptionSelectorViewModel для управления состоянием
            session_id: ID текущей сессии
            keyboard_manager: KeyboardManager для hotkeys
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._view_model = view_model
        self._session_id = session_id
        self._keyboard_manager = keyboard_manager or get_keyboard_manager()
        self._filtered_options: list[ConfigOption] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        """Создаёт содержимое модального окна."""
        title = f"Выбор {self._view_model.title.lower()}"
        with Container():
            yield Label(title, classes="modal-title")

            # Показываем текущее значение
            current_label = self._view_model.get_current_label()
            yield Label(f"Текущее: {current_label}", classes="current-option")

            with Container(classes="search-container"):
                placeholder = f"Поиск {self._view_model.title.lower()}..."
                yield Input(placeholder=placeholder, id="option-search")

            with VerticalScroll(classes="options-scroll"):
                yield from self._render_options()

            yield Label("↑↓ навигация • Enter выбор • Esc закрыть", classes="hint")

    def _render_options(self) -> ComposeResult:
        """Рендерит список опций."""
        all_options = self._view_model.available_options.value
        options = self._filtered_options if self._filtered_options else all_options

        if not options:
            if self._view_model.available_options.value:
                yield Label("Опции не найдены", classes="no-results")
            else:
                title_lower = self._view_model.title.lower()
                message = f"Список {title_lower} недоступен.\nСоздайте или загрузите сессию."
                yield Label(message, classes="no-options")
            return

        current_value = self._view_model.current_value.value

        for i, option in enumerate(options):
            is_selected = i == self._selected_index
            is_current = option.value == current_value
            # Безопасный ID: заменяем специальные символы
            safe_value = option.value.replace("/", "_").replace("-", "_").replace(".", "_")
            yield ConfigOptionItem(
                option,
                selected=is_selected,
                is_current=is_current,
                id=f"option-{safe_value}",
            )

    def on_mount(self) -> None:
        """Фокусируемся на поле поиска при открытии."""
        search_input = self.query_one("#option-search", Input)
        search_input.focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Обрабатывает изменение поискового запроса."""
        query = event.value.strip().lower()
        self._filter_options(query)
        await self._refresh_options()

    def _filter_options(self, query: str) -> None:
        """Фильтрует опции по запросу (fuzzy search).

        Args:
            query: Поисковый запрос
        """
        all_options = self._view_model.available_options.value

        if not query:
            self._filtered_options = all_options.copy()
        else:
            self._filtered_options = []
            for option in all_options:
                # Fuzzy match по названию и описанию
                if (
                    self._fuzzy_match(query, option.label.lower())
                    or self._fuzzy_match(query, option.description.lower())
                ):
                    self._filtered_options.append(option)

        # Сбрасываем выбор
        self._selected_index = 0

    def _fuzzy_match(self, query: str, text: str) -> bool:
        """Проверяет fuzzy соответствие запроса тексту.

        Args:
            query: Поисковый запрос
            text: Текст для проверки

        Returns:
            True если текст соответствует запросу
        """
        # Простой fuzzy match: все символы query должны быть в text в том же порядке
        query_index = 0
        for char in text:
            if query_index < len(query) and char == query[query_index]:
                query_index += 1
        return query_index == len(query)

    def _update_selection(self) -> None:
        """Обновляет класс -selected без пересоздания виджетов."""
        all_options = self._view_model.available_options.value
        options = self._filtered_options if self._filtered_options else all_options
        for i, option in enumerate(options):
            try:
                safe_value = option.value.replace("/", "_").replace("-", "_")
                widget_id = f"option-{safe_value}"
                item = self.query_one(widget_id, ConfigOptionItem)
                item.set_class(i == self._selected_index, "-selected")
            except Exception:
                pass

    async def _refresh_options(self) -> None:
        """Пересоздаёт список опций (используется после фильтрации)."""
        scroll = self.query_one(".options-scroll", VerticalScroll)
        await scroll.remove_children()
        await scroll.mount(*list(self._render_options()))

    def action_close(self) -> None:
        """Закрывает модальное окно без выбора."""
        self.dismiss(None)

    def action_previous(self) -> None:
        """Выбирает предыдущую опцию."""
        all_options = self._view_model.available_options.value
        options = self._filtered_options if self._filtered_options else all_options
        if options and self._selected_index > 0:
            self._selected_index -= 1
            self._update_selection()

    def action_next(self) -> None:
        """Выбирает следующую опцию."""
        all_options = self._view_model.available_options.value
        options = self._filtered_options if self._filtered_options else all_options
        if options and self._selected_index < len(options) - 1:
            self._selected_index += 1
            self._update_selection()

    def action_select(self) -> None:
        """Выбирает опцию и закрывает модальное окно."""
        all_options = self._view_model.available_options.value
        options = self._filtered_options if self._filtered_options else all_options
        if options and 0 <= self._selected_index < len(options):
            selected_option = options[self._selected_index]
            self.dismiss(selected_option.value)

    def on_config_option_item_selected(self, event: ConfigOptionItem.Selected) -> None:
        """Обрабатывает выбор опции кликом."""
        self.dismiss(event.option.value)

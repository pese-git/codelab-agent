"""StatusLine - строка статуса внизу экрана.

Отображает:
- Текущий режим (mode)
- Подсказки по горячим клавишам
- Индикаторы состояния (подключение, активность)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

if TYPE_CHECKING:
    from codelab.client.presentation.ui_view_model import UIViewModel


class StatusMode(Enum):
    """Режимы работы приложения."""

    NORMAL = "normal"       # Обычный режим
    CHAT = "chat"           # Ввод сообщения
    COMMAND = "command"     # Ввод команды
    SEARCH = "search"       # Режим поиска


@dataclass
class StatusIndicator:
    """Индикатор в строке статуса.

    Атрибуты:
        name: Имя индикатора
        icon: Иконка
        label: Текстовая метка
        active: Активен ли индикатор
        color: CSS класс цвета
    """

    name: str
    icon: str
    label: str = ""
    active: bool = True
    color: str = ""


# Иконки для режимов
MODE_ICONS: dict[StatusMode, str] = {
    StatusMode.NORMAL: "◆",
    StatusMode.CHAT: "💬",
    StatusMode.COMMAND: "⌘",
    StatusMode.SEARCH: "🔍",
}

# Названия режимов
MODE_NAMES: dict[StatusMode, str] = {
    StatusMode.NORMAL: "NORMAL",
    StatusMode.CHAT: "CHAT",
    StatusMode.COMMAND: "CMD",
    StatusMode.SEARCH: "SEARCH",
}


class StatusLine(Static):
    """Строка статуса с режимом, подсказками и индикаторами.

    Структура:
    [Режим] | Подсказки горячих клавиш | Индикаторы
    """

    DEFAULT_CSS = """
    StatusLine {
        width: 100%;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    StatusLine > Horizontal {
        width: 100%;
        height: 1;
    }

    StatusLine .mode-indicator {
        width: auto;
        padding: 0 1;
        background: $primary 30%;
        color: $primary;
        text-style: bold;
    }

    StatusLine .mode-indicator.-normal {
        background: $surface-lighten-1;
        color: $text;
    }

    StatusLine .mode-indicator.-chat {
        background: $success 30%;
        color: $success;
    }

    StatusLine .mode-indicator.-command {
        background: $warning 30%;
        color: $warning;
    }

    StatusLine .mode-indicator.-search {
        background: $secondary 30%;
        color: $secondary;
    }

    StatusLine .hotkey-hints {
        width: 1fr;
        padding: 0 2;
        text-align: center;
    }

    StatusLine .hotkey-hint {
        margin: 0 1;
    }

    StatusLine .hotkey-key {
        text-style: bold;
        color: $text;
    }

    StatusLine .hotkey-desc {
        color: $text-muted;
    }

    StatusLine .status-indicators {
        width: auto;
    }

    StatusLine .indicator {
        padding: 0 1;
    }

    StatusLine .indicator.-active {
        color: $success;
    }

    StatusLine .indicator.-inactive {
        color: $text-muted;
    }

    StatusLine .indicator.-error {
        color: $error;
    }
    """

    # Реактивные свойства
    mode: reactive[StatusMode] = reactive(StatusMode.NORMAL)

    # Стандартные подсказки для разных режимов
    DEFAULT_HINTS: ClassVar[dict[StatusMode, list[tuple[str, str]]]] = {
        StatusMode.NORMAL: [
            ("Ctrl+K", "Команды"),
            ("Ctrl+N", "Сессия"),
            ("?", "Справка"),
        ],
        StatusMode.CHAT: [
            ("Enter", "Отправить"),
            ("Esc", "Отмена"),
            ("Ctrl+C", "Прервать"),
        ],
        StatusMode.COMMAND: [
            ("Enter", "Выполнить"),
            ("Esc", "Закрыть"),
            ("↑↓", "Навигация"),
        ],
        StatusMode.SEARCH: [
            ("Enter", "Найти"),
            ("Esc", "Закрыть"),
            ("↑↓", "Результаты"),
        ],
    }

    def __init__(
        self,
        ui_vm: UIViewModel | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует строку статуса.

        Args:
            ui_vm: UIViewModel для получения состояния
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._ui_vm = ui_vm
        self._indicators: list[StatusIndicator] = []
        self._custom_hints: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        """Создаёт содержимое строки статуса."""
        with Horizontal():
            yield self._create_mode_indicator()
            yield self._create_hints()
            yield self._create_indicators()

    def _create_mode_indicator(self) -> Static:
        """Создаёт индикатор текущего режима."""
        mode = self.mode
        icon = MODE_ICONS.get(mode, "◆")
        name = MODE_NAMES.get(mode, "UNKNOWN")

        indicator = Static(f" {icon} {name} ", classes=f"mode-indicator -{mode.value}")
        return indicator

    def _create_hints(self) -> Static:
        """Создаёт подсказки горячих клавиш."""
        hints = self._custom_hints or self.DEFAULT_HINTS.get(self.mode, [])

        parts = []
        for key, desc in hints:
            parts.append(f"[bold]{key}[/bold] {desc}")

        hint_text = "  │  ".join(parts)
        return Static(hint_text, classes="hotkey-hints", markup=True)

    def _create_indicators(self) -> Static:
        """Создаёт индикаторы состояния."""
        if not self._indicators:
            # Индикаторы по умолчанию
            return self._create_default_indicators()

        parts = []
        for ind in self._indicators:
            cls = "active" if ind.active else "inactive"
            text = f"{ind.icon}"
            if ind.label:
                text += f" {ind.label}"
            parts.append(f"[{cls}]{text}[/{cls}]")

        return Static(" ".join(parts), classes="status-indicators", markup=True)

    def _create_default_indicators(self) -> Static:
        """Создаёт индикаторы по умолчанию на основе UIViewModel."""
        parts = []

        if self._ui_vm is not None:
            # Индикатор подключения
            from codelab.client.presentation.ui_view_model import ConnectionStatus

            conn_status = self._ui_vm.connection_status.value
            if conn_status == ConnectionStatus.CONNECTED:
                parts.append("[green]●[/green] Online")
            elif conn_status == ConnectionStatus.CONNECTING:
                parts.append("[yellow]○[/yellow] Connecting")
            else:
                parts.append("[red]○[/red] Offline")

        return Static(" ".join(parts) if parts else "", classes="status-indicators", markup=True)

    def watch_mode(self, new_mode: StatusMode) -> None:
        """Обрабатывает изменение режима."""
        self.refresh()

    def set_mode(self, mode: StatusMode) -> None:
        """Устанавливает режим работы.

        Args:
            mode: Новый режим
        """
        self.mode = mode

    def set_hints(self, hints: list[tuple[str, str]]) -> None:
        """Устанавливает кастомные подсказки.

        Args:
            hints: Список кортежей (клавиша, описание)
        """
        self._custom_hints = hints
        self.refresh()

    def clear_hints(self) -> None:
        """Сбрасывает подсказки на стандартные для текущего режима."""
        self._custom_hints = []
        self.refresh()

    def add_indicator(self, indicator: StatusIndicator) -> None:
        """Добавляет индикатор состояния.

        Args:
            indicator: Индикатор для добавления
        """
        self._indicators.append(indicator)
        self.refresh()

    def remove_indicator(self, name: str) -> bool:
        """Удаляет индикатор по имени.

        Args:
            name: Имя индикатора

        Returns:
            True если индикатор удалён
        """
        for i, ind in enumerate(self._indicators):
            if ind.name == name:
                self._indicators.pop(i)
                self.refresh()
                return True
        return False

    def update_indicator(
        self, name: str, active: bool | None = None, label: str | None = None
    ) -> bool:
        """Обновляет индикатор.

        Args:
            name: Имя индикатора
            active: Новое состояние активности
            label: Новая метка

        Returns:
            True если индикатор обновлён
        """
        for ind in self._indicators:
            if ind.name == name:
                if active is not None:
                    ind.active = active
                if label is not None:
                    ind.label = label
                self.refresh()
                return True
        return False


class CompactStatusLine(Static):
    """Компактная строка статуса для маленьких терминалов.

    Показывает только самую важную информацию.
    """

    DEFAULT_CSS = """
    CompactStatusLine {
        width: 100%;
        height: 1;
        background: $surface;
        color: $text-muted;
    }

    CompactStatusLine .status-text {
        width: 100%;
        text-align: center;
    }
    """

    def __init__(
        self,
        ui_vm: UIViewModel | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует компактную строку статуса.

        Args:
            ui_vm: UIViewModel
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._ui_vm = ui_vm
        self._message = "Ctrl+K команды • ? справка"

    def compose(self) -> ComposeResult:
        """Создаёт содержимое."""
        yield Static(self._message, classes="status-text")

    def set_message(self, message: str) -> None:
        """Устанавливает сообщение в строке статуса.

        Args:
            message: Текст сообщения
        """
        self._message = message
        self.refresh()

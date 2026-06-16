"""Компонент для отображения вывода терминала в TUI.

Включает:
- TerminalOutputToolbar - панель инструментов с кнопками управления
- TerminalOutputContent - область отображения вывода с ANSI поддержкой
- TerminalOutputPanel - объединённый компонент с toolbar и контентом
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Button, Label, Static

if TYPE_CHECKING:
    from codelab.client.presentation.terminal_view_model import TerminalViewModel


class TerminalOutputToolbar(Horizontal):
    """Панель инструментов для терминального вывода.
    
    Содержит кнопки:
    - Очистка вывода (🗑)
    - Копирование в буфер (📋)
    """

    DEFAULT_CSS = """
    TerminalOutputToolbar {
        width: 100%;
        height: 1;
        background: $background-secondary;
        padding: 0 1;
    }

    TerminalOutputToolbar .toolbar-title {
        width: 1fr;
        content-align: left middle;
        color: $foreground-muted;
    }

    TerminalOutputToolbar .toolbar-button {
        width: auto;
        min-width: 0;
        height: 1;
        border: none;
        background: transparent;
        margin-left: 1;
    }

    TerminalOutputToolbar .toolbar-button:hover {
        background: $background-tertiary;
    }
    """

    class ClearRequested(Message):
        """Запрос на очистку вывода терминала."""

        pass

    class CopyRequested(Message):
        """Запрос на копирование вывода в буфер обмена."""

        pass

    def __init__(
        self,
        title: str = "Terminal",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует панель инструментов.
        
        Args:
            title: Заголовок панели
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "terminal-output-toolbar", classes=classes)
        self._title = title

    def compose(self) -> ComposeResult:
        """Создаёт содержимое панели инструментов."""
        yield Label(self._title, classes="toolbar-title")
        yield Button("🗑", classes="toolbar-button", variant="default", id="btn-clear")
        yield Button("📋", classes="toolbar-button", variant="default", id="btn-copy")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обрабатывает нажатия кнопок."""
        button_id = event.button.id
        if button_id == "btn-clear":
            self.post_message(self.ClearRequested())
        elif button_id == "btn-copy":
            self.post_message(self.CopyRequested())

    def set_title(self, title: str) -> None:
        """Устанавливает заголовок панели.
        
        Args:
            title: Новый заголовок
        """
        self._title = title
        with suppress(Exception):
            self.query_one(".toolbar-title", Label).update(title)


class TerminalOutputContent(Static):
    """Область отображения вывода терминала с ANSI поддержкой.
    
    Отвечает только за рендеринг текста, без управления состоянием.
    """

    DEFAULT_CSS = """
    TerminalOutputContent {
        width: 100%;
        height: 1fr;
        background: $background;
        padding: 0 1;
        overflow-y: auto;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует область вывода.
        
        Args:
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "terminal-output-content", classes=classes)
        self._output_text = ""
        self._exit_code: int | None = None

    def set_output(self, text: str) -> None:
        """Устанавливает текст вывода.
        
        Args:
            text: Текст для отображения
        """
        self._output_text = text
        self.update(self._render_text())

    def set_exit_code(self, exit_code: int | None) -> None:
        """Устанавливает код завершения.
        
        Args:
            exit_code: Код завершения процесса или None
        """
        self._exit_code = exit_code
        self.update(self._render_text())

    def clear(self) -> None:
        """Очищает вывод."""
        self._output_text = ""
        self._exit_code = None
        self.update(self._render_text())

    def get_output(self) -> str:
        """Возвращает текущий текст вывода."""
        return self._output_text

    def _render_text(self) -> Text:
        """Рендерит текст с ANSI поддержкой."""
        if not self._output_text:
            if self._exit_code is None:
                return Text("Нет вывода терминала")
            return Text(f"Exit code: {self._exit_code}")

        output_text = Text.from_ansi(self._output_text)

        if self._exit_code is not None:
            output_text.append(f"\n\nExit code: {self._exit_code}", style="bold")

        return output_text


class TerminalOutputPanel(Container):
    """Панель вывода терминала с toolbar и MVVM интеграцией.
    
    Рендерит потоковый terminal output с поддержкой ANSI-последовательностей.
    Интегрирован с TerminalViewModel для управления состоянием вывода через MVVM паттерн.
    Все изменения вывода должны проходить через ViewModel.
    
    Включает:
    - TerminalOutputToolbar с кнопками очистки и копирования
    - TerminalOutputContent для отображения вывода
    
    Атрибуты:
        show_toolbar: Показывать ли панель инструментов (по умолчанию True)
    """

    DEFAULT_CSS = """
    TerminalOutputPanel {
        width: 100%;
        height: 100%;
        layout: vertical;
        background: $background;
    }

    TerminalOutputPanel > TerminalOutputToolbar {
        display: block;
    }

    TerminalOutputPanel.-no-toolbar > TerminalOutputToolbar {
        display: none;
    }
    """

    class OutputCopied(Message):
        """Сообщение о копировании вывода."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class OutputCleared(Message):
        """Сообщение об очистке вывода."""

        pass

    def __init__(
        self,
        terminal_vm: TerminalViewModel,
        *,
        show_toolbar: bool = True,
        title: str = "Terminal",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Создает панель вывода терминала с ViewModel.
        
        Args:
            terminal_vm: TerminalViewModel для управления состоянием (ТРЕБУЕТСЯ)
            show_toolbar: Показывать панель инструментов (по умолчанию True)
            title: Заголовок для toolbar
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "terminal-output", classes=classes)
        self._terminal_vm = terminal_vm
        self._show_toolbar = show_toolbar
        self._title = title
        self._exit_code: int | None = None
        self._toolbar: TerminalOutputToolbar | None = None
        self._content: TerminalOutputContent | None = None

        # Подписываемся на изменения ViewModel
        self._terminal_vm.output.subscribe(self._on_output_changed)
        self._terminal_vm.has_output.subscribe(self._on_has_output_changed)
        self._terminal_vm.is_running.subscribe(self._on_running_changed)

    def compose(self) -> ComposeResult:
        """Создаёт содержимое панели."""
        self._toolbar = TerminalOutputToolbar(title=self._title)
        yield self._toolbar
        self._content = TerminalOutputContent()
        yield self._content

    def on_mount(self) -> None:
        """Настраивает компонент при монтировании."""
        if not self._show_toolbar:
            self.add_class("-no-toolbar")
        # Синхронизируем начальное состояние
        self._sync_content()

    def _sync_content(self) -> None:
        """Синхронизирует контент с ViewModel."""
        if self._content:
            self._content.set_output(self._terminal_vm.output.value)
            self._content.set_exit_code(self._exit_code)

    def _on_output_changed(self, output: str) -> None:
        """Обработчик изменения вывода в ViewModel.
        
        Args:
            output: Новый текст вывода
        """
        with suppress(RuntimeError):
            if self._content:
                self._content.set_output(output)
                self._content.set_exit_code(self._exit_code)

    def _on_has_output_changed(self, has_output: bool) -> None:
        """Обработчик изменения флага наличия вывода.
        
        Args:
            has_output: True если есть вывод, False если пусто
        """
        # Вызывается автоматически при изменении output
        pass

    def _on_running_changed(self, is_running: bool) -> None:
        """Обработчик изменения статуса выполнения команды.
        
        Args:
            is_running: True если команда выполняется, False если завершена
        """
        # Можно добавить индикатор выполнения в toolbar
        if self._toolbar:
            status = "⏳" if is_running else ""
            self._toolbar.set_title(f"{self._title} {status}".strip())

    def on_terminal_output_toolbar_clear_requested(
        self, event: TerminalOutputToolbar.ClearRequested
    ) -> None:
        """Обрабатывает запрос на очистку."""
        self.reset()
        self.post_message(self.OutputCleared())

    def on_terminal_output_toolbar_copy_requested(
        self, event: TerminalOutputToolbar.CopyRequested
    ) -> None:
        """Обрабатывает запрос на копирование."""
        output = self._terminal_vm.output.value
        if output:
            # Отправляем сообщение для обработки на уровне приложения
            self.post_message(self.OutputCopied(output))

    def reset(self) -> None:
        """Сбрасывает вывод терминала через ViewModel."""
        self._terminal_vm.clear_output()
        self._exit_code = None
        if self._content:
            self._content.clear()

    def append_output(self, output: str) -> None:
        """Добавляет очередной chunk stdout/stderr через ViewModel.
        
        Args:
            output: Текст для добавления в конец вывода
        """
        if output:
            self._terminal_vm.append_output(output)

    def set_output(self, output: str) -> None:
        """Установить весь вывод через ViewModel.
        
        Args:
            output: Новый текст вывода (заменяет предыдущий)
        """
        self._terminal_vm.set_output(output)

    def set_exit_code(self, exit_code: int | None) -> None:
        """Сохраняет известный exit code завершенного терминального процесса.
        
        Args:
            exit_code: Код завершения процесса или None
        """
        self._exit_code = exit_code
        if self._content:
            self._content.set_exit_code(exit_code)

    def set_title(self, title: str) -> None:
        """Устанавливает заголовок toolbar.
        
        Args:
            title: Новый заголовок
        """
        self._title = title
        if self._toolbar:
            self._toolbar.set_title(title)

    def render_text(self) -> Text:
        """Возвращает итоговый Rich Text с ANSI-цветами и статусной строкой.
        
        Метод для обратной совместимости с предыдущей версией.
        """
        output = self._terminal_vm.output.value

        # Если нет вывода
        if not output:
            if self._exit_code is None:
                return Text("Нет вывода терминала")
            return Text(f"Exit code: {self._exit_code}")

        # Рендеризуем вывод с ANSI поддержкой
        output_text = Text.from_ansi(output)

        # Добавляем exit code если доступен
        if self._exit_code is not None:
            output_text.append(f"\n\nExit code: {self._exit_code}", style="bold")

        return output_text

    @property
    def toolbar_visible(self) -> bool:
        """Видимость toolbar."""
        return self._show_toolbar

    @toolbar_visible.setter
    def toolbar_visible(self, visible: bool) -> None:
        """Устанавливает видимость toolbar."""
        self._show_toolbar = visible
        if visible:
            self.remove_class("-no-toolbar")
        else:
            self.add_class("-no-toolbar")

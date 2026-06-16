"""TerminalPanel - улучшенная панель терминала.

Встроенный терминал с поддержкой:
- Множественные сессии терминала
- Табы для переключения
- Copy/paste поддержка
- Цветной вывод (ANSI colors)
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Label, RichLog

from .tabs import TabBar


@dataclass
class TerminalSession:
    """Сессия терминала.

    Атрибуты:
        id: Уникальный идентификатор сессии
        name: Отображаемое имя
        cwd: Рабочая директория
        output: Буфер вывода
        created_at: Время создания
    """

    id: str
    name: str
    cwd: str = ""
    output: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def add_output(self, text: str) -> None:
        """Добавляет текст в буфер вывода."""
        self.output.append(text)


class TerminalOutput(RichLog):
    """Виджет вывода терминала с поддержкой ANSI цветов."""

    DEFAULT_CSS = """
    TerminalOutput {
        width: 100%;
        height: 1fr;
        background: $background;
        color: $foreground;
        padding: 0 1;
        scrollbar-gutter: stable;
    }
    """

    def __init__(
        self,
        session_id: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует вывод терминала.

        Args:
            session_id: ID связанной сессии
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(
            name=name,
            id=id or f"terminal-output-{session_id}",
            classes=classes,
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=True,
        )
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        """ID связанной сессии."""
        return self._session_id

    def append(self, text: str) -> None:
        """Добавляет текст в вывод.

        Args:
            text: Текст для добавления (может содержать ANSI коды)
        """
        self.write(text)

    def clear_output(self) -> None:
        """Очищает вывод терминала."""
        self.clear()


class TerminalToolbar(Horizontal):
    """Панель инструментов терминала."""

    DEFAULT_CSS = """
    TerminalToolbar {
        width: 100%;
        height: 1;
        background: $background-secondary;
        padding: 0 1;
    }

    TerminalToolbar .toolbar-title {
        width: 1fr;
        content-align: left middle;
        color: $foreground-muted;
    }

    TerminalToolbar .toolbar-button {
        width: auto;
        min-width: 0;
        height: 1;
        border: none;
        background: transparent;
        margin-left: 1;
    }

    TerminalToolbar .toolbar-button:hover {
        background: $background-tertiary;
    }
    """

    class NewSessionRequested(Message):
        """Запрос на создание новой сессии."""

        pass

    class ClearRequested(Message):
        """Запрос на очистку вывода."""

        pass

    class CopyRequested(Message):
        """Запрос на копирование."""

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
            title: Заголовок
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "terminal-toolbar", classes=classes)
        self._title = title

    def compose(self) -> ComposeResult:
        """Создаёт содержимое панели."""
        yield Label(self._title, classes="toolbar-title")
        yield Button("+", classes="toolbar-button", variant="default")
        yield Button("🗑", classes="toolbar-button", variant="default")
        yield Button("📋", classes="toolbar-button", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обрабатывает нажатия кнопок."""
        label = event.button.label
        if label == "+":
            self.post_message(self.NewSessionRequested())
        elif label == "🗑":
            self.post_message(self.ClearRequested())
        elif label == "📋":
            self.post_message(self.CopyRequested())

    def set_title(self, title: str) -> None:
        """Устанавливает заголовок.

        Args:
            title: Новый заголовок
        """
        self._title = title
        with contextlib.suppress(Exception):
            self.query_one(".toolbar-title", Label).update(title)


class TerminalPanel(Container):
    """Панель терминала с множественными сессиями.

    Поддерживает:
    - Создание и переключение между сессиями
    - Табы для навигации
    - Цветной вывод
    - Очистка и копирование
    """

    DEFAULT_CSS = """
    TerminalPanel {
        width: 100%;
        height: 100%;
        layout: vertical;
        background: $background;
        border: solid $border;
    }

    TerminalPanel .terminal-tabs {
        height: 3;
    }

    TerminalPanel .terminal-content {
        height: 1fr;
    }

    TerminalPanel .terminal-content > * {
        display: none;
    }

    TerminalPanel .terminal-content > .-active {
        display: block;
    }
    """

    # Счётчик для генерации ID сессий
    _session_counter: ClassVar[int] = 0

    class SessionCreated(Message):
        """Сообщение о создании сессии."""

        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class SessionClosed(Message):
        """Сообщение о закрытии сессии."""

        def __init__(self, session_id: str) -> None:
            self.session_id = session_id
            super().__init__()

    class OutputReceived(Message):
        """Сообщение о получении вывода."""

        def __init__(self, session_id: str, text: str) -> None:
            self.session_id = session_id
            self.text = text
            super().__init__()

    active_session: reactive[str | None] = reactive(None)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует панель терминала."""
        super().__init__(name=name, id=id or "terminal-panel", classes=classes)
        self._sessions: dict[str, TerminalSession] = {}
        self._outputs: dict[str, TerminalOutput] = {}
        self._tab_bar: TabBar | None = None
        self._content: Container | None = None

    def compose(self) -> ComposeResult:
        """Создаёт содержимое панели."""
        yield TerminalToolbar()
        self._tab_bar = TabBar(classes="terminal-tabs")
        yield self._tab_bar
        self._content = Container(classes="terminal-content")
        yield self._content

    def on_mount(self) -> None:
        """Создаёт первую сессию при монтировании."""
        if not self._sessions:
            self.create_session("Terminal 1")

    def create_session(self, name: str | None = None) -> str:
        """Создаёт новую сессию терминала.

        Args:
            name: Имя сессии (генерируется если не указано)

        Returns:
            ID созданной сессии
        """
        TerminalPanel._session_counter += 1
        session_id = f"term-{TerminalPanel._session_counter}"

        if name is None:
            name = f"Terminal {TerminalPanel._session_counter}"

        session = TerminalSession(id=session_id, name=name)
        self._sessions[session_id] = session

        # Создаём виджет вывода
        output = TerminalOutput(session_id)
        self._outputs[session_id] = output

        # Добавляем в контейнер
        if self._content:
            self._content.mount(output)

        # Добавляем таб
        if self._tab_bar:
            self._tab_bar.add_tab(session_id, name, icon="⌨")

        self.post_message(self.SessionCreated(session_id))
        return session_id

    def close_session(self, session_id: str) -> bool:
        """Закрывает сессию терминала.

        Args:
            session_id: ID сессии для закрытия

        Returns:
            True если сессия была закрыта
        """
        if session_id not in self._sessions:
            return False

        # Удаляем сессию
        del self._sessions[session_id]

        # Удаляем виджет вывода
        if session_id in self._outputs:
            self._outputs[session_id].remove()
            del self._outputs[session_id]

        # Удаляем таб
        if self._tab_bar:
            self._tab_bar.remove_tab(session_id)

        self.post_message(self.SessionClosed(session_id))
        return True

    def write_to_session(self, session_id: str, text: str) -> None:
        """Записывает текст в сессию.

        Args:
            session_id: ID сессии
            text: Текст для записи
        """
        if session_id in self._sessions:
            self._sessions[session_id].add_output(text)

        if session_id in self._outputs:
            self._outputs[session_id].append(text)

        self.post_message(self.OutputReceived(session_id, text))

    def write(self, text: str) -> None:
        """Записывает текст в активную сессию.

        Args:
            text: Текст для записи
        """
        if self.active_session:
            self.write_to_session(self.active_session, text)

    def clear_session(self, session_id: str) -> None:
        """Очищает вывод сессии.

        Args:
            session_id: ID сессии
        """
        if session_id in self._sessions:
            self._sessions[session_id].output.clear()

        if session_id in self._outputs:
            self._outputs[session_id].clear_output()

    def clear_active(self) -> None:
        """Очищает активную сессию."""
        if self.active_session:
            self.clear_session(self.active_session)

    def watch_active_session(self, session_id: str | None) -> None:
        """Обновляет отображение при смене активной сессии."""
        for sid, output in self._outputs.items():
            output.set_class(sid == session_id, "-active")

    def on_tab_bar_tab_activated(self, event: TabBar.TabActivated) -> None:
        """Обрабатывает переключение табов."""
        self.active_session = event.tab_id

    def on_tab_bar_tab_closed(self, event: TabBar.TabClosed) -> None:
        """Обрабатывает закрытие таба."""
        self.close_session(event.tab_id)

    def on_terminal_toolbar_new_session_requested(
        self, event: TerminalToolbar.NewSessionRequested
    ) -> None:
        """Создаёт новую сессию."""
        self.create_session()

    def on_terminal_toolbar_clear_requested(
        self, event: TerminalToolbar.ClearRequested
    ) -> None:
        """Очищает активную сессию."""
        self.clear_active()

    def on_terminal_toolbar_copy_requested(
        self, event: TerminalToolbar.CopyRequested
    ) -> None:
        """Копирует содержимое в буфер обмена."""
        # TODO: реализовать копирование через pyperclip или системный буфер
        pass

    @property
    def sessions(self) -> list[str]:
        """Список ID сессий."""
        return list(self._sessions.keys())

    def get_session(self, session_id: str) -> TerminalSession | None:
        """Получает данные сессии.

        Args:
            session_id: ID сессии

        Returns:
            Данные сессии или None
        """
        return self._sessions.get(session_id)

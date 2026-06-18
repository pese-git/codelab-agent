"""Компонент SessionTurn - объединение user prompt + assistant response.

Отвечает за:
- Объединение user prompt + assistant response в один turn
- Статус turn: pending, streaming, complete, error
- Индикатор thinking/загрузки
- Expand/collapse для длинных turns

Референс OpenCode: packages/web/src/ui/session/turn.tsx
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Static

from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
from codelab.client.tui.components.streaming_text import StreamingText, ThinkingIndicator


class TurnStatus(Enum):
    """Статусы turn."""
    
    PENDING = "pending"      # Ожидает ответа агента
    STREAMING = "streaming"  # Streaming ответ агента
    COMPLETE = "complete"    # Завершен успешно
    ERROR = "error"          # Завершен с ошибкой
    CANCELLED = "cancelled"  # Отменен


@dataclass
class TurnData:
    """Данные одного turn (prompt + response)."""
    
    turn_id: str
    user_content: str
    user_timestamp: datetime | None = None
    assistant_content: str = ""
    assistant_timestamp: datetime | None = None
    status: TurnStatus = TurnStatus.PENDING
    error_message: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class TurnStatusIndicator(Static):
    """Индикатор статуса turn."""
    
    DEFAULT_CSS = """
    TurnStatusIndicator {
        width: auto;
        height: 1;
        padding: 0 1;
    }
    
    TurnStatusIndicator.pending {
        color: $text-muted;
    }
    
    TurnStatusIndicator.streaming {
        color: $primary;
    }
    
    TurnStatusIndicator.complete {
        color: $success;
    }
    
    TurnStatusIndicator.error {
        color: $error;
    }
    
    TurnStatusIndicator.cancelled {
        color: $warning;
    }
    """
    
    STATUS_ICONS = {
        TurnStatus.PENDING: "⏳",
        TurnStatus.STREAMING: "📡",
        TurnStatus.COMPLETE: "✅",
        TurnStatus.ERROR: "❌",
        TurnStatus.CANCELLED: "🚫",
    }
    
    STATUS_LABELS = {
        TurnStatus.PENDING: "Ожидание...",
        TurnStatus.STREAMING: "Streaming...",
        TurnStatus.COMPLETE: "",
        TurnStatus.ERROR: "Ошибка",
        TurnStatus.CANCELLED: "Отменено",
    }
    
    def __init__(
        self,
        status: TurnStatus = TurnStatus.PENDING,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует TurnStatusIndicator.
        
        Args:
            status: Начальный статус
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        self._status = status
        status_class = status.value if classes is None else f"{classes} {status.value}"
        
        icon = self.STATUS_ICONS.get(status, "")
        label = self.STATUS_LABELS.get(status, "")
        text = f"{icon} {label}".strip() if label else icon
        
        super().__init__(text, name=name, id=id, classes=status_class)
    
    def update_status(self, status: TurnStatus) -> None:
        """Обновляет статус.
        
        Args:
            status: Новый статус
        """
        # Удаляем старый класс статуса
        self.remove_class(self._status.value)
        self._status = status
        self.add_class(status.value)
        
        icon = self.STATUS_ICONS.get(status, "")
        label = self.STATUS_LABELS.get(status, "")
        text = f"{icon} {label}".strip() if label else icon
        self.update(text)


class ToolCallWidget(Static):
    """Виджет отображения tool call."""
    
    DEFAULT_CSS = """
    ToolCallWidget {
        width: 100%;
        height: auto;
        padding: 1;
        margin: 1 0;
        background: $surface;
        border: dashed $primary;
    }
    
    ToolCallWidget > .tool-header {
        text-style: bold;
        color: $primary;
    }
    
    ToolCallWidget > .tool-args {
        color: $text-muted;
        margin-left: 2;
    }
    """
    
    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует ToolCallWidget.
        
        Args:
            tool_name: Имя инструмента
            arguments: Аргументы вызова
            result: Результат выполнения
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        self._tool_name = tool_name
        self._arguments = arguments
        self._result = result
        
        # Форматируем отображение
        lines = [f"[bold]🔧 {tool_name}[/bold]"]
        
        if arguments:
            args_str = ", ".join(f"{k}={v!r}" for k, v in list(arguments.items())[:3])
            if len(arguments) > 3:
                args_str += ", ..."
            lines.append(f"  [dim]Args: {args_str}[/dim]")
        
        if result:
            result_preview = result[:100] + "..." if len(result) > 100 else result
            lines.append(f"  [dim]→ {result_preview}[/dim]")
        
        super().__init__("\n".join(lines), name=name, id=id, classes=classes, markup=True)


class SessionTurn(Vertical):
    """Компонент для отображения одного turn (prompt + response).
    
    Turn объединяет:
    - Сообщение пользователя (prompt)
    - Индикатор thinking (при ожидании)
    - Streaming text (при получении ответа)
    - Сообщение ассистента (response)
    - Tool calls (если есть)
    - Статус turn
    
    Пример:
        >>> turn = SessionTurn(
        ...     turn_id="turn-1",
        ...     user_content="Как дела?",
        ... )
        >>> turn.start_streaming()
        >>> turn.update_streaming("Всё ")
        >>> turn.update_streaming("Всё хорошо!")
        >>> turn.complete("Всё хорошо!")
    """
    
    DEFAULT_CSS = """
    SessionTurn {
        width: 100%;
        height: auto;
        padding: 1;
        margin: 0 0 1 0;
        border: solid $primary 30%;
    }
    
    SessionTurn.complete {
        border: solid $success 30%;
    }
    
    SessionTurn.error {
        border: solid $error 30%;
    }
    
    SessionTurn > .turn-header {
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }
    
    SessionTurn > .user-section {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    
    SessionTurn > .assistant-section {
        width: 100%;
        height: auto;
    }
    
    SessionTurn > .tool-calls-section {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    """
    
    # Реактивные свойства
    status: reactive[TurnStatus] = reactive(TurnStatus.PENDING)
    is_collapsed: reactive[bool] = reactive(False)
    
    def __init__(
        self,
        turn_id: str,
        user_content: str,
        user_timestamp: datetime | None = None,
        assistant_content: str = "",
        assistant_timestamp: datetime | None = None,
        status: TurnStatus = TurnStatus.PENDING,
        tool_calls: list[dict[str, Any]] | None = None,
        collapsible: bool = True,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует SessionTurn.
        
        Args:
            turn_id: Уникальный ID turn
            user_content: Сообщение пользователя
            user_timestamp: Время сообщения пользователя
            assistant_content: Ответ ассистента
            assistant_timestamp: Время ответа
            status: Начальный статус
            tool_calls: Список tool calls
            collapsible: Можно ли сворачивать
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        # Внутренние виджеты - инициализируем ДО super().__init__
        # чтобы reactive watchers могли к ним обращаться
        self._status_indicator: TurnStatusIndicator | None = None
        self._thinking_indicator: ThinkingIndicator | None = None
        self._streaming_widget: StreamingText | None = None
        self._assistant_bubble: MessageBubble | None = None
        self._assistant_section: Container | None = None
        self._tool_calls_section: Container | None = None
        
        super().__init__(name=name, id=id or turn_id, classes=classes)
        
        self.turn_id = turn_id
        self._user_content = user_content
        self._user_timestamp = user_timestamp or datetime.now()
        self._assistant_content = assistant_content
        self._assistant_timestamp = assistant_timestamp
        self._tool_calls = tool_calls or []
        self._collapsible = collapsible
        
        # Устанавливаем статус после инициализации атрибутов
        self.status = status
    
    def compose(self) -> ComposeResult:
        """Создает структуру turn."""
        # Заголовок с ID и статусом
        with Container(classes="turn-header"):
            yield Static(f"[dim]Turn #{self.turn_id[-8:]}[/dim]", markup=True)
            self._status_indicator = TurnStatusIndicator(self.status)
            yield self._status_indicator
        
        # Секция пользователя
        with Container(classes="user-section"):
            yield MessageBubble(
                role=MessageRole.USER,
                content=self._user_content,
                timestamp=self._user_timestamp,
                show_avatar=True,
                show_header=True,
            )
        
        # Секция ассистента
        self._assistant_section = Container(classes="assistant-section")
        yield self._assistant_section
        
        # Секция tool calls
        self._tool_calls_section = Container(classes="tool-calls-section")
        yield self._tool_calls_section
    
    def on_mount(self) -> None:
        """Инициализирует начальное состояние при монтировании."""
        # Если уже есть ответ - показываем его
        if self._assistant_content:
            self._show_assistant_message()
        elif self.status == TurnStatus.PENDING:
            self._show_thinking()
        
        # Показываем tool calls если есть
        self._render_tool_calls()
    
    def watch_status(self, new_status: TurnStatus) -> None:
        """Реагирует на изменение статуса.
        
        Args:
            new_status: Новый статус
        """
        if self._status_indicator is not None:
            self._status_indicator.update_status(new_status)
        
        # Обновляем класс для стилизации
        self.remove_class("pending", "streaming", "complete", "error", "cancelled")
        self.add_class(new_status.value)
    
    def _show_thinking(self) -> None:
        """Показывает индикатор thinking."""
        if self._assistant_section is None:
            return
        
        self._hide_thinking()
        self._thinking_indicator = ThinkingIndicator("Агент думает")
        self._assistant_section.mount(self._thinking_indicator)
    
    def _hide_thinking(self) -> None:
        """Скрывает индикатор thinking."""
        if self._thinking_indicator is not None:
            self._thinking_indicator.remove()
            self._thinking_indicator = None
    
    def _show_streaming(self, initial_text: str = "") -> None:
        """Показывает streaming виджет.
        
        Args:
            initial_text: Начальный текст
        """
        if self._assistant_section is None:
            return
        
        self._hide_streaming()
        self._streaming_widget = StreamingText(initial_text)
        self._assistant_section.mount(self._streaming_widget)
    
    def _hide_streaming(self) -> None:
        """Скрывает streaming виджет."""
        if self._streaming_widget is not None:
            self._streaming_widget.remove()
            self._streaming_widget = None
    
    def _show_assistant_message(self) -> None:
        """Показывает финальное сообщение ассистента."""
        if self._assistant_section is None:
            return
        
        # Удаляем старый bubble если есть
        if self._assistant_bubble is not None:
            self._assistant_bubble.remove()
        
        self._assistant_bubble = MessageBubble(
            role=MessageRole.ASSISTANT,
            content=self._assistant_content,
            timestamp=self._assistant_timestamp or datetime.now(),
            show_avatar=True,
            show_header=True,
        )
        self._assistant_section.mount(self._assistant_bubble)
    
    def _render_tool_calls(self) -> None:
        """Рендерит tool calls."""
        if self._tool_calls_section is None:
            return
        
        self._tool_calls_section.query("*").remove()
        
        for tc in self._tool_calls:
            tool_name = tc.get("name", "unknown")
            arguments = tc.get("arguments", {})
            result = tc.get("result")
            
            widget = ToolCallWidget(tool_name, arguments, result)
            self._tool_calls_section.mount(widget)
    
    # --- Public API ---
    
    def start_streaming(self) -> None:
        """Переводит turn в режим streaming."""
        self._hide_thinking()
        self.status = TurnStatus.STREAMING
        self._show_streaming()
    
    def update_streaming(self, text: str) -> None:
        """Обновляет streaming текст.
        
        Args:
            text: Новый полный текст
        """
        if self._streaming_widget is not None:
            self._streaming_widget.set_text(text)
    
    def append_streaming(self, chunk: str) -> None:
        """Добавляет chunk к streaming.
        
        Args:
            chunk: Порция текста
        """
        if self._streaming_widget is not None:
            self._streaming_widget.append_text(chunk)
    
    def complete(self, assistant_content: str, timestamp: datetime | None = None) -> None:
        """Завершает turn успешно.
        
        Args:
            assistant_content: Финальный ответ ассистента
            timestamp: Время ответа
        """
        self._hide_thinking()
        self._hide_streaming()
        
        self._assistant_content = assistant_content
        self._assistant_timestamp = timestamp or datetime.now()
        self.status = TurnStatus.COMPLETE
        
        self._show_assistant_message()
    
    def fail(self, error_message: str) -> None:
        """Завершает turn с ошибкой.
        
        Args:
            error_message: Текст ошибки
        """
        self._hide_thinking()
        self._hide_streaming()
        
        self._assistant_content = f"❌ Ошибка: {error_message}"
        self.status = TurnStatus.ERROR
        
        self._show_assistant_message()
    
    def cancel(self) -> None:
        """Отменяет turn."""
        self._hide_thinking()
        self._hide_streaming()
        
        self._assistant_content = "🚫 Запрос отменен"
        self.status = TurnStatus.CANCELLED
        
        self._show_assistant_message()
    
    def add_tool_call(self, tool_call: dict[str, Any]) -> None:
        """Добавляет tool call.
        
        Args:
            tool_call: Данные tool call
        """
        self._tool_calls.append(tool_call)
        self._render_tool_calls()
    
    @property
    def user_content(self) -> str:
        """Возвращает сообщение пользователя."""
        return self._user_content
    
    @property
    def assistant_content(self) -> str:
        """Возвращает ответ ассистента."""
        return self._assistant_content
    
    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        """Возвращает список tool calls."""
        return self._tool_calls.copy()
    
    @classmethod
    def from_data(cls, data: TurnData, **kwargs: Any) -> SessionTurn:
        """Создает SessionTurn из TurnData.
        
        Args:
            data: Данные turn
            **kwargs: Дополнительные аргументы
            
        Returns:
            Экземпляр SessionTurn
        """
        return cls(
            turn_id=data.turn_id,
            user_content=data.user_content,
            user_timestamp=data.user_timestamp,
            assistant_content=data.assistant_content,
            assistant_timestamp=data.assistant_timestamp,
            status=data.status,
            tool_calls=data.tool_calls,
            **kwargs,
        )

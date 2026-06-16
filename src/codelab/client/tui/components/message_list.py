"""Компонент MessageList - контейнер для списка сообщений.

Отвечает за:
- Контейнер для списка сообщений
- Auto-scroll к последнему сообщению  
- Группировка по дате/времени (опционально)

Референс OpenCode: packages/web/src/ui/session/message-list.tsx
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static

from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
from codelab.client.tui.components.streaming_text import StreamingText, ThinkingIndicator

if TYPE_CHECKING:
    pass


class DateSeparator(Static):
    """Разделитель с датой между сообщениями.
    
    Показывает дату для группировки сообщений.
    """
    
    DEFAULT_CSS = """
    DateSeparator {
        width: 100%;
        height: 1;
        text-align: center;
        color: $text-muted;
        margin: 1 0;
    }
    """
    
    def __init__(
        self,
        date: datetime,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует DateSeparator.
        
        Args:
            date: Дата для отображения
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        today = datetime.now().date()
        message_date = date.date()
        
        if message_date == today:
            date_str = "Сегодня"
        elif (today - message_date).days == 1:
            date_str = "Вчера"
        else:
            date_str = date.strftime("%d %B %Y")
        
        super().__init__(f"── {date_str} ──", name=name, id=id, classes=classes)


class MessageList(VerticalScroll):
    """Скроллируемый контейнер для списка сообщений.
    
    Поддерживает:
    - Добавление сообщений динамически
    - Auto-scroll к последнему сообщению
    - Группировку по датам (опционально)
    - Streaming text для активного ответа
    - Thinking indicator
    
    Пример:
        >>> msg_list = MessageList()
        >>> msg_list.add_message(MessageRole.USER, "Привет!")
        >>> msg_list.add_message(MessageRole.ASSISTANT, "Здравствуйте!")
        >>> msg_list.scroll_to_bottom()
    """
    
    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        padding: 1;
        background: $surface;
    }
    
    MessageList > #message-container {
        width: 100%;
        height: auto;
        layout: vertical;
    }
    
    MessageList > .empty-state {
        width: 100%;
        height: auto;
        text-align: center;
        color: $text-muted;
        padding: 2;
    }
    """
    
    def __init__(
        self,
        messages: list[dict[str, Any]] | None = None,
        *,
        group_by_date: bool = False,
        show_avatars: bool = True,
        show_headers: bool = True,
        empty_message: str = "Начните диалог, отправив сообщение",
        auto_scroll: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует MessageList.
        
        Args:
            messages: Начальный список сообщений
            group_by_date: Группировать ли по датам
            show_avatars: Показывать аватары
            show_headers: Показывать заголовки
            empty_message: Текст при пустом списке
            auto_scroll: Автоматически скроллить вниз
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._messages = messages or []
        self._group_by_date = group_by_date
        self._show_avatars = show_avatars
        self._show_headers = show_headers
        self._empty_message = empty_message
        self._auto_scroll = auto_scroll
        
        self._container: Container | None = None
        self._streaming_widget: StreamingText | None = None
        self._thinking_indicator: ThinkingIndicator | None = None
        self._last_date: datetime | None = None
        self._message_count = 0
    
    def compose(self) -> ComposeResult:
        """Создает структуру списка сообщений."""
        self._container = Container(id="message-container")
        yield self._container
    
    def on_mount(self) -> None:
        """Отрисовывает начальные сообщения при монтировании."""
        self._render_messages()
    
    def _render_messages(self) -> None:
        """Перерисовывает все сообщения."""
        if self._container is None:
            return
        
        # Очищаем контейнер
        self._container.query("*").remove()
        self._last_date = None
        self._message_count = 0
        
        # Если список пуст - показываем empty state
        if not self._messages:
            self._container.mount(
                Static(self._empty_message, classes="empty-state")
            )
            return
        
        # Рендерим сообщения
        for msg in self._messages:
            self._add_message_widget(msg)
        
        # Scroll вниз
        if self._auto_scroll:
            self.scroll_end(animate=False)
    
    def _add_message_widget(self, message: dict[str, Any]) -> None:
        """Добавляет виджет сообщения в контейнер.
        
        Args:
            message: Данные сообщения
        """
        if self._container is None:
            return
        
        # Добавляем разделитель даты если нужно
        if self._group_by_date:
            ts = message.get("timestamp")
            if isinstance(ts, datetime):
                msg_date = ts.date()
                if self._last_date is None or self._last_date != msg_date:
                    self._container.mount(DateSeparator(ts))
                    self._last_date = msg_date
        
        # Создаем и добавляем MessageBubble
        bubble = MessageBubble.from_dict(
            message,
            show_avatar=self._show_avatars,
            show_header=self._show_headers,
        )
        bubble.id = f"message-{self._message_count}"
        self._message_count += 1
        self._container.mount(bubble)
    
    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        """Устанавливает список сообщений (полная замена).
        
        Args:
            messages: Новый список сообщений
        """
        self._messages = messages
        self._render_messages()
    
    def add_message(
        self,
        role: MessageRole | str,
        content: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Добавляет новое сообщение в список.
        
        Args:
            role: Роль отправителя
            content: Текст сообщения
            timestamp: Время сообщения (по умолчанию - сейчас)
        """
        role_str = role.value if isinstance(role, MessageRole) else role
        
        message = {
            "role": role_str,
            "content": content,
            "timestamp": timestamp or datetime.now(),
        }
        self._messages.append(message)
        
        # Удаляем empty state если был
        if self._container is not None:
            self._container.query(".empty-state").remove()
        
        # Добавляем виджет
        self._add_message_widget(message)
        
        # Scroll вниз
        if self._auto_scroll:
            self.scroll_end(animate=True)
    
    def clear(self) -> None:
        """Очищает список сообщений."""
        self._messages = []
        self._render_messages()
    
    @property
    def messages(self) -> list[dict[str, Any]]:
        """Возвращает список сообщений."""
        return self._messages.copy()
    
    @property
    def message_count(self) -> int:
        """Возвращает количество сообщений."""
        return len(self._messages)
    
    def scroll_to_bottom(self, animate: bool = True) -> None:
        """Прокручивает к последнему сообщению.
        
        Args:
            animate: Анимировать ли прокрутку
        """
        self.scroll_end(animate=animate)
    
    # --- Streaming support ---
    
    def start_streaming(self, initial_text: str = "") -> None:
        """Начинает streaming режим с отображением курсора.
        
        Args:
            initial_text: Начальный текст
        """
        if self._container is None:
            return
        
        # Удаляем старый streaming виджет если есть
        self.stop_streaming()
        
        # Создаем новый streaming виджет
        self._streaming_widget = StreamingText(initial_text)
        self._container.mount(self._streaming_widget)
        
        if self._auto_scroll:
            self.scroll_end(animate=True)
    
    def update_streaming(self, text: str) -> None:
        """Обновляет текст в streaming режиме.
        
        Args:
            text: Новый полный текст
        """
        if self._streaming_widget is not None:
            self._streaming_widget.set_text(text)
            if self._auto_scroll:
                self.scroll_end(animate=False)
    
    def append_streaming(self, chunk: str) -> None:
        """Добавляет chunk к streaming тексту.
        
        Args:
            chunk: Порция текста
        """
        if self._streaming_widget is not None:
            self._streaming_widget.append_text(chunk)
            if self._auto_scroll:
                self.scroll_end(animate=False)
    
    def stop_streaming(self, final_text: str | None = None) -> None:
        """Завершает streaming и преобразует в обычное сообщение.
        
        Args:
            final_text: Финальный текст (если None - используется текущий)
        """
        if self._streaming_widget is not None:
            # Получаем финальный текст
            text = final_text if final_text is not None else self._streaming_widget.text
            
            # Удаляем streaming виджет
            self._streaming_widget.remove()
            self._streaming_widget = None
            
            # Добавляем как обычное сообщение
            if text:
                self.add_message(MessageRole.ASSISTANT, text)
    
    @property
    def is_streaming(self) -> bool:
        """Проверяет, активен ли streaming."""
        return self._streaming_widget is not None
    
    # --- Thinking indicator ---
    
    def show_thinking(self, label: str = "Агент думает") -> None:
        """Показывает индикатор "thinking".
        
        Args:
            label: Текст индикатора
        """
        if self._container is None:
            return
        
        self.hide_thinking()
        self._thinking_indicator = ThinkingIndicator(label)
        self._container.mount(self._thinking_indicator)
        
        if self._auto_scroll:
            self.scroll_end(animate=True)
    
    def hide_thinking(self) -> None:
        """Скрывает индикатор "thinking"."""
        if self._thinking_indicator is not None:
            self._thinking_indicator.remove()
            self._thinking_indicator = None
    
    @property
    def is_thinking(self) -> bool:
        """Проверяет, показан ли индикатор thinking."""
        return self._thinking_indicator is not None

"""Компонент MessageBubble для отображения одного сообщения в чате.

Отвечает за:
- Отображение одного сообщения с аватаром
- Различные стили для user/assistant/system
- Timestamp отображение
- Markdown контент внутри

Референс OpenCode: packages/web/src/ui/session/message.tsx
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Markdown as TextualMarkdown
from textual.widgets import Static


class MessageRole(Enum):
    """Роли отправителей сообщений."""
    
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    ERROR = "error"


class Avatar(Static):
    """Аватар отправителя сообщения.
    
    Отображает символ/эмодзи в зависимости от роли.
    """
    
    DEFAULT_CSS = """
    Avatar {
        width: 3;
        height: 1;
        padding: 0;
        margin-right: 1;
        text-align: center;
    }
    
    Avatar.user {
        color: $primary;
    }
    
    Avatar.assistant {
        color: $success;
    }
    
    Avatar.system {
        color: $warning;
    }
    
    Avatar.error {
        color: $error;
    }
    """
    
    # Иконки для разных ролей
    ROLE_ICONS = {
        MessageRole.USER: "👤",
        MessageRole.ASSISTANT: "🤖",
        MessageRole.SYSTEM: "⚙️",
        MessageRole.ERROR: "❌",
    }
    
    def __init__(
        self,
        role: MessageRole = MessageRole.USER,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует Avatar.
        
        Args:
            role: Роль отправителя
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        icon = self.ROLE_ICONS.get(role, "•")
        role_class = role.value if classes is None else f"{classes} {role.value}"
        super().__init__(icon, name=name, id=id, classes=role_class)
        self._role = role
    
    @property
    def role(self) -> MessageRole:
        """Возвращает роль."""
        return self._role


class MessageHeader(Horizontal):
    """Заголовок сообщения с именем отправителя и timestamp."""
    
    DEFAULT_CSS = """
    MessageHeader {
        height: 1;
        width: 100%;
        padding: 0;
    }
    
    MessageHeader > .sender-name {
        width: auto;
        text-style: bold;
    }
    
    MessageHeader > .sender-name.user {
        color: $primary;
    }
    
    MessageHeader > .sender-name.assistant {
        color: $success;
    }
    
    MessageHeader > .sender-name.system {
        color: $warning;
    }
    
    MessageHeader > .timestamp {
        width: auto;
        color: $text-muted;
        margin-left: 1;
    }
    """
    
    # Имена отправителей по ролям
    ROLE_NAMES = {
        MessageRole.USER: "Ты",
        MessageRole.ASSISTANT: "Агент",
        MessageRole.SYSTEM: "Система",
        MessageRole.ERROR: "Ошибка",
    }
    
    def __init__(
        self,
        role: MessageRole = MessageRole.USER,
        timestamp: datetime | None = None,
        custom_name: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует MessageHeader.
        
        Args:
            role: Роль отправителя
            timestamp: Время сообщения
            custom_name: Кастомное имя вместо стандартного
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._role = role
        self._timestamp = timestamp
        self._custom_name = custom_name
    
    def compose(self) -> ComposeResult:
        """Создает элементы заголовка."""
        # Имя отправителя
        sender_name = self._custom_name or self.ROLE_NAMES.get(self._role, "Unknown")
        yield Static(sender_name, classes=f"sender-name {self._role.value}")
        
        # Timestamp (если есть)
        if self._timestamp is not None:
            time_str = self._timestamp.strftime("%H:%M")
            yield Static(time_str, classes="timestamp")


class MessageContent(TextualMarkdown):
    """Контент сообщения с поддержкой Markdown.
    
    Использует textual.widgets.Markdown для корректного парсинга Markdown
    без смешения уровней абстракции.
    """
    
    DEFAULT_CSS = """
    MessageContent {
        width: 100%;
        height: auto;
        padding: 0;
    }
    
    MessageContent MarkdownBlock {
        padding: 0;
        margin: 0;
    }
    
    MessageContent MarkdownH1,
    MessageContent MarkdownH2,
    MessageContent MarkdownH3,
    MessageContent MarkdownH4,
    MessageContent MarkdownH5,
    MessageContent MarkdownH6 {
        padding: 0;
        margin: 0;
    }
    
    MessageContent MarkdownParagraph {
        padding: 0;
        margin: 0;
    }
    """
    
    def __init__(
        self,
        content: str = "",
        use_markdown: bool = True,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует MessageContent.
        
        Args:
            content: Текст сообщения
            use_markdown: Использовать ли Markdown форматирование
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        self._raw_content = content
        self._use_markdown = use_markdown
        
        super().__init__(content, name=name, id=id, classes=classes)
    
    @property
    def raw_content(self) -> str:
        """Возвращает исходный контент."""
        return self._raw_content
    
    def update_content(self, content: str) -> None:
        """Обновляет контент.
        
        Args:
            content: Новый текст
        """
        self._raw_content = content
        self.update(content)


class MessageBubble(Vertical):
    """Виджет для отображения одного сообщения в чате.
    
    Объединяет аватар, заголовок и контент сообщения
    в едином стилизованном контейнере.
    
    Пример:
        >>> msg = MessageBubble(
        ...     role=MessageRole.ASSISTANT,
        ...     content="Привет! Как я могу помочь?",
        ...     timestamp=datetime.now(),
        ... )
    """
    
    DEFAULT_CSS = """
    MessageBubble {
        width: 100%;
        height: auto;
        padding: 1;
        margin: 0 0 1 0;
        background: $surface;
        border: solid $primary 20%;
    }
    
    MessageBubble.user {
        background: $primary 20%;
        border: solid $primary;
    }
    
    MessageBubble.assistant {
        background: $success 20%;
        border: solid $success;
    }
    
    MessageBubble.system {
        background: $warning 20%;
        border: solid $warning;
    }
    
    MessageBubble.error {
        background: $error 20%;
        border: solid $error;
    }
    
    MessageBubble > .message-row {
        width: 100%;
        height: auto;
    }
    
    MessageBubble > .message-row > .message-body {
        width: 1fr;
        height: auto;
    }
    """
    
    def __init__(
        self,
        role: MessageRole = MessageRole.USER,
        content: str = "",
        timestamp: datetime | None = None,
        sender_name: str | None = None,
        show_avatar: bool = True,
        show_header: bool = True,
        use_markdown: bool = True,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует MessageBubble.
        
        Args:
            role: Роль отправителя (user, assistant, system, error)
            content: Текст сообщения
            timestamp: Время отправки
            sender_name: Кастомное имя отправителя
            show_avatar: Показывать ли аватар
            show_header: Показывать ли заголовок (имя + время)
            use_markdown: Форматировать как Markdown
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        role_class = role.value if classes is None else f"{classes} {role.value}"
        super().__init__(name=name, id=id, classes=role_class)
        
        self._role = role
        self._content = content
        self._timestamp = timestamp
        self._sender_name = sender_name
        self._show_avatar = show_avatar
        self._show_header = show_header
        self._use_markdown = use_markdown
        self._content_widget: MessageContent | None = None
    
    def compose(self) -> ComposeResult:
        """Создает структуру сообщения."""
        # Горизонтальный контейнер: Avatar + Body
        with Horizontal(classes="message-row"):
            # Аватар (опционально)
            if self._show_avatar:
                yield Avatar(self._role)
            
            # Тело сообщения
            with Vertical(classes="message-body"):
                # Заголовок (опционально)
                if self._show_header:
                    yield MessageHeader(
                        role=self._role,
                        timestamp=self._timestamp,
                        custom_name=self._sender_name,
                    )
                
                # Контент
                self._content_widget = MessageContent(
                    content=self._content,
                    use_markdown=self._use_markdown,
                )
                yield self._content_widget
    
    @property
    def role(self) -> MessageRole:
        """Возвращает роль отправителя."""
        return self._role
    
    @property
    def content(self) -> str:
        """Возвращает текст сообщения."""
        return self._content
    
    @property
    def timestamp(self) -> datetime | None:
        """Возвращает timestamp сообщения."""
        return self._timestamp
    
    def update_content(self, content: str) -> None:
        """Обновляет контент сообщения.
        
        Args:
            content: Новый текст
        """
        self._content = content
        if self._content_widget is not None:
            self._content_widget.update_content(content)
    
    @classmethod
    def from_dict(
        cls,
        message: dict[str, Any],
        show_avatar: bool = True,
        show_header: bool = True,
    ) -> MessageBubble:
        """Создает MessageBubble из словаря сообщения.
        
        Args:
            message: Словарь с ключами role, content, timestamp (опц.)
            show_avatar: Показывать ли аватар
            show_header: Показывать ли заголовок
            
        Returns:
            Экземпляр MessageBubble
        """
        # Извлекаем роль
        role_str = message.get("role") or message.get("type", "user")
        try:
            role = MessageRole(role_str)
        except ValueError:
            role = MessageRole.USER
        
        # Извлекаем контент
        content = str(message.get("content", ""))
        
        # Извлекаем timestamp (если есть)
        ts_value = message.get("timestamp")
        timestamp = None
        if isinstance(ts_value, datetime):
            timestamp = ts_value
        elif isinstance(ts_value, str):
            import contextlib
            with contextlib.suppress(ValueError):
                timestamp = datetime.fromisoformat(ts_value)
        
        return cls(
            role=role,
            content=content,
            timestamp=timestamp,
            show_avatar=show_avatar,
            show_header=show_header,
        )

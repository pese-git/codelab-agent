"""Компонент для отображения streaming текста в реальном времени.

Отвечает за:
- Посимвольное/построчное отображение текста
- Cursor индикатор (мигающий)
- Поддержка Markdown в реальном времени

Референс OpenCode: используется в message для streaming response
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Markdown as TextualMarkdown
from textual.widgets import Static


class StreamingText(Container):
    """Виджет для отображения streaming текста с курсором.
    
    Показывает текст, который постепенно появляется (streaming),
    с мигающим курсором в конце для индикации активного состояния.
    
    Поддерживает:
    - Добавление текста посимвольно или порциями
    - Мигающий курсор (можно отключить)
    - Автоматическую конвертацию Markdown в Rich
    - Финализацию (убирает курсор после завершения)
    
    Пример:
        >>> streaming = StreamingText()
        >>> streaming.append_text("Hello ")
        >>> streaming.append_text("World!")
        >>> streaming.finalize()  # Убирает курсор
    """
    
    DEFAULT_CSS = """
    StreamingText {
        height: auto;
        padding: 0;
        margin: 0;
    }
    
    StreamingText > .streaming-content {
        height: auto;
        padding: 0;
        margin: 0;
    }
    
    StreamingText > .streaming-content MarkdownBlock {
        padding: 0;
        margin: 0;
    }
    
    StreamingText > .streaming-content MarkdownParagraph {
        padding: 0;
        margin: 0;
    }
    
    StreamingText > .streaming-cursor {
        width: 1;
        height: 1;
        background: $accent;
    }
    
    StreamingText > .streaming-cursor.hidden {
        display: none;
    }
    """
    
    # Реактивные свойства
    text: reactive[str] = reactive("", layout=True)
    is_streaming: reactive[bool] = reactive(True)
    show_cursor: reactive[bool] = reactive(True)
    
    # Символы курсора для анимации
    CURSOR_CHARS = ["▌", "▐"]
    
    def __init__(
        self,
        initial_text: str = "",
        *,
        show_cursor: bool = True,
        use_markdown: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует StreamingText.
        
        Args:
            initial_text: Начальный текст
            show_cursor: Показывать ли курсор
            use_markdown: Конвертировать Markdown в Rich markup
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._initial_text = initial_text
        self._use_markdown = use_markdown
        self._cursor_index = 0
        self._cursor_timer: Timer | None = None
        self._content_widget: TextualMarkdown | Static | None = None
        self._cursor_widget: Static | None = None
        
        # Устанавливаем начальные значения
        self.text = initial_text
        self.show_cursor = show_cursor
    
    def compose(self) -> ComposeResult:
        """Создает внутренние виджеты."""
        # Виджет для текстового контента
        if self._use_markdown:
            self._content_widget = TextualMarkdown(
                self._initial_text,
                classes="streaming-content",
            )
        else:
            self._content_widget = Static(
                self._initial_text,
                classes="streaming-content",
                markup=False,
            )
        yield self._content_widget
        
        # Виджет курсора
        cursor_classes = "streaming-cursor"
        if not self.show_cursor:
            cursor_classes += " hidden"
        self._cursor_widget = Static(self.CURSOR_CHARS[0], classes=cursor_classes)
        yield self._cursor_widget
    
    def on_mount(self) -> None:
        """Запускает таймер мигания курсора при монтировании."""
        if self.show_cursor:
            self._start_cursor_blink()
    
    def on_unmount(self) -> None:
        """Останавливает таймер при размонтировании."""
        self._stop_cursor_blink()
    
    def _start_cursor_blink(self) -> None:
        """Запускает анимацию мигания курсора."""
        if self._cursor_timer is None:
            self._cursor_timer = self.set_interval(0.5, self._toggle_cursor)
    
    def _stop_cursor_blink(self) -> None:
        """Останавливает анимацию мигания курсора."""
        if self._cursor_timer is not None:
            self._cursor_timer.stop()
            self._cursor_timer = None
    
    def _toggle_cursor(self) -> None:
        """Переключает символ курсора для анимации."""
        if self._cursor_widget is not None and self.show_cursor:
            self._cursor_index = (self._cursor_index + 1) % len(self.CURSOR_CHARS)
            self._cursor_widget.update(self.CURSOR_CHARS[self._cursor_index])
    
    def watch_text(self, new_text: str) -> None:
        """Реагирует на изменение текста.
        
        Args:
            new_text: Новый текст
        """
        if self._content_widget is not None:
            # Markdown.update() принимает Markdown текст напрямую
            # Static.update() принимает строку
            self._content_widget.update(new_text)
    
    def watch_show_cursor(self, show: bool) -> None:
        """Реагирует на изменение видимости курсора.
        
        Args:
            show: Показывать ли курсор
        """
        if self._cursor_widget is not None:
            if show:
                self._cursor_widget.remove_class("hidden")
                self._start_cursor_blink()
            else:
                self._cursor_widget.add_class("hidden")
                self._stop_cursor_blink()
    
    def watch_is_streaming(self, streaming: bool) -> None:
        """Реагирует на изменение статуса streaming.
        
        Args:
            streaming: Идет ли streaming
        """
        if not streaming:
            self.show_cursor = False
    
    def append_text(self, chunk: str) -> None:
        """Добавляет текст к существующему.
        
        Args:
            chunk: Порция текста для добавления
        """
        self.text = self.text + chunk
    
    def set_text(self, text: str) -> None:
        """Устанавливает текст полностью (заменяет существующий).
        
        Args:
            text: Новый текст
        """
        self.text = text
    
    def clear(self) -> None:
        """Очищает текст."""
        self.text = ""
    
    def finalize(self) -> None:
        """Завершает streaming (убирает курсор).
        
        Вызывается когда streaming закончен, чтобы убрать
        мигающий курсор и показать финальное состояние.
        """
        self.is_streaming = False


class TypewriterText(StreamingText):
    """Текст с эффектом печатной машинки.
    
    Расширяет StreamingText, добавляя автоматическое
    посимвольное отображение текста с задержкой.
    
    Пример:
        >>> typewriter = TypewriterText()
        >>> typewriter.type_text("Hello World!", delay=0.05)
    """
    
    def __init__(
        self,
        *,
        char_delay: float = 0.03,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует TypewriterText.
        
        Args:
            char_delay: Задержка между символами (в секундах)
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._char_delay = char_delay
        self._target_text = ""
        self._current_index = 0
        self._typing_timer: Timer | None = None
    
    def type_text(self, text: str, delay: float | None = None) -> None:
        """Запускает печать текста с эффектом typewriter.
        
        Args:
            text: Текст для печати
            delay: Задержка между символами (или использует default)
        """
        self._stop_typing()
        self._target_text = text
        self._current_index = 0
        self.text = ""
        self.is_streaming = True
        self.show_cursor = True
        
        actual_delay = delay if delay is not None else self._char_delay
        self._typing_timer = self.set_interval(actual_delay, self._type_next_char)
    
    def _stop_typing(self) -> None:
        """Останавливает текущую печать."""
        if self._typing_timer is not None:
            self._typing_timer.stop()
            self._typing_timer = None
    
    def _type_next_char(self) -> None:
        """Печатает следующий символ."""
        if self._current_index < len(self._target_text):
            self.text = self._target_text[:self._current_index + 1]
            self._current_index += 1
        else:
            self._stop_typing()
            self.finalize()
    
    def skip_to_end(self) -> None:
        """Пропускает анимацию и показывает весь текст сразу."""
        self._stop_typing()
        self.text = self._target_text
        self.finalize()


class ThinkingIndicator(Static):
    """Индикатор "thinking" / "typing" с анимацией.
    
    Показывает анимированные точки, индицирующие что агент думает.
    
    Пример:
        >>> indicator = ThinkingIndicator("Agent is thinking")
    """
    
    DEFAULT_CSS = """
    ThinkingIndicator {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """
    
    # Состояния анимации
    ANIMATION_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(
        self,
        label: str = "Thinking",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует ThinkingIndicator.
        
        Args:
            label: Текст метки
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._label = label
        self._frame_index = 0
        self._timer: Timer | None = None
    
    def on_mount(self) -> None:
        """Запускает анимацию при монтировании."""
        self._timer = self.set_interval(0.1, self._next_frame)
        self._update_display()
    
    def on_unmount(self) -> None:
        """Останавливает анимацию при размонтировании."""
        if self._timer is not None:
            self._timer.stop()
    
    def _next_frame(self) -> None:
        """Переключает на следующий кадр анимации."""
        self._frame_index = (self._frame_index + 1) % len(self.ANIMATION_FRAMES)
        self._update_display()
    
    def _update_display(self) -> None:
        """Обновляет отображение."""
        spinner = self.ANIMATION_FRAMES[self._frame_index]
        self.update(f"{spinner} [italic]{self._label}...[/italic]")
    
    def set_label(self, label: str) -> None:
        """Устанавливает новый текст метки.
        
        Args:
            label: Новый текст
        """
        self._label = label
        self._update_display()

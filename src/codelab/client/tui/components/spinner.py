"""Spinner - анимированный индикатор загрузки.

Компонент индикатора загрузки:
- Размеры: sm, md, lg
- Варианты анимации (dots, line, circle)
- Опциональный текст
"""

from __future__ import annotations

import asyncio
import contextlib
from enum import Enum
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label


class SpinnerSize(Enum):
    """Размеры спиннера."""

    SMALL = "sm"
    MEDIUM = "md"
    LARGE = "lg"


class SpinnerVariant(Enum):
    """Варианты анимации спиннера."""

    DOTS = "dots"
    LINE = "line"
    CIRCLE = "circle"
    ARROW = "arrow"
    PULSE = "pulse"


class Spinner(Widget):
    """Анимированный индикатор загрузки.

    Показывает анимацию во время выполнения асинхронных операций.
    Поддерживает различные размеры и стили анимации.
    """

    DEFAULT_CSS = """
    Spinner {
        width: auto;
        height: auto;
        layout: horizontal;
        content-align: center middle;
    }

    Spinner .spinner-animation {
        width: auto;
        height: auto;
        color: $primary;
    }

    Spinner .spinner-text {
        width: auto;
        margin-left: 1;
        color: $foreground-muted;
    }

    Spinner.-sm .spinner-animation {
        text-style: none;
    }

    Spinner.-md .spinner-animation {
        text-style: bold;
    }

    Spinner.-lg .spinner-animation {
        text-style: bold;
    }

    Spinner.-hidden {
        display: none;
    }
    """

    # Кадры анимации для разных вариантов
    ANIMATIONS: ClassVar[dict[SpinnerVariant, list[str]]] = {
        SpinnerVariant.DOTS: ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        SpinnerVariant.LINE: ["—", "\\", "|", "/"],
        SpinnerVariant.CIRCLE: ["◐", "◓", "◑", "◒"],
        SpinnerVariant.ARROW: ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        SpinnerVariant.PULSE: ["█", "▓", "▒", "░", "▒", "▓"],
    }

    # Скорость анимации (мс между кадрами)
    SPEEDS: ClassVar[dict[SpinnerSize, int]] = {
        SpinnerSize.SMALL: 100,
        SpinnerSize.MEDIUM: 80,
        SpinnerSize.LARGE: 60,
    }

    # Активна ли анимация
    spinning: reactive[bool] = reactive(True)

    # Текст рядом со спиннером
    text: reactive[str] = reactive("")

    def __init__(
        self,
        *,
        text: str = "",
        size: SpinnerSize = SpinnerSize.MEDIUM,
        variant: SpinnerVariant = SpinnerVariant.DOTS,
        spinning: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует спиннер.

        Args:
            text: Текст рядом со спиннером
            size: Размер спиннера
            variant: Вариант анимации
            spinning: Запустить анимацию сразу
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "spinner", classes=classes)
        self._spinner_size: SpinnerSize = size
        self._variant: SpinnerVariant = variant
        self._frame_index: int = 0
        self._animation_task: asyncio.Task | None = None

        # Добавляем класс размера
        self.add_class(f"-{size.value}")

        # Устанавливаем начальные значения
        self.text = text
        self.spinning = spinning

    def compose(self) -> ComposeResult:
        """Создаёт содержимое спиннера."""
        frames = self.ANIMATIONS[self._variant]
        with Horizontal():
            yield Label(frames[0], classes="spinner-animation")
            yield Label(self.text, classes="spinner-text")

    @property
    def animation_label(self) -> Label:
        """Возвращает виджет анимации."""
        return self.query_one(".spinner-animation", Label)

    @property
    def text_label(self) -> Label:
        """Возвращает виджет текста."""
        return self.query_one(".spinner-text", Label)

    def watch_spinning(self, spinning: bool) -> None:
        """Запускает/останавливает анимацию."""
        if spinning:
            self._start_animation()
        else:
            self._stop_animation()

    def watch_text(self, text: str) -> None:
        """Обновляет текст спиннера."""
        with contextlib.suppress(Exception):
            self.text_label.update(text)

    def _start_animation(self) -> None:
        """Запускает анимацию спиннера."""
        if self._animation_task:
            return

        frames = self.ANIMATIONS[self._variant]
        speed_ms = self.SPEEDS[self._spinner_size]

        async def animate() -> None:
            while True:
                self._frame_index = (self._frame_index + 1) % len(frames)
                with contextlib.suppress(Exception):
                    self.animation_label.update(frames[self._frame_index])
                await asyncio.sleep(speed_ms / 1000)

        self._animation_task = asyncio.create_task(animate())

    def _stop_animation(self) -> None:
        """Останавливает анимацию."""
        if self._animation_task:
            self._animation_task.cancel()
            self._animation_task = None

    def start(self) -> None:
        """Запускает спиннер."""
        self.spinning = True
        self.remove_class("-hidden")

    def stop(self) -> None:
        """Останавливает спиннер."""
        self.spinning = False

    def hide(self) -> None:
        """Скрывает спиннер."""
        self.stop()
        self.add_class("-hidden")

    def show(self) -> None:
        """Показывает спиннер."""
        self.remove_class("-hidden")
        self.start()

    def set_text(self, text: str) -> None:
        """Устанавливает текст спиннера.

        Args:
            text: Новый текст
        """
        self.text = text

    def set_variant(self, variant: SpinnerVariant) -> None:
        """Устанавливает вариант анимации.

        Args:
            variant: Новый вариант
        """
        was_spinning = self.spinning
        self._stop_animation()
        self._variant = variant
        self._frame_index = 0
        if was_spinning:
            self._start_animation()

    async def on_unmount(self) -> None:
        """Останавливает анимацию при размонтировании."""
        self._stop_animation()


class LoadingIndicator(Widget):
    """Индикатор загрузки с текстом и спиннером.

    Удобный композитный виджет для показа состояния загрузки.
    """

    DEFAULT_CSS = """
    LoadingIndicator {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 1;
    }

    LoadingIndicator.-hidden {
        display: none;
    }
    """

    # Виден ли индикатор
    visible: reactive[bool] = reactive(True)

    def __init__(
        self,
        text: str = "Загрузка...",
        *,
        size: SpinnerSize = SpinnerSize.MEDIUM,
        variant: SpinnerVariant = SpinnerVariant.DOTS,
        visible: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует индикатор загрузки.

        Args:
            text: Текст индикатора
            size: Размер спиннера
            variant: Вариант анимации
            visible: Показывать сразу
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "loading-indicator", classes=classes)
        self._text: str = text
        self._spinner_size: SpinnerSize = size
        self._variant: SpinnerVariant = variant
        self.visible = visible

    def compose(self) -> ComposeResult:
        """Создаёт спиннер с текстом."""
        yield Spinner(
            text=self._text,
            size=self._spinner_size,
            variant=self._variant,
            spinning=self.visible,
        )

    @property
    def spinner(self) -> Spinner:
        """Возвращает спиннер."""
        return self.query_one(Spinner)

    def watch_visible(self, visible: bool) -> None:
        """Обновляет видимость индикатора."""
        self.set_class(not visible, "-hidden")
        with contextlib.suppress(Exception):
            self.spinner.spinning = visible

    def show(self, text: str | None = None) -> None:
        """Показывает индикатор.

        Args:
            text: Опциональный новый текст
        """
        if text:
            self.spinner.text = text
        self.visible = True

    def hide(self) -> None:
        """Скрывает индикатор."""
        self.visible = False

    def set_text(self, text: str) -> None:
        """Устанавливает текст.

        Args:
            text: Новый текст
        """
        try:
            self.spinner.text = text
        except Exception:
            self._text = text

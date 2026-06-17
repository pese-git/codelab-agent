"""Toast Notifications - всплывающие уведомления.

Компонент для отображения уведомлений с авто-скрытием:
- Типы: info, success, warning, error
- Стек уведомлений (несколько одновременно)
- Auto-dismiss с настраиваемым таймером
- Позиция: bottom-right
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Label, Static


class ToastType(Enum):
    """Типы уведомлений с соответствующими стилями."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ToastData:
    """Данные уведомления.

    Атрибуты:
        message: Текст уведомления
        toast_type: Тип уведомления (info, success, warning, error)
        duration: Время отображения в секундах (0 = без авто-скрытия)
        title: Опциональный заголовок
    """

    message: str
    toast_type: ToastType = ToastType.INFO
    duration: float = 3.0
    title: str | None = None
    toast_id: str = field(default_factory=lambda: str(id(object())))


class Toast(Static):
    """Отдельное уведомление.

    Виджет уведомления с анимацией появления и исчезновения.
    Автоматически закрывается после указанного времени.
    """

    DEFAULT_CSS = """
    Toast {
        width: 40;
        height: auto;
        min-height: 3;
        padding: 0 1;
        margin: 0 0 1 0;
        border: solid $border;
        layer: toast;
    }

    Toast.-info {
        background: $primary 20%;
        border: solid $primary;
    }

    Toast.-success {
        background: $success 20%;
        border: solid $success;
    }

    Toast.-warning {
        background: $warning 20%;
        border: solid $warning;
    }

    Toast.-error {
        background: $error 20%;
        border: solid $error;
    }

    Toast .toast-title {
        text-style: bold;
        margin-bottom: 0;
    }

    Toast .toast-message {
        color: $text;
    }

    Toast .toast-icon {
        width: 3;
        height: auto;
    }

    Toast.-fading {
        opacity: 0;
    }
    """

    # Иконки для разных типов уведомлений
    ICONS: ClassVar[dict[ToastType, str]] = {
        ToastType.INFO: "ℹ",
        ToastType.SUCCESS: "✓",
        ToastType.WARNING: "⚠",
        ToastType.ERROR: "✗",
    }

    class Dismissed(Message):
        """Сообщение о закрытии уведомления."""

        def __init__(self, toast_id: str) -> None:
            self.toast_id = toast_id
            super().__init__()

    def __init__(
        self,
        data: ToastData,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует уведомление.

        Args:
            data: Данные уведомления
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._data = data
        self._dismiss_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        """Создаёт содержимое уведомления."""
        icon = self.ICONS.get(self._data.toast_type, "•")

        # Добавляем класс типа уведомления
        self.add_class(f"-{self._data.toast_type.value}")

        yield Label(f"{icon} ", classes="toast-icon")

        if self._data.title:
            yield Label(self._data.title, classes="toast-title")

        yield Label(self._data.message, classes="toast-message")

    async def on_mount(self) -> None:
        """Запускает таймер авто-скрытия при монтировании."""
        if self._data.duration > 0:
            self._dismiss_task = asyncio.create_task(self._auto_dismiss())

    async def _auto_dismiss(self) -> None:
        """Автоматически закрывает уведомление после таймаута."""
        await asyncio.sleep(self._data.duration)
        self.dismiss()

    def dismiss(self) -> None:
        """Закрывает уведомление с анимацией."""
        self.add_class("-fading")
        self.set_timer(0.3, self._remove)

    def _remove(self) -> None:
        """Удаляет уведомление из DOM."""
        self.post_message(self.Dismissed(self._data.toast_id))
        self.remove()

    async def on_click(self) -> None:
        """Закрывает уведомление при клике."""
        if self._dismiss_task:
            self._dismiss_task.cancel()
        self.dismiss()


class ToastContainer(Container):
    """Контейнер для стека уведомлений.

    Управляет отображением нескольких уведомлений одновременно.
    Позиционируется в правом нижнем углу экрана.
    """

    DEFAULT_CSS = """
    ToastContainer {
        dock: bottom;
        align: right bottom;
        width: auto;
        height: auto;
        max-height: 50%;
        padding: 1;
        layer: toast;
    }
    """

    # Максимальное количество одновременных уведомлений
    MAX_TOASTS: ClassVar[int] = 5

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует контейнер уведомлений."""
        super().__init__(name=name, id=id or "toast-container", classes=classes)
        self._toasts: dict[str, Toast] = {}

    def show_toast(
        self,
        message: str,
        *,
        toast_type: ToastType = ToastType.INFO,
        duration: float = 3.0,
        title: str | None = None,
    ) -> str:
        """Показывает новое уведомление.

        Args:
            message: Текст уведомления
            toast_type: Тип уведомления
            duration: Время отображения в секундах
            title: Опциональный заголовок

        Returns:
            ID созданного уведомления
        """
        data = ToastData(
            message=message,
            toast_type=toast_type,
            duration=duration,
            title=title,
        )

        # Удаляем старые уведомления если превышен лимит
        while len(self._toasts) >= self.MAX_TOASTS:
            oldest_id = next(iter(self._toasts))
            self._toasts[oldest_id].dismiss()

        toast = Toast(data)
        self._toasts[data.toast_id] = toast
        self.mount(toast)

        return data.toast_id

    def dismiss_toast(self, toast_id: str) -> None:
        """Закрывает уведомление по ID.

        Args:
            toast_id: ID уведомления для закрытия
        """
        if toast_id in self._toasts:
            self._toasts[toast_id].dismiss()

    def dismiss_all(self) -> None:
        """Закрывает все уведомления."""
        for toast in list(self._toasts.values()):
            toast.dismiss()

    def on_toast_dismissed(self, event: Toast.Dismissed) -> None:
        """Обрабатывает закрытие уведомления."""
        self._toasts.pop(event.toast_id, None)

    # Удобные методы для разных типов уведомлений

    def info(self, message: str, *, title: str | None = None, duration: float = 3.0) -> str:
        """Показывает информационное уведомление."""
        return self.show_toast(message, toast_type=ToastType.INFO, title=title, duration=duration)

    def success(self, message: str, *, title: str | None = None, duration: float = 3.0) -> str:
        """Показывает уведомление об успехе."""
        return self.show_toast(
            message, toast_type=ToastType.SUCCESS, title=title, duration=duration
        )

    def warning(self, message: str, *, title: str | None = None, duration: float = 5.0) -> str:
        """Показывает предупреждение."""
        return self.show_toast(
            message, toast_type=ToastType.WARNING, title=title, duration=duration
        )

    def error(self, message: str, *, title: str | None = None, duration: float = 0.0) -> str:
        """Показывает уведомление об ошибке (без авто-скрытия по умолчанию)."""
        return self.show_toast(message, toast_type=ToastType.ERROR, title=title, duration=duration)

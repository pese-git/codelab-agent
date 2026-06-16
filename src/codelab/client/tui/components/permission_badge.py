"""Компактный badge для статуса разрешения.

Цветовая индикация состояния:
- granted (green): разрешение выдано
- denied (red): разрешение отклонено  
- pending (yellow): ожидает решения
"""

from __future__ import annotations

from typing import Literal

from textual.widgets import Static

# Типы статусов разрешения
PermissionStatus = Literal["granted", "denied", "pending", "unknown"]


# Иконки для статусов
STATUS_ICONS: dict[PermissionStatus, str] = {
    "granted": "✓",
    "denied": "✗",
    "pending": "⏳",
    "unknown": "?",
}

# Текстовые метки для статусов
STATUS_LABELS: dict[PermissionStatus, str] = {
    "granted": "Разрешено",
    "denied": "Отклонено",
    "pending": "Ожидает",
    "unknown": "Неизвестно",
}


class PermissionBadge(Static):
    """Компактный badge для отображения статуса разрешения.
    
    Визуально показывает текущий статус разрешения через цвет и иконку.
    Используется в списках tool calls, панели разрешений и т.д.
    
    Пример использования:
        >>> badge = PermissionBadge("granted")
        >>> badge = PermissionBadge("pending", show_label=True)
    """

    DEFAULT_CSS = """
    PermissionBadge {
        width: auto;
        height: 1;
        padding: 0 1;
        text-style: bold;
    }
    
    PermissionBadge.granted {
        color: $success;
        background: $success 20%;
    }
    
    PermissionBadge.denied {
        color: $error;
        background: $error 20%;
    }
    
    PermissionBadge.pending {
        color: $warning;
        background: $warning 20%;
    }
    
    PermissionBadge.unknown {
        color: $text-muted;
        background: $surface;
    }
    
    PermissionBadge.compact {
        padding: 0;
        width: 1;
    }
    """

    def __init__(
        self,
        status: PermissionStatus = "unknown",
        *,
        show_label: bool = False,
        compact: bool = False,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Создаёт badge статуса разрешения.
        
        Args:
            status: Статус разрешения (granted, denied, pending, unknown)
            show_label: Показывать текстовую метку рядом с иконкой
            compact: Компактный режим (только иконка без padding)
            name: Имя виджета
            id: ID виджета
            classes: Дополнительные CSS классы
        """
        self._status = status
        self._show_label = show_label
        self._compact = compact
        
        # Формируем CSS классы
        css_classes = status
        if compact:
            css_classes = f"{css_classes} compact"
        if classes:
            css_classes = f"{css_classes} {classes}"
        
        # Формируем отображаемый текст
        display_text = self._format_display()
        
        super().__init__(display_text, name=name, id=id, classes=css_classes)
    
    def _format_display(self) -> str:
        """Форматировать текст для отображения.
        
        Returns:
            Строка с иконкой и опционально меткой
        """
        icon = STATUS_ICONS.get(self._status, "?")
        
        if self._show_label:
            label = STATUS_LABELS.get(self._status, "")
            return f"{icon} {label}"
        
        return icon
    
    @property
    def status(self) -> PermissionStatus:
        """Текущий статус разрешения."""
        return self._status
    
    @status.setter
    def status(self, value: PermissionStatus) -> None:
        """Установить новый статус разрешения.
        
        Args:
            value: Новый статус
        """
        # Удаляем старый класс статуса
        self.remove_class(self._status)
        
        # Устанавливаем новый
        self._status = value
        self.add_class(value)
        
        # Обновляем отображение
        self.update(self._format_display())
    
    @property
    def show_label(self) -> bool:
        """Показывается ли текстовая метка."""
        return self._show_label
    
    @show_label.setter
    def show_label(self, value: bool) -> None:
        """Установить отображение текстовой метки.
        
        Args:
            value: True для показа метки
        """
        self._show_label = value
        self.update(self._format_display())

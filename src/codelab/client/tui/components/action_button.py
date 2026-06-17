"""Стилизованная кнопка действия с вариантами оформления.

Референс OpenCode: packages/web/src/ui/button.tsx
Поддерживает варианты: primary, secondary, danger, ghost.
Состояния: normal, hover, pressed, disabled.
Опционально с иконкой.
"""

from __future__ import annotations

from typing import Literal

from textual.message import Message
from textual.widgets import Button, Static

# Типы вариантов кнопки
ButtonVariant = Literal["primary", "secondary", "danger", "ghost"]


class ActionButton(Button):
    """Стилизованная кнопка действия.
    
    Расширяет стандартную Button с дополнительной стилизацией
    и поддержкой иконок.
    
    Варианты оформления:
        - primary: основное действие (акцентный цвет)
        - secondary: второстепенное действие (приглушённый)
        - danger: опасное действие (красный)
        - ghost: минималистичный (без фона)
    
    Пример использования:
        >>> button = ActionButton("Save", variant="primary", icon="💾")
        >>> button = ActionButton("Delete", variant="danger", icon="🗑️")
    """

    # CSS классы для разных вариантов
    DEFAULT_CSS = """
    ActionButton {
        min-width: 8;
        height: 3;
        padding: 0 1;
    }
    
    ActionButton.primary {
        background: $primary;
        color: $text;
        border: tall $primary-lighten-2;
    }
    
    ActionButton.primary:hover {
        background: $primary-lighten-1;
    }
    
    ActionButton.primary:focus {
        background: $primary-darken-1;
    }
    
    ActionButton.secondary {
        background: $surface;
        color: $text;
        border: tall $surface-lighten-2;
    }
    
    ActionButton.secondary:hover {
        background: $surface-lighten-1;
    }
    
    ActionButton.danger {
        background: $error;
        color: $text;
        border: tall $error-lighten-2;
    }
    
    ActionButton.danger:hover {
        background: $error-lighten-1;
    }
    
    ActionButton.ghost {
        background: transparent;
        color: $text-muted;
        border: none;
    }
    
    ActionButton.ghost:hover {
        background: $surface;
        color: $text;
    }
    
    ActionButton.-disabled {
        opacity: 0.5;
    }
    """

    def __init__(
        self,
        label: str = "",
        *,
        variant: ButtonVariant = "secondary",
        icon: str | None = None,
        disabled: bool = False,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Создаёт кнопку действия.
        
        Args:
            label: Текст кнопки
            variant: Вариант оформления (primary, secondary, danger, ghost)
            icon: Иконка (emoji/символ) перед текстом
            disabled: Отключена ли кнопка
            name: Имя виджета для идентификации
            id: ID виджета для CSS селекторов
            classes: Дополнительные CSS классы
        """
        # Формируем label с иконкой
        display_label = f"{icon} {label}" if icon else label
        
        # Добавляем класс варианта
        css_classes = variant
        if classes:
            css_classes = f"{variant} {classes}"
        
        super().__init__(
            display_label,
            disabled=disabled,
            name=name,
            id=id,
            classes=css_classes,
        )
        
        # Инициализируем приватные поля ПОСЛЕ вызова super().__init__()
        # _button_variant для нашего стиля (отличается от родительского variant)
        self._button_variant = variant
        self._icon = icon
        self._label = label
    
    @property
    def button_variant(self) -> ButtonVariant:
        """Текущий вариант оформления кнопки (наш стиль)."""
        return self._button_variant
    
    @button_variant.setter
    def button_variant(self, value: ButtonVariant) -> None:
        """Изменить вариант оформления кнопки.
        
        Args:
            value: Новый вариант (primary, secondary, danger, ghost)
        """
        # Удаляем старый класс варианта
        self.remove_class(self._button_variant)
        # Устанавливаем новый
        self._button_variant = value
        self.add_class(value)
    
    @property
    def icon(self) -> str | None:
        """Иконка кнопки."""
        return self._icon
    
    @icon.setter
    def icon(self, value: str | None) -> None:
        """Изменить иконку кнопки.
        
        Args:
            value: Новая иконка (emoji/символ) или None для удаления
        """
        self._icon = value
        # Обновляем отображаемый label
        display_label = f"{value} {self._label}" if value else self._label
        self.label = display_label


class IconButton(Static):
    """Кнопка-иконка без текста.
    
    Компактная кнопка только с иконкой для тулбаров и панелей.
    
    Пример использования:
        >>> button = IconButton("❌", variant="ghost", tooltip="Закрыть")
    """

    # Сообщение о нажатии кнопки
    class Pressed(Message):
        """Событие нажатия на иконку."""
        
        def __init__(self, button: IconButton) -> None:
            """Создать событие нажатия.
            
            Args:
                button: Кнопка, на которую нажали
            """
            self.button = button
            super().__init__()

    DEFAULT_CSS = """
    IconButton {
        width: 3;
        height: 1;
        content-align: center middle;
        text-style: bold;
    }
    
    IconButton:hover {
        background: $surface-lighten-1;
    }
    
    IconButton.primary {
        color: $primary;
    }
    
    IconButton.danger {
        color: $error;
    }
    
    IconButton.success {
        color: $success;
    }
    
    IconButton.-disabled {
        opacity: 0.3;
    }
    """

    def __init__(
        self,
        icon: str,
        *,
        variant: ButtonVariant = "secondary",
        tooltip: str | None = None,
        disabled: bool = False,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Создаёт кнопку-иконку.
        
        Args:
            icon: Иконка (emoji/символ)
            variant: Вариант оформления для цвета
            tooltip: Текст подсказки при наведении
            disabled: Отключена ли кнопка
            name: Имя виджета
            id: ID виджета
            classes: Дополнительные CSS классы
        """
        css_classes = variant
        if classes:
            css_classes = f"{variant} {classes}"
        if disabled:
            css_classes = f"{css_classes} -disabled"
        
        super().__init__(icon, name=name, id=id, classes=css_classes)
        
        self._icon = icon
        self._variant = variant
        self._tooltip = tooltip
        self._disabled = disabled
    
    @property
    def disabled(self) -> bool:
        """Отключена ли кнопка."""
        return self._disabled
    
    @disabled.setter
    def disabled(self, value: bool) -> None:
        """Установить состояние disabled.
        
        Args:
            value: True для отключения кнопки
        """
        self._disabled = value
        if value:
            self.add_class("-disabled")
        else:
            self.remove_class("-disabled")
    
    def on_click(self) -> None:
        """Обработчик клика - отправляет событие Pressed."""
        if not self._disabled:
            self.post_message(self.Pressed(self))

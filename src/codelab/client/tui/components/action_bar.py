"""Горизонтальная панель с кнопками действий.

Используется в ToolCallCard, PermissionRequest и других компонентах
для группировки связанных действий.
"""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widgets import Static

from .action_button import ActionButton, ButtonVariant


class ActionBar(Horizontal):
    """Горизонтальная панель с кнопками действий.
    
    Контейнер для группировки ActionButton компонентов.
    Поддерживает выравнивание и разделители между кнопками.
    
    Пример использования:
        >>> bar = ActionBar()
        >>> bar.add_action("Save", variant="primary", action_id="save")
        >>> bar.add_action("Cancel", variant="ghost", action_id="cancel")
    """

    DEFAULT_CSS = """
    ActionBar {
        width: 100%;
        height: auto;
        layout: horizontal;
        align: center middle;
        padding: 0;
    }
    
    ActionBar.left {
        align: left middle;
    }
    
    ActionBar.right {
        align: right middle;
    }
    
    ActionBar.spread {
        width: 100%;
    }
    
    ActionBar.spread > ActionButton {
        width: 1fr;
    }
    
    ActionBar > ActionButton {
        margin: 0 1;
    }
    
    ActionBar > .separator {
        width: 1;
        height: 100%;
        background: $surface-lighten-2;
        margin: 0 1;
    }
    """

    def __init__(
        self,
        *,
        align: str = "center",
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Создаёт панель действий.
        
        Args:
            align: Выравнивание кнопок (left, center, right, spread)
            name: Имя виджета
            id: ID виджета
            classes: Дополнительные CSS классы
        """
        css_classes = align
        if classes:
            css_classes = f"{align} {classes}"
        
        super().__init__(name=name, id=id, classes=css_classes)
        self._buttons: dict[str, ActionButton] = {}
    
    def add_action(
        self,
        label: str,
        *,
        variant: ButtonVariant = "secondary",
        icon: str | None = None,
        action_id: str | None = None,
        disabled: bool = False,
    ) -> ActionButton:
        """Добавить кнопку действия в панель.
        
        Args:
            label: Текст кнопки
            variant: Вариант оформления
            icon: Иконка перед текстом
            action_id: Уникальный ID для идентификации действия
            disabled: Отключена ли кнопка
            
        Returns:
            Созданная кнопка ActionButton
        """
        button_id = action_id or f"action-{len(self._buttons)}"
        
        button = ActionButton(
            label,
            variant=variant,
            icon=icon,
            disabled=disabled,
            id=button_id,
        )
        
        self._buttons[button_id] = button
        self.mount(button)
        
        return button
    
    def add_separator(self) -> None:
        """Добавить вертикальный разделитель между кнопками."""
        separator = Static("", classes="separator")
        self.mount(separator)
    
    def get_action(self, action_id: str) -> ActionButton | None:
        """Получить кнопку по ID.
        
        Args:
            action_id: ID кнопки
            
        Returns:
            ActionButton или None если не найдена
        """
        return self._buttons.get(action_id)
    
    def set_action_disabled(self, action_id: str, disabled: bool) -> None:
        """Установить состояние disabled для кнопки.
        
        Args:
            action_id: ID кнопки
            disabled: Новое состояние
        """
        button = self._buttons.get(action_id)
        if button:
            button.disabled = disabled
    
    def remove_action(self, action_id: str) -> None:
        """Удалить кнопку из панели.
        
        Args:
            action_id: ID кнопки для удаления
        """
        button = self._buttons.pop(action_id, None)
        if button:
            button.remove()
    
    def clear_actions(self) -> None:
        """Удалить все кнопки из панели."""
        for button in self._buttons.values():
            button.remove()
        self._buttons.clear()

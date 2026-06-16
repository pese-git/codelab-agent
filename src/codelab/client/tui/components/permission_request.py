"""Виджет запроса разрешения.

Референс OpenCode: packages/web/src/ui/session/permission.tsx

Отображает:
- Что запрашивается (тип разрешения)
- Путь/команда
- Кнопки: Allow, Deny, Allow Always
- Опциональный таймер автоотклонения
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Static

from codelab.client.messages import PermissionOption

from .action_bar import ActionBar
from .action_button import ActionButton
from .permission_badge import PermissionBadge

if TYPE_CHECKING:
    from codelab.client.presentation.permission_view_model import PermissionViewModel


# Типы разрешений
PermissionType = Literal[
    "file_read",
    "file_write",
    "file_delete",
    "execute_command",
    "mcp_access",
    "unknown",
]


# Иконки для типов разрешений
PERMISSION_ICONS: dict[PermissionType, str] = {
    "file_read": "📄",
    "file_write": "✏️",
    "file_delete": "🗑️",
    "execute_command": "⚡",
    "mcp_access": "🔌",
    "unknown": "❓",
}

# Описания типов разрешений
PERMISSION_DESCRIPTIONS: dict[PermissionType, str] = {
    "file_read": "Чтение файла",
    "file_write": "Запись в файл",
    "file_delete": "Удаление файла",
    "execute_command": "Выполнение команды",
    "mcp_access": "Доступ к MCP серверу",
    "unknown": "Неизвестное действие",
}


class PermissionRequest(Static):
    """Виджет запроса разрешения с кнопками действий.
    
    Отображает информацию о запрашиваемом разрешении и предоставляет
    кнопки для принятия решения.
    
    Интегрируется с PermissionViewModel для управления состоянием.
    
    Пример использования:
        >>> request = PermissionRequest(
        ...     permission_vm=vm,
        ...     request_id="req_123",
        ...     permission_type="file_write",
        ...     resource="/home/user/file.txt",
        ...     options=options,
        ...     on_choice=handle_choice,
        ... )
    """

    # Сообщение о выборе пользователя
    class Choice(Message):
        """Событие выбора разрешения."""
        
        def __init__(
            self,
            request_id: str | int,
            option_id: str,
            widget: PermissionRequest,
        ) -> None:
            """Создать событие выбора.
            
            Args:
                request_id: ID запроса
                option_id: ID выбранной опции
                widget: Виджет, в котором сделан выбор
            """
            self.request_id = request_id
            self.option_id = option_id
            self.widget = widget
            super().__init__()

    DEFAULT_CSS = """
    PermissionRequest {
        width: 100%;
        height: auto;
        background: $warning 10%;
        border: thick $warning;
        padding: 1;
        margin: 1 0;
    }
    
    PermissionRequest.granted {
        background: $success 10%;
        border: thick $success;
    }
    
    PermissionRequest.denied {
        background: $error 10%;
        border: thick $error;
    }
    
    #permission-req-header {
        width: 100%;
        height: auto;
        layout: horizontal;
    }
    
    #permission-req-icon {
        width: 3;
        text-style: bold;
    }
    
    #permission-req-title {
        width: 1fr;
        text-style: bold;
        color: $text;
    }
    
    #permission-req-badge {
        width: auto;
    }
    
    #permission-req-resource {
        width: 100%;
        margin-top: 1;
        padding: 0 1;
        color: $text-muted;
    }
    
    #permission-req-message {
        width: 100%;
        margin-top: 1;
        color: $text 80%;
    }
    
    #permission-req-timer {
        width: 100%;
        margin-top: 1;
        color: $warning;
        text-style: italic;
    }
    
    #permission-req-actions {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        *,
        permission_vm: PermissionViewModel,
        request_id: str | int,
        permission_type: PermissionType = "unknown",
        resource: str = "",
        message: str = "",
        options: list[PermissionOption] | None = None,
        on_choice: Callable[[str | int, str], None] | None = None,
        auto_deny_seconds: int | None = None,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Создаёт виджет запроса разрешения.
        
        Args:
            permission_vm: PermissionViewModel для управления состоянием
            request_id: ID запроса разрешения
            permission_type: Тип запрашиваемого разрешения
            resource: Путь к файлу, команда или другой ресурс
            message: Дополнительное сообщение
            options: Список доступных опций
            on_choice: Callback при выборе (request_id, option_id)
            auto_deny_seconds: Время до автоматического отклонения (None = отключено)
            name: Имя виджета
            id: ID виджета
            classes: Дополнительные CSS классы
        """
        super().__init__(name=name, id=id or f"perm-req-{request_id}", classes=classes)
        
        self.permission_vm = permission_vm
        self._request_id = request_id
        self._permission_type = permission_type
        self._resource = resource
        self._message = message
        self._options = options or []
        self._on_choice = on_choice
        self._auto_deny_seconds = auto_deny_seconds
        
        # Кэш опций по ID
        self._option_by_id = {opt.optionId: opt for opt in self._options}
        
        # Таймер автоотклонения
        self._auto_deny_timer: Timer | None = None
        self._remaining_seconds = auto_deny_seconds or 0
        
        # Статус решения
        self._resolved = False
        
        # Ссылка на ActionBar (инициализируется в compose)
        self._action_bar: ActionBar | None = None
    
    @property
    def request_id(self) -> str | int:
        """ID запроса."""
        return self._request_id
    
    @property
    def permission_type(self) -> PermissionType:
        """Тип запрашиваемого разрешения."""
        return self._permission_type
    
    @property
    def resource(self) -> str:
        """Запрашиваемый ресурс."""
        return self._resource
    
    @property
    def is_resolved(self) -> bool:
        """Было ли принято решение."""
        return self._resolved
    
    def compose(self) -> ComposeResult:
        """Создаёт структуру виджета."""
        # Иконка типа разрешения
        icon = PERMISSION_ICONS.get(self._permission_type, "❓")
        description = PERMISSION_DESCRIPTIONS.get(self._permission_type, "Действие")
        
        # Заголовок с иконкой и типом
        with Horizontal(id="permission-req-header"):
            yield Static(icon, id="permission-req-icon")
            yield Static(f"Запрос: {description}", id="permission-req-title")
            yield PermissionBadge("pending", id="permission-req-badge")
        
        # Ресурс (путь/команда)
        if self._resource:
            yield Static(f"📍 {self._resource}", id="permission-req-resource")
        
        # Сообщение
        if self._message:
            yield Static(self._message, id="permission-req-message")
        
        # Таймер автоотклонения
        if self._auto_deny_seconds:
            yield Static(
                f"⏱️ Автоотклонение через {self._remaining_seconds}с",
                id="permission-req-timer",
            )
        
        # Кнопки действий через ActionBar
        action_bar = ActionBar(align="left", id="permission-req-actions")
        yield action_bar
        
        # Сохраняем ссылку на ActionBar для добавления кнопок после mount
        self._action_bar = action_bar
    
    def on_mount(self) -> None:
        """Запускает таймер автоотклонения при монтировании и добавляет кнопки в ActionBar."""
        # Добавляем кнопки в ActionBar
        if self._action_bar:
            # Кнопка Allow (primary)
            self._action_bar.add_action(
                "Allow",
                variant="primary",
                icon="✓",
                action_id="perm-allow",
            )
            
            # Кнопка Deny (danger)
            self._action_bar.add_action(
                "Deny",
                variant="danger",
                icon="✗",
                action_id="perm-deny",
            )
            
            # Кнопка Always Allow (если есть такая опция)
            if any(opt.kind == "always" for opt in self._options):
                self._action_bar.add_action(
                    "Always",
                    variant="secondary",
                    icon="∞",
                    action_id="perm-always",
                )
        
        # Запуск таймера автоотклонения
        if self._auto_deny_seconds and self._auto_deny_seconds > 0:
            self._auto_deny_timer = self.set_interval(1.0, self._tick_auto_deny)
    
    def _tick_auto_deny(self) -> None:
        """Обработчик тика таймера автоотклонения."""
        if self._resolved:
            if self._auto_deny_timer:
                self._auto_deny_timer.stop()
            return
        
        self._remaining_seconds -= 1
        
        # Обновляем отображение таймера
        try:
            timer_widget = self.query_one("#permission-req-timer", Static)
            timer_widget.update(f"⏱️ Автоотклонение через {self._remaining_seconds}с")
        except Exception:
            pass
        
        # Если время вышло - автоматически отклоняем
        if self._remaining_seconds <= 0:
            if self._auto_deny_timer:
                self._auto_deny_timer.stop()
            self._select_option("deny")
    
    def on_button_pressed(self, event: ActionButton.Pressed) -> None:
        """Обработчик нажатия кнопки."""
        if self._resolved:
            return
        
        button_id = event.button.id
        
        if button_id == "perm-allow":
            # Ищем опцию "allow_once"
            option_id = self._find_option_id("allow_once")
            self._select_option(option_id or "allow")
        
        elif button_id == "perm-deny":
            # Ищем опцию "reject_once"
            option_id = self._find_option_id("reject_once")
            self._select_option(option_id or "deny")
        
        elif button_id == "perm-always":
            # Ищем опцию "allow_always"
            option_id = self._find_option_id("allow_always")
            self._select_option(option_id or "always")
    
    def _find_option_id(self, kind: str) -> str | None:
        """Найти ID опции по типу (kind).
        
        Args:
            kind: Тип опции (allow_once, reject_once, allow_always, reject_always)
            
        Returns:
            ID опции или None
        """
        for opt in self._options:
            if opt.kind == kind:
                return opt.optionId
        return None
    
    def _select_option(self, option_id: str) -> None:
        """Выбрать опцию и уведомить.
        
        Args:
            option_id: ID выбранной опции
        """
        if self._resolved:
            return
        
        self._resolved = True
        
        # Останавливаем таймер
        if self._auto_deny_timer:
            self._auto_deny_timer.stop()
        
        # Обновляем визуал
        is_granted = "allow" in option_id.lower() or option_id == "always"
        badge_status = "granted" if is_granted else "denied"
        
        try:
            badge = self.query_one("#permission-req-badge", PermissionBadge)
            badge.status = badge_status
        except Exception:
            pass
        
        # Добавляем класс статуса
        self.add_class(badge_status)
        
        # Отключаем кнопки
        try:
            for button in self.query(ActionButton):
                button.disabled = True
        except Exception:
            pass
        
        # Вызываем callback
        if self._on_choice:
            self._on_choice(self._request_id, option_id)
        
        # Отправляем сообщение
        self.post_message(self.Choice(self._request_id, option_id, self))
        
        # Скрываем через ViewModel
        self.permission_vm.hide()
    
    def allow(self) -> None:
        """Программно выбрать Allow."""
        option_id = self._find_option_id("allow_once")
        self._select_option(option_id or "allow")
    
    def deny(self) -> None:
        """Программно выбрать Deny."""
        option_id = self._find_option_id("reject_once")
        self._select_option(option_id or "deny")
    
    def always_allow(self) -> None:
        """Программно выбрать Always Allow."""
        option_id = self._find_option_id("allow_always")
        self._select_option(option_id or "always")

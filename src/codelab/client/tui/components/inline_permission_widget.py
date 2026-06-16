"""Встроенный виджет подтверждения разрешения в ChatView.

Заменяет ModalScreen на встроенный Static компонент для лучшей видимости.
Отображается как часть чата, всегда виден пользователю.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from codelab.client.messages import PermissionOption, PermissionToolCall

if TYPE_CHECKING:
    from codelab.client.presentation.permission_view_model import PermissionViewModel


class InlinePermissionWidget(Static):
    """Встроенный виджет выбора решения для session/request_permission.

    Интегрирован в ChatView как часть истории сообщений.
    Отображает опции разрешения и обрабатывает клики пользователя.
    """

    DEFAULT_CSS = """
    InlinePermissionWidget {
        width: 100%;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 1;
        margin: 1 0;
    }

    #permission-header {
        width: 100%;
        content-align: left top;
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    #permission-description {
        width: 100%;
        content-align: left top;
        color: $text 80%;
        margin-bottom: 1;
    }

    #permission-buttons {
        width: 100%;
        height: auto;
        layout: horizontal;
    }

    #permission-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        *,
        permission_vm: PermissionViewModel,
        request_id: str | int,
        tool_call: PermissionToolCall,
        options: list[PermissionOption],
        on_choice: Callable[[str | int, str], None],
    ) -> None:
        """Инициализирует встроенный виджет разрешения.

        Args:
            permission_vm: PermissionViewModel для управления состоянием
            request_id: ID permission request для callback
            tool_call: Информация о tool call (kind, title)
            options: Доступные опции для выбора
            on_choice: Callback при выборе (request_id, option_id)
        """
        super().__init__(id=f"permission_widget_{request_id}")
        self.permission_vm = permission_vm
        self._request_id = request_id
        self._tool_call = tool_call
        self._options = options
        self._on_choice = on_choice
        # Кэш для быстрого поиска опции по ID
        self._option_by_id = {opt.optionId: opt for opt in options}
        self._logger = structlog.get_logger("inline_permission_widget")

    def compose(self) -> ComposeResult:
        """Рендерит виджет разрешения."""
        # Заголовок с типом разрешения
        header = f"{self._tool_call.kind}: {self._tool_call.title}"
        yield Static(header, id="permission-header")

        # Опциональное описание/сообщение
        description = self.permission_vm.message.value
        if description:
            yield Static(description, id="permission-description")

        # Кнопки опций в горизонтальном контейнере
        with Horizontal(id="permission-buttons"):
            # Рендерим все доступные опции
            for option in self._options:
                label = f"{option.name} ({option.kind})"
                yield Button(label, id=f"permission-{option.optionId}")

            # Кнопка отмены
            yield Button("Cancel", id="permission-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обработчик нажатия кнопки выбора разрешения.

        Args:
            event: Event от нажатия кнопки
        """
        pressed_id = event.button.id

        if pressed_id == "permission-cancel":
            # Пользователь отменил запрос
            self._logger.info(
                "permission_cancelled",
                request_id=self._request_id,
            )
            self._on_choice(self._request_id, "cancelled")
            self.permission_vm.hide()
            # Удалить виджет из DOM
            self.remove()
            return

        if isinstance(pressed_id, str) and pressed_id.startswith("permission-"):
            # Извлечь optionId из ID кнопки
            option_id = pressed_id.removeprefix("permission-")
            if option_id in self._option_by_id:
                # Пользователь выбрал опцию
                self._logger.info(
                    "permission_selected",
                    request_id=self._request_id,
                    option_id=option_id,
                )
                self._on_choice(self._request_id, option_id)
                self.permission_vm.hide()
                # Удалить виджет из DOM
                self.remove()

"""Менеджер встроенного виджета разрешения в ChatView.

Управляет жизненным циклом виджетов разрешения:
- InlinePermissionWidget: базовый виджет с кнопками
- PermissionRequest: расширенный виджет с иконками, типами и автоотклонением

Поддерживает:
- Создание и монтирование в ChatView
- Скрытие и удаление
- Синхронизация с PermissionViewModel
- Выбор типа виджета (inline/request)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import structlog

from codelab.client.messages import PermissionOption, PermissionToolCall
from codelab.client.tui.components.inline_permission_widget import InlinePermissionWidget
from codelab.client.tui.components.permission_request import (
    PermissionRequest,
    PermissionType,
)

if TYPE_CHECKING:
    from codelab.client.presentation.permission_view_model import PermissionViewModel
    from codelab.client.tui.components.chat_view import ChatView


@dataclass
class PermissionWidgetInfo:
    """Информация о текущем виджете разрешения для пересоздания."""

    request_id: str | int
    tool_call: PermissionToolCall
    options: list[PermissionOption]
    on_choice: Callable[[str | int, str], None]
    auto_deny_seconds: int | None = None
    message: str = ""


class PermissionWidgetType(Enum):
    """Тип виджета разрешения.

    - INLINE: базовый виджет с кнопками (InlinePermissionWidget)
    - REQUEST: расширенный виджет с иконками и автоотклонением (PermissionRequest)
    """

    INLINE = "inline"
    REQUEST = "request"


# Маппинг tool_call.kind -> PermissionType
# MCP инструменты теперь имеют inferred kind (read, edit, execute и т.д.)
# и маппятся на соответствующие permission-типы вместе с нативными инструментами.
_TOOL_KIND_TO_PERMISSION_TYPE: dict[str, PermissionType] = {
    "read_file": "file_read",
    "file_read": "file_read",
    "read": "file_read",
    "write_file": "file_write",
    "file_write": "file_write",
    "edit": "file_write",
    "delete_file": "file_delete",
    "file_delete": "file_delete",
    "delete": "file_delete",
    "execute": "execute_command",
    "execute_command": "execute_command",
    "terminal": "execute_command",
    "search": "file_read",
    "fetch": "execute_command",
    "move": "file_write",
    "think": "unknown",
    "switch_mode": "unknown",
    "other": "unknown",
}


class ChatViewPermissionManager:
    """Менеджер встроенного виджета разрешения в ChatView.

    Ответственность:
    - Управление жизненным циклом виджетов разрешения
    - Поддержка InlinePermissionWidget и PermissionRequest
    - Интеграция с ChatView._content_container
    - Синхронизация с PermissionViewModel через Observable паттерн
    - Показ/скрытие виджета разрешения
    """

    def __init__(
        self,
        chat_view: ChatView,
        permission_vm: PermissionViewModel,
        widget_type: PermissionWidgetType = PermissionWidgetType.REQUEST,
    ) -> None:
        """Инициализирует менеджер разрешений.

        Args:
            chat_view: ChatView компонент для монтирования виджета
            permission_vm: PermissionViewModel для управления состоянием
            widget_type: Тип виджета разрешения (по умолчанию REQUEST)
        """
        self.chat_view = chat_view
        self.permission_vm = permission_vm
        self.widget_type = widget_type
        self._current_widget: InlinePermissionWidget | PermissionRequest | None = None
        self._current_widget_info: PermissionWidgetInfo | None = None
        # Очередь ещё не показанных запросов: второй запрос не вытесняет
        # неотвеченный первый (иначе первый оставался без ответа на сервере),
        # а ждёт его разрешения (tech-debt #19).
        self._queue: list[PermissionWidgetInfo] = []
        self._logger = structlog.get_logger("chat_view_permission_manager")

        # Подписаться на изменения видимости в ViewModel
        permission_vm.is_visible.subscribe(self._on_visibility_changed)

    def show_permission_request(
        self,
        request_id: str | int,
        tool_call: PermissionToolCall,
        options: list[PermissionOption],
        on_choice: Callable[[str | int, str], None],
        *,
        auto_deny_seconds: int | None = None,
    ) -> None:
        """Показать виджет разрешения в ChatView.

        В зависимости от widget_type создаёт:
        - INLINE: InlinePermissionWidget (базовый)
        - REQUEST: PermissionRequest (расширенный с иконками и автоотклонением)

        Args:
            request_id: ID permission request
            tool_call: Информация о tool call
            options: Доступные опции для выбора
            on_choice: Callback при выборе (request_id, option_id)
            auto_deny_seconds: Время до автоотклонения (только для REQUEST)
        """
        self._logger.info(
            "show_permission_request_start",
            request_id=request_id,
            tool_call_kind=tool_call.kind,
            tool_call_title=tool_call.title,
            options_count=len(options),
            widget_type=self.widget_type.value,
            has_existing_widget=self._current_widget is not None,
        )

        info = PermissionWidgetInfo(
            request_id=request_id,
            tool_call=tool_call,
            options=options,
            on_choice=on_choice,
            auto_deny_seconds=auto_deny_seconds,
            message=self.permission_vm.message.value,
        )

        # Не вытесняем неотвеченный запрос: ставим новый в очередь и покажем,
        # когда текущий будет разрешён (tech-debt #19).
        if self._current_widget is not None:
            self._queue.append(info)
            self._logger.info(
                "permission_request_queued",
                request_id=request_id,
                queue_len=len(self._queue),
            )
            return

        self._show_widget(info)

    def _show_widget(self, info: PermissionWidgetInfo) -> None:
        """Создать и смонтировать виджет разрешения из сохранённой информации."""
        self._current_widget_info = info

        # Установить is_visible = True, чтобы hide() мог уведомить подписчиков
        self.permission_vm.is_visible.value = True

        # Создать виджет в зависимости от типа
        if self.widget_type == PermissionWidgetType.REQUEST:
            # Определяем тип разрешения из tool_call.kind
            kind = info.tool_call.kind or "unknown"
            permission_type = self._get_permission_type(kind)

            self._logger.info(
                "creating_permission_request_widget",
                permission_type=permission_type,
                resource=info.tool_call.title or "",
            )

            self._current_widget = PermissionRequest(
                permission_vm=self.permission_vm,
                request_id=info.request_id,
                permission_type=permission_type,
                resource=info.tool_call.title or "",
                message=info.message,
                options=info.options,
                on_choice=info.on_choice,
                auto_deny_seconds=info.auto_deny_seconds,
            )
        else:
            # Создать InlinePermissionWidget (INLINE по умолчанию для обратной совместимости)
            self._logger.info("creating_inline_permission_widget")
            self._current_widget = InlinePermissionWidget(
                permission_vm=self.permission_vm,
                request_id=info.request_id,
                tool_call=info.tool_call,
                options=info.options,
                on_choice=info.on_choice,
            )

        # Монтировать в permission_container если он доступен
        if self.chat_view._permission_container is not None:
            self._logger.info(
                "mounting_permission_widget_to_container",
                container_id=self.chat_view._permission_container.id,
                widget_type=type(self._current_widget).__name__,
            )
            self.chat_view._permission_container.mount(self._current_widget)

            self._logger.info(
                "permission_widget_mounted",
                request_id=info.request_id,
                tool_call_kind=info.tool_call.kind,
                widget_type=self.widget_type.value,
            )
        else:
            self._logger.error(
                "chat_view_permission_container_not_available",
                request_id=info.request_id,
                chat_view_id=self.chat_view.id,
            )

    def _get_permission_type(self, kind: str) -> PermissionType:
        """Преобразовать tool_call.kind в PermissionType.

        Args:
            kind: Тип tool call

        Returns:
            Соответствующий PermissionType
        """
        return _TOOL_KIND_TO_PERMISSION_TYPE.get(kind, "unknown")

    def hide_permission_request(self) -> None:
        """Скрыть и удалить встроенный виджет разрешения.

        Удаляет текущий виджет из DOM и очищает ссылку.
        """
        self._logger.info(
            "hide_permission_request_called",
            has_widget=self._current_widget is not None,
            widget_type=type(self._current_widget).__name__ if self._current_widget else None,
            widget_id=self._current_widget.id if self._current_widget else None,
        )
        if self._current_widget is not None:
            widget = self._current_widget
            try:
                # Проверяем, что виджет всё ещё в DOM
                widget_parent = widget.parent
                self._logger.info(
                    "permission_widget_removal_attempt",
                    widget_id=widget.id,
                    has_parent=widget_parent is not None,
                    parent_type=type(widget_parent).__name__ if widget_parent else None,
                )

                if widget_parent is not None:
                    # Удаляем виджет напрямую
                    widget.remove()
                    self._logger.info(
                        "permission_widget_removed_from_dom",
                        widget_type=type(widget).__name__,
                        widget_id=widget.id,
                    )
                else:
                    self._logger.info(
                        "permission_widget_already_removed",
                        widget_type=type(widget).__name__,
                        widget_id=widget.id,
                    )
            except Exception as e:
                # Виджет уже удален или произошла ошибка
                self._logger.warning(
                    "failed_to_remove_permission_widget",
                    error=str(e),
                    error_type=type(e).__name__,
                    widget_id=widget.id,
                )
            finally:
                self._current_widget = None
                self._current_widget_info = None
            self._logger.info("permission_widget_hidden")
        else:
            self._logger.debug("hide_permission_request_no_widget_to_hide")

    def is_widget_visible(self) -> bool:
        """Проверить видимость встроенного виджета.

        Returns:
            True если виджет смонтирован, False иначе
        """
        return self._current_widget is not None

    def _on_visibility_changed(self, is_visible: bool) -> None:
        """Обработчик изменения видимости в PermissionViewModel.

        Скрывает виджет когда ViewModel.is_visible становится False.

        Args:
            is_visible: Новое значение видимости
        """
        self._logger.info(
            "on_visibility_changed",
            is_visible=is_visible,
            has_widget=self._current_widget is not None,
            widget_id=self._current_widget.id if self._current_widget else None,
        )
        if not is_visible:
            self._logger.info("visibility_became_false_calling_hide")
            self.hide_permission_request()
            # Текущий запрос разрешён — показать следующий из очереди (#19).
            # Отложенно: чтобы remove() старого виджета завершился до монтирования
            # нового (нет оверлея) и без вложенной нотификации is_visible.
            if self._queue:
                self.chat_view.call_after_refresh(self._show_next_queued)

    def _show_next_queued(self) -> None:
        """Показать следующий запрос из очереди, если он есть (fix #19)."""
        if self._current_widget is not None or not self._queue:
            return
        next_info = self._queue.pop(0)
        self._logger.info(
            "showing_next_queued_permission_request",
            request_id=next_info.request_id,
            queue_len=len(self._queue),
        )
        self._show_widget(next_info)

    def get_widget_info(self) -> PermissionWidgetInfo | None:
        """Получить информацию о текущем виджете для пересоздания.

        Returns:
            PermissionWidgetInfo если виджет существует, None иначе
        """
        return self._current_widget_info

    def recreate_widget(self, info: PermissionWidgetInfo) -> None:
        """Пересоздать виджет разрешения с сохранённой информацией.

        Используется при _update_display() для перемещения виджета в конец.

        Args:
            info: Информация о виджете для пересоздания
        """
        self._logger.info(
            "recreate_permission_widget",
            request_id=info.request_id,
            widget_type=self.widget_type.value,
        )

        # Скрыть текущий виджет если есть
        if self._current_widget is not None:
            self.hide_permission_request()

        # Создать новый виджет с уникальным ID
        unique_id = f"perm-req-{info.request_id}-{int(time.time() * 1000000)}"

        if self.widget_type == PermissionWidgetType.REQUEST:
            kind = info.tool_call.kind or "unknown"
            permission_type = self._get_permission_type(kind)

            self._current_widget = PermissionRequest(
                permission_vm=self.permission_vm,
                request_id=info.request_id,
                permission_type=permission_type,
                resource=info.tool_call.title or "",
                message=info.message,
                options=info.options,
                on_choice=info.on_choice,
                auto_deny_seconds=info.auto_deny_seconds,
                id=unique_id,
            )
        else:
            self._current_widget = InlinePermissionWidget(
                permission_vm=self.permission_vm,
                request_id=info.request_id,
                tool_call=info.tool_call,
                options=info.options,
                on_choice=info.on_choice,
                id=unique_id,
            )

        # Монтировать в контейнер ChatView
        if self.chat_view._content_container is not None:
            self.chat_view._content_container.mount(self._current_widget)
            self._logger.info(
                "permission_widget_recreated",
                request_id=info.request_id,
                widget_id=unique_id,
            )

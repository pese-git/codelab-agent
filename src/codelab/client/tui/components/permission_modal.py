"""Модальное окно выбора решения для session/request_permission."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from codelab.client.messages import PermissionOption

if TYPE_CHECKING:
    from codelab.client.presentation.permission_view_model import PermissionViewModel


class PermissionModal(ModalScreen[str | None]):
    """Показывает список permission-опций и возвращает выбранный optionId.

    Интегрирован с PermissionViewModel для управления состоянием:
    - permission_type: тип запрашиваемого разрешения из ViewModel
    - resource: ресурс для которого запрашивается разрешение из ViewModel
    - message: сообщение с описанием запроса из ViewModel
    - is_visible: видимость модального окна из ViewModel

    Все изменения UI синхронизируются с ViewModel через Observable паттерн.
    """

    BINDINGS = [
        ("a", "allow_once", "Allow"),
        ("r", "reject_once", "Reject"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        *,
        permission_vm: PermissionViewModel,
        request_id: str | int | None = None,
        title: str = "",
        options: list[PermissionOption] | None = None,
        on_choice: Callable[[str | int, str], None] | None = None,
    ) -> None:
        """Создает модальное окно запроса разрешения.

        Args:
            permission_vm: PermissionViewModel для управления состоянием.
                Обязательный параметр для MVVM интеграции.
            request_id: ID permission request для callback (опционально).
                Передается в on_choice callback при выборе.
            title: Заголовок запроса разрешения (опционально).
                Если указан, используется вместо значения из ViewModel.
            options: Список вариантов разрешения (опционально).
                Если указан, используется для инициализации.
            on_choice: Callback вызываемый при выборе (request_id, option_id).
                Сигнатура: Callable[[str | int, str], None]
                Опционально для backward compatibility и тестирования.
        """

        super().__init__()
        self.permission_vm = permission_vm
        self._request_id = request_id
        self._title = title
        self._options = options or []
        self._option_by_id: dict[str, PermissionOption] = {
            option.optionId: option for option in self._options
        }
        self._on_choice = on_choice

        # Сохраняем unsubscribe функции для очистки при уничтожении
        self._unsubscribers: list[Callable[[], None]] = []

        # Подписываемся на изменения ViewModel сразу (не только при on_mount)
        self._subscribe_to_view_model()

    def compose(self) -> ComposeResult:
        """Рендерит заголовок и кнопки выбора разрешения."""

        with Vertical(id="permission-modal"):
            yield Static(self._title, id="permission-title")
            for option in self._options:
                label = f"{option.name} ({option.kind})"
                yield Button(label, id=f"permission-{option.optionId}")
            yield Button("Cancel", id="permission-cancel")

    def _subscribe_to_view_model(self) -> None:
        """Подписаться на изменения ViewModel.

        Устанавливает observers на все Observable свойства ViewModel
        для синхронизации UI при изменениях состояния.
        """
        # Подписываемся на изменение типа разрешения
        unsub_type = self.permission_vm.permission_type.subscribe(self._on_permission_type_changed)
        self._unsubscribers.append(unsub_type)

        # Подписываемся на изменение ресурса
        unsub_resource = self.permission_vm.resource.subscribe(self._on_resource_changed)
        self._unsubscribers.append(unsub_resource)

        # Подписываемся на изменение сообщения
        unsub_message = self.permission_vm.message.subscribe(self._on_message_changed)
        self._unsubscribers.append(unsub_message)

    def _on_permission_type_changed(self, new_type: str) -> None:
        """Обработчик изменения типа разрешения в ViewModel.

        Args:
            new_type: Новый тип разрешения.
        """
        # Обновляем заголовок если компонент смонтирован
        try:
            title_widget = self.query_one("#permission-title", Static)
            title_text = f"{new_type}: {self.permission_vm.resource.value}"
            if self.permission_vm.message.value:
                title_text += f" - {self.permission_vm.message.value}"
            title_widget.update(title_text)
        except Exception:
            pass  # Компонент еще не смонтирован

    def _on_resource_changed(self, new_resource: str) -> None:
        """Обработчик изменения ресурса в ViewModel.

        Args:
            new_resource: Новый ресурс.
        """
        # Обновляем заголовок если компонент смонтирован
        try:
            title_widget = self.query_one("#permission-title", Static)
            title_text = f"{self.permission_vm.permission_type.value}: {new_resource}"
            if self.permission_vm.message.value:
                title_text += f" - {self.permission_vm.message.value}"
            title_widget.update(title_text)
        except Exception:
            pass  # Компонент еще не смонтирован

    def _on_message_changed(self, new_message: str) -> None:
        """Обработчик изменения сообщения в ViewModel.

        Args:
            new_message: Новое сообщение.
        """
        # Обновляем заголовок если компонент смонтирован
        try:
            title_widget = self.query_one("#permission-title", Static)
            perm_type = self.permission_vm.permission_type.value
            resource = self.permission_vm.resource.value
            title_text = f"{perm_type}: {resource}"
            if new_message:
                title_text += f" - {new_message}"
            title_widget.update(title_text)
        except Exception:
            pass  # Компонент еще не смонтирован

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обрабатывает нажатие кнопки выбора разрешения.
        
        Вызывает on_choice callback если он установлен, затем закрывает модал.
        """

        pressed_id = event.button.id
        if pressed_id == "permission-cancel":
            # Вызвать callback с cancelled если есть
            if self._on_choice and self._request_id is not None:
                self._on_choice(self._request_id, "cancelled")
            self.permission_vm.hide()
            self.dismiss(None)
            return
        if isinstance(pressed_id, str) and pressed_id.startswith("permission-"):
            option_id = pressed_id.removeprefix("permission-")
            if option_id in self._option_by_id:
                # Вызвать callback если есть
                if self._on_choice and self._request_id is not None:
                    self._on_choice(self._request_id, option_id)
                self.permission_vm.hide()
                self.dismiss(option_id)

    def action_cancel(self) -> None:
        """Обрабатывает отмену выбора разрешения клавишей Escape.
        
        Вызывает on_choice callback с "cancelled" если он установлен.
        """

        # Вызвать callback если есть
        if self._on_choice and self._request_id is not None:
            self._on_choice(self._request_id, "cancelled")
        
        self.permission_vm.hide()
        self.dismiss(None)

    def action_allow_once(self) -> None:
        """Выбирает разрешение по горячей клавише A.
        
        Вызывает on_choice callback если установлен.
        """

        option_id = self._resolve_option_id_by_kinds(["allow_once", "allow_always"])
        if option_id and self._on_choice and self._request_id is not None:
            # Вызвать callback если есть
            self._on_choice(self._request_id, option_id)
        self.permission_vm.hide()
        self.dismiss(option_id)

    def action_reject_once(self) -> None:
        """Выбирает отклонение по горячей клавише R.
        
        Вызывает on_choice callback если установлен.
        """

        option_id = self._resolve_option_id_by_kinds(["reject_once", "reject_always"])
        if option_id and self._on_choice and self._request_id is not None:
            # Вызвать callback если есть
            self._on_choice(self._request_id, option_id)
        self.permission_vm.hide()
        self.dismiss(option_id)

    def on_mount(self) -> None:
        """Ставит фокус на безопасный вариант выбора при открытии модала."""

        default_button_id = self._default_focus_button_id()
        if default_button_id is None:
            return
        self.query_one(f"#{default_button_id}", Button).focus()

    def on_unmount(self) -> None:
        """Очищает подписки при уничтожении компонента."""
        # Отписываемся от всех наблюдений
        for unsubscriber in self._unsubscribers:
            unsubscriber()
        self._unsubscribers.clear()

    def on_key(self, event: events.Key) -> None:
        """Оставляет стандартную клавиатурную навигацию между кнопками."""

        if event.key in {"up", "down", "tab", "shift+tab", "enter"}:
            return

    def _dismiss_by_kinds(self, preferred_kinds: list[str]) -> None:
        """Закрывает модал, выбрав первую доступную option по списку kind."""

        self.dismiss(self._resolve_option_id_by_kinds(preferred_kinds))

    def _resolve_option_id_by_kinds(self, preferred_kinds: list[str]) -> str | None:
        """Подбирает optionId по приоритетному списку kind без dismiss."""

        for option in self._options:
            if option.kind in preferred_kinds:
                return option.optionId
        return None

    def _default_focus_button_id(self) -> str | None:
        """Возвращает id кнопки для безопасного дефолтного фокуса."""

        for option in self._options:
            if option.kind == "reject_once":
                return f"permission-{option.optionId}"
        for option in self._options:
            if option.kind == "reject_always":
                return f"permission-{option.optionId}"
        if self._options:
            return f"permission-{self._options[0].optionId}"
        return "permission-cancel"

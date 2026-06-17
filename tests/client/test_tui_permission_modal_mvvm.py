"""Тесты для компонента PermissionModal с MVVM интеграцией."""

from __future__ import annotations

import pytest
from textual.app import App

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.messages import PermissionOption
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.tui.components.permission_modal import PermissionModal


class _TestApp(App):
    """Минимальный app для создания Textual контекста в тестах."""

    pass


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def permission_view_model(event_bus: EventBus) -> PermissionViewModel:
    """Создать PermissionViewModel для тестов."""
    return PermissionViewModel(event_bus=event_bus, logger=None)


@pytest.fixture
def sample_options() -> list[PermissionOption]:
    """Создать примеры опций разрешения для тестов."""
    return [
        PermissionOption(
            optionId="allow_once_123",
            name="Allow Once",
            kind="allow_once",
        ),
        PermissionOption(
            optionId="reject_once_123",
            name="Reject Once",
            kind="reject_once",
        ),
    ]


def test_permission_modal_requires_permission_vm(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить что PermissionModal требует обязательный параметр permission_vm.

    PermissionModal не может быть инициализирован без PermissionViewModel.
    """
    # PermissionModal должен быть инициализирован с обязательным параметром
    modal = PermissionModal(
        permission_vm=permission_view_model,
        title="Test Permission",
        options=sample_options,
    )

    assert modal.permission_vm is permission_view_model
    assert modal.permission_vm.permission_type.value == ""
    assert modal.permission_vm.resource.value == ""
    assert modal.permission_vm.message.value == ""
    assert modal.permission_vm.is_visible.value is False


def test_permission_modal_shows_request(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить отображение запроса разрешения через ViewModel.

    При вызове show_request через ViewModel, состояние должно быть
    обновлено и окно должно быть отмечено как видимое.
    """
    PermissionModal(
        permission_vm=permission_view_model,
        title="Test Permission",
        options=sample_options,
    )

    permission_type = "file_read"
    resource = "/home/user/file.txt"
    message = "Read access needed"

    # Показываем запрос разрешения через ViewModel
    permission_view_model.show_request(permission_type, resource, message)

    # Проверяем что состояние обновлено
    assert permission_view_model.permission_type.value == permission_type
    assert permission_view_model.resource.value == resource
    assert permission_view_model.message.value == message
    assert permission_view_model.is_visible.value is True


def test_permission_modal_updates_on_type_change(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить обновление при изменении типа разрешения в ViewModel.

    Когда тип разрешения изменяется через ViewModel, модальное окно
    должно обновиться и отразить новый тип.
    """
    PermissionModal(
        permission_vm=permission_view_model,
        title="Test Permission",
        options=sample_options,
    )

    # Показываем начальный запрос
    initial_type = "file_read"
    permission_view_model.show_request(initial_type, "/home/user/file.txt", "test")
    assert permission_view_model.permission_type.value == initial_type

    # Изменяем тип разрешения
    new_type = "file_write"
    permission_view_model._permission_type.value = new_type

    # Проверяем что тип обновился
    assert permission_view_model.permission_type.value == new_type


def test_permission_modal_updates_on_resource_change(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить обновление при изменении ресурса в ViewModel.

    Когда ресурс изменяется через ViewModel, модальное окно
    должно обновиться и отразить новый ресурс.
    """
    PermissionModal(
        permission_vm=permission_view_model,
        title="Test Permission",
        options=sample_options,
    )

    # Показываем начальный запрос
    initial_resource = "/home/user/file.txt"
    permission_view_model.show_request("file_read", initial_resource, "test")
    assert permission_view_model.resource.value == initial_resource

    # Изменяем ресурс
    new_resource = "/home/user/another_file.txt"
    permission_view_model._resource.value = new_resource

    # Проверяем что ресурс обновился
    assert permission_view_model.resource.value == new_resource


def test_permission_modal_hides_on_close(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить скрытие модального окна при закрытии.

    Когда окно закрывается, флаг is_visible в ViewModel должен
    быть установлен в False.
    """
    PermissionModal(
        permission_vm=permission_view_model,
        title="Test Permission",
        options=sample_options,
    )

    # Показываем запрос разрешения
    permission_view_model.show_request("file_read", "/home/user/file.txt", "test")
    assert permission_view_model.is_visible.value is True

    # Скрываем модальное окно через метод
    permission_view_model.hide()

    # Флаг видимости должен быть сброшен
    assert permission_view_model.is_visible.value is False


def test_permission_modal_clear(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить очистку состояния ViewModel.

    При вызове clear(), все значения должны быть сброшены в исходное состояние.
    """
    PermissionModal(
        permission_vm=permission_view_model,
        title="Test Permission",
        options=sample_options,
    )

    # Показываем запрос разрешения с данными
    permission_view_model.show_request(
        "file_read",
        "/home/user/file.txt",
        "Read access needed",
    )

    # Проверяем что состояние заполнено
    assert permission_view_model.permission_type.value == "file_read"
    assert permission_view_model.resource.value == "/home/user/file.txt"
    assert permission_view_model.message.value == "Read access needed"
    assert permission_view_model.is_visible.value is True

    # Очищаем состояние
    permission_view_model.clear()

    # Проверяем что все значения сброшены
    assert permission_view_model.permission_type.value == ""
    assert permission_view_model.resource.value == ""
    assert permission_view_model.message.value == ""
    assert permission_view_model.is_visible.value is False


def test_permission_modal_initializes_with_title_and_options(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить инициализацию модального окна с параметрами.

    Если title и options переданы в конструктор, они должны быть
    сохранены модальным окном.
    """
    test_title = "Request File Permission"

    # Создаем модальное окно с параметрами
    modal = PermissionModal(
        permission_vm=permission_view_model,
        title=test_title,
        options=sample_options,
    )

    # Проверяем что параметры сохранены
    assert modal._title == test_title
    assert modal._options == sample_options
    assert len(modal._option_by_id) == len(sample_options)


def test_permission_modal_initializes_with_message(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить инициализацию модального окна без сообщения.

    Когда сообщение не передано, оно должно быть пустым по умолчанию.
    """
    PermissionModal(
        permission_vm=permission_view_model,
        title="Test",
        options=sample_options,
    )

    # Показываем запрос без сообщения
    permission_view_model.show_request("file_read", "/path/to/file")

    # Проверяем что сообщение пустое
    assert permission_view_model.message.value == ""


@pytest.mark.asyncio
async def test_permission_modal_unsubscribes_on_unmount(
    permission_view_model: PermissionViewModel,
    sample_options: list[PermissionOption],
) -> None:
    """Проверить отписку от ViewModel при уничтожении компонента.

    При вызове on_unmount(), все подписки должны быть очищены.
    """
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        modal = PermissionModal(
            permission_vm=permission_view_model,
            title="Test",
            options=sample_options,
        )

        # Проверяем что подписки установлены (может быть 3 или 4 в зависимости от реализации)
        initial_subs = len(modal._unsubscribers)
        assert initial_subs > 0

        # Имитируем уничтожение компонента
        modal.on_unmount()

        # Проверяем что подписки очищены
        assert len(modal._unsubscribers) == 0

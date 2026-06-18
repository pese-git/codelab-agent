"""Тесты для компонента FileViewerModal с MVVM интеграцией."""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.file_viewer_view_model import FileViewerViewModel
from codelab.client.tui.components.file_viewer import FileViewerModal


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def file_viewer_view_model(event_bus: EventBus) -> FileViewerViewModel:
    """Создать FileViewerViewModel для тестов."""
    return FileViewerViewModel(event_bus=event_bus, logger=None)


def test_file_viewer_requires_file_viewer_vm(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить что FileViewerModal требует обязательный параметр file_viewer_vm.

    FileViewerModal не может быть инициализирован без FileViewerViewModel.
    """
    # FileViewerModal должен быть инициализирован с обязательным параметром
    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    assert modal.file_viewer_vm is file_viewer_view_model
    assert modal.file_viewer_vm.file_path.value is None
    assert modal.file_viewer_vm.content.value == ""
    assert modal.file_viewer_vm.is_visible.value is False


def test_file_viewer_shows_file(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить отображение файла через ViewModel.

    При вызове show_file через ViewModel, содержимое должно быть
    обновлено и файл должен быть отмечен как видимый.
    """
    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    test_path = Path("/home/user/test.py")
    test_content = "print('Hello, World!')"

    # Показываем файл через ViewModel
    file_viewer_view_model.show_file(test_path, test_content)

    # Проверяем что состояние обновлено
    assert file_viewer_view_model.file_path.value == test_path
    assert file_viewer_view_model.content.value == test_content
    assert file_viewer_view_model.is_visible.value is True
    assert file_viewer_view_model.is_loading.value is False

    # Проверяем что модальное окно инициализировано с этим содержимым
    assert modal._file_path == str(test_path)
    assert modal._content == test_content


def test_file_viewer_initializes_with_parameters(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить инициализацию модального окна с параметрами.

    Если file_path и content переданы в конструктор, они должны быть
    установлены в ViewModel и использованы модальным окном.
    """
    test_path = "/home/user/main.py"
    test_content = "def main():\n    pass"

    # Создаем модальное окно с параметрами
    modal = FileViewerModal(
        file_viewer_vm=file_viewer_view_model,
        file_path=test_path,
        content=test_content,
    )

    # Проверяем что состояние инициализировано
    assert file_viewer_view_model.file_path.value == Path(test_path)
    assert file_viewer_view_model.content.value == test_content
    assert file_viewer_view_model.is_visible.value is True
    assert modal._file_path == test_path
    assert modal._content == test_content


def test_file_viewer_updates_on_content_change(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить обновление при изменении содержимого в ViewModel.

    Когда содержимое изменяется через ViewModel, модальное окно
    должно обновиться и отразить новое содержимое.
    """
    test_path = Path("/home/user/test.py")
    initial_content = "x = 1"

    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    # Показываем начальный файл
    file_viewer_view_model.show_file(test_path, initial_content)
    assert modal._content == initial_content

    # Изменяем содержимое
    new_content = "x = 2\ny = 3"
    file_viewer_view_model._content.value = new_content

    # Модальное окно должно обновиться
    assert modal._content == new_content


def test_file_viewer_hides_on_close(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить скрытие модального окна при закрытии.

    Когда окно закрывается, флаг is_visible в ViewModel должен
    быть установлен в False.
    """
    test_path = Path("/home/user/test.py")
    test_content = "code"

    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    # Показываем файл
    file_viewer_view_model.show_file(test_path, test_content)
    assert file_viewer_view_model.is_visible.value is True

    # Скрываем модальное окно через метод
    modal.file_viewer_vm.hide()

    # Флаг видимости должен быть сброшен
    assert file_viewer_view_model.is_visible.value is False


def test_file_viewer_loading_status(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить отображение статуса загрузки из ViewModel.

    FileViewerModal должен реагировать на изменения флага is_loading
    в ViewModel.
    """
    # Изначально не загружается
    assert file_viewer_view_model.is_loading.value is False

    # Устанавливаем статус загрузки
    file_viewer_view_model.set_loading(True)
    assert file_viewer_view_model.is_loading.value is True

    # Показываем файл (обнуляет is_loading)
    file_viewer_view_model.show_file(Path("/test.py"), "content")
    assert file_viewer_view_model.is_loading.value is False

    # Снова устанавливаем загрузку
    file_viewer_view_model.set_loading(True)
    assert file_viewer_view_model.is_loading.value is True


def test_file_viewer_clear(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить очистку состояния ViewModel.

    При вызове clear() на ViewModel, все свойства должны быть
    сброшены в исходное состояние.
    """
    # Установим значения
    file_viewer_view_model.show_file(Path("/test.py"), "code")
    file_viewer_view_model.set_loading(True)

    # Проверим что они установлены
    assert file_viewer_view_model.file_path.value is not None
    assert file_viewer_view_model.content.value != ""
    assert file_viewer_view_model.is_visible.value is True
    assert file_viewer_view_model.is_loading.value is True

    # Очищаем состояние
    file_viewer_view_model.clear()

    # Все должно быть сброшено
    assert file_viewer_view_model.file_path.value is None
    assert file_viewer_view_model.content.value == ""
    assert file_viewer_view_model.is_visible.value is False
    assert file_viewer_view_model.is_loading.value is False


def test_file_viewer_show_file_via_view_model(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить обновление состояния через show_file в ViewModel."""
    FileViewerModal(file_viewer_vm=file_viewer_view_model)

    test_path = Path("/home/user/test.py")
    test_content = "print('test')"

    file_viewer_view_model.show_file(test_path, test_content)

    # Состояние должно быть обновлено через ViewModel
    assert file_viewer_view_model.file_path.value == test_path
    assert file_viewer_view_model.content.value == test_content
    assert file_viewer_view_model.is_visible.value is True


def test_file_viewer_show_file_with_path_object(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить работу show_file с Path значением."""
    FileViewerModal(file_viewer_vm=file_viewer_view_model)

    test_path = Path("/home/user/test.py")
    test_content = "code"

    file_viewer_view_model.show_file(test_path, test_content)

    # Состояние должно быть обновлено
    assert file_viewer_view_model.file_path.value == test_path
    assert file_viewer_view_model.content.value == test_content


def test_file_viewer_hide_resets_visibility(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить скрытие модального окна через ViewModel."""
    FileViewerModal(file_viewer_vm=file_viewer_view_model)

    # Показываем файл
    file_viewer_view_model.show_file(Path("/test.py"), "content")
    assert file_viewer_view_model.is_visible.value is True

    file_viewer_view_model.hide()

    # Флаг видимости должен быть сброшен
    assert file_viewer_view_model.is_visible.value is False


def test_file_viewer_multiple_files_switch(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить переключение между несколькими файлами.

    Модальное окно должно корректно обновляться при переключении
    между разными файлами в ViewModel.
    """
    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    # Первый файл
    path1 = Path("/home/user/file1.py")
    content1 = "# File 1"
    file_viewer_view_model.show_file(path1, content1)

    assert file_viewer_view_model.file_path.value == path1
    assert file_viewer_view_model.content.value == content1
    assert modal._file_path == str(path1)
    assert modal._content == content1

    # Второй файл
    path2 = Path("/home/user/file2.py")
    content2 = "# File 2"
    file_viewer_view_model.show_file(path2, content2)

    assert file_viewer_view_model.file_path.value == path2
    assert file_viewer_view_model.content.value == content2
    assert modal._file_path == str(path2)
    assert modal._content == content2


def test_file_viewer_path_normalization(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить нормализацию путей при отображении.

    Пути должны корректно преобразовываться из Path в строку
    для отображения в модальном окне.
    """
    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    # Используем Path с различными компонентами
    test_path = Path("/home") / "user" / "project" / "src" / "main.py"
    test_content = "code"

    file_viewer_view_model.show_file(test_path, test_content)

    # Путь должен быть преобразован в строку
    assert modal._file_path == str(test_path)
    assert "/" in modal._file_path or "\\" in modal._file_path


def test_file_viewer_empty_content(
    file_viewer_view_model: FileViewerViewModel,
) -> None:
    """Проверить обработку пустого содержимого файла.

    Модальное окно должно корректно работать с пустым содержимым.
    """
    modal = FileViewerModal(file_viewer_vm=file_viewer_view_model)

    test_path = Path("/home/user/empty.txt")
    empty_content = ""

    file_viewer_view_model.show_file(test_path, empty_content)

    assert file_viewer_view_model.content.value == ""
    assert modal._content == ""
    assert file_viewer_view_model.file_path.value == test_path

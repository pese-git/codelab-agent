"""Тесты для компонента FileTree с MVVM интеграцией."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.filesystem_view_model import FileSystemViewModel
from codelab.client.tui.components.file_tree import FileTree


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def filesystem_view_model(event_bus: EventBus) -> FileSystemViewModel:
    """Создать FileSystemViewModel для тестов."""
    return FileSystemViewModel(event_bus=event_bus, logger=None)


@pytest.fixture
def temp_dir() -> TemporaryDirectory:
    """Создать временный каталог для тестов."""
    return TemporaryDirectory()


def test_file_tree_requires_filesystem_vm(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить что FileTree требует обязательный параметр filesystem_vm.
    
    FileTree не может быть инициализирован без FileSystemViewModel.
    """
    # FileTree должен быть инициализирован с обязательным параметром
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    assert file_tree.filesystem_vm is filesystem_view_model
    assert file_tree.id == "file-tree"


def test_file_tree_initializes_root_path_from_param(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить инициализацию корневого пути из параметра конструктора.
    
    При передаче root_path в конструктор, он должен быть установлен
    в ViewModel и использоваться деревом.
    """
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Корневой путь должен быть установлен
    assert file_tree.root_path == Path(temp_dir.name)
    # ViewModel должен содержать установленный путь
    assert filesystem_view_model.root_path.value == Path(temp_dir.name)


def test_file_tree_initializes_root_path_from_view_model(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить инициализацию корневого пути из ViewModel.
    
    Если root_path не передан в конструктор, должно использоваться
    значение из ViewModel или дефолтный путь.
    """
    # Установим путь в ViewModel перед созданием компонента
    test_path = Path(temp_dir.name)
    filesystem_view_model.set_root(test_path)
    
    # Создаем FileTree без explicit root_path
    file_tree = FileTree(filesystem_vm=filesystem_view_model)
    
    # Должен использоваться путь из ViewModel
    assert file_tree.root_path == test_path
    assert filesystem_view_model.root_path.value == test_path


def test_file_tree_updates_on_root_change(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить обновление UI при изменении корня в ViewModel.
    
    При изменении root_path в ViewModel, FileTree должен обновиться
    и отразить новое корневое значение.
    """
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Начальный путь
    assert file_tree.root_path == Path(temp_dir.name)
    
    # Создаем новую временную папку и устанавливаем ее через ViewModel
    with TemporaryDirectory() as new_dir:
        new_path = Path(new_dir)
        filesystem_view_model.set_root(new_path)
        
        # FileTree должен обновиться через callback
        assert file_tree.root_path == new_path


def test_file_tree_updates_on_selection_change(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить обновление при выборе файла в ViewModel.
    
    Когда выбранный путь изменяется через ViewModel, компонент
    должен отреагировать на это изменение.
    """
    FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Изначально ничего не выбрано
    assert filesystem_view_model.selected_path.value is None
    
    # Выбираем путь через ViewModel
    selected_path = Path(temp_dir.name)
    filesystem_view_model.select_path(selected_path)
    
    # ViewModel должен содержать выбранный путь
    assert filesystem_view_model.selected_path.value == selected_path


def test_file_tree_select_file_method(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить метод select_file компонента.
    
    Метод select_file должен обновлять выбранный путь через ViewModel.
    """
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Используем метод компонента для выбора файла
    selected_path = Path(temp_dir.name)
    file_tree.select_file(selected_path)
    
    # ViewModel должен содержать выбранный путь
    assert filesystem_view_model.selected_path.value == selected_path


def test_file_tree_loading_status(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить статус загрузки из ViewModel.
    
    FileTree должен реагировать на изменения флага is_loading в ViewModel.
    """
    FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Изначально не загружается
    assert filesystem_view_model.is_loading.value is False
    
    # Устанавливаем статус загрузки
    filesystem_view_model.set_loading(True)
    assert filesystem_view_model.is_loading.value is True
    
    # Отключаем загрузку
    filesystem_view_model.set_loading(False)
    assert filesystem_view_model.is_loading.value is False


def test_file_tree_clear(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить очистку состояния ViewModel.
    
    При вызове clear() на ViewModel, все свойства должны быть
    сброшены в исходное состояние.
    """
    FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Установим значения
    filesystem_view_model.select_path(Path(temp_dir.name))
    filesystem_view_model.set_loading(True)
    
    # Проверим что они установлены
    assert filesystem_view_model.root_path.value is not None
    assert filesystem_view_model.selected_path.value is not None
    assert filesystem_view_model.is_loading.value is True
    
    # Очищаем состояние
    filesystem_view_model.clear()
    
    # Все должно быть сброшено
    assert filesystem_view_model.root_path.value is None
    assert filesystem_view_model.selected_path.value is None
    assert filesystem_view_model.is_loading.value is False


def test_file_tree_backward_compatibility_set_root_path(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить обратную совместимость метода set_root_path.
    
    Старый метод set_root_path должен работать через ViewModel
    и обновлять состояние компонента.
    """
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Используем старый метод
    with TemporaryDirectory() as new_dir:
        file_tree.set_root_path(new_dir)
        
        # Путь должен быть обновлен через ViewModel
        assert file_tree.root_path == Path(new_dir)
        assert filesystem_view_model.root_path.value == Path(new_dir)


def test_file_tree_backward_compatibility_mark_changed(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить обратную совместимость метода mark_changed.
    
    Старый метод mark_changed должен продолжать работать как раньше.
    """
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    test_path = Path(temp_dir.name) / "test.txt"
    
    # Помечаем файл как измененный
    file_tree.mark_changed(test_path)
    
    # Проверяем что файл помечен
    assert file_tree.is_changed(test_path)


def test_file_tree_observable_subscription(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить подписку на Observable в ViewModel.
    
    FileTree должен устанавливать observers на все свойства ViewModel
    при инициализации.
    """
    file_tree = FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Должны быть установлены unsubscribe функции
    assert len(file_tree._unsubscribers) == 3  # root_path, selected_path, is_loading
    
    # При удалении компонента должны быть вызваны unsubscribe функции
    file_tree._unsubscribe_from_view_model()
    assert len(file_tree._unsubscribers) == 0


def test_file_tree_mvvm_decoupling(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить отделение ViewModel от компонента.
    
    ViewModel не должен зависеть от FileTree компонента.
    Они должны быть независимыми и взаимодействовать через Observable.
    """
    # Создаем ViewModel без компонента
    vm = FileSystemViewModel()
    
    # ViewModel должен работать независимо
    test_path = Path(temp_dir.name)
    vm.set_root(test_path)
    vm.select_path(test_path)
    vm.set_loading(True)
    
    # Все значения должны быть установлены
    assert vm.root_path.value == test_path
    assert vm.selected_path.value == test_path
    assert vm.is_loading.value is True
    
    # Теперь создаем компонент и подключаем к ViewModel
    file_tree = FileTree(filesystem_vm=vm)
    
    # Компонент должен получить текущие значения из ViewModel
    assert file_tree.root_path == test_path


def test_file_tree_multiple_observers(
    filesystem_view_model: FileSystemViewModel,
    temp_dir: TemporaryDirectory,
) -> None:
    """Проверить работу с несколькими observers на одном Observable.
    
    Несколько компонентов или функций могут подписаться на один Observable,
    и все должны получить уведомления об изменениях.
    """
    # Создаем список для отслеживания событий
    events: list[Path | None] = []
    
    # Подписываемся на изменение корневого пути
    def on_root_changed(path: Path | None) -> None:
        events.append(path)
    
    unsub = filesystem_view_model.root_path.subscribe(on_root_changed)
    
    # Создаем FileTree, который тоже подписан
    FileTree(
        filesystem_vm=filesystem_view_model,
        root_path=temp_dir.name,
    )
    
    # Изменяем путь
    with TemporaryDirectory() as new_dir:
        new_path = Path(new_dir)
        filesystem_view_model.set_root(new_path)
        
        # Наш callback должен был получить уведомление
        assert len(events) > 0
        assert new_path in events
    
    unsub()

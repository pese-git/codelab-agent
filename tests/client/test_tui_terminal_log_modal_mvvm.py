"""Тесты для компонента TerminalLogModal с MVVM интеграцией."""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.terminal_log_view_model import TerminalLogViewModel
from codelab.client.tui.components.terminal_log_modal import TerminalLogModal


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def terminal_log_view_model(event_bus: EventBus) -> TerminalLogViewModel:
    """Создать TerminalLogViewModel для тестов."""
    return TerminalLogViewModel(event_bus=event_bus, logger=None)


def test_terminal_log_modal_requires_terminal_log_vm(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить что TerminalLogModal требует обязательный параметр terminal_log_vm.

    TerminalLogModal не может быть инициализирован без TerminalLogViewModel.
    """
    # TerminalLogModal должен быть инициализирован с обязательным параметром
    modal = TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    assert modal.terminal_log_vm is terminal_log_view_model
    assert modal.terminal_log_vm.log_entries.value == []
    assert modal.terminal_log_vm.is_visible.value is False


def test_terminal_log_modal_adds_entry(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить добавление записи в лог через ViewModel.

    При вызове add_entry через ViewModel, запись должна быть добавлена
    в список log_entries.
    """
    # Создаем модальное окно с ViewModel
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    entry = "Command executed successfully"

    # Добавляем запись через ViewModel
    terminal_log_view_model.add_entry(entry)

    # Проверяем что запись добавлена
    assert len(terminal_log_view_model.log_entries.value) == 1
    assert terminal_log_view_model.log_entries.value[0] == entry


def test_terminal_log_modal_adds_multiple_entries(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить добавление нескольких записей в лог.

    Каждый вызов add_entry должен добавлять новую запись в конец списка.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    entries = [
        "Starting command",
        "Processing data",
        "Command completed",
    ]

    # Добавляем несколько записей через ViewModel
    for entry in entries:
        terminal_log_view_model.add_entry(entry)

    # Проверяем что все записи добавлены
    assert len(terminal_log_view_model.log_entries.value) == 3
    assert terminal_log_view_model.log_entries.value == entries


def test_terminal_log_modal_sets_entries(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить установку всех записей лога через ViewModel.

    При вызове set_entries, все записи должны быть заменены на новый список.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    # Добавляем несколько записей
    terminal_log_view_model.add_entry("Entry 1")
    terminal_log_view_model.add_entry("Entry 2")

    assert len(terminal_log_view_model.log_entries.value) == 2

    # Устанавливаем новые записи
    new_entries = ["New Entry A", "New Entry B", "New Entry C"]
    terminal_log_view_model.set_entries(new_entries)

    # Проверяем что все записи заменены
    assert len(terminal_log_view_model.log_entries.value) == 3
    assert terminal_log_view_model.log_entries.value == new_entries


def test_terminal_log_modal_clears_entries(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить очистку всех записей через ViewModel.

    При вызове clear_entries(), все записи должны быть удалены.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    # Добавляем несколько записей
    terminal_log_view_model.add_entry("Entry 1")
    terminal_log_view_model.add_entry("Entry 2")
    terminal_log_view_model.add_entry("Entry 3")

    assert len(terminal_log_view_model.log_entries.value) == 3

    # Очищаем все записи
    terminal_log_view_model.clear_entries()

    # Проверяем что все записи удалены
    assert len(terminal_log_view_model.log_entries.value) == 0
    assert terminal_log_view_model.log_entries.value == []


def test_terminal_log_modal_shows_and_hides(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить показ и скрытие модального окна через ViewModel.

    При вызове show(), флаг is_visible должен быть True.
    При вызове hide(), флаг is_visible должен быть False.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    # Проверяем начальное состояние
    assert terminal_log_view_model.is_visible.value is False

    # Показываем модальное окно
    terminal_log_view_model.show()
    assert terminal_log_view_model.is_visible.value is True

    # Скрываем модальное окно
    terminal_log_view_model.hide()
    assert terminal_log_view_model.is_visible.value is False


def test_terminal_log_modal_updates_on_entries_change(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить обновление UI при изменении записей в ViewModel.

    Когда log_entries изменяются через ViewModel, модальное окно
    должно синхронизировать UI через Observable паттерн.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    # Отслеживаем изменения через Observable
    change_count = 0

    def on_entries_changed(entries: list[str]) -> None:
        nonlocal change_count
        change_count += 1

    # Подписываемся на изменения
    unsub = terminal_log_view_model.log_entries.subscribe(on_entries_changed)

    try:
        # Добавляем запись
        terminal_log_view_model.add_entry("Entry 1")
        assert change_count == 1

        # Добавляем еще одну запись
        terminal_log_view_model.add_entry("Entry 2")
        assert change_count == 2

        # Устанавливаем новые записи
        terminal_log_view_model.set_entries(["New Entry"])
        assert change_count == 3

        # Очищаем записи
        terminal_log_view_model.clear_entries()
        assert change_count == 4
    finally:
        # Отписываемся
        unsub()


def test_terminal_log_modal_empty_entries_list(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить работу с пустым списком записей.

    Изначально список записей должен быть пуст, и операции
    с пустым списком должны работать корректно.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    # Проверяем что список пуст
    assert terminal_log_view_model.log_entries.value == []
    assert len(terminal_log_view_model.log_entries.value) == 0

    # Очищаем пустой список - должно работать без ошибок
    terminal_log_view_model.clear_entries()
    assert terminal_log_view_model.log_entries.value == []

    # Устанавливаем новый список на пустой список - должно работать
    terminal_log_view_model.set_entries([])
    assert terminal_log_view_model.log_entries.value == []


def test_terminal_log_modal_set_entries_creates_copy(
    terminal_log_view_model: TerminalLogViewModel,
) -> None:
    """Проверить что set_entries создает копию списка.

    Когда устанавливаем записи, должна создаваться копия списка,
    чтобы внешние изменения не влияли на ViewModel.
    """
    TerminalLogModal(
        terminal_log_vm=terminal_log_view_model,
        title="Test Terminal Log",
        terminal_id="term_001",
    )

    # Создаем список и устанавливаем его
    original_list = ["Entry 1", "Entry 2", "Entry 3"]
    terminal_log_view_model.set_entries(original_list)

    # Получаем список из ViewModel
    stored_list = terminal_log_view_model.log_entries.value

    # Проверяем что это разные объекты (копия)
    assert stored_list == original_list
    assert stored_list is not original_list

    # Изменяем исходный список
    original_list[0] = "Modified Entry 1"

    # Проверяем что ViewModel не изменился
    assert terminal_log_view_model.log_entries.value[0] == "Entry 1"
    assert terminal_log_view_model.log_entries.value != original_list

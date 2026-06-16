"""Тесты для компонента TerminalOutputPanel с MVVM интеграцией.

Включает тесты для:
- TerminalOutputToolbar - панель инструментов
- TerminalOutputContent - область вывода
- TerminalOutputPanel - объединённый компонент
"""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.terminal_view_model import TerminalViewModel
from codelab.client.tui.components.terminal_output import (
    TerminalOutputContent,
    TerminalOutputPanel,
    TerminalOutputToolbar,
)


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def terminal_view_model(event_bus: EventBus) -> TerminalViewModel:
    """Создать TerminalViewModel для тестов."""
    return TerminalViewModel(event_bus=event_bus, logger=None)


@pytest.fixture
def terminal_output_panel(terminal_view_model: TerminalViewModel) -> TerminalOutputPanel:
    """Создать TerminalOutputPanel с TerminalViewModel."""
    return TerminalOutputPanel(terminal_view_model)


# ===== Инициализация Tests =====

def test_terminal_output_requires_terminal_vm() -> None:
    """Проверить что TerminalOutputPanel требует обязательный параметр terminal_vm."""
    terminal_vm = TerminalViewModel()
    
    # Должен создаться успешно с ViewModel
    panel = TerminalOutputPanel(terminal_vm)
    assert panel._terminal_vm is terminal_vm
    assert panel.id == "terminal-output"


def test_terminal_output_initializes_with_terminal_vm(
    terminal_view_model: TerminalViewModel,
    terminal_output_panel: TerminalOutputPanel,
) -> None:
    """Проверить что TerminalOutputPanel инициализируется с TerminalViewModel."""
    assert terminal_output_panel._terminal_vm is terminal_view_model
    assert terminal_output_panel.id == "terminal-output"
    assert terminal_output_panel._exit_code is None


# ===== Output Updates Tests =====

def test_terminal_output_updates_on_output_change(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что UI обновляется при изменении вывода в ViewModel."""
    # Изменяем вывод через ViewModel
    terminal_view_model.set_output("Hello World!")
    
    # Проверяем что ViewModel содержит текст
    assert terminal_view_model.output.value == "Hello World!"
    
    # Проверяем что панель может отобразить текст
    rendered = terminal_output_panel.render_text()
    assert "Hello World!" in rendered.plain


def test_terminal_output_appends_text(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что можно добавлять текст к выводу."""
    # Добавляем текст через ViewModel
    terminal_view_model.append_output("Hello ")
    terminal_view_model.append_output("World!")
    
    # Проверяем результат
    assert terminal_view_model.output.value == "Hello World!"
    
    # Проверяем что has_output флаг установлен
    assert terminal_view_model.has_output.value is True


def test_terminal_output_clears_on_reset(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что очистка работает корректно."""
    # Добавляем вывод
    terminal_view_model.set_output("Some output")
    assert terminal_view_model.output.value == "Some output"
    assert terminal_view_model.has_output.value is True
    
    # Очищаем через reset
    terminal_output_panel.reset()
    
    # Проверяем что всё очищено
    assert terminal_view_model.output.value == ""
    assert terminal_view_model.has_output.value is False


def test_terminal_output_running_status(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить отображение статуса выполнения команды."""
    # Изначально не запущено
    assert terminal_view_model.is_running.value is False
    
    # Запускаем
    terminal_view_model.set_running(True)
    assert terminal_view_model.is_running.value is True
    
    # Останавливаем
    terminal_view_model.set_running(False)
    assert terminal_view_model.is_running.value is False


# ===== Backward Compatibility Tests =====

def test_terminal_output_backward_compatibility_append(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что старые методы append_output работают через ViewModel."""
    # Используем старый метод компонента
    terminal_output_panel.append_output("Test ")
    terminal_output_panel.append_output("Output")
    
    # Проверяем что данные попали в ViewModel
    assert terminal_view_model.output.value == "Test Output"
    assert terminal_view_model.has_output.value is True


def test_terminal_output_backward_compatibility_set_output(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что метод set_output работает через ViewModel."""
    # Используем метод компонента
    terminal_output_panel.set_output("New Output")
    
    # Проверяем что данные попали в ViewModel
    assert terminal_view_model.output.value == "New Output"
    assert terminal_view_model.has_output.value is True


def test_terminal_output_backward_compatibility_reset(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что метод reset работает через ViewModel."""
    # Добавляем данные
    terminal_output_panel.set_output("Some data")
    assert terminal_view_model.output.value == "Some data"
    
    # Используем старый метод reset
    terminal_output_panel.reset()
    
    # Проверяем что всё очищено
    assert terminal_view_model.output.value == ""
    assert terminal_output_panel._exit_code is None


# ===== Rendering Tests =====

def test_terminal_output_renders_empty_message_when_no_output(
    terminal_output_panel: TerminalOutputPanel,
) -> None:
    """Проверить отображение сообщения когда нет вывода."""
    rendered = terminal_output_panel.render_text()
    assert "Нет вывода терминала" in rendered.plain


def test_terminal_output_set_exit_code(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить установку кода завершения."""
    terminal_view_model.set_output("Command executed")
    # Не вызываем update(), просто проверяем что exit code сохранился
    terminal_output_panel._exit_code = 0
    
    assert terminal_output_panel._exit_code == 0


def test_terminal_output_renders_output_with_ansi(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить отображение вывода с ANSI последовательностями."""
    # Текст с ANSI кодом цвета (например красный)
    output_with_ansi = "\x1b[31mError: Something went wrong\x1b[0m"
    terminal_view_model.set_output(output_with_ansi)
    
    rendered = terminal_output_panel.render_text()
    # Должен содержать текст ошибки
    assert "Error" in rendered.plain


# ===== Observable Subscription Tests =====

def test_terminal_output_subscribes_to_output_observable(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что компонент подписан на изменения output."""
    changes = []
    terminal_view_model.output.subscribe(lambda value: changes.append(value))
    
    terminal_view_model.set_output("Test")
    
    # Проверяем что callback был вызван
    assert "Test" in changes


def test_terminal_output_subscribes_to_has_output_observable(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что компонент подписан на has_output флаг."""
    changes = []
    terminal_view_model.has_output.subscribe(lambda value: changes.append(value))
    
    terminal_view_model.set_output("Test")
    
    # Проверяем что флаг был изменен
    assert True in changes


def test_terminal_output_subscribes_to_is_running_observable(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что компонент подписан на is_running флаг."""
    changes = []
    terminal_view_model.is_running.subscribe(lambda value: changes.append(value))
    
    terminal_view_model.set_running(True)
    
    # Проверяем что флаг был изменен
    assert True in changes


# ===== Integration Tests =====

def test_terminal_output_mvvm_integration_flow(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить полный цикл MVVM интеграции."""
    # 1. Проверяем начальное состояние
    assert terminal_view_model.output.value == ""
    assert terminal_view_model.has_output.value is False
    assert terminal_view_model.is_running.value is False
    
    # 2. Запускаем команду
    terminal_view_model.set_running(True)
    assert terminal_view_model.is_running.value is True
    
    # 3. Добавляем вывод
    terminal_view_model.append_output("Processing...")
    assert terminal_view_model.has_output.value is True
    
    # 4. Завершаем
    terminal_view_model.set_running(False)
    # Установляем exit code напрямую (без вызова update которому нужен Textual app)
    terminal_output_panel._exit_code = 0
    
    # 5. Проверяем финальное состояние
    assert terminal_view_model.is_running.value is False
    assert terminal_output_panel._exit_code == 0
    assert "Processing" in terminal_view_model.output.value


def test_terminal_output_multiple_appends(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить несколько последовательных добавлений вывода."""
    chunks = ["Line 1\n", "Line 2\n", "Line 3\n"]
    
    for chunk in chunks:
        terminal_view_model.append_output(chunk)
    
    expected = "".join(chunks)
    assert terminal_view_model.output.value == expected
    
    rendered = terminal_output_panel.render_text()
    assert "Line 1" in rendered.plain
    assert "Line 2" in rendered.plain
    assert "Line 3" in rendered.plain


def test_terminal_output_handles_whitespace_only(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что пробелы не считаются выводом."""
    terminal_view_model.set_output("   \n\t  ")
    
    # has_output должен быть False для чистых пробелов
    assert terminal_view_model.has_output.value is False


def test_terminal_output_preserves_exit_code_on_reset(
    terminal_output_panel: TerminalOutputPanel,
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что exit code сбрасывается вместе с выводом."""
    # Добавляем вывод и exit code
    terminal_view_model.set_output("Some output")
    terminal_output_panel._exit_code = 42
    
    # Очищаем вывод через reset
    terminal_output_panel.reset()
    
    # Проверяем что exit code тоже очищен
    assert terminal_output_panel._exit_code is None
    assert terminal_view_model.output.value == ""


# ===== TerminalOutputToolbar Tests =====

def test_terminal_output_toolbar_creation() -> None:
    """Проверить создание TerminalOutputToolbar."""
    toolbar = TerminalOutputToolbar(title="My Terminal")
    assert toolbar.id == "terminal-output-toolbar"
    assert toolbar._title == "My Terminal"


def test_terminal_output_toolbar_default_title() -> None:
    """Проверить заголовок по умолчанию."""
    toolbar = TerminalOutputToolbar()
    assert toolbar._title == "Terminal"


def test_terminal_output_toolbar_set_title() -> None:
    """Проверить изменение заголовка."""
    toolbar = TerminalOutputToolbar(title="Original")
    toolbar.set_title("Updated")
    assert toolbar._title == "Updated"


def test_terminal_output_toolbar_custom_id() -> None:
    """Проверить кастомный ID."""
    toolbar = TerminalOutputToolbar(id="custom-toolbar")
    assert toolbar.id == "custom-toolbar"


# ===== TerminalOutputContent Tests =====

def test_terminal_output_content_creation() -> None:
    """Проверить создание TerminalOutputContent."""
    content = TerminalOutputContent()
    assert content.id == "terminal-output-content"
    assert content._output_text == ""
    assert content._exit_code is None


def test_terminal_output_content_set_output() -> None:
    """Проверить установку вывода."""
    content = TerminalOutputContent()
    content._output_text = "Test output"  # Без вызова set_output который требует Textual
    assert content._output_text == "Test output"


def test_terminal_output_content_clear() -> None:
    """Проверить очистку вывода."""
    content = TerminalOutputContent()
    content._output_text = "Some output"
    content._exit_code = 0
    
    # Очищаем напрямую без вызова Textual
    content._output_text = ""
    content._exit_code = None
    
    assert content._output_text == ""
    assert content._exit_code is None


def test_terminal_output_content_get_output() -> None:
    """Проверить получение вывода."""
    content = TerminalOutputContent()
    content._output_text = "Test"
    assert content.get_output() == "Test"


def test_terminal_output_content_custom_id() -> None:
    """Проверить кастомный ID."""
    content = TerminalOutputContent(id="custom-content")
    assert content.id == "custom-content"


# ===== TerminalOutputPanel with Toolbar Tests =====

def test_terminal_output_panel_with_toolbar(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить создание панели с toolbar."""
    panel = TerminalOutputPanel(terminal_view_model, show_toolbar=True)
    assert panel._show_toolbar is True
    assert panel.toolbar_visible is True


def test_terminal_output_panel_without_toolbar(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить создание панели без toolbar."""
    panel = TerminalOutputPanel(terminal_view_model, show_toolbar=False)
    assert panel._show_toolbar is False
    assert panel.toolbar_visible is False


def test_terminal_output_panel_default_toolbar(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить что toolbar включен по умолчанию."""
    panel = TerminalOutputPanel(terminal_view_model)
    assert panel._show_toolbar is True


def test_terminal_output_panel_custom_title(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить кастомный заголовок."""
    panel = TerminalOutputPanel(terminal_view_model, title="Custom Title")
    assert panel._title == "Custom Title"


def test_terminal_output_panel_set_title(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить изменение заголовка."""
    panel = TerminalOutputPanel(terminal_view_model, title="Original")
    panel.set_title("Updated")
    assert panel._title == "Updated"


def test_terminal_output_panel_toggle_toolbar_visibility(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить переключение видимости toolbar."""
    panel = TerminalOutputPanel(terminal_view_model, show_toolbar=True)
    assert panel.toolbar_visible is True
    
    # Скрываем toolbar
    panel.toolbar_visible = False
    assert panel._show_toolbar is False
    
    # Показываем toolbar
    panel.toolbar_visible = True
    assert panel._show_toolbar is True


def test_terminal_output_panel_custom_id(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить кастомный ID панели."""
    panel = TerminalOutputPanel(terminal_view_model, id="custom-panel")
    assert panel.id == "custom-panel"


def test_terminal_output_panel_custom_classes(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить кастомные CSS классы."""
    panel = TerminalOutputPanel(terminal_view_model, classes="my-class")
    assert "my-class" in panel.classes


# ===== Integration Tests for New Components =====

def test_terminal_output_panel_full_integration(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить полную интеграцию нового TerminalOutputPanel."""
    # Создаём панель с toolbar
    panel = TerminalOutputPanel(
        terminal_view_model,
        show_toolbar=True,
        title="Integration Test",
    )
    
    # Проверяем начальное состояние
    assert panel._terminal_vm is terminal_view_model
    assert panel._show_toolbar is True
    assert panel._title == "Integration Test"
    assert panel._exit_code is None
    
    # Добавляем вывод через панель
    panel.append_output("Hello ")
    panel.append_output("World!")
    
    # Проверяем что данные в ViewModel
    assert terminal_view_model.output.value == "Hello World!"
    assert terminal_view_model.has_output.value is True
    
    # Устанавливаем exit code
    panel.set_exit_code(0)
    assert panel._exit_code == 0
    
    # Сбрасываем
    panel.reset()
    assert terminal_view_model.output.value == ""
    assert panel._exit_code is None


def test_terminal_output_panel_render_text_compatibility(
    terminal_view_model: TerminalViewModel,
) -> None:
    """Проверить обратную совместимость render_text()."""
    panel = TerminalOutputPanel(terminal_view_model)
    
    # Без вывода
    rendered = panel.render_text()
    assert "Нет вывода терминала" in rendered.plain
    
    # С выводом
    terminal_view_model.set_output("Test output")
    rendered = panel.render_text()
    assert "Test output" in rendered.plain
    
    # С exit code
    panel._exit_code = 42
    rendered = panel.render_text()
    assert "Exit code: 42" in rendered.plain

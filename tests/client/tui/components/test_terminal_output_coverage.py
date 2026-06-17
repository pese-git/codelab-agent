"""Тесты для покрытия terminal_output.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from rich.text import Text
from textual._context import active_app
from textual.app import App
from textual.widgets import Button, Label

from codelab.client.presentation.terminal_view_model import TerminalViewModel
from codelab.client.tui.components.terminal_output import (
    TerminalOutputContent,
    TerminalOutputPanel,
    TerminalOutputToolbar,
)


class TestTerminalOutputToolbar:
    """Тесты для TerminalOutputToolbar."""

    def test_init_default_id(self) -> None:
        """ID по умолчанию задан."""
        toolbar = TerminalOutputToolbar()
        assert toolbar.id == "terminal-output-toolbar"
        assert toolbar._title == "Terminal"

    def test_compose(self) -> None:
        """Toolbar содержит заголовок и две кнопки."""
        toolbar = TerminalOutputToolbar()
        children = list(toolbar.compose())
        labels = [c for c in children if isinstance(c, Label)]
        buttons = [c for c in children if isinstance(c, Button)]
        assert len(labels) == 1
        assert len(buttons) == 2

    def test_button_pressed_clear(self) -> None:
        """Кнопка очистки отправляет ClearRequested."""
        toolbar = TerminalOutputToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("🗑", id="btn-clear")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert len(posted) == 1
        assert isinstance(posted[0], TerminalOutputToolbar.ClearRequested)

    def test_button_pressed_copy(self) -> None:
        """Кнопка копирования отправляет CopyRequested."""
        toolbar = TerminalOutputToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("📋", id="btn-copy")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert isinstance(posted[0], TerminalOutputToolbar.CopyRequested)

    def test_button_pressed_unknown(self) -> None:
        """Неизвестная кнопка не отправляет сообщения."""
        toolbar = TerminalOutputToolbar()
        posted: list[object] = []
        toolbar.post_message = posted.append
        button = Button("?", id="btn-unknown")
        toolbar.on_button_pressed(Button.Pressed(button))
        assert len(posted) == 0

    def test_set_title(self) -> None:
        """set_title обновляет состояние."""
        toolbar = TerminalOutputToolbar()
        toolbar.set_title("New")
        assert toolbar._title == "New"

    def test_set_title_updates_label(self) -> None:
        """set_title обновляет виджет заголовка."""
        toolbar = TerminalOutputToolbar()
        label_mock = MagicMock()
        with patch.object(toolbar, "query_one", return_value=label_mock):
            toolbar.set_title("New")
        label_mock.update.assert_called_once_with("New")


class TestTerminalOutputContent:
    """Тесты для TerminalOutputContent."""

    def test_init(self) -> None:
        """Начальное состояние пустое."""
        content = TerminalOutputContent()
        assert content._output_text == ""
        assert content._exit_code is None
        assert content.id == "terminal-output-content"

    def test_set_output(self) -> None:
        """set_output обновляет текст и виджет."""
        content = TerminalOutputContent()
        with patch.object(content, "update") as update_mock:
            content.set_output("hello")
        assert content._output_text == "hello"
        update_mock.assert_called_once()

    def test_set_exit_code(self) -> None:
        """set_exit_code обновляет код и виджет."""
        content = TerminalOutputContent()
        with patch.object(content, "update") as update_mock:
            content.set_exit_code(1)
        assert content._exit_code == 1
        update_mock.assert_called_once()

    def test_clear(self) -> None:
        """clear сбрасывает состояние."""
        content = TerminalOutputContent()
        content._output_text = "hello"
        content._exit_code = 1
        with patch.object(content, "update") as update_mock:
            content.clear()
        assert content._output_text == ""
        assert content._exit_code is None
        update_mock.assert_called_once()

    def test_get_output(self) -> None:
        """get_output возвращает текущий текст."""
        content = TerminalOutputContent()
        content._output_text = "text"
        assert content.get_output() == "text"

    def test_render_text_empty(self) -> None:
        """Пустой вывод рендерит сообщение."""
        content = TerminalOutputContent()
        text = content._render_text()
        assert isinstance(text, Text)
        assert "Нет вывода" in text.plain

    def test_render_text_exit_only(self) -> None:
        """При отсутствии вывода показывается exit code."""
        content = TerminalOutputContent()
        content._exit_code = 42
        text = content._render_text()
        assert "Exit code: 42" in text.plain

    def test_render_text_with_ansi(self) -> None:
        """Вывод рендерится с ANSI-поддержкой."""
        content = TerminalOutputContent()
        content._output_text = "\x1b[31mred\x1b[0m"
        text = content._render_text()
        assert "red" in text.plain

    def test_render_text_with_exit_code(self) -> None:
        """Exit code добавляется к выводу."""
        content = TerminalOutputContent()
        content._output_text = "out"
        content._exit_code = 1
        text = content._render_text()
        assert "out" in text.plain
        assert "Exit code: 1" in text.plain


class TestTerminalOutputPanel:
    """Тесты для TerminalOutputPanel."""

    def test_init(self) -> None:
        """Инициализация панели."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        assert panel.id == "terminal-output"
        assert panel._terminal_vm is vm
        assert panel._show_toolbar is True
        assert panel._title == "Terminal"

    def test_init_no_toolbar(self) -> None:
        """Можно скрыть toolbar."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm, show_toolbar=False)
        assert panel._show_toolbar is False

    def test_subscriptions(self) -> None:
        """Панель подписывается на Observable ViewModel."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        assert panel._content is None

    def test_compose(self) -> None:
        """Панель создаёт toolbar и content."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        app = App()
        token = active_app.set(app)
        try:
            children = list(panel.compose())
        finally:
            active_app.reset(token)
        assert panel._toolbar is not None
        assert panel._content is not None
        assert len(children) >= 2

    def test_on_mount_no_toolbar(self) -> None:
        """on_mount добавляет класс -no-toolbar если toolbar скрыт."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm, show_toolbar=False)
        content_mock = MagicMock()
        panel._content = content_mock
        panel.on_mount()
        assert panel.has_class("-no-toolbar")

    def test_on_mount_sync_content(self) -> None:
        """on_mount синхронизирует контент."""
        vm = TerminalViewModel()
        vm.set_output("initial")
        panel = TerminalOutputPanel(vm)
        content_mock = MagicMock()
        panel._content = content_mock
        panel.on_mount()
        content_mock.set_output.assert_called_once_with("initial")
        content_mock.set_exit_code.assert_called_once_with(None)

    def test_sync_content(self) -> None:
        """_sync_content обновляет content."""
        vm = TerminalViewModel()
        vm.set_output("hello")
        panel = TerminalOutputPanel(vm)
        content_mock = MagicMock()
        panel._content = content_mock
        panel._sync_content()
        content_mock.set_output.assert_called_once_with("hello")
        content_mock.set_exit_code.assert_called_once_with(None)

    def test_on_output_changed(self) -> None:
        """Изменение output обновляет content."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        content_mock = MagicMock()
        panel._content = content_mock
        panel._exit_code = 0
        panel._on_output_changed("new output")
        content_mock.set_output.assert_called_once_with("new output")
        content_mock.set_exit_code.assert_called_once_with(0)

    def test_on_output_changed_suppresses_runtime_error(self) -> None:
        """RuntimeError при обновлении output подавляется."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        content_mock = MagicMock()
        content_mock.set_output.side_effect = RuntimeError("boom")
        panel._content = content_mock
        panel._on_output_changed("x")

    def test_on_running_changed(self) -> None:
        """Изменение running обновляет заголовок toolbar."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        toolbar_mock = MagicMock()
        panel._toolbar = toolbar_mock
        panel._on_running_changed(True)
        toolbar_mock.set_title.assert_called_once_with("Terminal ⏳")

    def test_on_running_changed_finished(self) -> None:
        """По завершении заголовок возвращается."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        toolbar_mock = MagicMock()
        panel._toolbar = toolbar_mock
        panel._on_running_changed(False)
        toolbar_mock.set_title.assert_called_once_with("Terminal")

    def test_on_toolbar_clear(self) -> None:
        """Запрос очистки сбрасывает вывод и отправляет сообщение."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        posted: list[object] = []
        panel.post_message = posted.append
        with patch.object(panel, "reset"):
            panel.on_terminal_output_toolbar_clear_requested(
                TerminalOutputToolbar.ClearRequested()
            )
        assert any(isinstance(m, TerminalOutputPanel.OutputCleared) for m in posted)

    def test_on_toolbar_copy(self) -> None:
        """Запрос копирования отправляет OutputCopied."""
        vm = TerminalViewModel()
        vm.set_output("data")
        panel = TerminalOutputPanel(vm)
        posted: list[object] = []
        panel.post_message = posted.append
        panel.on_terminal_output_toolbar_copy_requested(
            TerminalOutputToolbar.CopyRequested()
        )
        copied = [m for m in posted if isinstance(m, TerminalOutputPanel.OutputCopied)]
        assert len(copied) == 1
        assert copied[0].text == "data"

    def test_on_toolbar_copy_empty_output(self) -> None:
        """Копирование пустого вывода не отправляет сообщение."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        posted: list[object] = []
        panel.post_message = posted.append
        panel.on_terminal_output_toolbar_copy_requested(
            TerminalOutputToolbar.CopyRequested()
        )
        assert len(posted) == 0

    def test_reset(self) -> None:
        """reset очищает ViewModel и content."""
        vm = TerminalViewModel()
        vm.set_output("data")
        panel = TerminalOutputPanel(vm)
        content_mock = MagicMock()
        panel._content = content_mock
        panel._exit_code = 5
        panel.reset()
        assert vm.output.value == ""
        assert panel._exit_code is None
        content_mock.clear.assert_called_once()

    def test_append_output(self) -> None:
        """append_output добавляет вывод через ViewModel."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        panel.append_output("chunk")
        assert vm.output.value == "chunk"

    def test_append_output_empty(self) -> None:
        """Пустой chunk игнорируется."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        panel.append_output("")
        assert vm.output.value == ""

    def test_set_output(self) -> None:
        """set_output устанавливает вывод через ViewModel."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        panel.set_output("full")
        assert vm.output.value == "full"

    def test_set_exit_code(self) -> None:
        """set_exit_code сохраняет код и обновляет content."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        content_mock = MagicMock()
        panel._content = content_mock
        panel.set_exit_code(7)
        assert panel._exit_code == 7
        content_mock.set_exit_code.assert_called_once_with(7)

    def test_set_title(self) -> None:
        """set_title обновляет заголовок toolbar."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        toolbar_mock = MagicMock()
        panel._toolbar = toolbar_mock
        panel.set_title("New")
        assert panel._title == "New"
        toolbar_mock.set_title.assert_called_once_with("New")

    def test_render_text_empty(self) -> None:
        """render_text для пустого вывода."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        text = panel.render_text()
        assert "Нет вывода" in text.plain

    def test_render_text_exit_only(self) -> None:
        """render_text показывает exit code при пустом выводе."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        panel._exit_code = 5
        text = panel.render_text()
        assert "Exit code: 5" in text.plain

    def test_render_text_with_output(self) -> None:
        """render_text для непустого вывода."""
        vm = TerminalViewModel()
        vm.set_output("hello")
        panel = TerminalOutputPanel(vm)
        panel._exit_code = 2
        text = panel.render_text()
        assert "hello" in text.plain
        assert "Exit code: 2" in text.plain

    def test_toolbar_visible_getter(self) -> None:
        """toolbar_visible возвращает текущее состояние."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm, show_toolbar=False)
        assert panel.toolbar_visible is False

    def test_toolbar_visible_setter_show(self) -> None:
        """Установка True убирает класс -no-toolbar."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm, show_toolbar=False)
        panel.toolbar_visible = True
        assert panel._show_toolbar is True
        assert not panel.has_class("-no-toolbar")

    def test_toolbar_visible_setter_hide(self) -> None:
        """Установка False добавляет класс -no-toolbar."""
        vm = TerminalViewModel()
        panel = TerminalOutputPanel(vm)
        panel.toolbar_visible = False
        assert panel._show_toolbar is False
        assert panel.has_class("-no-toolbar")

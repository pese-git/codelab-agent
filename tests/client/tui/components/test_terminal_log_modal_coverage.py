"""Тесты покрытия для TerminalLogModal компонента."""

from __future__ import annotations

from unittest.mock import MagicMock

from rich.text import Text
from textual.app import App

from codelab.client.presentation.terminal_log_view_model import TerminalLogViewModel
from codelab.client.tui.components.terminal_log_modal import TerminalLogModal


class TestTerminalLogModalCoverage:
    """Тесты для непокрытых строк terminal_log_modal.py."""

    async def test_compose_with_terminal_id(self) -> None:
        """compose рендерит заголовок с terminal_id."""
        vm = TerminalLogViewModel()
        modal = TerminalLogModal(
            terminal_log_vm=vm,
            title="Output",
            terminal_id="term-1",
            output=Text("line"),
        )

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.app.mount(modal)

            title = modal.query_one("#terminal-log-title")
            rendered = str(title.render())
            assert "Output" in rendered
            assert "term-1" in rendered

            content = modal.query_one("#terminal-log-content")
            assert "line" in str(content.render())

    async def test_on_entries_changed_updates_content(self) -> None:
        """Изменение записей лога обновляет виджет содержимого."""
        vm = TerminalLogViewModel()
        modal = TerminalLogModal(terminal_log_vm=vm)

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.app.mount(modal)

            modal._on_entries_changed(["first", "second"])

            content = modal.query_one("#terminal-log-content")
            rendered = str(content.render())
            assert "first" in rendered
            assert "second" in rendered

    async def test_action_close_hides_view_model(self) -> None:
        """action_close скрывает модальное окно через ViewModel."""
        vm = TerminalLogViewModel()
        vm.show()
        modal = TerminalLogModal(terminal_log_vm=vm)

        modal.action_close()

        assert vm.is_visible.value is False

    async def test_on_unmount_unsubscribes(self) -> None:
        """on_unmount вызывает все функции отписки."""
        vm = TerminalLogViewModel()
        modal = TerminalLogModal(terminal_log_vm=vm)

        unsub = MagicMock()
        modal._unsubscribers = [unsub]

        modal.on_unmount()

        unsub.assert_called_once()
        assert modal._unsubscribers == []

    async def test_on_unmount_suppresses_errors(self) -> None:
        """on_unmount не падает если отписка бросает исключение."""
        vm = TerminalLogViewModel()
        modal = TerminalLogModal(terminal_log_vm=vm)

        unsub = MagicMock(side_effect=RuntimeError("unsubscribe failed"))
        modal._unsubscribers = [unsub]

        modal.on_unmount()

        unsub.assert_called_once()
        assert modal._unsubscribers == []

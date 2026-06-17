"""Тесты покрытия для FileViewerModal компонента.

Проверяют непокрытые строки в:
- FileViewerModal
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from textual.app import App
from textual.widgets import Input, Static

from codelab.client.presentation.file_viewer_view_model import FileViewerViewModel
from codelab.client.tui.components.file_viewer import FileViewerModal


class TestFileViewerModal:
    """Тесты для FileViewerModal."""

    def test_init_with_path_and_content(self) -> None:
        """Инициализация с путем и содержимым обновляет ViewModel."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="print(1)")
        assert modal._file_path == "/tmp/test.py"
        assert modal._content == "print(1)"
        assert vm.file_path.value == Path("/tmp/test.py")
        assert vm.content.value == "print(1)"

    def test_init_without_path_uses_vm(self) -> None:
        """Инициализация без параметров использует состояние ViewModel."""
        vm = FileViewerViewModel()
        vm.show_file(Path("/tmp/main.py"), "x = 1")
        modal = FileViewerModal(file_viewer_vm=vm)
        assert modal._file_path == "/tmp/main.py"
        assert modal._content == "x = 1"

    async def test_compose_and_mount(self) -> None:
        """Компонент рендерится и монтируется."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            assert pilot.app.query_one("#file-viewer-title", Static)
            assert pilot.app.query_one("#file-viewer-search", Input)
            assert pilot.app.query_one("#file-viewer-search-status", Static)
            assert pilot.app.query_one("#file-viewer-content", Static)

    def test_on_mount_focuses_content(self) -> None:
        """При открытии фокус на контенте файла."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")
        content_mock = MagicMock()
        with patch.object(modal, "query_one", return_value=content_mock):
            modal.on_mount()
        content_mock.focus.assert_called_once()

    def test_action_close(self) -> None:
        """Закрытие окна скрывает ViewModel."""
        vm = FileViewerViewModel()
        vm.show_file(Path("/tmp/test.py"), "x = 1")
        modal = FileViewerModal(file_viewer_vm=vm)
        modal.action_close()
        assert vm.is_visible.value is False

    async def test_action_focus_search(self) -> None:
        """Ctrl+F переводит фокус в строку поиска."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            modal.action_focus_search()
            search = pilot.app.query_one("#file-viewer-search", Input)
            assert search.has_focus
            assert search.cursor_position == len(search.value)

    async def test_on_input_changed(self) -> None:
        """Изменение строки поиска пересчитывает совпадения."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(
            file_viewer_vm=vm,
            file_path="/tmp/test.py",
            content="hello\nworld\nhello",
        )

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            search = pilot.app.query_one("#file-viewer-search", Input)
            event = Input.Changed(input=search, value="hello")
            modal.on_input_changed(event)
            assert len(modal._match_lines) == 2
            assert modal._active_match_index == 0

    def test_on_input_changed_ignores_other_inputs(self) -> None:
        """Изменение другого Input игнорируется."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")
        other_mock = MagicMock()
        other_mock.id = "other"
        event = Input.Changed(input=other_mock, value="hello")
        modal.on_input_changed(event)
        assert modal._match_lines == []

    async def test_on_input_submitted(self) -> None:
        """Enter в поиске переходит к следующему совпадению."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(
            file_viewer_vm=vm,
            file_path="/tmp/test.py",
            content="hello\nworld\nhello",
        )

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            modal._match_lines = [1, 3]
            modal._active_match_index = 0
            search = pilot.app.query_one("#file-viewer-search", Input)
            event = Input.Submitted(input=search, value="hello")
            modal.on_input_submitted(event)
            assert modal._active_match_index == 1

    def test_on_input_submitted_ignores_other_inputs(self) -> None:
        """Submit другого Input игнорируется."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")
        other_mock = MagicMock()
        other_mock.id = "other"
        event = Input.Submitted(input=other_mock, value="hello")
        modal._match_lines = [1]
        modal._active_match_index = 0
        modal.on_input_submitted(event)
        assert modal._active_match_index == 0

    async def test_action_next_match(self) -> None:
        """F3 переходит к следующему совпадению."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(
            file_viewer_vm=vm,
            file_path="/tmp/test.py",
            content="hello\nworld\nhello",
        )

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test():
            modal._match_lines = [1, 3]
            modal._active_match_index = 0
            modal.action_next_match()
            assert modal._active_match_index == 1

    def test_action_next_match_no_matches(self) -> None:
        """F3 без совпадений не падает."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")
        status_mock = MagicMock()
        search_mock = MagicMock()
        search_mock.value = ""
        with patch.object(
            modal,
            "query_one",
            side_effect=lambda selector, expect_type: (
                status_mock if "search-status" in selector else search_mock
            ),
        ):
            modal.action_next_match()
        status_mock.update.assert_called_once_with("Поиск: введите текст")
        assert modal._active_match_index == -1

    async def test_action_previous_match(self) -> None:
        """Shift+F3 переходит к предыдущему совпадению."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(
            file_viewer_vm=vm,
            file_path="/tmp/test.py",
            content="hello\nworld\nhello",
        )

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test():
            modal._match_lines = [1, 3]
            modal._active_match_index = 0
            modal.action_previous_match()
            assert modal._active_match_index == 1

    def test_build_syntax(self) -> None:
        """Создание Syntax определяет язык по расширению."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")
        syntax = modal._build_syntax()
        assert syntax.lexer.name.lower() == "python"

    def test_build_syntax_text(self) -> None:
        """Создание Syntax без расширения использует text."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/Makefile", content="x = 1")
        syntax = modal._build_syntax()
        # Makefile имеет расширение '', поэтому language будет 'text'
        assert "text" in syntax.lexer.name.lower()

    async def test_rebuild_matches(self) -> None:
        """Пересчет совпадений обновляет статус."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(
            file_viewer_vm=vm,
            file_path="/tmp/test.py",
            content="hello\nworld\nhello again",
        )

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            modal._rebuild_matches("hello")
            assert modal._match_lines == [1, 3]
            assert modal._active_match_index == 0
            status = pilot.app.query_one("#file-viewer-search-status", Static)
            assert "1/2" in str(status.render())

    async def test_rebuild_matches_empty_query(self) -> None:
        """Пустой поиск сбрасывает совпадения."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="hello")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test():
            modal._match_lines = [1]
            modal._active_match_index = 0
            modal._rebuild_matches("  ")
            assert modal._match_lines == []
            assert modal._active_match_index == -1

    async def test_update_search_status_no_matches_empty_query(self) -> None:
        """Статус поиска при пустом запросе."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="hello")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            modal._update_search_status()
            status = pilot.app.query_one("#file-viewer-search-status", Static)
            assert "введите текст" in str(status.render())

    async def test_update_search_status_no_matches_non_empty_query(self) -> None:
        """Статус поиска при отсутствии совпадений."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="hello")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            search = pilot.app.query_one("#file-viewer-search", Input)
            search.value = "xyz"
            modal._update_search_status()
            status = pilot.app.query_one("#file-viewer-search-status", Static)
            assert "совпадений не найдено" in str(status.render())

    async def test_scroll_to_active_match(self) -> None:
        """Прокрутка к активному совпадению работает."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(
            file_viewer_vm=vm,
            file_path="/tmp/test.py",
            content="line0\nline1\nline2\nline3",
        )

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test():
            modal._match_lines = [3]
            modal._active_match_index = 0
            modal._scroll_to_active_match()
            # Проверяем, что метод отработал без ошибок
            assert modal._active_match_index == 0

    def test_on_file_path_changed_not_mounted(self) -> None:
        """Изменение пути без смонтированного компонента не падает."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm)
        modal._on_file_path_changed(Path("/tmp/new.py"))
        assert modal._file_path == "/tmp/new.py"

    async def test_on_file_path_changed_mounted(self) -> None:
        """Изменение пути обновляет заголовок в смонтированном компоненте."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            modal._on_file_path_changed(Path("/tmp/new.py"))
            title = pilot.app.query_one("#file-viewer-title", Static)
            assert "new.py" in str(title.render())

    def test_on_content_changed_not_mounted(self) -> None:
        """Изменение содержимого без смонтированного компонента не падает."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm)
        modal._on_content_changed("new content")
        assert modal._content == "new content"
        assert modal._match_lines == []
        assert modal._active_match_index == -1

    async def test_on_content_changed_mounted(self) -> None:
        """Изменение содержимого обновляет контент в смонтированном компоненте."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            search = pilot.app.query_one("#file-viewer-search", Input)
            search.value = "x"
            modal._on_content_changed("y = 2")
            assert modal._content == "y = 2"
            assert modal._match_lines == []
            assert search.value == ""

    def test_on_loading_changed(self) -> None:
        """Изменение статуса загрузки не вызывает ошибок."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm)
        modal._on_loading_changed(True)
        modal._on_loading_changed(False)

    def test_on_unmount_unsubscribes(self) -> None:
        """При удалении компонента отписываются обработчики."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm)
        unsubscriber = MagicMock()
        modal._unsubscribers = [unsubscriber]
        modal.on_unmount()
        unsubscriber.assert_called_once()
        assert modal._unsubscribers == []

    def test_subscribe_to_view_model(self) -> None:
        """Подписка на ViewModel добавляет unsubscribe-функции."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm)
        assert len(modal._unsubscribers) == 3
        # Проверяем, что подписки реагируют на изменения
        vm.file_path.value = Path("/tmp/a.py")
        assert modal._file_path == "/tmp/a.py"

        vm.content.value = "new"
        assert modal._content == "new"

    def test_on_file_path_changed_none(self) -> None:
        """Изменение пути на None игнорируется."""
        vm = FileViewerViewModel()
        modal = FileViewerModal(file_viewer_vm=vm, file_path="/tmp/test.py", content="x = 1")
        modal._on_file_path_changed(None)
        assert modal._file_path == "/tmp/test.py"

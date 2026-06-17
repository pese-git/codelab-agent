"""Тесты покрытия для FileChangePreview компонента.

Проверяют непокрытые строки в:
- DiffLine
- FileChangePreview
"""

from __future__ import annotations

from unittest.mock import patch

from textual.app import App
from textual.widgets import Collapsible, Static

from codelab.client.tui.components.file_change_preview import (
    CHANGE_SYMBOLS,
    DiffLine,
    FileChangePreview,
)


class TestDiffLine:
    """Тесты для DiffLine."""

    def test_init_defaults(self) -> None:
        """Инициализация со значениями по умолчанию."""
        line = DiffLine("content", "added")
        assert line.content == "content"
        assert line.change_type == "added"
        assert line.old_line_number is None
        assert line.new_line_number is None

    def test_init_with_line_numbers(self) -> None:
        """Инициализация с номерами строк."""
        line = DiffLine("content", "removed", old_line_number=5, new_line_number=6)
        assert line.old_line_number == 5
        assert line.new_line_number == 6


class TestChangeSymbols:
    """Тесты для CHANGE_SYMBOLS."""

    def test_all_types_present(self) -> None:
        """Все типы изменений имеют символы."""
        assert CHANGE_SYMBOLS["added"] == "+"
        assert CHANGE_SYMBOLS["removed"] == "-"
        assert CHANGE_SYMBOLS["unchanged"] == " "
        assert CHANGE_SYMBOLS["context"] == " "


class TestFileChangePreviewInit:
    """Тесты инициализации FileChangePreview."""

    def test_init_defaults(self) -> None:
        """Инициализация со значениями по умолчанию."""
        widget = FileChangePreview("/path/to/file.txt")
        assert widget.file_path == "/path/to/file.txt"
        assert widget._old_content == ""
        assert widget._new_content == ""
        assert widget._collapsed is False
        assert widget._max_lines == 50
        assert widget._show_line_numbers is True
        assert widget.added_count == 0
        assert widget.removed_count == 0

    def test_init_with_diff_lines(self) -> None:
        """Инициализация с готовыми diff строками."""
        lines = [
            DiffLine("added", "added", new_line_number=1),
            DiffLine("removed", "removed", old_line_number=1),
        ]
        widget = FileChangePreview(
            "/path/to/file.txt",
            diff_lines=lines,
            collapsed=True,
            max_lines=10,
            show_line_numbers=False,
        )
        assert widget._diff_lines is lines
        assert widget._collapsed is True
        assert widget._max_lines == 10
        assert widget._show_line_numbers is False
        assert widget.added_count == 1
        assert widget.removed_count == 1


class TestFileChangePreviewDiff:
    """Тесты вычисления diff в FileChangePreview."""

    def test_compute_diff_unchanged(self) -> None:
        """Общие строки помечаются как unchanged."""
        widget = FileChangePreview(
            "file.txt",
            old_content="line1\nline2",
            new_content="line1\nline2",
        )
        assert all(line.change_type == "unchanged" for line in widget._diff_lines)
        assert widget.added_count == 0
        assert widget.removed_count == 0

    def test_compute_diff_added(self) -> None:
        """Новые строки помечаются как added."""
        widget = FileChangePreview(
            "file.txt",
            old_content="line1",
            new_content="line1\nline2",
        )
        added = [line for line in widget._diff_lines if line.change_type == "added"]
        assert len(added) == 1
        assert added[0].content == "line2"
        assert widget.added_count == 1

    def test_compute_diff_removed(self) -> None:
        """Удалённые строки помечаются как removed."""
        widget = FileChangePreview(
            "file.txt",
            old_content="line1\nline2",
            new_content="line1",
        )
        removed = [line for line in widget._diff_lines if line.change_type == "removed"]
        assert len(removed) == 1
        assert removed[0].content == "line2"
        assert widget.removed_count == 1

    def test_compute_diff_empty_contents(self) -> None:
        """Пустые содержимые возвращают пустой diff."""
        widget = FileChangePreview("file.txt")
        assert widget._diff_lines == []


class TestFileChangePreviewCompose:
    """Тесты compose FileChangePreview."""

    async def test_compose_structure(self) -> None:
        """Компонент создаёт заголовок, статистику и содержимое."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = FileChangePreview(
                "file.txt",
                old_content="old",
                new_content="new",
            )
            await pilot.app.mount(widget)

            header = widget.query_one("#diff-header", Static)
            assert "file.txt" in str(header.render())
            stats = widget.query_one("#diff-stats", Static)
            assert "+1" in str(stats.render())
            assert "-1" in str(stats.render())

    async def test_compose_truncates_lines(self) -> None:
        """compose ограничивает количество отображаемых строк."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            diff_lines = [DiffLine(f"line {i}", "added", new_line_number=i) for i in range(5)]
            widget = FileChangePreview(
                "file.txt",
                diff_lines=diff_lines,
                max_lines=2,
            )
            await pilot.app.mount(widget)

            lines = widget.query(".diff-line")
            # 2 строки + сообщение о truncation
            assert len(lines) == 3


class TestFileChangePreviewRender:
    """Тесты рендеринга строк diff."""

    def test_render_diff_line_with_numbers(self) -> None:
        """Рендер строки с номерами."""
        widget = FileChangePreview("file.txt", show_line_numbers=True)
        line = DiffLine("content", "added", old_line_number=2, new_line_number=3)
        static = widget._render_diff_line(line)
        assert isinstance(static, Static)
        rendered = str(static.render())
        assert "2" in rendered
        assert "3" in rendered
        assert "+" in rendered
        assert "content" in rendered

    def test_render_diff_line_without_numbers(self) -> None:
        """Рендер строки без номеров."""
        widget = FileChangePreview("file.txt", show_line_numbers=False)
        line = DiffLine("content", "removed")
        static = widget._render_diff_line(line)
        rendered = str(static.render())
        assert "content" in rendered
        assert "-" in rendered

    def test_render_diff_line_unknown_type(self) -> None:
        """Неизвестный тип изменения использует пробел."""
        widget = FileChangePreview("file.txt", show_line_numbers=False)
        line = DiffLine("content", "context")  # type: ignore[arg-type]
        static = widget._render_diff_line(line)
        rendered = str(static.render())
        assert "content" in rendered


class TestFileChangePreviewSetDiff:
    """Тесты set_diff FileChangePreview."""

    async def test_set_diff_updates_state(self) -> None:
        """set_diff пересчитывает diff и обновляет счётчики."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = FileChangePreview("file.txt", old_content="a", new_content="a")
            await pilot.app.mount(widget)

            with patch.object(widget, "refresh") as mock_refresh:
                widget.set_diff("old", "new\ncontent")

            assert widget._old_content == "old"
            assert widget._new_content == "new\ncontent"
            assert widget.added_count == 2
            assert widget.removed_count == 1
            mock_refresh.assert_called_once()


class TestFileChangePreviewCollapse:
    """Тесты сворачивания/разворачивания FileChangePreview."""

    async def test_collapse(self) -> None:
        """collapse сворачивает Collapsible."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = FileChangePreview("file.txt")
            await pilot.app.mount(widget)

            widget.expand()
            assert widget._collapsed is False

            widget.collapse()
            assert widget._collapsed is True
            collapsible = widget.query_one(Collapsible)
            assert collapsible.collapsed is True

    async def test_expand(self) -> None:
        """expand разворачивает Collapsible."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = FileChangePreview("file.txt", collapsed=True)
            await pilot.app.mount(widget)

            widget.expand()
            assert widget._collapsed is False
            collapsible = widget.query_one(Collapsible)
            assert collapsible.collapsed is False

    async def test_toggle(self) -> None:
        """toggle переключает состояние."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = FileChangePreview("file.txt")
            await pilot.app.mount(widget)

            widget.toggle()
            assert widget._collapsed is True

            widget.toggle()
            assert widget._collapsed is False

    def test_collapse_without_collapsible(self) -> None:
        """collapse без смонтированного Collapsible не падает."""
        widget = FileChangePreview("file.txt")
        with patch.object(widget, "query_one", side_effect=Exception("not found")):
            widget.collapse()
        assert widget._collapsed is True

    def test_expand_without_collapsible(self) -> None:
        """expand без смонтированного Collapsible не падает."""
        widget = FileChangePreview("file.txt")
        with patch.object(widget, "query_one", side_effect=Exception("not found")):
            widget.expand()
        assert widget._collapsed is False

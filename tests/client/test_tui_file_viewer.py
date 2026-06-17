from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from codelab.client.presentation.file_viewer_view_model import FileViewerViewModel
from codelab.client.tui.components.file_viewer import FileViewerModal


class _FakeInput:
    """Минимальный double Input для тестов поиска в file viewer."""

    def __init__(self, value: str = "") -> None:
        self.value = value


class _FakeStatic:
    """Минимальный double Static для статуса и прокрутки контента."""

    def __init__(self) -> None:
        self.updated_text: str = ""
        self.scroll_y: int | None = None

    def update(self, text: str) -> None:
        """Сохраняет текст статуса для проверок."""

        self.updated_text = text

    def scroll_to(self, *, y: int, animate: bool = False) -> None:
        """Сохраняет позицию прокрутки в тестовом объекте."""

        _ = animate
        self.scroll_y = y


def test_file_viewer_search_rebuilds_matches_and_updates_status(monkeypatch: Any) -> None:
    mock_vm = MagicMock(spec=FileViewerViewModel)
    viewer = FileViewerModal(
        file_viewer_vm=mock_vm,
        file_path="/tmp/demo.py",
        content="alpha\nbeta\nalpha\n",
    )
    search_input = _FakeInput("alpha")
    status = _FakeStatic()
    content = _FakeStatic()

    def _query_one(selector: str, _expected_type: object) -> object:
        if selector == "#file-viewer-search":
            return search_input
        if selector == "#file-viewer-search-status":
            return status
        if selector == "#file-viewer-content":
            return content
        msg = f"Unexpected selector: {selector}"
        raise AssertionError(msg)

    monkeypatch.setattr(viewer, "query_one", _query_one)

    viewer._rebuild_matches("alpha")  # noqa: SLF001

    assert viewer._match_lines == [1, 3]  # noqa: SLF001
    assert viewer._active_match_index == 0  # noqa: SLF001
    assert status.updated_text == "Поиск: 1/2, строка 1"
    assert content.scroll_y == 0


def test_file_viewer_move_match_cycles_positions(monkeypatch: Any) -> None:
    mock_vm = MagicMock(spec=FileViewerViewModel)
    viewer = FileViewerModal(
        file_viewer_vm=mock_vm,
        file_path="/tmp/demo.py",
        content="alpha\nbeta\nalpha\n",
    )
    search_input = _FakeInput("alpha")
    status = _FakeStatic()
    content = _FakeStatic()

    def _query_one(selector: str, _expected_type: object) -> object:
        if selector == "#file-viewer-search":
            return search_input
        if selector == "#file-viewer-search-status":
            return status
        if selector == "#file-viewer-content":
            return content
        msg = f"Unexpected selector: {selector}"
        raise AssertionError(msg)

    monkeypatch.setattr(viewer, "query_one", _query_one)

    viewer._rebuild_matches("alpha")  # noqa: SLF001
    viewer._move_match(step=1)  # noqa: SLF001

    assert viewer._active_match_index == 1  # noqa: SLF001
    assert status.updated_text == "Поиск: 2/2, строка 3"
    assert content.scroll_y == 1

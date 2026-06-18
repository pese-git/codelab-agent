from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.app import App

from codelab.client.presentation.filesystem_view_model import FileSystemViewModel
from codelab.client.tui.components.file_tree import FileTree

pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'DirectoryTree.watch_path' was never awaited:RuntimeWarning"
)


class _TestApp(App):
    """Минимальный app для создания Textual контекста в тестах."""
    pass


@pytest.mark.asyncio
async def test_file_tree_updates_root_for_valid_directory(tmp_path: Path) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        mock_vm = MagicMock(spec=FileSystemViewModel)
        tree = FileTree(filesystem_vm=mock_vm, root_path=str(tmp_path))
        target = tmp_path / "workspace"
        target.mkdir()

        # Вызываем _on_root_path_changed напрямую, так как mock не синхронизирует
        tree._on_root_path_changed(target)

        assert tree.root_path == target


@pytest.mark.asyncio
async def test_file_tree_ignores_relative_root_path(tmp_path: Path) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        mock_vm = MagicMock(spec=FileSystemViewModel)
        tree = FileTree(filesystem_vm=mock_vm, root_path=str(tmp_path))
        initial_path = tree.root_path

        tree.set_root_path("relative/path")

        assert tree.root_path == initial_path


@pytest.mark.asyncio
async def test_file_tree_filters_hidden_paths() -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        mock_vm = MagicMock(spec=FileSystemViewModel)
        tree = FileTree(filesystem_vm=mock_vm, root_path=str(Path.cwd()))
        visible = Path("src")
        hidden = Path(".git")

        filtered = tree.filter_paths([visible, hidden])

        assert filtered == [visible]


@pytest.mark.asyncio
async def test_file_tree_refresh_tree_skips_when_not_mounted(tmp_path: Path) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        mock_vm = MagicMock(spec=FileSystemViewModel)
        tree = FileTree(filesystem_vm=mock_vm, root_path=str(tmp_path))

        tree.refresh_tree()

        assert tree.root_path == tmp_path


@pytest.mark.asyncio
async def test_file_tree_marks_changed_file_and_parent_directory(tmp_path: Path) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        mock_vm = MagicMock(spec=FileSystemViewModel)
        tree = FileTree(filesystem_vm=mock_vm, root_path=str(tmp_path))
        changed_file = tmp_path / "src" / "main.py"
        changed_file.parent.mkdir(parents=True)
        changed_file.write_text("print('ok')\n", encoding="utf-8")

        tree.mark_changed(changed_file)

        assert tree.is_changed(changed_file) is True
        assert tree.is_changed(changed_file.parent) is True

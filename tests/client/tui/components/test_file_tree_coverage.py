"""Тесты покрытия для FileTree компонента.

Проверяют непокрытые строки в:
- FileTree
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.style import Style
from rich.text import Text
from textual.app import App
from textual.widgets import DirectoryTree

from codelab.client.presentation.observable import Observable
from codelab.client.tui.components.file_tree import FileTree


class FakeFileSystemViewModel:
    """Фейковый FileSystemViewModel для изоляции тестов FileTree."""

    def __init__(self) -> None:
        self.root_path: Observable[Path | None] = Observable(None)
        self.selected_path: Observable[Path | None] = Observable(None)
        self.is_loading: Observable[bool] = Observable(False)
        self._set_root_calls: list[Path] = []
        self._select_path_calls: list[Path | None] = []

    def set_root(self, path: Path) -> None:
        """Устанавливает корневой путь и уведомляет observers."""
        self._set_root_calls.append(path)
        self.root_path.value = path

    def select_path(self, path: Path | None) -> None:
        """Выбирает путь и уведомляет observers."""
        self._select_path_calls.append(path)
        self.selected_path.value = path


class TestFileTree:
    """Тесты для FileTree."""

    def test_init_with_root_path(self, tmp_path: Path) -> None:
        """Инициализация с явным root_path обновляет ViewModel."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        assert tree._root_path == tmp_path
        assert tree.root_path == tmp_path
        assert vm._set_root_calls == [tmp_path]
        assert len(tree._unsubscribers) == 3

    def test_init_without_root_path_uses_vm_value(self, tmp_path: Path) -> None:
        """При отсутствии root_path используется значение из ViewModel."""
        vm = FakeFileSystemViewModel()
        vm.root_path.value = tmp_path
        tree = FileTree(filesystem_vm=vm)

        assert tree._root_path == tmp_path
        assert vm._set_root_calls == []

    def test_init_without_root_path_uses_home(self) -> None:
        """Если ViewModel не содержит root_path, используется домашняя директория."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm)

        assert tree._root_path == Path.home()

    def test_on_root_path_changed_ignores_none(self, tmp_path: Path) -> None:
        """Обработчик игнорирует None."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree._on_root_path_changed(None)
        assert tree._root_path == tmp_path

    def test_on_root_path_changed_ignores_relative_path(self, tmp_path: Path) -> None:
        """Обработчик игнорирует относительные пути."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree._on_root_path_changed(Path("relative/path"))
        assert tree._root_path == tmp_path

    def test_on_root_path_changed_ignores_nonexistent_path(self, tmp_path: Path) -> None:
        """Обработчик игнорирует несуществующий путь."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree._on_root_path_changed(tmp_path / "missing")
        assert tree._root_path == tmp_path

    def test_on_root_path_changed_ignores_file_path(self, tmp_path: Path) -> None:
        """Обработчик игнорирует путь к файлу."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        file_path = tmp_path / "file.txt"
        file_path.write_text("data")

        tree._on_root_path_changed(file_path)
        assert tree._root_path == tmp_path

    def test_on_root_path_changed_unmounted(self, tmp_path: Path) -> None:
        """Обработчик обновляет путь даже если компонент не смонтирован."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        new_dir = tmp_path / "other"
        new_dir.mkdir()

        tree._on_root_path_changed(new_dir)

        assert tree._root_path == new_dir
        assert tree._changed_paths == set()

    async def test_on_root_path_changed_mounted(self, tmp_path: Path) -> None:
        """После монтирования смена root обновляет дерево."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = FakeFileSystemViewModel()
            tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
            await pilot.app.mount(tree)

            new_dir = tmp_path / "mounted_dir"
            new_dir.mkdir()
            vm.set_root(new_dir)
            await pilot.pause()

            assert tree._root_path == new_dir
            assert tree.path == new_dir

    def test_on_selected_path_changed_passes(self, tmp_path: Path) -> None:
        """Обработчик выбранного пути не вызывает ошибок."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree._on_selected_path_changed(tmp_path / "selected.txt")

    def test_on_loading_changed_passes(self, tmp_path: Path) -> None:
        """Обработчик статуса загрузки не вызывает ошибок."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree._on_loading_changed(True)
        tree._on_loading_changed(False)

    def test_unsubscribe_from_view_model(self, tmp_path: Path) -> None:
        """Отписка очищает список подписчиков и отключает обработчики."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        new_dir = tmp_path / "after_unsub"
        new_dir.mkdir()

        tree._unsubscribe_from_view_model()
        vm.set_root(new_dir)

        assert tree._root_path == tmp_path
        assert tree._unsubscribers == []

    def test_set_root_path_ignores_relative(self, tmp_path: Path) -> None:
        """set_root_path игнорирует относительный путь."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree.set_root_path("relative/path")
        assert vm._set_root_calls == [tmp_path]

    def test_set_root_path_ignores_nonexistent(self, tmp_path: Path) -> None:
        """set_root_path игнорирует несуществующий путь."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree.set_root_path(str(tmp_path / "missing"))
        assert vm._set_root_calls == [tmp_path]

    def test_set_root_path_ignores_file(self, tmp_path: Path) -> None:
        """set_root_path игнорирует путь к файлу."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        file_path = tmp_path / "file.txt"
        file_path.write_text("data")

        tree.set_root_path(str(file_path))
        assert vm._set_root_calls == [tmp_path]

    def test_set_root_path_valid(self, tmp_path: Path) -> None:
        """set_root_path обновляет путь через ViewModel."""
        initial = tmp_path / "initial"
        initial.mkdir()
        vm = FakeFileSystemViewModel()
        vm.root_path.value = initial
        tree = FileTree(filesystem_vm=vm)

        tree.set_root_path(str(tmp_path))

        assert tmp_path in vm._set_root_calls
        assert tree._root_path == tmp_path

    def test_select_file(self, tmp_path: Path) -> None:
        """select_file делегирует выбор в ViewModel."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        target = tmp_path / "target.txt"

        tree.select_file(target)

        assert vm._select_path_calls == [target]

    def test_refresh_tree_unmounted(self, tmp_path: Path) -> None:
        """refresh_tree безопасен до монтирования."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        tree.refresh_tree()

    async def test_refresh_tree_mounted(self, tmp_path: Path) -> None:
        """refresh_tree вызывает reload после монтирования."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = FakeFileSystemViewModel()
            tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
            await pilot.app.mount(tree)

            with patch.object(tree, "reload") as mock_reload:
                tree.refresh_tree()

            mock_reload.assert_called_once()

    def test_mark_changed_and_is_changed(self, tmp_path: Path) -> None:
        """mark_changed помечает файл и его родительскую директорию."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        file_path = tmp_path / "changed.txt"
        file_path.write_text("data")

        tree.mark_changed(file_path)

        assert tree.is_changed(file_path) is True
        assert tree.is_changed(tmp_path) is True
        assert tree._path_has_changes(file_path) is True
        assert tree._path_has_changes(tmp_path / "other.txt") is False

    def test_path_has_changes_with_nested_file(self, tmp_path: Path) -> None:
        """Изменения во вложенном файле обнаруживаются у родительской директории."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        nested = subdir / "nested.txt"
        nested.write_text("data")

        tree.mark_changed(nested)

        assert tree._path_has_changes(subdir) is True
        assert tree._path_has_changes(tmp_path) is True
        assert tree._path_has_changes(tmp_path / "elsewhere.txt") is False

    def test_on_directory_tree_file_selected_ignores_none(self, tmp_path: Path) -> None:
        """Выбор с пустым путем игнорируется."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        event = MagicMock(path=None)

        tree.on_directory_tree_file_selected(event)
        assert vm._select_path_calls == []

    def test_on_directory_tree_file_selected_ignores_directory(self, tmp_path: Path) -> None:
        """Выбор директории игнорируется."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        event = MagicMock(path=str(subdir))

        tree.on_directory_tree_file_selected(event)
        assert vm._select_path_calls == []

    def test_on_directory_tree_file_selected_posts_request(self, tmp_path: Path) -> None:
        """Выбор файла обновляет VM и отправляет FileOpenRequested."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        file_path = tmp_path / "file.txt"
        file_path.write_text("data")
        event = MagicMock(path=str(file_path))

        posted: list[object] = []
        tree.post_message = posted.append
        tree.on_directory_tree_file_selected(event)

        assert vm._select_path_calls == [file_path]
        assert len(posted) == 1
        assert isinstance(posted[0], FileTree.FileOpenRequested)
        assert posted[0].path == file_path

    def test_render_label_with_changed_path(self, tmp_path: Path) -> None:
        """render_label добавляет звездочку к измененному пути."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        file_path = tmp_path / "changed.txt"
        file_path.write_text("data")
        tree.mark_changed(file_path)

        node = MagicMock()
        node.data.path = file_path

        with patch.object(DirectoryTree, "render_label", return_value=Text("node")):
            label = tree.render_label(node, Style(), Style())

        assert str(label).endswith(" *")

    def test_render_label_without_changes(self, tmp_path: Path) -> None:
        """render_label не добавляет звездочку если изменений нет."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        file_path = tmp_path / "unchanged.txt"
        file_path.write_text("data")

        node = MagicMock()
        node.data.path = file_path

        with patch.object(DirectoryTree, "render_label", return_value=Text("node")):
            label = tree.render_label(node, Style(), Style())

        assert str(label) == "node"

    def test_render_label_with_none_data(self, tmp_path: Path) -> None:
        """render_label возвращает базовую метку если data отсутствует."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        node = MagicMock()
        node.data = None

        with patch.object(DirectoryTree, "render_label", return_value=Text("node")):
            label = tree.render_label(node, Style(), Style())

        assert str(label) == "node"

    def test_filter_paths_hides_dot_files(self, tmp_path: Path) -> None:
        """filter_paths скрывает dot-файлы и dot-директории."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))
        paths = [Path(".hidden"), Path("visible"), Path(".git")]

        filtered = list(tree.filter_paths(paths))

        assert filtered == [Path("visible")]

    def test_remove_unsubscribes_and_calls_super(self, tmp_path: Path) -> None:
        """remove отписывается от ViewModel и делегирует удаление базовому классу."""
        vm = FakeFileSystemViewModel()
        tree = FileTree(filesystem_vm=vm, root_path=str(tmp_path))

        with patch.object(DirectoryTree, "remove", return_value=MagicMock()) as super_remove:
            tree.remove()

        super_remove.assert_called_once()
        assert tree._unsubscribers == []

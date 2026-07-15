"""Тесты для нормализации путей в ACPContextGatherer.

Покрывают:
- Нормализацию абсолютных путей в относительные
- Нормализацию путей с префиксами ./
- Нормализацию путей с backslash
- Матчинг target_modules с project_files
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.file_matching import (
    filter_paths,
    is_binary,
    normalize_path,
)
from codelab.server.agent.context.gatherer import ACPContextGatherer


@pytest.fixture
def dependency_graph() -> RegexDependencyGraph:
    """Создаёт тестовый граф зависимостей."""
    return RegexDependencyGraph()


@pytest.fixture
def gatherer(dependency_graph: RegexDependencyGraph) -> ACPContextGatherer:
    """Создаёт тестовый gatherer."""
    return ACPContextGatherer(
        tool_registry=MagicMock(),
        dependency_graph=dependency_graph,
        session_id="test_session",
    )


class TestNormalizePath:
    """Тесты для _normalize_path."""

    def test_relative_path_unchanged(self, gatherer: ACPContextGatherer) -> None:
        """Относительный путь не меняется."""
        result = normalize_path("lib/main.dart")
        assert result == "lib/main.dart"

    def test_dot_slash_prefix_removed(self, gatherer: ACPContextGatherer) -> None:
        """Префикс ./ удаляется."""
        result = normalize_path("./lib/main.dart")
        assert result == "lib/main.dart"

    def test_backslash_converted(self, gatherer: ACPContextGatherer) -> None:
        """Backslash конвертируется в forward slash."""
        result = normalize_path("lib\\main.dart")
        assert result == "lib/main.dart"

    def test_absolute_path_with_project_root(self, gatherer: ACPContextGatherer) -> None:
        """Абсолютный путь нормализуется относительно project_root."""
        result = normalize_path(
            "/Users/user/project/lib/main.dart",
            project_root="/Users/user/project",
        )
        assert result == "lib/main.dart"

    def test_absolute_path_without_project_root(self, gatherer: ACPContextGatherer) -> None:
        """Абсолютный путь без project_root берёт последние компоненты."""
        result = normalize_path("/Users/user/project/lib/main.dart")
        # Берёт последние 2 компонента: lib/main.dart
        assert result == "lib/main.dart"

    def test_absolute_path_single_component(self, gatherer: ACPContextGatherer) -> None:
        """Абсолютный путь с одним компонентом."""
        result = normalize_path("/main.dart")
        assert result == "main.dart"

    def test_empty_path(self, gatherer: ACPContextGatherer) -> None:
        """Пустой путь возвращается как пустая строка."""
        result = normalize_path("")
        assert result == ""

    def test_path_with_trailing_slash(self, gatherer: ACPContextGatherer) -> None:
        """Путь с trailing slash нормализуется."""
        result = normalize_path("lib/main.dart/")
        # normalize_path не убирает trailing slash, это делает _filter_paths
        assert result == "lib/main.dart/"


class TestFilterPaths:
    """Тесты для _filter_paths."""

    def test_filters_ignore_dirs(self, gatherer: ACPContextGatherer) -> None:
        """Фильтрует директории из IGNORE_DIRS."""
        paths = [
            "lib/main.dart",
            ".git/config",
            "node_modules/package.json",
            ".venv/lib/python3.12/site.py",
        ]
        result = filter_paths(paths)
        assert result == ["lib/main.dart"]

    def test_removes_dot_slash_prefix(self, gatherer: ACPContextGatherer) -> None:
        """Удаляет префикс ./."""
        paths = ["./lib/main.dart", "./src/app.py"]
        result = filter_paths(paths)
        assert result == ["lib/main.dart", "src/app.py"]

    def test_filters_empty_paths(self, gatherer: ACPContextGatherer) -> None:
        """Фильтрует пустые пути."""
        paths = ["lib/main.dart", "", ".", "./"]
        result = filter_paths(paths)
        assert result == ["lib/main.dart"]

    def test_filters_codegraph_dir(self) -> None:
        """Отсекает служебную директорию индекса codegraph (P2-20)."""
        paths = [
            "src/main.py",
            ".codegraph/codegraph.db",
            ".codegraph/codegraph.db-shm",
        ]
        assert filter_paths(paths) == ["src/main.py"]


class TestIsBinary:
    """is_binary распознаёт бинарные файлы, включая SQLite-сайдкары (P2-20)."""

    @pytest.mark.parametrize(
        "path",
        [
            "codegraph.db-shm",
            "codegraph.db-wal",
            "codegraph.db-journal",
            "index.sqlite-shm",
            "index.sqlite-wal",
            ".codegraph/codegraph.db-shm",
            "data.db",
            "data.sqlite3",
        ],
    )
    def test_sqlite_sidecars_are_binary(self, path: str) -> None:
        assert is_binary(path) is True

    @pytest.mark.parametrize("path", ["main.py", "lib/app.dart", "notes.md"])
    def test_source_files_not_binary(self, path: str) -> None:
        assert is_binary(path) is False


class TestTargetModulesMatching:
    """Тесты для матчинга target_modules с project_files."""

    def test_relative_target_matches_project_files(self, gatherer: ACPContextGatherer) -> None:
        """Относительный target_module матчится с project_files."""
        # Симулируем project_files из _list_project_files
        project_files = ["lib/main.dart", "lib/weather_service.dart"]

        target_module = "lib/main.dart"
        normalized = normalize_path(target_module)

        assert normalized in project_files

    def test_absolute_target_matches_project_files(self, gatherer: ACPContextGatherer) -> None:
        """Абсолютный target_module нормализуется и матчится."""
        project_files = ["lib/main.dart", "lib/weather_service.dart"]
        project_root = "/Users/user/project"

        target_module = "/Users/user/project/lib/main.dart"
        normalized = normalize_path(target_module, project_root)

        assert normalized in project_files

    def test_dot_slash_target_matches_project_files(self, gatherer: ACPContextGatherer) -> None:
        """Target с ./ матчится после нормализации."""
        project_files = ["lib/main.dart", "lib/weather_service.dart"]

        target_module = "./lib/main.dart"
        normalized = normalize_path(target_module)

        assert normalized in project_files

    def test_backslash_target_matches_project_files(self, gatherer: ACPContextGatherer) -> None:
        """Target с backslash матчится после нормализации."""
        project_files = ["lib/main.dart", "lib/weather_service.dart"]

        target_module = "lib\\main.dart"
        normalized = normalize_path(target_module)

        assert normalized in project_files

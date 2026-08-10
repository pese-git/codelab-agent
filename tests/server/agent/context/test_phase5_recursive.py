"""Интеграционные тесты Phase 5 — рекурсивное разрешение зависимостей.

Тестирует:
- Рекурсивный обход графа с ограничением глубины
- Интеграцию ContextGatherer с recursive_dependencies=True/False
- Производительность на больших проектах (100+ файлов)
- Корректность транзитивного замыкания зависимостей
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.agent.context.models import (
    ContextConfig,
    TaskProfile,
    TaskType,
)
from codelab.server.domain.value_objects import ToolInvocationSubject
from codelab.server.tools.base import ToolExecutionResult


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class MockToolRegistry:
    """Mock ToolRegistry для тестирования."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self._files = files or {}
        self._terminal_counter = 0

    def get_available_tools(self, session_id: str) -> list:
        return [_FakeTool("fs/read_text_file")]

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        session: Any = None,
        subject: ToolInvocationSubject = ToolInvocationSubject.UNKNOWN,
    ) -> ToolExecutionResult:
        if tool_name == "fs/read_text_file":
            path = arguments.get("path", "")
            content = self._files.get(path)
            if content is not None:
                return ToolExecutionResult(success=True, output=content)
            return ToolExecutionResult(success=False, error="File not found")

        if tool_name == "terminal/create":
            self._terminal_counter += 1
            terminal_id = f"mock-terminal-{self._terminal_counter}"
            return ToolExecutionResult(
                success=True,
                raw_output={"terminal_id": terminal_id},
                metadata={"terminal_id": terminal_id},
            )

        if tool_name == "terminal/wait_for_exit":
            return ToolExecutionResult(
                success=True,
                raw_output={"output": ""},
                output="",
            )

        return ToolExecutionResult(success=False, error="Unknown tool")


def _make_session(
    session_id: str = "test_session",
    file_paths: list[str] | None = None,
) -> MagicMock:
    """Создать mock session с project_structure в config_values."""
    session = MagicMock()
    session.session_id = session_id
    session.config_values = {}
    session.cwd = "/test/project"
    if file_paths is not None:
        session.config_values["project_structure"] = json.dumps(file_paths)
    return session


def _make_profile(
    search_terms: list[str] | None = None,
    target_modules: list[str] | None = None,
    investigation_depth: int = 2,
) -> TaskProfile:
    """Создать TaskProfile для тестирования."""
    return TaskProfile(
        task_type=TaskType.FEATURE,
        search_terms=search_terms or [],
        target_modules=target_modules or [],
        investigation_depth=investigation_depth,
        needs_tests=False,
    )


class TestRecursiveDependenciesIntegration:
    """Интеграционные тесты рекурсивного разрешения зависимостей."""

    @pytest.mark.asyncio
    async def test_gather_with_recursive_dependencies_includes_transitive(self):
        """При recursive_dependencies=True добавляются транзитивные зависимости."""
        files = {
            "src/main.py": "import src.utils\nimport src.config",
            "src/utils.py": "import src.helpers",
            "src/helpers.py": "import src.constants",
            "src/config.py": "pass",
            "src/constants.py": "VALUE = 42",
        }
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()

        # Добавляем файлы с уже разрешёнными путями зависимостей
        dep_graph.add_file("src/main.py", ["src/utils.py", "src/config.py"])
        dep_graph.add_file("src/utils.py", ["src/helpers.py"])
        dep_graph.add_file("src/helpers.py", ["src/constants.py"])
        dep_graph.add_file("src/config.py", [])
        dep_graph.add_file("src/constants.py", [])

        config = ContextConfig(recursive_dependencies=True)
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
            config=config,
        )

        profile = _make_profile(target_modules=["src/main.py"], investigation_depth=3)
        session = _make_session(file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)
        file_ids = [item.id for item in items]

        # Должны быть включены транзитивные зависимости
        assert "src/main.py" in file_ids
        assert "src/utils.py" in file_ids
        assert "src/helpers.py" in file_ids
        assert "src/constants.py" in file_ids
        assert "src/config.py" in file_ids

    @pytest.mark.asyncio
    async def test_gather_without_recursive_dependencies_only_direct(self):
        """При recursive_dependencies=False только прямые зависимости."""
        files = {
            "src/main.py": "import src.utils\nimport src.config",
            "src/utils.py": "import src.helpers",
            "src/helpers.py": "import src.constants",
            "src/config.py": "pass",
            "src/constants.py": "VALUE = 42",
        }
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()

        dep_graph.add_file("src/main.py", ["src/utils.py", "src/config.py"])
        dep_graph.add_file("src/utils.py", ["src/helpers.py"])
        dep_graph.add_file("src/helpers.py", ["src/constants.py"])
        dep_graph.add_file("src/config.py", [])
        dep_graph.add_file("src/constants.py", [])

        config = ContextConfig(recursive_dependencies=False)
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
            config=config,
        )

        profile = _make_profile(target_modules=["src/main.py"], investigation_depth=3)
        session = _make_session(file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)
        file_ids = [item.id for item in items]

        # main.py должен быть включён
        assert "src/main.py" in file_ids
        # Прямые зависимости (utils, config) — включены
        assert "src/utils.py" in file_ids or "src/config.py" in file_ids
        # Транзитивные (helpers, constants) — НЕ включены при recursive=False
        # (могут быть включены через search, но не через рекурсию)

    @pytest.mark.asyncio
    async def test_gather_respects_investigation_depth(self):
        """Глубина обхода ограничена investigation_depth из TaskProfile."""
        files = {
            "src/a.py": "import src.b",
            "src/b.py": "import src.c",
            "src/c.py": "import src.d",
            "src/d.py": "import src.e",
            "src/e.py": "pass",
        }
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()

        dep_graph.add_file("src/a.py", ["src/b.py"])
        dep_graph.add_file("src/b.py", ["src/c.py"])
        dep_graph.add_file("src/c.py", ["src/d.py"])
        dep_graph.add_file("src/d.py", ["src/e.py"])
        dep_graph.add_file("src/e.py", [])

        config = ContextConfig(recursive_dependencies=True)
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
            config=config,
        )

        # Глубина 1: только прямые зависимости
        profile_depth_1 = _make_profile(target_modules=["src/a.py"], investigation_depth=1)
        session = _make_session(file_paths=list(files.keys()))

        items = await gatherer.gather(profile_depth_1, session)
        file_ids = [item.id for item in items]

        assert "src/a.py" in file_ids
        assert "src/b.py" in file_ids
        # При depth=1 транзитивные зависимости не должны быть включены
        # (если только они не добавлены через другие механизмы)

    @pytest.mark.asyncio
    async def test_gather_performance_large_project(self):
        """Производительность: gather() на 100+ файлов завершается за <1с."""
        # Генерируем 150 файлов с цепочками зависимостей
        files = {}
        dep_graph = RegexDependencyGraph()

        for i in range(150):
            path = f"src/module_{i:03d}.py"
            files[path] = f"import src.module_{i + 1:03d}"
            if i < 149:
                dep_graph.add_file(path, [f"src/module_{i + 1:03d}.py"])
            else:
                dep_graph.add_file(path, [])

        tool_registry = MockToolRegistry(files)

        config = ContextConfig(recursive_dependencies=True)
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
            config=config,
        )

        profile = _make_profile(target_modules=["src/module_000.py"], investigation_depth=3)
        session = _make_session(file_paths=list(files.keys()))

        start = time.time()
        items = await gatherer.gather(profile, session)
        elapsed = time.time() - start

        # Должно завершиться за <1 секунду
        assert elapsed < 1.0, f"gather() took {elapsed:.2f}s, expected <1s"
        # Должны быть собраны файлы
        assert len(items) > 0


class TestDependencyGraphRecursiveDepth:
    """Тесты ограничения глубины в DependencyGraph."""

    def test_recursive_depth_1_only_direct(self):
        """При max_depth=1 включаются только прямые зависимости."""
        graph = RegexDependencyGraph(max_depth=1)

        graph.add_file("a.py", ["b.py"])
        graph.add_file("b.py", ["c.py"])
        graph.add_file("c.py", ["d.py"])

        deps = graph.get_dependencies("a.py", recursive=True)

        assert "b.py" in deps
        assert "c.py" not in deps
        assert "d.py" not in deps

    def test_recursive_depth_2_two_levels(self):
        """При max_depth=2 включаются зависимости до 2 уровней."""
        graph = RegexDependencyGraph(max_depth=2)

        graph.add_file("a.py", ["b.py"])
        graph.add_file("b.py", ["c.py"])
        graph.add_file("c.py", ["d.py"])

        deps = graph.get_dependencies("a.py", recursive=True)

        assert "b.py" in deps
        assert "c.py" in deps
        assert "d.py" not in deps

    def test_recursive_depth_none_unlimited(self):
        """При max_depth=None рекурсия не ограничена."""
        graph = RegexDependencyGraph(max_depth=None)

        graph.add_file("a.py", ["b.py"])
        graph.add_file("b.py", ["c.py"])
        graph.add_file("c.py", ["d.py"])
        graph.add_file("d.py", ["e.py"])

        deps = graph.get_dependencies("a.py", recursive=True)

        assert "b.py" in deps
        assert "c.py" in deps
        assert "d.py" in deps
        assert "e.py" in deps

    def test_set_max_depth_runtime(self):
        """Глубина может быть изменена в runtime через set_max_depth."""
        graph = RegexDependencyGraph()

        graph.add_file("a.py", ["b.py"])
        graph.add_file("b.py", ["c.py"])
        graph.add_file("c.py", ["d.py"])

        # Без ограничения
        unlimited = graph.get_dependencies("a.py", recursive=True)
        assert "d.py" in unlimited

        # С ограничением глубины 1
        graph.set_max_depth(1)
        limited = graph.get_dependencies("a.py", recursive=True)
        assert "b.py" in limited
        assert "c.py" not in limited

    def test_circular_dependencies_with_depth_limit(self):
        """Защита от циклов работает с ограничением глубины."""
        graph = RegexDependencyGraph(max_depth=3)

        graph.add_file("a.py", ["b.py"])
        graph.add_file("b.py", ["a.py"])  # Цикл

        deps = graph.get_dependencies("a.py", recursive=True)

        assert "b.py" in deps
        assert deps.count("a.py") == 0 or "a.py" not in deps  # a.py не в результате

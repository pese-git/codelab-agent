"""Тесты для ProjectStructureDecorator.

Тестирует автоматическое извлечение структуры проекта из terminal output.
Decorator перехватывает terminal/create (сохраняет terminal_id → command)
и terminal/wait_for_exit (парсит output и сохраняет структуру).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators.project_structure import (
    ProjectStructureDecorator,
)


class TestProjectStructureDecorator:
    """Тесты для ProjectStructureDecorator."""

    def _make_session(self) -> MagicMock:
        """Создать mock session."""
        session = MagicMock()
        session.session_id = "test_session"
        session.config_values = {}
        return session

    def _make_executor(self, result: ToolExecutionResult) -> AsyncMock:
        """Создать mock executor."""
        executor = AsyncMock()
        executor.execute = AsyncMock(return_value=result)
        return executor

    @pytest.mark.asyncio
    async def test_tracks_terminal_create(self):
        """Decorator должен сохранять terminal_id → command при terminal/create."""
        result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        executor = self._make_executor(result)
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()
        arguments = {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        }

        await decorator.execute(session, arguments)

        assert "term_1" in decorator._terminal_commands
        assert decorator._terminal_commands["term_1"] == "find . -type f"

    @pytest.mark.asyncio
    async def test_saves_structure_on_terminal_wait(self):
        """Decorator должен сохранять структуру при terminal/wait_for_exit."""
        create_result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        wait_result = ToolExecutionResult(
            success=True,
            output="./src/main.py\n./src/utils.py\n./README.md\n",
            metadata={"terminal_id": "term_1", "exit_code": 0},
        )

        executor = AsyncMock()
        executor.execute = AsyncMock(side_effect=[create_result, wait_result])
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()

        # 1. terminal/create
        await decorator.execute(session, {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        })

        # 2. terminal/wait_for_exit
        await decorator.execute(session, {
            "tool_name": "terminal/wait_for_exit",
            "terminal_id": "term_1",
        })

        assert "project_structure" in session.config_values
        files = json.loads(session.config_values["project_structure"])
        assert "src/main.py" in files
        assert "src/utils.py" in files
        assert "README.md" in files

    @pytest.mark.asyncio
    async def test_extracts_base_command(self):
        """Decorator должен извлекать базовую команду из 'ls -la'."""
        result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "ls -la lib"},
            raw_output={"terminal_id": "term_1"},
        )
        executor = self._make_executor(result)
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()
        arguments = {
            "tool_name": "terminal/create",
            "command": "ls -la lib",
        }

        await decorator.execute(session, arguments)

        assert "term_1" in decorator._terminal_commands
        assert decorator._terminal_commands["term_1"] == "ls -la lib"

    @pytest.mark.asyncio
    async def test_ignores_non_structure_commands(self):
        """Decorator не должен отслеживать не-structure команды."""
        result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "npm install"},
            raw_output={"terminal_id": "term_1"},
        )
        executor = self._make_executor(result)
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()
        arguments = {
            "tool_name": "terminal/create",
            "command": "npm install",
        }

        await decorator.execute(session, arguments)

        assert "term_1" not in decorator._terminal_commands

    @pytest.mark.asyncio
    async def test_filters_ignored_dirs(self):
        """Decorator должен фильтровать мусорные папки."""
        create_result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        wait_result = ToolExecutionResult(
            success=True,
            output=(
                "./src/main.py\n"
                "./.git/config\n"
                "./node_modules/pkg/index.js\n"
                "./__pycache__/main.cpython-312.pyc\n"
                "./src/utils.py\n"
            ),
            metadata={"terminal_id": "term_1", "exit_code": 0},
        )

        executor = AsyncMock()
        executor.execute = AsyncMock(side_effect=[create_result, wait_result])
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()

        await decorator.execute(session, {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        })

        await decorator.execute(session, {
            "tool_name": "terminal/wait_for_exit",
            "terminal_id": "term_1",
        })

        files = json.loads(session.config_values["project_structure"])
        assert "src/main.py" in files
        assert "src/utils.py" in files
        assert not any(".git" in f for f in files)
        assert not any("node_modules" in f for f in files)
        assert not any("__pycache__" in f for f in files)

    @pytest.mark.asyncio
    async def test_skips_unknown_terminal_id(self):
        """Decorator не должен обрабатывать неизвестные terminal_id."""
        result = ToolExecutionResult(
            success=True,
            output="./src/main.py\n",
            metadata={"terminal_id": "unknown_terminal", "exit_code": 0},
        )
        executor = self._make_executor(result)
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()
        arguments = {
            "tool_name": "terminal/wait_for_exit",
            "terminal_id": "unknown_terminal",
        }

        await decorator.execute(session, arguments)

        assert "project_structure" not in session.config_values

    @pytest.mark.asyncio
    async def test_skips_empty_output(self):
        """Decorator не должен сохранять пустой output."""
        create_result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        wait_result = ToolExecutionResult(
            success=True,
            output="",
            metadata={"terminal_id": "term_1", "exit_code": 0},
        )

        executor = AsyncMock()
        executor.execute = AsyncMock(side_effect=[create_result, wait_result])
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()

        await decorator.execute(session, {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        })

        await decorator.execute(session, {
            "tool_name": "terminal/wait_for_exit",
            "terminal_id": "term_1",
        })

        assert "project_structure" not in session.config_values

    @pytest.mark.asyncio
    async def test_delegates_to_wrapped_executor(self):
        """Decorator должен делегировать выполнение обёрнутому executor."""
        result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        executor = self._make_executor(result)
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()
        arguments = {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        }

        returned = await decorator.execute(session, arguments)

        executor.execute.assert_called_once_with(session, arguments)
        assert returned is result

    @pytest.mark.asyncio
    async def test_handles_find_error_lines(self):
        """Decorator должен игнорировать строки ошибок find."""
        create_result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        wait_result = ToolExecutionResult(
            success=True,
            output="find: android/..: unknown primary or operator\n./src/main.py\n",
            metadata={"terminal_id": "term_1", "exit_code": 1},
        )

        executor = AsyncMock()
        executor.execute = AsyncMock(side_effect=[create_result, wait_result])
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()

        await decorator.execute(session, {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        })

        await decorator.execute(session, {
            "tool_name": "terminal/wait_for_exit",
            "terminal_id": "term_1",
        })

        files = json.loads(session.config_values["project_structure"])
        assert "src/main.py" in files
        assert not any("find:" in f for f in files)

    @pytest.mark.asyncio
    async def test_removes_terminal_id_after_processing(self):
        """Decorator должен удалять terminal_id из маппинга после обработки."""
        create_result = ToolExecutionResult(
            success=True,
            metadata={"terminal_id": "term_1", "command": "find . -type f"},
            raw_output={"terminal_id": "term_1"},
        )
        wait_result = ToolExecutionResult(
            success=True,
            output="./src/main.py\n",
            metadata={"terminal_id": "term_1", "exit_code": 0},
        )

        executor = AsyncMock()
        executor.execute = AsyncMock(side_effect=[create_result, wait_result])
        decorator = ProjectStructureDecorator(executor)

        session = self._make_session()

        await decorator.execute(session, {
            "tool_name": "terminal/create",
            "command": "find . -type f",
        })

        assert "term_1" in decorator._terminal_commands

        await decorator.execute(session, {
            "tool_name": "terminal/wait_for_exit",
            "terminal_id": "term_1",
        })

        assert "term_1" not in decorator._terminal_commands


class TestFilterPaths:
    """Тесты для статического метода _filter_paths."""

    def test_filters_git_directory(self):
        """Должен фильтровать .git директорию."""
        paths = ["src/main.py", ".git/config", ".git/HEAD"]
        filtered = ProjectStructureDecorator._filter_paths(paths)
        assert filtered == ["src/main.py"]

    def test_filters_node_modules(self):
        """Должен фильтровать node_modules."""
        paths = ["src/index.js", "node_modules/pkg/index.js"]
        filtered = ProjectStructureDecorator._filter_paths(paths)
        assert filtered == ["src/index.js"]

    def test_filters_pycache(self):
        """Должен фильтровать __pycache__."""
        paths = ["src/main.py", "__pycache__/main.cpython-312.pyc"]
        filtered = ProjectStructureDecorator._filter_paths(paths)
        assert filtered == ["src/main.py"]

    def test_normalizes_slashes(self):
        """Должен нормализовать слэши."""
        paths = ["src\\main.py", "lib\\utils.py"]
        filtered = ProjectStructureDecorator._filter_paths(paths)
        assert all("/" in f or "\\" not in f for f in filtered)

    def test_filters_empty_paths(self):
        """Должен фильтровать пустые пути."""
        paths = ["src/main.py", "", ".", "./"]
        filtered = ProjectStructureDecorator._filter_paths(paths)
        assert filtered == ["src/main.py"]


class TestParseFindOutput:
    """Тесты для парсинга find output."""

    def test_parses_simple_paths(self):
        """Должен парсить простые пути."""
        output = "./src/main.py\n./src/utils.py\n"
        paths = ProjectStructureDecorator._parse_find_output(output)
        assert "src/main.py" in paths
        assert "src/utils.py" in paths

    def test_strips_dot_slash(self):
        """Должен убирать префикс ./."""
        output = "./src/main.py\n./lib/utils.py\n"
        paths = ProjectStructureDecorator._parse_find_output(output)
        assert all(not p.startswith("./") for p in paths)

    def test_skips_empty_lines(self):
        """Должен пропускать пустые строки."""
        output = "./src/main.py\n\n\n./src/utils.py\n"
        paths = ProjectStructureDecorator._parse_find_output(output)
        assert len(paths) == 2

    def test_skips_error_lines(self):
        """Должен пропускать строки ошибок."""
        output = "find: error message\n./src/main.py\n"
        paths = ProjectStructureDecorator._parse_find_output(output)
        assert len(paths) == 1
        assert "src/main.py" in paths


class TestParseLsOutput:
    """Тесты для парсинга ls output."""

    def test_parses_ls_la_output(self):
        """Должен парсить вывод ls -la."""
        output = (
            "total 32\n"
            "drwxr-xr-x@  5 user  staff   160 Jun 26 17:18 .\n"
            "drwxr-xr-x@ 23 user  staff   736 Jun 26 22:05 ..\n"
            "-rw-r--r--@  1 user  staff  4097 Jun 26 17:31 main.dart\n"
            "-rw-r--r--   1 user  staff  1290 Jun 26 14:14 utils.dart\n"
        )
        paths = ProjectStructureDecorator._parse_ls_output("ls -la", output)
        assert "main.dart" in paths
        assert "utils.dart" in paths

    def test_parses_recursive_ls(self):
        """Должен парсить рекурсивный ls -R."""
        output = (
            "./lib:\n"
            "main.dart\n"
            "utils.dart\n"
            "\n"
            "./src:\n"
            "service.dart\n"
        )
        paths = ProjectStructureDecorator._parse_ls_output("ls -R", output)
        assert "lib/main.dart" in paths
        assert "lib/utils.dart" in paths
        assert "src/service.dart" in paths

    def test_skips_hidden_files_in_ls_la(self):
        """Должен пропускать скрытые файлы в ls -la."""
        output = (
            "total 8\n"
            "-rw-r--r--  1 user  staff  100 Jun 26 17:18 .hidden\n"
            "-rw-r--r--  1 user  staff  200 Jun 26 17:18 visible.txt\n"
        )
        paths = ProjectStructureDecorator._parse_ls_output("ls -la", output)
        assert "visible.txt" in paths
        assert not any(".hidden" in p for p in paths)

    def test_parses_plain_ls(self):
        """Должен парсить простой ls без флагов."""
        output = "main.dart\nutils.dart\nservice.dart\n"
        paths = ProjectStructureDecorator._parse_ls_output("ls", output)
        assert "main.dart" in paths
        assert "utils.dart" in paths
        assert "service.dart" in paths

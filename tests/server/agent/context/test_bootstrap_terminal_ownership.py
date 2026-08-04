"""Владение терминалом bootstrap'а структуры проекта (P2-58).

Терминал освобождает тот, кто его создал. Без этого реестр alias'ов растёт на
каждый bootstrap, целиком уезжает на диск в каждой ревизии документа сессии, а
модель видит в нём терминалы, которых не просила (за живой прогон наблюдалось
11 `terminal/create` и 0 `terminal/release`).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.tools.base import ToolExecutionResult


class _RecordingRegistry:
    """Реестр инструментов, записывающий порядок вызовов."""

    def __init__(self, *, wait_fails: bool = False, release_fails: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._wait_fails = wait_fails
        self._release_fails = release_fails

    def get_available_tools(self, session_id: str) -> list:
        return []

    async def execute_tool(
        self, session_id: str, tool_name: str, arguments: dict, session: Any = None
    ) -> ToolExecutionResult:
        self.calls.append((tool_name, arguments))

        if tool_name == "terminal/create":
            return ToolExecutionResult(
                success=True,
                raw_output={"terminal_id": "term_1"},
                metadata={"terminal_id": "term_1"},
            )
        if tool_name == "terminal/wait_for_exit":
            if self._wait_fails:
                return ToolExecutionResult(success=False, error="wait failed")
            return ToolExecutionResult(success=True, output="./lib/main.dart\n./pubspec.yaml\n")
        if tool_name == "terminal/release":
            if self._release_fails:
                return ToolExecutionResult(success=False, error="unknown terminal")
            return ToolExecutionResult(success=True)

        return ToolExecutionResult(success=False, error="Unknown tool")

    def tool_names(self) -> list[str]:
        return [name for name, _ in self.calls]


def _make_gatherer(registry: _RecordingRegistry) -> ACPContextGatherer:
    return ACPContextGatherer(
        tool_registry=registry,  # type: ignore[arg-type]
        dependency_graph=RegexDependencyGraph(),
        session_id="sess_test",
    )


def _make_session(tmp_path) -> MagicMock:
    session = MagicMock()
    session.session_id = "sess_test"
    session.cwd = str(tmp_path)
    session.config_values = {}
    return session


class TestBootstrapReleasesTerminal:
    """Гейт: созданный для bootstrap'а терминал освобождается всегда."""

    async def test_releases_terminal_after_success(self, tmp_path) -> None:
        """На успешном пути терминал освобождается после чтения вывода."""
        registry = _RecordingRegistry()
        gatherer = _make_gatherer(registry)

        files = await gatherer._bootstrap_project_files(_make_session(tmp_path))

        assert files
        assert registry.tool_names() == [
            "terminal/create",
            "terminal/wait_for_exit",
            "terminal/release",
        ]
        assert registry.calls[-1][1] == {"terminal_id": "term_1"}

    async def test_releases_terminal_when_wait_fails(self, tmp_path) -> None:
        """Терминал освобождается и на неуспешном ожидании — иначе alias утечёт."""
        registry = _RecordingRegistry(wait_fails=True)
        gatherer = _make_gatherer(registry)

        files = await gatherer._bootstrap_project_files(_make_session(tmp_path))

        assert files == []
        assert "terminal/release" in registry.tool_names()

    async def test_failed_release_does_not_break_gathering(self, tmp_path) -> None:
        """Неудачное освобождение не отменяет уже собранную структуру."""
        registry = _RecordingRegistry(release_fails=True)
        gatherer = _make_gatherer(registry)

        files = await gatherer._bootstrap_project_files(_make_session(tmp_path))

        assert files
        assert "terminal/release" in registry.tool_names()

    async def test_no_release_without_terminal_id(self, tmp_path) -> None:
        """Без полученного alias'а освобождать нечего — лишнего вызова нет."""

        class _NoIdRegistry(_RecordingRegistry):
            async def execute_tool(
                self, session_id: str, tool_name: str, arguments: dict, session: Any = None
            ) -> ToolExecutionResult:
                self.calls.append((tool_name, arguments))
                if tool_name == "terminal/create":
                    return ToolExecutionResult(success=True, raw_output={}, metadata={})
                return ToolExecutionResult(success=False, error="unexpected call")

        registry = _NoIdRegistry()
        gatherer = _make_gatherer(registry)

        files = await gatherer._bootstrap_project_files(_make_session(tmp_path))

        assert files == []
        assert registry.tool_names() == ["terminal/create"]


class TestBootstrapStructureStillSaved:
    """Освобождение терминала не должно ломать основной результат bootstrap'а."""

    async def test_structure_written_to_session(self, tmp_path) -> None:
        """Структура проекта по-прежнему сохраняется в носитель состояния."""
        registry = _RecordingRegistry()
        gatherer = _make_gatherer(registry)
        session = _make_session(tmp_path)
        writable = MagicMock()

        # Запись идёт через сейм `writable_session` (ADR-006), а не напрямую в
        # переданный порт — проверяем именно то, что действительно записывается.
        with patch(
            "codelab.server.agent.context.gatherer.writable_session",
            return_value=writable,
        ):
            files = await gatherer._bootstrap_project_files(session)

        writable.set_config_value.assert_called_once()
        config_id, raw_value = writable.set_config_value.call_args.args
        assert config_id == "project_structure"
        assert json.loads(raw_value) == files


@pytest.mark.parametrize("wait_fails", [False, True])
async def test_exactly_one_release_per_bootstrap(tmp_path, wait_fails: bool) -> None:
    """Один bootstrap — ровно одно освобождение, независимо от исхода ожидания."""
    registry = _RecordingRegistry(wait_fails=wait_fails)
    gatherer = _make_gatherer(registry)

    await gatherer._bootstrap_project_files(_make_session(tmp_path))

    assert registry.tool_names().count("terminal/release") == 1

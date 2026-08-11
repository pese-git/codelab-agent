"""Полномочие сборщика контекста сужено до перечисления файлов (ADR-009, раздел 6).

Прежде bootstrap структуры проекта делал три сырых вызова `terminal/*` с
литеральной командой — то есть держал право исполнить произвольную команду ради
нужды «перечислить файлы». Теперь он вызывает узкую возможность
`project/list_files`, а владение терминалом (создать → дождаться → освободить,
P2-58) переехало в её реализацию: `tests/server/tools/definitions/
test_project_list_files.py`.

Гейт возвратом дефекта: вернуть в `_bootstrap_project_files` вызов
`terminal/create` — и `test_context_path_never_touches_terminal` падает.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.domain.value_objects import ToolInvocationSubject
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.definitions.project import LIST_FILES_TOOL


class _RecordingRegistry:
    """Реестр инструментов, записывающий инвокации сборщика контекста."""

    def __init__(self, *, listing_fails: bool = False, output: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationSubject]] = []
        self._listing_fails = listing_fails
        self._output = output if output is not None else "./lib/main.dart\n./pubspec.yaml\n"

    def get_available_tools(self, session_id: str) -> list:
        return []

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        session: Any = None,
        subject: ToolInvocationSubject = ToolInvocationSubject.UNKNOWN,
    ) -> ToolExecutionResult:
        self.calls.append((tool_name, arguments, subject))

        if tool_name == LIST_FILES_TOOL:
            if self._listing_fails:
                return ToolExecutionResult(success=False, error="listing failed")
            return ToolExecutionResult(success=True, output=self._output)

        return ToolExecutionResult(success=False, error="Unknown tool")

    def tool_names(self) -> list[str]:
        return [name for name, _, _ in self.calls]


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


class TestBootstrapUsesNarrowCapability:
    """Сборщик просит перечисление, а не исполнение команды."""

    async def test_single_listing_invocation(self, tmp_path) -> None:
        """Один bootstrap — одна инвокация возможности, без аргумента-команды."""
        registry = _RecordingRegistry()
        gatherer = _make_gatherer(registry)

        files = await gatherer._bootstrap_project_files(_make_session(tmp_path))

        assert files
        assert registry.tool_names() == [LIST_FILES_TOOL]
        name, arguments, subject = registry.calls[0]
        assert arguments == {}
        assert subject is ToolInvocationSubject.CONTEXT

    async def test_context_path_never_touches_terminal(self, tmp_path) -> None:
        """Гейт: путь сборки контекста не вызывает `terminal/*` ни на каком исходе.

        Право запускать команду исчезло по построению: команду формирует
        владелец возможности, а сборщик её не передаёт и передать не может.
        """
        for listing_fails in (False, True):
            registry = _RecordingRegistry(listing_fails=listing_fails)
            gatherer = _make_gatherer(registry)

            await gatherer._bootstrap_project_files(_make_session(tmp_path))

            assert not [name for name in registry.tool_names() if name.startswith("terminal/")]
            assert not any(
                "command" in arguments for _, arguments, _ in registry.calls
            ), "сборщик контекста не вправе передавать команду"

    async def test_failed_listing_degrades_gracefully(self, tmp_path) -> None:
        """Отказ перечисления не роняет горячий путь — структура просто пуста."""
        registry = _RecordingRegistry(listing_fails=True)
        gatherer = _make_gatherer(registry)

        assert await gatherer._bootstrap_project_files(_make_session(tmp_path)) == []

    async def test_empty_output_is_not_a_structure(self, tmp_path) -> None:
        """Пустой вывод перечисления не сохраняется как структура проекта."""
        registry = _RecordingRegistry(output="")
        gatherer = _make_gatherer(registry)

        assert await gatherer._bootstrap_project_files(_make_session(tmp_path)) == []


class TestBootstrapStructureStillSaved:
    """Сужение полномочия не изменило основной результат bootstrap'а."""

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

    async def test_output_parsed_as_before(self, tmp_path) -> None:
        """Формат вывода возможности — тот же, что давал `find`: пути с `./`."""
        registry = _RecordingRegistry()
        gatherer = _make_gatherer(registry)

        files = await gatherer._bootstrap_project_files(_make_session(tmp_path))

        assert files == ["lib/main.dart", "pubspec.yaml"]

"""Возможность `project/list_files` — узкое право вместо широкого (ADR-009, раздел 6).

Здесь живут две вещи, ради которых возможность и вводилась:

* **команду формирует один владелец** — потребитель её не передаёт, поэтому
  валидировать нечего и белый список команд не нужен;
* **владение терминалом** (создать → дождаться → освободить), переехавшее из
  `ContextGatherer` вместе с реализацией (P2-58).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.definitions.project import (
    LIST_FILES_TOOL,
    ProjectToolDefinitions,
    _list_files,
)


class _RecordingExecutor:
    """Терминальный executor, записывающий операции."""

    def __init__(
        self,
        *,
        create_fails: bool = False,
        no_terminal_id: bool = False,
        wait_fails: bool = False,
        release_fails: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._create_fails = create_fails
        self._no_terminal_id = no_terminal_id
        self._wait_fails = wait_fails
        self._release_fails = release_fails

    async def execute(self, session: Any, arguments: dict[str, Any]) -> ToolExecutionResult:
        self.calls.append(arguments)
        operation = arguments.get("operation")

        if operation == "create":
            if self._create_fails:
                return ToolExecutionResult(success=False, error="create failed")
            if self._no_terminal_id:
                return ToolExecutionResult(success=True, metadata={}, raw_output={})
            return ToolExecutionResult(
                success=True,
                metadata={"terminal_id": "term_1"},
                raw_output={"terminal_id": "term_1"},
            )
        if operation == "wait_for_exit":
            if self._wait_fails:
                return ToolExecutionResult(success=False, error="wait failed")
            return ToolExecutionResult(success=True, output="./lib/main.dart\n")
        if operation == "release":
            if self._release_fails:
                return ToolExecutionResult(success=False, error="unknown terminal")
            return ToolExecutionResult(success=True)

        return ToolExecutionResult(success=False, error=f"unexpected: {operation}")

    def operations(self) -> list[str]:
        return [call.get("operation", "") for call in self.calls]


def _make_session(tmp_path) -> MagicMock:
    session = MagicMock()
    session.id = "sess_test"
    session.config.cwd = str(tmp_path)
    return session


class TestDefinition:
    """Форма возможности: чтение, внутренняя, без аргументов."""

    def test_listing_is_a_read(self) -> None:
        """`kind=read`: перечисление — чтение, а не исполнение.

        Это же чинит поведение в plan-режиме, где `execute` блокируется, хотя
        ничего исполняющего по смыслу не происходит.
        """
        assert ProjectToolDefinitions.list_files().kind == "read"

    def test_not_offered_to_model(self) -> None:
        """Возможность внутренняя: набор инструментов модели не меняется."""
        assert ProjectToolDefinitions.list_files().internal is True

    def test_caller_cannot_supply_a_command(self) -> None:
        """У возможности нет параметров — командой её не параметризовать."""
        definition = ProjectToolDefinitions.list_files()

        assert definition.name == LIST_FILES_TOOL
        assert definition.parameters["properties"] == {}
        assert definition.parameters["required"] == []


class TestCommandOwnership:
    """Команду формирует владелец возможности, а не вызывающий."""

    async def test_command_is_fixed_by_the_owner(self, tmp_path) -> None:
        """Исполняется ровно перечисление, и в рабочем каталоге сессии."""
        executor = _RecordingExecutor()

        result = await _list_files(_make_session(tmp_path), executor)

        assert result.success
        create = executor.calls[0]
        assert create["command"] == "find . -type f"
        assert create["cwd"] == str(tmp_path)


class TestTerminalOwnership:
    """Терминал освобождает тот, кто его создал (P2-58)."""

    async def test_releases_after_success(self, tmp_path) -> None:
        executor = _RecordingExecutor()

        result = await _list_files(_make_session(tmp_path), executor)

        assert result.output == "./lib/main.dart\n"
        assert executor.operations() == ["create", "wait_for_exit", "release"]
        assert executor.calls[-1]["terminal_id"] == "term_1"

    async def test_releases_when_wait_fails(self, tmp_path) -> None:
        """Терминал освобождается и на неуспешном ожидании — иначе alias утечёт."""
        executor = _RecordingExecutor(wait_fails=True)

        result = await _list_files(_make_session(tmp_path), executor)

        assert not result.success
        assert "release" in executor.operations()

    async def test_failed_release_does_not_lose_the_listing(self, tmp_path) -> None:
        """Неудачное освобождение не отменяет уже полученный результат."""
        executor = _RecordingExecutor(release_fails=True)

        result = await _list_files(_make_session(tmp_path), executor)

        assert result.success
        assert result.output == "./lib/main.dart\n"

    async def test_no_release_without_terminal_id(self, tmp_path) -> None:
        """Без полученного alias'а освобождать нечего — лишнего вызова нет."""
        executor = _RecordingExecutor(no_terminal_id=True)

        result = await _list_files(_make_session(tmp_path), executor)

        assert not result.success
        assert executor.operations() == ["create"]

    async def test_create_failure_reports_reason(self, tmp_path) -> None:
        executor = _RecordingExecutor(create_fails=True)

        result = await _list_files(_make_session(tmp_path), executor)

        assert not result.success
        assert result.error == "create failed"
        assert executor.operations() == ["create"]

    async def test_exactly_one_release_per_listing(self, tmp_path) -> None:
        executor = _RecordingExecutor()

        await _list_files(_make_session(tmp_path), executor)

        assert executor.operations().count("release") == 1


class TestRegistration:
    """Регистрация в реестре: имя, обработчик, отсутствие в наборе для модели."""

    async def test_registered_handler_lists_files(self, tmp_path) -> None:
        from codelab.server.tools.registry import SimpleToolRegistry

        registry = SimpleToolRegistry()
        executor = _RecordingExecutor()
        ProjectToolDefinitions.register_all(registry, executor)

        assert registry.get(LIST_FILES_TOOL) is not None
        assert [t.name for t in registry.get_available_tools("sess_test")] == []

        handler = registry._handlers[LIST_FILES_TOOL]
        result = await handler(session=_make_session(tmp_path))

        assert result.success
        assert executor.operations() == ["create", "wait_for_exit", "release"]

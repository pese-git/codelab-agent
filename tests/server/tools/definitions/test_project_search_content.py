"""Возможность `project/search_content` — узкое право вместо цикла чтений (P2-57).

Здесь живут три вещи, ради которых возможность вводилась:

* **команду формирует владелец**, потребитель передаёт только термин;
* **термин не разбирается shell'ом** — он уходит элементом argv, поэтому
  инъекции нет по построению, а не по экранированию;
* **исход определяется выводом, а не кодом возврата**: отсутствие совпадений —
  успех с пустым выводом, а найденное переживает ненулевой код, потому что у
  grep «ошибка» — это любой нечитаемый файл в дереве.

Владение терминалом (создать → дождаться → освободить) проверено у
`project/list_files` на общей реализации `_run` и здесь не дублируется, кроме
веток с собственным выходом: «совпадений нет» и «результат неполон».
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.definitions.project import (
    SEARCH_CONTENT_TOOL,
    ProjectToolDefinitions,
    _search_content,
)


class _RecordingExecutor:
    """Терминальный executor, записывающий операции."""

    def __init__(self, *, exit_code: int = 0, output: str = "./lib/main.dart\n") -> None:
        self.calls: list[dict[str, Any]] = []
        self._exit_code = exit_code
        self._output = output

    async def execute(self, session: Any, arguments: dict[str, Any]) -> ToolExecutionResult:
        self.calls.append(arguments)
        operation = arguments.get("operation")

        if operation == "create":
            return ToolExecutionResult(
                success=True,
                metadata={"terminal_id": "term_1"},
                raw_output={"terminal_id": "term_1"},
            )
        if operation == "wait_for_exit":
            # `success` терминала — это `exit_code == 0`, поэтому всё, кроме
            # найденных совпадений, приходит сюда неуспехом. Вывод при этом
            # **не обнуляется**: живой grep печатает найденное и лишь потом
            # возвращает 2 из-за нечитаемого файла — модель, обнулявшая вывод
            # на ненулевом коде, ровно этот дефект и скрыла.
            return ToolExecutionResult(
                success=self._exit_code == 0,
                output=self._output,
                metadata={"terminal_id": "term_1", "exit_code": self._exit_code},
                raw_output={"exit_code": self._exit_code},
            )
        if operation == "release":
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
    """Форма возможности: чтение, внутренняя, один параметр."""

    def test_search_is_a_read(self) -> None:
        assert ProjectToolDefinitions.search_content().kind == "read"

    def test_not_offered_to_model(self) -> None:
        """У модели поиск уже есть через терминал: набор в payload'е не меняется."""
        assert ProjectToolDefinitions.search_content().internal is True

    def test_caller_supplies_only_the_term(self) -> None:
        definition = ProjectToolDefinitions.search_content()

        assert definition.name == SEARCH_CONTENT_TOOL
        assert list(definition.parameters["properties"]) == ["term"]
        assert definition.parameters["required"] == ["term"]


class TestCommandOwnership:
    """Команду формирует владелец; термин — данные, а не часть команды."""

    async def test_command_is_fixed_by_the_owner(self, tmp_path) -> None:
        executor = _RecordingExecutor()

        result = await _search_content(_make_session(tmp_path), executor, "AuthService")

        assert result.success
        create = executor.calls[0]
        assert create["command"] == "grep"
        assert create["cwd"] == str(tmp_path)

    async def test_term_goes_as_a_separate_argument(self, tmp_path) -> None:
        """Термин — элемент argv, а не подстрока команды: разбирать его нечему."""
        executor = _RecordingExecutor()

        await _search_content(_make_session(tmp_path), executor, "rm -rf /; echo pwned")

        create = executor.calls[0]
        assert create["command"] == "grep"
        assert "rm -rf /; echo pwned" in create["args"]
        assert "rm -rf /; echo pwned" not in create["command"]

    async def test_term_starting_with_a_dash_stays_a_term(self, tmp_path) -> None:
        """`--` закрывает опции: `-i` ищется, а не включает режим."""
        executor = _RecordingExecutor()

        await _search_content(_make_session(tmp_path), executor, "-i")

        args = executor.calls[0]["args"]
        assert args.index("--") < args.index("-i", args.index("--"))

    async def test_search_is_literal_and_case_insensitive(self, tmp_path) -> None:
        """Семантика сохранена: та же, что была у `term.lower() in content.lower()`."""
        executor = _RecordingExecutor()

        await _search_content(_make_session(tmp_path), executor, "Auth")

        args = executor.calls[0]["args"]
        assert "-i" in args
        assert "-F" in args

    async def test_search_covers_the_whole_tree(self, tmp_path) -> None:
        """Область поиска у владельца и не ограничена окном потребителя."""
        executor = _RecordingExecutor()

        await _search_content(_make_session(tmp_path), executor, "auth")

        args = executor.calls[0]["args"]
        assert "-r" in args
        assert args[-1] == "."


class TestUnreadableFilesInTree:
    """Нечитаемый файл в дереве не отменяет уже найденное.

    Дефект, найденный первым живым прогоном (2026-08-17, `codelab-23132`): grep
    напечатал `./lib/presentation/counter/counter_page.dart` и **следом** вернул
    2 из-за `./.codegraph/daemon.sock: Operation not supported on socket`. У grep
    «произошла ошибка» включает любой нечитаемый файл, поэтому на живом проекте
    код 2 — норма, а не отказ: 5 поисков из 5 выбрасывали верный результат.
    """

    async def test_matches_survive_a_nonzero_exit(self, tmp_path) -> None:
        executor = _RecordingExecutor(
            exit_code=2,
            output=(
                "./lib/presentation/counter/counter_page.dart\n"
                "grep: ./.codegraph/daemon.sock: Operation not supported on socket\n"
            ),
        )

        result = await _search_content(_make_session(tmp_path), executor, "Scaffold")

        assert result.success
        assert "counter_page.dart" in (result.output or "")

    async def test_incomplete_result_is_named_incomplete(self, tmp_path) -> None:
        """Неполнота попадает в метаданные: успех и полный успех — разные вещи."""
        executor = _RecordingExecutor(exit_code=2, output="./lib/main.dart\n")

        result = await _search_content(_make_session(tmp_path), executor, "void")

        assert result.metadata is not None
        assert result.metadata["partial"] is True

    async def test_full_result_is_not_marked_partial(self, tmp_path) -> None:
        executor = _RecordingExecutor(exit_code=0)

        result = await _search_content(_make_session(tmp_path), executor, "auth")

        assert result.success
        assert (result.metadata or {}).get("partial") is None


class TestNoMatches:
    """Совпадений нет — это результат, а не ошибка."""

    async def test_absence_is_success(self, tmp_path) -> None:
        executor = _RecordingExecutor(exit_code=1, output="")

        result = await _search_content(_make_session(tmp_path), executor, "nothing")

        assert result.success
        assert result.output == ""

    async def test_real_error_stays_an_error(self, tmp_path) -> None:
        """Код >= 2 — отказ утилиты, и он не выдаётся за пустой результат."""
        executor = _RecordingExecutor(exit_code=2, output="")

        result = await _search_content(_make_session(tmp_path), executor, "auth")

        assert not result.success

    async def test_failure_carries_the_exit_code(self, tmp_path) -> None:
        """Код возврата доезжает до вызывающего.

        Без него «совпадений нет», «утилита не поняла аргументы» и «команда не
        запустилась» неразличимы по логу — на первом живом прогоне возможность
        отказала 44 раза из 44, и причину нечем было отличить от пустого
        результата.
        """
        executor = _RecordingExecutor(exit_code=2, output="")

        result = await _search_content(_make_session(tmp_path), executor, "auth")

        assert "exit_code=2" in (result.error or "")
        assert result.metadata is not None
        assert result.metadata["exit_code"] == 2

    async def test_terminal_released_when_there_are_no_matches(self, tmp_path) -> None:
        """У ветки «совпадений нет» свой выход — alias не должен на нём утечь."""
        executor = _RecordingExecutor(exit_code=1, output="")

        await _search_content(_make_session(tmp_path), executor, "nothing")

        assert executor.operations() == ["create", "wait_for_exit", "release"]


class TestTermValidation:
    """Пустой термин отклоняется до терминала."""

    async def test_missing_term_is_rejected(self, tmp_path) -> None:
        executor = _RecordingExecutor()

        result = await _search_content(_make_session(tmp_path), executor, None)

        assert not result.success
        assert executor.calls == []

    async def test_blank_term_is_rejected(self, tmp_path) -> None:
        """Иначе `grep ' '` вернул бы почти весь проект как совпадение."""
        executor = _RecordingExecutor()

        result = await _search_content(_make_session(tmp_path), executor, "   ")

        assert not result.success
        assert executor.calls == []


class TestRegistration:
    async def test_registered_handler_searches(self, tmp_path) -> None:
        from codelab.server.tools.registry import SimpleToolRegistry

        registry = SimpleToolRegistry()
        executor = _RecordingExecutor()
        ProjectToolDefinitions.register_all(registry, executor)

        assert registry.get(SEARCH_CONTENT_TOOL) is not None
        assert [t.name for t in registry.get_available_tools("sess_test")] == []

        handler = registry._handlers[SEARCH_CONTENT_TOOL]
        result = await handler(session=_make_session(tmp_path), term="auth")

        assert result.success
        assert result.output == "./lib/main.dart\n"
        assert executor.operations() == ["create", "wait_for_exit", "release"]

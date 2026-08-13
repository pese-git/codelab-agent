"""Инвариант: на каждый tool_call модель получает ответ `role: tool`.

Найдено разбором живой сессии `sess_f71ff601b1bf`: 53 запроса инструментов в
истории против 35 ответов — 18 вызовов остались без ответа, потому что
reject-пути писали статус и нотификацию клиенту, но не результат в историю.
Модель видела вызов без ответа и повторяла его до упора в `max_turn_requests`.

Инвариант двусторонний: он же контракт LLM-API (за assistant-сообщением с
`tool_calls` обязан следовать `role: tool` на каждый `tool_call_id`) и шаг 6
ACP `05-Prompt Turn` («Agent sends the tool results back to the language model»).

Второй канал того же дефекта (P2-38) — прерванный батч: `process_batch` бросал
остаток вызовов на паузе permission и на отмене, хотя `loop.py` уже положил в
историю assistant-сообщение со всеми id батча. Первая версия этого файла
проверяла только одиночные reject-пути и дефект не поймала — поэтому здесь
покрыты батчи.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.session import TurnState
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry
from codelab.server.tools.base import ToolExecutionResult
from tests.server._domain_sessions import make_commands, make_domain_session, wire_history


def _make_processor(
    turn_cancellation: TurnCancellationRegistry | None = None,
) -> ToolCallProcessor:
    return ToolCallProcessor(
        tool_registry=MagicMock(),
        # Ответ на невыполненный вызов и запись его в журнал принадлежат
        # обработчику (ADR-008, шаг 4), поэтому здесь он настоящий: с заглушкой
        # инвариант «на каждый вызов ответ» проверялся бы мимо владельца.
        tool_call_handler=ToolCallHandler(),
        permission_manager=MagicMock(),
        content_extractor=AsyncMock(),
        content_validator=MagicMock(),
        plan_builder=MagicMock(),
        global_policy_manager=MagicMock(),
        turn_cancellation=turn_cancellation,
    )


def _session(mode: str = "plan") -> DomainSession:
    session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])
    session.set_config_value("mode", mode)
    return session


def _tool_answers(session: DomainSession) -> list[dict[str, Any]]:
    """Ответы `role: tool` в том виде, в каком они уезжают на диск."""
    return [m for m in wire_history(session) if m.get("role") == "tool"]


class TestRejectPathsAnswerTheModel:
    @pytest.mark.asyncio
    async def test_policy_rejection_is_answered(self) -> None:
        processor = _make_processor()
        session = _session()

        await processor._reject_tool_call(
            make_commands(session),
            "s",
            "call_1",
            "terminal/create",
            "execute",
            "llm_1",
            AsyncMock(),
        )

        answers = _tool_answers(session)
        assert len(answers) == 1
        assert answers[0]["tool_call_id"] == "llm_1"
        assert "plan" in answers[0]["content"]

    @pytest.mark.asyncio
    async def test_unknown_tool_rejection_is_answered(self) -> None:
        processor = _make_processor()
        processor._tool_registry.list_tools.return_value = []
        session = _session()

        await processor._reject_unknown_tool(
            make_commands(session), "s", "call_1", "hallucinated_tool", "llm_1", AsyncMock()
        )

        answers = _tool_answers(session)
        assert len(answers) == 1
        assert answers[0]["tool_call_id"] == "llm_1"
        assert "hallucinated_tool" in answers[0]["content"]

    @pytest.mark.asyncio
    async def test_loop_guard_rejection_is_answered(self) -> None:
        processor = _make_processor()
        session = _session(mode="bypass")
        name, args = "terminal/create", {"command": "fvm"}
        for _ in range(4):
            processor._loop_detector.register_attempt(name, args)
        processor._loop_detector.record_output(
            name, args, ToolExecutionResult(success=True, output="Терминал создан")
        )

        await processor._reject_looping_tool(
            make_commands(session), "s", "call_1", name, args, "llm_1", AsyncMock()
        )

        answers = _tool_answers(session)
        assert len(answers) == 1
        assert answers[0]["tool_call_id"] == "llm_1"
        assert "повтор" in answers[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_answer_uses_llm_tool_call_id_when_present(self) -> None:
        """Ответ адресуется id, который прислал LLM, иначе он не сматчится."""
        processor = _make_processor()
        session = _session()

        await processor._reject_tool_call(
            make_commands(session),
            "s",
            "call_042",
            "terminal/create",
            "execute",
            "chatcmpl-tool-abc",
            AsyncMock(),
        )

        assert _tool_answers(session)[0]["tool_call_id"] == "chatcmpl-tool-abc"

    @pytest.mark.asyncio
    async def test_answer_falls_back_to_acp_id(self) -> None:
        processor = _make_processor()
        session = _session()

        await processor._reject_tool_call(
            make_commands(session), "s", "call_042", "terminal/create", "execute", None, AsyncMock()
        )

        assert _tool_answers(session)[0]["tool_call_id"] == "call_042"


class _Call:
    """Минимальный tool call в форме, которую отдаёт LLM-адаптер."""

    def __init__(self, id_: str, name: str = "fs/read_text_file") -> None:
        self.id = id_
        self.name = name
        self.arguments: dict[str, Any] = {"path": "/tmp/a.txt"}


class TestInterruptedBatchIsFullyAnswered:
    """Прерванный батч: каждый вызов получает ответ (tech-debt P2-38)."""

    @pytest.mark.asyncio
    async def test_permission_pause_defers_rest_of_batch(self) -> None:
        """Остаток батча уходит в `pending_batch`, а не выбрасывается (P2-40).

        До P2-40 хвост получал «вызов не выполнялся» и терялся: модель
        перезапрашивала те же файлы, на живом прогоне — 80 брошенных вызовов за
        turn. Инвариант `role: tool` при этом не нарушается: отложенные вызовы
        будут выполнены и отвечены после разрешения.
        """
        processor = _make_processor()
        session = _session(mode="standard")
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="s")
        batch = [_Call(f"llm_{i}") for i in range(11)]

        async def _pause_first(*args: Any, **kwargs: Any):
            from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
                _ToolCallStep,
            )

            return _ToolCallStep(pause_tool_call_id="call_001")

        processor._process_single_tool_call = _pause_first  # type: ignore[method-assign]

        result = await processor.process_batch(
            make_commands(session), "s", batch, AsyncMock(), None
        )

        assert result.pending_permission is True
        deferred = session.active_turn.pending_batch
        assert [c["id"] for c in deferred] == [f"llm_{i}" for i in range(1, 11)]
        # Служебных ответов «не выполнялся» больше нет — вызовы не потеряны
        assert _tool_answers(session) == []

    @pytest.mark.asyncio
    async def test_pause_without_active_turn_still_answers(self) -> None:
        """Если хвост сохранить некуда, модель обязана получить ответ.

        Иначе вызовы остались бы без `role: tool` — тот же дефект, что P2-38.
        """
        processor = _make_processor()
        session = _session(mode="standard")
        session.active_turn = None
        batch = [_Call(f"llm_{i}") for i in range(3)]

        async def _pause_first(*args: Any, **kwargs: Any):
            from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
                _ToolCallStep,
            )

            return _ToolCallStep(pause_tool_call_id="call_001")

        processor._process_single_tool_call = _pause_first  # type: ignore[method-assign]

        await processor.process_batch(make_commands(session), "s", batch, AsyncMock(), None)

        answered = {m["tool_call_id"] for m in _tool_answers(session)}
        assert answered == {"llm_1", "llm_2"}

    @pytest.mark.asyncio
    async def test_permission_pause_answers_rest_when_turn_is_absent(self) -> None:
        """Пауза без `active_turn`: остаток обязан получить ответ.

        Воспроизводит живой случай `sess_ba92d6fb021f` (батч из 11 вызовов, пауза на
        первом, 10 вызовов без `role: tool`). После P2-40 штатный путь хвост
        откладывает, а этот тест держит запасной: если складывать некуда, модель
        всё равно не остаётся без ответа.
        """
        processor = _make_processor()
        session = _session(mode="standard")
        batch = [_Call(f"llm_{i}") for i in range(11)]

        # Первый вызов уходит в permission, остальные обработаны не будут
        async def _pause_first(*args: Any, **kwargs: Any):
            from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
                _ToolCallStep,
            )

            return _ToolCallStep(pause_tool_call_id="call_001")

        processor._process_single_tool_call = _pause_first  # type: ignore[method-assign]

        result = await processor.process_batch(
            make_commands(session), "s", batch, AsyncMock(), None
        )

        assert result.pending_permission is True
        # Без `active_turn` (например, turn уже закрыт) хвост сохранить некуда,
        # поэтому вызовы отвечаются — инвариант `role: tool` держится (P2-38).
        answered = {m["tool_call_id"] for m in _tool_answers(session)}
        assert answered == {f"llm_{i}" for i in range(1, 11)}
        assert all("не выполнялся" in m["content"] for m in _tool_answers(session))

    @pytest.mark.asyncio
    async def test_cancel_answers_remaining_batch(self) -> None:
        """Отмена turn'а тоже не оставляет вызовы без ответа.

        Отмена подаётся реальным сигналом — поколением в процессном реестре, как
        это делает `handle_cancel`. Раньше тест подменял `_is_cancel_requested` и
        потому проходил, хотя в проде ветка была недостижима (P0-39).
        """
        registry = TurnCancellationRegistry()
        processor = _make_processor(registry)
        session = _session(mode="standard")
        batch = [_Call(f"llm_{i}") for i in range(4)]
        started_epoch = registry.generation("s")
        registry.cancel("s")

        result = await processor.process_batch(
            make_commands(session), "s", batch, AsyncMock(), None, started_epoch
        )

        assert result.pending_permission is False
        answered = {m["tool_call_id"] for m in _tool_answers(session)}
        assert answered == {f"llm_{i}" for i in range(4)}
        assert all("отменён" in m["content"] for m in _tool_answers(session))

    @pytest.mark.asyncio
    async def test_call_without_name_is_answered(self) -> None:
        """Вызов без имени инструмента тоже требует ответа."""
        processor = _make_processor()
        session = _session(mode="standard")
        nameless = _Call("llm_x", name="")

        await processor.process_batch(make_commands(session), "s", [nameless], AsyncMock(), None)

        answers = _tool_answers(session)
        assert len(answers) == 1
        assert answers[0]["tool_call_id"] == "llm_x"
        assert "имя инструмента" in answers[0]["content"]

    @pytest.mark.asyncio
    async def test_empty_remainder_writes_nothing(self) -> None:
        """Пауза на последнем вызове батча не добавляет лишних ответов."""
        processor = _make_processor()
        session = _session(mode="standard")

        await processor._answer_unprocessed_tool_calls(
            make_commands(session), "s", [], reason="неважно"
        )

        assert _tool_answers(session) == []


class TestAnswerIsAJournalEvent:
    """Ответ на невыполненный вызов — событие журнала (ADR-008, шаг 4).

    Требование найдено живым прогоном и воспроизведено трижды: 26 записей
    `role=tool` против 23 вызовов, затем 28/26 и 39/35. Лишние отвечали вызовам,
    которых нет ни в `tool_calls`, ни в журнале, — значит проекция `history` из
    журнала невыводима, пока такой ответ не является событием.
    """

    @staticmethod
    def _answer_events(session: DomainSession) -> list[dict[str, Any]]:
        return [
            e
            for e in session.runtime.events_history
            if e.get("event") == "unexecuted_tool_call_answered"
        ]

    @pytest.mark.asyncio
    async def test_interrupted_batch_is_journalled(self) -> None:
        processor = _make_processor()
        session = _session(mode="standard")

        await processor._answer_unprocessed_tool_calls(
            make_commands(session), "s", [_Call("llm_1"), _Call("llm_2")], reason="отмена"
        )

        events = self._answer_events(session)
        assert [e["data"]["tool_call_id"] for e in events] == ["llm_1", "llm_2"]
        # Текст в журнале — тот же, что уехал модели: иначе проекция `history`
        # выдала бы не то, что видела модель.
        answers = _tool_answers(session)
        assert [e["data"]["text"] for e in events] == [m["content"] for m in answers]

    @pytest.mark.asyncio
    async def test_nameless_call_is_journalled(self) -> None:
        processor = _make_processor()
        session = _session(mode="standard")

        await processor.process_batch(
            make_commands(session), "s", [_Call("llm_x", name="")], AsyncMock(), None
        )

        events = self._answer_events(session)
        assert len(events) == 1
        assert events[0]["data"]["tool_call_id"] == "llm_x"

    @pytest.mark.asyncio
    async def test_suppressed_duplicate_is_not_journalled(self) -> None:
        """Подавленный дубль ответа события не порождает.

        Иначе журнал описывал бы запись, которой в истории нет, и проекция
        разошлась бы с состоянием во второй раз — уже в другую сторону (P2-63).
        """
        processor = _make_processor()
        session = _session(mode="standard")
        commands = make_commands(session)

        await processor._answer_unprocessed_tool_calls(
            commands, "s", [_Call("llm_1")], reason="отмена"
        )
        await processor._answer_unprocessed_tool_calls(
            commands, "s", [_Call("llm_1")], reason="сессия была переключена"
        )

        assert len(self._answer_events(session)) == 1
        assert len(_tool_answers(session)) == 1

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

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult


def _make_processor() -> ToolCallProcessor:
    return ToolCallProcessor(
        tool_registry=MagicMock(),
        tool_call_handler=MagicMock(),
        permission_manager=MagicMock(),
        content_extractor=AsyncMock(),
        content_validator=MagicMock(),
        content_formatter=MagicMock(),
        plan_builder=MagicMock(),
        global_policy_manager=MagicMock(),
    )


def _session(mode: str = "plan") -> SessionState:
    session = SessionState(session_id="s", cwd="/tmp", mcp_servers=[])
    session.set_config_value("mode", mode)
    return session


def _tool_answers(session: SessionState) -> list[dict[str, Any]]:
    return [m for m in session.history if isinstance(m, dict) and m.get("role") == "tool"]


class TestRejectPathsAnswerTheModel:
    @pytest.mark.asyncio
    async def test_policy_rejection_is_answered(self) -> None:
        processor = _make_processor()
        session = _session()

        await processor._reject_tool_call(
            session, "s", "call_1", "terminal/create", "execute", "llm_1", AsyncMock()
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
            session, "s", "call_1", "hallucinated_tool", "llm_1", AsyncMock()
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
            session, "s", "call_1", name, args, "llm_1", AsyncMock()
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
            session, "s", "call_042", "terminal/create", "execute", "chatcmpl-tool-abc", AsyncMock()
        )

        assert _tool_answers(session)[0]["tool_call_id"] == "chatcmpl-tool-abc"

    @pytest.mark.asyncio
    async def test_answer_falls_back_to_acp_id(self) -> None:
        processor = _make_processor()
        session = _session()

        await processor._reject_tool_call(
            session, "s", "call_042", "terminal/create", "execute", None, AsyncMock()
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
    async def test_permission_pause_answers_rest_of_batch(self) -> None:
        """Пауза на первом вызове не оставляет остальные без ответа.

        Воспроизводит живой случай `sess_ba92d6fb021f`: батч из 11 вызовов, пауза
        на первом — и 10 вызовов без `role: tool` до конца сессии.
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

        result = await processor.process_batch(session, "s", batch, AsyncMock(), None)

        assert result.pending_permission is True
        # Приостановленный вызов ответит execute_pending; остальные 10 — здесь
        answered = {m["tool_call_id"] for m in _tool_answers(session)}
        assert answered == {f"llm_{i}" for i in range(1, 11)}
        assert all("не выполнялся" in m["content"] for m in _tool_answers(session))

    @pytest.mark.asyncio
    async def test_cancel_answers_remaining_batch(self) -> None:
        """Отмена turn'а тоже не оставляет вызовы без ответа."""
        processor = _make_processor()
        session = _session(mode="standard")
        batch = [_Call(f"llm_{i}") for i in range(4)]
        processor._is_cancel_requested = lambda _session: True  # type: ignore[method-assign]

        result = await processor.process_batch(session, "s", batch, AsyncMock(), None)

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

        await processor.process_batch(session, "s", [nameless], AsyncMock(), None)

        answers = _tool_answers(session)
        assert len(answers) == 1
        assert answers[0]["tool_call_id"] == "llm_x"
        assert "имя инструмента" in answers[0]["content"]

    @pytest.mark.asyncio
    async def test_empty_remainder_writes_nothing(self) -> None:
        """Пауза на последнем вызове батча не добавляет лишних ответов."""
        processor = _make_processor()
        session = _session(mode="standard")

        processor._answer_unprocessed_tool_calls(session, "s", [], reason="неважно")

        assert _tool_answers(session) == []

"""Инвариант: на каждый tool_call модель получает ответ `role: tool`.

Найдено разбором живой сессии `sess_f71ff601b1bf`: 53 запроса инструментов в
истории против 35 ответов — 18 вызовов остались без ответа, потому что
reject-пути писали статус и нотификацию клиенту, но не результат в историю.
Модель видела вызов без ответа и повторяла его до упора в `max_turn_requests`.

Инвариант двусторонний: он же контракт LLM-API (за assistant-сообщением с
`tool_calls` обязан следовать `role: tool` на каждый `tool_call_id`) и шаг 6
ACP `05-Prompt Turn` («Agent sends the tool results back to the language model»).
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

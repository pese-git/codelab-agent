"""Интеграция детектора зацикливания в ToolCallProcessor (tech-debt #22).

Логика детекции покрыта в test_loop_detector.py; здесь — что процессор
композирует детектор и корректно отклоняет зацикленный вызов.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.tools.base import ToolExecutionResult
from tests.server._domain_sessions import make_commands, make_domain_session


def _make_processor(limit: int = 3) -> ToolCallProcessor:
    return ToolCallProcessor(
        tool_registry=MagicMock(),
        tool_call_handler=MagicMock(),
        permission_manager=MagicMock(),
        content_extractor=AsyncMock(),
        content_validator=MagicMock(),
        plan_builder=MagicMock(),
        global_policy_manager=MagicMock(),
        loop_guard_limit=limit,
    )


class TestProcessorLoopGuardIntegration:
    def test_processor_builds_detector_with_limit(self) -> None:
        p = _make_processor(limit=5)
        assert p._loop_detector.limit == 5

    @pytest.mark.asyncio
    async def test_reject_looping_tool_returns_hint_without_execution(self) -> None:
        p = _make_processor(limit=2)
        name, args = "terminal/create", {"command": "fvm", "args": ["analyze"]}
        # Набиваем счётчик и вывод через детектор (как будто исполнялось).
        for _ in range(3):
            p._loop_detector.register_attempt(name, args)
        p._loop_detector.record_output(
            name, args, ToolExecutionResult(success=True, output="Терминал создан")
        )

        sink = AsyncMock()
        session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])

        result = await p._reject_looping_tool(
            make_commands(session), "s", "call_1", name, args, "llm_1", sink
        )

        assert result.success is False
        assert result.error is not None
        assert "terminal/create" in result.error
        assert "Терминал создан" in result.error
        assert result.tool_call_id == "llm_1"
        p._tool_registry.execute_tool.assert_not_called()
        sink.emit_and_save_tool_update.assert_awaited_once()

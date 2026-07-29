"""Отказ policy доносит модели причину (tech-debt P2-36).

Логика формулировки покрыта в `handlers/test_tool_policy.py::TestDescribeRejection`;
здесь — что процессор кладёт причину в tool result (то, что читает модель) и в
`tool_call_update` (то, что видит клиент), а инструмент при этом не исполняется.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.protocol.state import SessionState


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


def _plan_mode_session() -> SessionState:
    session = SessionState(session_id="s", cwd="/tmp", mcp_servers=[])
    session.set_config_value("mode", "plan")
    return session


class TestPolicyRejectionCarriesReason:
    @pytest.mark.asyncio
    async def test_tool_result_names_mode_and_persistence(self) -> None:
        """Модель получает режим и то, что повтор бесполезен.

        Прежний текст «Tool execution rejected by policy for execute» не говорил
        ни того, ни другого: на живых прогонах модель повторяла `terminal/create`
        и работала с несуществующими терминалами до упора в лимит запросов.
        """
        processor = _make_processor()
        sink = AsyncMock()

        result = await processor._reject_tool_call(
            _plan_mode_session(),
            "s",
            "call_1",
            "terminal/create",
            "execute",
            "llm_1",
            sink,
        )

        assert result.success is False
        assert result.error is not None
        assert "terminal/create" in result.error
        assert "plan" in result.error
        assert "Повторный вызов даст тот же отказ" in result.error
        assert result.tool_call_id == "llm_1"
        processor._tool_registry.execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_reason_goes_to_client_notification(self) -> None:
        """Тот же текст уходит клиенту в content `tool_call_update`."""
        processor = _make_processor()
        sink = AsyncMock()

        await processor._reject_tool_call(
            _plan_mode_session(), "s", "call_1", "terminal/create", "execute", None, sink
        )

        content = processor._tool_call_handler.build_tool_update_notification.call_args.kwargs[
            "content"
        ]
        text = content[0]["content"]["text"]
        assert "plan" in text
        sink.emit_and_save_tool_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejection_is_logged_with_reason_and_mode(self) -> None:
        """Причина и режим попадают в лог — для разбора прогонов."""
        import structlog

        processor = _make_processor()

        with structlog.testing.capture_logs() as logs:
            await processor._reject_tool_call(
                _plan_mode_session(), "s", "call_1", "terminal/create", "execute", None, AsyncMock()
            )

        entry = next(log for log in logs if log["event"] == "tool_call_rejected")
        assert entry["mode"] == "plan"
        assert "read-only" in entry["reason"]

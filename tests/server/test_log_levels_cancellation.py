"""Уровни логирования: отмена и ошибки модели — не `error` (tech-debt P2-37).

Уровень `error` в логе сервера должен означать сбой сервера. Раньше его занимали
события, где сервер отработал верно: штатная отмена RPC по `session/cancel` и
обращение модели к несуществующему alias'у терминала. Из-за этого «0 ошибок за
прогон» перестал работать как критерий чистоты — а именно им проверяется
поведенческая нейтральность на живых прогонах (ADR-006).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from codelab.server.client_rpc.exceptions import ClientRPCCancelledError
from codelab.server.client_rpc.service import ClientRPCService
from codelab.server.protocol.state import SessionState
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge


@pytest.fixture
def session() -> SessionState:
    return SessionState(session_id="s", cwd="/tmp", mcp_servers=[])


def _bridge(**service_behaviour: object) -> ClientRPCBridge:
    service = AsyncMock(spec=ClientRPCService)
    for name, effect in service_behaviour.items():
        setattr(service, name, AsyncMock(side_effect=effect))
    return ClientRPCBridge(client_rpc_service=service)


def _levels(logs: list[dict], event: str) -> list[str]:
    return [log["log_level"] for log in logs if log["event"] == event]


class TestCancellationIsNotAnError:
    @pytest.mark.asyncio
    async def test_wait_terminal_exit_cancelled_logs_info(self, session: SessionState) -> None:
        """Отмена возвращает то же, что и раньше (None), но уровнем info."""
        bridge = _bridge(wait_for_exit=ClientRPCCancelledError("вызов отменён"))

        with structlog.testing.capture_logs() as logs:
            result = await bridge.wait_terminal_exit(session, "term_1")

        assert result is None
        assert _levels(logs, "client_rpc_cancelled") == ["info"]
        assert not [log for log in logs if log["log_level"] == "error"]

    @pytest.mark.asyncio
    async def test_read_file_cancelled_reraises_with_info(self, session: SessionState) -> None:
        """Для read_file поведение прежнее — проброс исключения, но без error."""
        bridge = _bridge(read_text_file=ClientRPCCancelledError("вызов отменён"))

        with structlog.testing.capture_logs() as logs, pytest.raises(ClientRPCCancelledError):
            await bridge.read_file(session, "/tmp/a.txt")

        assert _levels(logs, "client_rpc_cancelled") == ["info"]
        assert not [log for log in logs if log["log_level"] == "error"]

    @pytest.mark.asyncio
    async def test_release_terminal_cancelled_returns_false(self, session: SessionState) -> None:
        bridge = _bridge(release_terminal=ClientRPCCancelledError("вызов отменён"))

        with structlog.testing.capture_logs() as logs:
            result = await bridge.release_terminal(session, "term_1")

        assert result is False
        assert _levels(logs, "client_rpc_cancelled") == ["info"]


class TestModelMistakesAreWarnings:
    def test_unknown_terminal_alias_is_warning(self, session: SessionState) -> None:
        """Промах по alias — галлюцинация модели; сервер отработал верно."""
        from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor

        executor = TerminalToolExecutor(
            client_rpc_bridge=MagicMock(), permission_checker=MagicMock()
        )

        with structlog.testing.capture_logs() as logs:
            # Сессия без терминалов — alias не резолвится
            client_id, failure = executor._resolve_terminal(session, "term_9")

        assert client_id is None
        assert failure is not None
        assert _levels(logs, "terminal_alias_not_found") == ["warning"]

    @pytest.mark.asyncio
    async def test_unknown_tool_is_warning(self, session: SessionState) -> None:
        """Несуществующий инструмент — тоже галлюцинация, а не сбой сервера."""
        from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
            ToolCallProcessor,
        )

        processor = ToolCallProcessor(
            tool_registry=MagicMock(),
            tool_call_handler=MagicMock(),
            permission_manager=MagicMock(),
            content_extractor=AsyncMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            plan_builder=MagicMock(),
            global_policy_manager=MagicMock(),
        )
        processor._tool_registry.list_tools.return_value = []

        with structlog.testing.capture_logs() as logs:
            await processor._reject_unknown_tool(
                session, "s", "call_1", "hallucinated", "llm_1", AsyncMock()
            )

        assert _levels(logs, "tool not found in registry") == ["warning"]

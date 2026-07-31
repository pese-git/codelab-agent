"""Отмена turn'а не выглядит сбоем инструмента (tech-debt P2-50).

Найдено на живом прогоне `sess_f95e3fc5563d`: пользователь отменил turn, пока
клиентский `terminal/wait_for_exit` ждал 25 секунд. Отмена сработала штатно, но
вызов лёг на диск как `failed`, а модель получила «Ошибка при ожидании завершения
терминала» — то есть повод «починить» несуществующую поломку.

Причина была в асимметрии моста: fs-методы пробрасывали `ClientRPCCancelledError`,
а терминальные возвращали `None`/`False` и на отмену, и на сбой, поэтому executor
их не различал.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.client_rpc import ClientRPCCancelledError
from codelab.server.domain.session import Session as DomainSession
from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def session() -> DomainSession:
    session = make_domain_session(session_id="sess_1", cwd="/tmp", mcp_servers=[])
    session.runtime.terminals = {"term_1": "client-term-1"}
    session.runtime.terminal_counter = 1
    return session


def _bridge(**side_effects: BaseException) -> ClientRPCBridge:
    service = MagicMock()
    service.has_terminal_capability.return_value = True
    for name, error in side_effects.items():
        setattr(service, name, AsyncMock(side_effect=error))
    return ClientRPCBridge(service)


def _executor(bridge: ClientRPCBridge) -> TerminalToolExecutor:
    checker = MagicMock()
    return TerminalToolExecutor(client_rpc_bridge=bridge, permission_checker=checker)


@pytest.mark.asyncio
class TestCancelledResultIsMarkedCancelled:
    async def test_wait_for_exit_cancel_is_not_an_error(self, session: DomainSession) -> None:
        """Результат помечен `cancelled`, а текст не называет отмену ошибкой."""
        bridge = _bridge(
            terminal_output=ClientRPCCancelledError("RPC вызов terminal/output был отменён"),
            wait_for_exit=ClientRPCCancelledError("RPC вызов terminal/wait_for_exit был отменён"),
        )

        result = await _executor(bridge).execute_wait_for_exit(session, "term_1")

        assert result.cancelled is True
        assert result.success is False
        assert result.error is not None
        assert "отменено пользователем" in result.error
        assert "Ошибка" not in result.error

    async def test_create_cancel_is_not_an_error(self, session: DomainSession) -> None:
        bridge = _bridge(
            create_terminal=ClientRPCCancelledError("RPC вызов terminal/create был отменён")
        )

        result = await _executor(bridge).execute_create(session, "sleep 30")

        assert result.cancelled is True
        assert result.error is not None
        assert "отменено пользователем" in result.error

    async def test_failure_is_still_a_failure(self, session: DomainSession) -> None:
        """Сбой обязан остаться сбоем: признак отмены не должен его поглотить."""
        bridge = _bridge(wait_for_exit=RuntimeError("клиент отвалился"))

        result = await _executor(bridge).execute_wait_for_exit(session, "term_1")

        assert result.cancelled is False
        assert result.success is False

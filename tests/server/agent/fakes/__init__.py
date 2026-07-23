"""Fakes для тестов ядра агента (порты из `agent.contracts.ports`).

Позволяют тестировать ядро (`agent.core.*`) без Pydantic-фикстур
`protocol.state.SessionState` — driving-адаптер ACP заменяется фейком порта.
"""

from tests.server.agent.fakes.session_view import (
    FakeCapabilities,
    FakeSessionView,
)

__all__ = ["FakeCapabilities", "FakeSessionView"]

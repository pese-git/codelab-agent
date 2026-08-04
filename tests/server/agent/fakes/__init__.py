"""Fakes для тестов ядра агента (порты из `agent.contracts.ports`).

Позволяют тестировать ядро (`agent.core.*`) без Pydantic-фикстур
`protocol.state.SessionDocument` — driving-адаптер ACP заменяется фейком порта.
"""

from tests.server.agent.fakes.content_codec import FakeContentCodec
from tests.server.agent.fakes.llm import FakeLLM
from tests.server.agent.fakes.session_view import (
    FakeCapabilities,
    FakeSessionView,
)
from tests.server.agent.fakes.tool_gateway import FakeToolGateway

__all__ = [
    "FakeCapabilities",
    "FakeContentCodec",
    "FakeLLM",
    "FakeSessionView",
    "FakeToolGateway",
]

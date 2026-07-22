"""Фейки для тестов ядра агента (без Pydantic, без SessionState).

ADR-005 Фаза 1: ядро ``core/`` принимает ``SessionView`` Protocol.
Тесты должны иметь возможность конструировать ``SessionView`` без
Pydantic-фикстур и без ``SessionState`` (иначе — утечка в тесты).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from codelab.server.agent.contracts.ports import SessionView
from codelab.server.domain.conversation import ConversationMessage
from codelab.server.domain.session import SessionConfig
from codelab.server.domain.value_objects import SessionId
from codelab.shared.capabilities import ClientCapabilities


@dataclass
class FakeSessionView(SessionView):
    """In-memory реализация ``SessionView`` для unit-тестов ядра.

    Не зависит от ``SessionState`` (Pydantic) и от ``SessionMapper``.
    Принимает готовые доменные VO: ``SessionConfig`` и список
    ``ConversationMessage``.
    """

    session_id: str = "sess_test"
    cwd: str = "/tmp"
    config_values: dict[str, str] = field(default_factory=dict)
    active_strategy: str = "single"
    runtime_capabilities: ClientCapabilities | None = None
    messages_: list[ConversationMessage] = field(default_factory=list)

    @property
    def id(self) -> SessionId:
        return SessionId(self.session_id)

    @property
    def config(self) -> SessionConfig:
        return SessionConfig(
            cwd=self.cwd,
            config_values=dict(self.config_values),
            active_strategy=self.active_strategy,
            runtime_capabilities=self.runtime_capabilities,
        )

    def messages(self) -> Sequence[ConversationMessage]:
        return list(self.messages_)


__all__ = ["FakeSessionView"]

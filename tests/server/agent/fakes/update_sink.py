"""FakeUpdateSink — тестовая реализация UpdateSink (ADR-005, Фаза 3).

Используется в unit-тестах ядра. Собирает все вызовы emit_* в списки
для ассертов. Не отправляет ничего по сети.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from codelab.server.agent.contracts.ports import SessionView, UpdateSink


@dataclass
class UpdateCalls:
    """Все вызовы UpdateSink в одном объекте для удобства ассертов."""

    agent_message: list[tuple[str, str]] = field(default_factory=list)
    streaming_delta: list[tuple[str, str]] = field(default_factory=list)
    plan: list[tuple[str, Any]] = field(default_factory=list)
    tool_call: list[tuple[str, Any]] = field(default_factory=list)
    tool_update: list[tuple[str, Any]] = field(default_factory=list)


class FakeUpdateSink(UpdateSink):
    """Предсказуемая реализация ``UpdateSink`` для тестов.

    Все вызовы сохраняются в ``self.calls`` (и в типизированных списках).
    По умолчанию ``session_id_fn`` возвращает ``"sess_test"``; можно
    переопределить для кастомного ID.

    Не отправляет ничего по сети, не бросает исключений.
    """

    def __init__(
        self,
        session_id_fn: Callable[[SessionView], str] | None = None,
    ) -> None:
        self._session_id_fn: Callable[[SessionView], str] = (
            session_id_fn or (lambda view: str(view.id))
        )
        self.calls = UpdateCalls()

    def _sid(self, session: SessionView) -> str:
        return self._session_id_fn(session)

    async def emit_agent_message(self, session: SessionView, text: str) -> None:
        self.calls.agent_message.append((self._sid(session), text))

    async def emit_streaming_delta(self, session: SessionView, text: str) -> None:
        self.calls.streaming_delta.append((self._sid(session), text))

    async def emit_plan(self, session: SessionView, plan: Any) -> None:
        self.calls.plan.append((self._sid(session), plan))

    async def emit_tool_call(self, session: SessionView, call: Any) -> None:
        self.calls.tool_call.append((self._sid(session), call))

    async def emit_tool_update(self, session: SessionView, update: Any) -> None:
        self.calls.tool_update.append((self._sid(session), update))


__all__ = ["FakeUpdateSink", "UpdateCalls"]

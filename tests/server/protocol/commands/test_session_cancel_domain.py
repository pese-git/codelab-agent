"""`session/cancel` работает доменным агрегатом в области транзакции (фаза D ADR-006).

Гейт шага двойной. Во-первых, поведенческая нейтральность: транзакция пишет на
диск через `SessionMapper`, поэтому потеря поля переписала бы существующие сессии
(тот же гейт, что у `session/load`). Во-вторых, область транзакции обязана
заменить две последовательные записи одной — прежде отмена сохраняла сессию
дважды (`session_cancel.py:95` и `:108` в аудите ADR-006).
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog

from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.messages import ACPMessage
from codelab.server.protocol.commands.session_cancel import SessionCancelCommandHandler
from codelab.server.protocol.handlers.prompt_orchestrator import PromptOrchestrator
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.session_factory import SessionFactory
from codelab.server.protocol.state import ActiveTurnState, SessionState, ToolCallState
from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry
from codelab.server.storage import InMemoryStorage, SessionRepository
from codelab.server.storage.base import SessionStorage


class _CountingStorage(InMemoryStorage):
    """Backend, считающий записи: гейт «одна запись на транзакцию»."""

    def __init__(self) -> None:
        super().__init__()
        self.saves = 0

    async def save_session(self, session: SessionState) -> None:
        self.saves += 1
        await super().save_session(session)


def _orchestrator(registry: TurnCancellationRegistry | None = None) -> PromptOrchestrator:
    """Оркестратор для пути отмены: реальны tool-call хендлер и реестр сигнала."""
    from unittest.mock import MagicMock

    return PromptOrchestrator(
        state_manager=MagicMock(),
        plan_builder=MagicMock(),
        turn_lifecycle_manager=MagicMock(),
        tool_call_handler=ToolCallHandler(),
        permission_manager=MagicMock(),
        tool_registry=MagicMock(),
        llm_loop_stage=MagicMock(),
        command_registry=MagicMock(),
        pipeline=MagicMock(),
        turn_cancellation=registry,
    )


def _handler(
    storage: SessionStorage,
    orchestrator: PromptOrchestrator,
    llm_adapter: Any | None = None,
) -> SessionCancelCommandHandler:
    async def provider() -> PromptOrchestrator:
        return orchestrator

    return SessionCancelCommandHandler(
        repository=SessionRepository(backend=storage),
        orchestrator_provider=provider,
        llm_adapter=llm_adapter,
    )


def _session_in_turn(*, permission_request_id: str | None = None) -> SessionState:
    session = SessionFactory.create_session(cwd="/tmp")
    session.tool_calls["call_001"] = ToolCallState(
        tool_call_id="call_001",
        title="terminal/create",
        kind="execute",
        status="pending",
        tool_call_id_from_llm="chatcmpl-tool-abc",
    )
    session.tool_call_counter = 1
    session.history.append(
        {
            "role": "assistant",
            "text": "",
            "tool_calls": [{"id": "chatcmpl-tool-abc", "name": "terminal_create", "arguments": {}}],
        }
    )
    session.active_turn = ActiveTurnState(
        prompt_request_id="prompt_req",
        session_id=session.session_id,
        permission_request_id=permission_request_id,
        phase="running",
    )
    return session


@pytest.mark.asyncio
class TestCancelTransaction:
    async def test_state_is_persisted_once(self) -> None:
        """Отмена ложится на диск, и ровно одной записью."""
        storage = _CountingStorage()
        session = _session_in_turn()
        await storage.save_session(session)
        storage.saves = 0

        message = ACPMessage.request(
            "session/cancel",
            {"sessionId": session.session_id},
            request_id="cancel_1",
        )
        outcome = await _handler(storage, _orchestrator()).handle(message)

        assert storage.saves == 1
        stored = await storage.load_session(session.session_id)
        assert stored is not None
        assert stored.active_turn is None
        assert stored.tool_calls["call_001"].status == "cancelled"
        # Отменённый вызов получил `role: tool` (P2-38) — и это тоже на диске
        answers = [m for m in stored.history if m.role == "tool"]
        assert [m.tool_call_id for m in answers] == ["chatcmpl-tool-abc"]
        # Отмена ушла и в реплей
        replayed = [
            e
            for e in stored.events_history
            if (e.get("update") or {}).get("sessionUpdate") == "tool_call_update"
        ]
        assert [e["update"]["status"] for e in replayed] == ["cancelled"]
        # Ответ на отложенный `session/prompt` отдан клиенту и снят с состояния
        assert [m.id for m in outcome.followup_responses] == ["prompt_req"]
        assert stored.pending_prompt_response is None

    async def test_log_reports_answered_deferred_prompt(self) -> None:
        """Лог обязан показывать, ответили ли на отложенный `session/prompt`.

        Счётчик считался до сбора followup, поэтому по логу это было не видно.
        """
        storage = InMemoryStorage()
        session = _session_in_turn()
        await storage.save_session(session)

        with structlog.testing.capture_logs() as logs:
            await _handler(storage, _orchestrator()).handle(
                ACPMessage.request(
                    "session/cancel",
                    {"sessionId": session.session_id},
                    request_id="cancel_1",
                )
            )

        handled = [e for e in logs if e["event"] == "session_cancel_handled"]
        assert len(handled) == 1
        assert handled[0]["deferred_prompt_answered"] is True
        assert handled[0]["followup_count"] == 1

    async def test_permission_tombstone_survives_write(self) -> None:
        """Tombstone нужен, чтобы поздний ответ поглощался тихо, а не -32603."""
        storage = InMemoryStorage()
        session = _session_in_turn(permission_request_id="perm_1")
        await storage.save_session(session)

        message = ACPMessage.request(
            "session/cancel",
            {"sessionId": session.session_id},
            request_id="cancel_1",
        )
        await _handler(storage, _orchestrator()).handle(message)

        stored = await storage.load_session(session.session_id)
        assert stored is not None
        assert stored.is_permission_cancelled("perm_1")

    async def test_round_trip_changes_only_cancel_related_fields(self) -> None:
        """Гейт нейтральности: транзакция не переписывает остальной документ.

        Меняться вправе только состояние отмены и метка записи; всё прочее
        обязано пройти конверсию домен↔wire без изменений.
        """
        storage = InMemoryStorage()
        session = _session_in_turn()
        await storage.save_session(session)
        before = (await storage.load_session(session.session_id)).model_dump(mode="json")

        message = ACPMessage.request(
            "session/cancel",
            {"sessionId": session.session_id},
            request_id="cancel_1",
        )
        await _handler(storage, _orchestrator()).handle(message)

        after = (await storage.load_session(session.session_id)).model_dump(mode="json")
        changed = {key for key in before if before[key] != after[key]}
        assert changed == {
            "active_turn",
            "tool_calls",
            "history",
            "events_history",
            "updated_at",
            "revision",
        }

    async def test_missing_session_id_does_not_write(self) -> None:
        """Отклонённый запрос не штампует `updated_at` (валидация до транзакции)."""
        storage = _CountingStorage()
        session = _session_in_turn()
        await storage.save_session(session)
        storage.saves = 0

        outcome = await _handler(storage, _orchestrator()).handle(
            ACPMessage.request("session/cancel", {}, request_id="cancel_1")
        )

        assert outcome.response is None
        assert storage.saves == 0

    async def test_unknown_session_does_not_write(self) -> None:
        storage = _CountingStorage()

        outcome = await _handler(storage, _orchestrator()).handle(
            ACPMessage.request(
                "session/cancel", {"sessionId": "missing"}, request_id="cancel_1"
            )
        )

        assert outcome.response is not None
        assert outcome.response.result is None
        assert storage.saves == 0

    async def test_cancel_signal_reaches_process_registry(self) -> None:
        """Сигнал живёт в реестре, а не в состоянии: копию turn не увидит (P0-39)."""
        storage = InMemoryStorage()
        session = _session_in_turn()
        await storage.save_session(session)
        registry = TurnCancellationRegistry()
        started = registry.generation(session.session_id)

        await _handler(storage, _orchestrator(registry)).handle(
            ACPMessage.request(
                "session/cancel",
                {"sessionId": session.session_id},
                request_id="cancel_1",
            )
        )

        assert registry.is_cancelled(session.session_id, started) is True

    async def test_domain_state_matches_mapper_round_trip(self) -> None:
        """Сохранённый документ — ровно то, что даёт маппер из агрегата."""
        storage = InMemoryStorage()
        session = _session_in_turn()
        await storage.save_session(session)

        domain = SessionMapper.to_domain(session)
        _orchestrator().handle_cancel(
            request_id="cancel_1",
            params={"sessionId": session.session_id},
            session=domain,
        )
        expected = SessionMapper.to_protocol(domain).model_dump(mode="json")
        # Отложенный ответ снимает сам обработчик, отдав его клиенту
        expected["pending_prompt_response"] = None

        await _handler(storage, _orchestrator()).handle(
            ACPMessage.request(
                "session/cancel",
                {"sessionId": session.session_id},
                request_id="cancel_1",
            )
        )
        stored = (await storage.load_session(session.session_id)).model_dump(mode="json")

        # Метки времени и ревизия ставятся при записи, история несёт timestamp'ы
        for volatile in ("updated_at", "revision", "events_history"):
            expected.pop(volatile, None)
            stored.pop(volatile, None)
        assert stored == expected

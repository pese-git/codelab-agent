"""Отмена действительно останавливает turn (P0-39).

Сигнал отмены живёт в процессном реестре, а не в `SessionState`, и это не
стилистический выбор: у каждого JSON-RPC запроса своя копия сессии,
десериализованная из `JsonFileStorage`, поэтому запись в состояние идущий turn не
видит. Доказано пробами id объектов на e2e-прогоне: turn держал копию с
поколением 0, отмена инкрементировала другую копию.

Живая хронология дефекта (`sess_142dec045e89`): turn продолжался 52 секунды после
отмены — 12 новых tool call'ов и 8 запросов разрешения, причём клиенту уже был
отправлен `stop_reason: cancelled`.

Сквозная проверка — `tests/server/test_cancel_during_rpc_e2e.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.protocol.handlers.prompt_orchestrator import PromptOrchestrator
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.state import ActiveTurnState, SessionState, ToolCallState
from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry


def _session_in_turn() -> SessionState:
    session = SessionState(session_id="s", cwd="/tmp", mcp_servers=[])
    session.set_config_value("mode", "standard")
    session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="s")
    return session


def _orchestrator(registry: TurnCancellationRegistry) -> PromptOrchestrator:
    """Оркестратор для пути отмены: реальны реестр сигнала и tool-call хендлер.

    Остальные компоненты `handle_cancel` не задействует — мутации состояния делают
    доменные сеймы агрегата (фаза D ADR-006).
    """
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


def _processor(registry: TurnCancellationRegistry | None) -> ToolCallProcessor:
    return ToolCallProcessor(
        tool_registry=MagicMock(),
        tool_call_handler=MagicMock(),
        permission_manager=MagicMock(),
        content_extractor=AsyncMock(),
        content_validator=MagicMock(),
        content_formatter=MagicMock(),
        plan_builder=MagicMock(),
        global_policy_manager=MagicMock(),
        turn_cancellation=registry,
    )


class TestSignalSurvivesSessionCopies:
    """Ядро дефекта: сигнал не должен зависеть от копии состояния."""

    def test_cancel_is_visible_to_holder_of_another_session_copy(self) -> None:
        registry = TurnCancellationRegistry()
        started = registry.generation("s")
        # Отмена работает со своей копией сессии — turn о ней ничего не знает
        cancel_side_copy = _session_in_turn()
        cancel_side_copy.active_turn = None
        registry.cancel("s")

        turn_side_copy = _session_in_turn()

        assert _processor(registry)._is_cancel_requested(turn_side_copy, started, "s") is True

    def test_not_cancelled_without_registry_entry(self) -> None:
        registry = TurnCancellationRegistry()
        session = _session_in_turn()

        result = _processor(registry)._is_cancel_requested(
            session, registry.generation("s"), "s"
        )

        assert result is False

    def test_active_turn_flag_remains_second_source(self) -> None:
        """Флаг в живом `active_turn` по-прежнему признаётся отменой."""
        registry = TurnCancellationRegistry()
        session = _session_in_turn()
        session.active_turn.cancel_requested = True

        result = _processor(registry)._is_cancel_requested(
            session, registry.generation("s"), "s"
        )

        assert result is True

    def test_generation_is_monotonic_per_session(self) -> None:
        registry = TurnCancellationRegistry()

        registry.cancel("s")
        registry.cancel("s")

        assert registry.generation("s") == 2
        # Отмена одной сессии не гасит другую
        assert registry.generation("other") == 0

    def test_next_turn_after_cancel_is_not_pre_cancelled(self) -> None:
        """Новый turn берёт актуальное поколение и не считается отменённым."""
        registry = TurnCancellationRegistry()
        registry.cancel("s")
        session = _session_in_turn()

        started = registry.generation("s")

        assert _processor(registry)._is_cancel_requested(session, started, "s") is False

    def test_missing_registry_degrades_to_flag_only(self) -> None:
        """Без реестра (тесты, демо-режим) проверка не падает."""
        session = _session_in_turn()

        assert _processor(None)._is_cancel_requested(session, 0, "s") is False


class TestCancelledTurnIsNotResumed:
    """`execute_pending_tool` не толкает отменённый turn дальше."""

    @pytest.mark.asyncio
    async def test_pending_tool_is_refused_when_turn_is_gone(self) -> None:
        from codelab.server.agent.core.system_prompt_builder import SystemPromptBuilder
        from codelab.server.protocol.handlers.pipeline.stages.llm_loop import LLMLoopStage
        from codelab.server.protocol.stop_reasons import StopReason

        stage = LLMLoopStage(
            tool_registry=MagicMock(),
            tool_call_handler=MagicMock(),
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            plan_builder=MagicMock(),
            system_prompt_builder=SystemPromptBuilder(global_prompt=""),
            strategy_dispatcher=MagicMock(),
        )
        session = _session_in_turn()
        session.tool_calls["call_001"] = ToolCallState(
            tool_call_id="call_001", title="fs/read_text_file", kind="read", status="pending"
        )
        # Отмена сохранила сессию с очищенным active_turn; следующая загрузка
        # (в BackgroundExecutor) видит именно это состояние
        session.active_turn = None

        result = await stage.execute_pending_tool(
            session=session,
            session_id="s",
            tool_call_id="call_001",
            notification_callback=AsyncMock(),
        )

        assert result.stop_reason == StopReason.CANCELLED
        assert result.notifications == []


class TestHandleCancelRegistersCancellation:
    """`handle_cancel` обязан отметить отмену в реестре."""

    def test_cancel_increments_generation(self) -> None:
        """Проверка идёт через настоящий `handle_cancel`, а не его пересказ."""
        registry = TurnCancellationRegistry()
        session = SessionMapper.to_domain(_session_in_turn())
        started = registry.generation("s")

        _orchestrator(registry).handle_cancel(
            request_id="cancel_1",
            params={"sessionId": "s"},
            session=session,
        )

        assert session.active_turn is None
        assert registry.is_cancelled("s", started) is True


class TestLoopStopsWhenCancelArrivesMidTurn:
    """Отмена приходит, пока LLM-запрос в полёте: цикл обязан остановиться."""

    @pytest.mark.asyncio
    async def test_no_tool_calls_created_after_cancel_during_llm_call(self) -> None:
        from codelab.server.agent.core.agent_base import AgentResponse
        from codelab.server.protocol.handlers.pipeline.stages.agent_loop.loop import AgentLoop
        from codelab.server.protocol.stop_reasons import StopReason

        registry = TurnCancellationRegistry()
        session = _session_in_turn()

        tool_call = MagicMock()
        tool_call.id = "llm_1"
        tool_call.name = "fs/read_text_file"
        tool_call.arguments = {"path": "/tmp/a.txt"}

        response = MagicMock(spec=AgentResponse)
        response.text = ""
        response.tool_calls = [tool_call]
        response.plan = None
        response.usage = None

        strategy = MagicMock()

        async def _cancel_while_llm_in_flight(*args, **kwargs):
            # Пользователь нажал стоп, пока ответ модели ещё не пришёл
            registry.cancel("s")
            return response

        strategy.execute = AsyncMock(side_effect=_cancel_while_llm_in_flight)

        spb = MagicMock()
        spb.build.return_value = ""
        tool_call_handler = MagicMock()
        loop = AgentLoop(
            strategy=strategy,
            tool_registry=MagicMock(),
            tool_call_handler=tool_call_handler,
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=AsyncMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            history_writer=MagicMock(),
            plan_builder=MagicMock(),
            system_prompt_builder=spb,
            turn_cancellation=registry,
        )

        result = await loop.run(session, "s", "Прочитай файл")

        assert result.stop_reason == StopReason.CANCELLED
        tool_call_handler.create_tool_call.assert_not_called()
        assert session.tool_calls == {}

"""Пошаговые записи turn'а (ADR-007).

До этого turn копил мутации в своей копии и писал один раз в конце: на живом
прогоне копия расходилась с диском 39 секунд, и слияние приходилось применять как
постоянное лечение, а не как редкую развязку.

Теперь состояние сохраняется на границах шагов — после каждого обработанного вызова
и перед паузой на разрешение. Окно сокращается до длительности одного вызова.

Полный вариант (turn вообще не держит состояние, каждый шаг работает против свежей
копии) остаётся целью: он снимает слияние совсем, но требует переезда turn-пути на
доменный агрегат.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.protocol.state import ActiveTurnState, SessionState


def _processor() -> ToolCallProcessor:
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


def _session() -> SessionState:
    # plan: вызовы отклоняются политикой, то есть обрабатываются без реального
    # исполнения инструмента — достаточно, чтобы проверить точки записи
    session = SessionState(session_id="s", cwd="/tmp", mcp_servers=[])
    session.set_config_value("mode", "plan")
    session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="s")
    return session


class _Call:
    def __init__(self, id_: str) -> None:
        self.id = id_
        self.name = "fs/read_text_file"
        self.arguments = {"path": "a.md"}


class TestStepPersistence:
    @pytest.mark.asyncio
    async def test_persist_called_after_each_processed_call(self) -> None:
        """Каждый обработанный вызов кладётся на диск, а не ждёт конца turn'а."""
        processor = _processor()
        session = _session()
        calls: list[int] = []

        async def _persist() -> None:
            calls.append(len(session.history))

        await processor.process_batch(
            session, "s", [_Call("llm_1"), _Call("llm_2")], AsyncMock(), None, None, _persist
        )

        assert len(calls) == 2, "по одной записи на вызов"

    @pytest.mark.asyncio
    async def test_persist_called_before_permission_pause(self) -> None:
        """Отложенный хвост должен лечь на диск до паузы.

        Ответ на разрешение придёт отдельным запросом и загрузит сессию заново — если
        хвост остался только в памяти, он потеряется (P2-40 живёт в состоянии).
        """
        processor = _processor()
        session = _session()
        persisted: list[int] = []

        async def _persist() -> None:
            persisted.append(len(session.active_turn.pending_batch))

        async def _pause_first(*args, **kwargs):
            from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
                _ToolCallStep,
            )

            return _ToolCallStep(pause_tool_call_id="call_001")

        processor._process_single_tool_call = _pause_first  # type: ignore[method-assign]

        await processor.process_batch(
            session,
            "s",
            [_Call("llm_1"), _Call("llm_2"), _Call("llm_3")],
            AsyncMock(),
            None,
            None,
            _persist,
        )

        assert persisted == [2], "хвост из двух вызовов сохранён до паузы"

    @pytest.mark.asyncio
    async def test_write_failure_does_not_abort_turn(self) -> None:
        """Сбой записи логируется, но turn продолжается.

        Срывать работу из-за временного сбоя диска хуже: финальное сохранение даст
        второй шанс. Молчать при этом нельзя — молчание скрывало потерю в P2-42.
        """
        processor = _processor()
        session = _session()
        attempts = 0

        async def _failing() -> None:
            nonlocal attempts
            attempts += 1
            raise OSError("диск недоступен")

        result = await processor.process_batch(
            session, "s", [_Call("llm_1"), _Call("llm_2")], AsyncMock(), None, None, _failing
        )

        assert attempts == 2, "сбой не должен останавливать обработку следующих вызовов"
        assert result.pending_permission is False

    @pytest.mark.asyncio
    async def test_no_persist_callback_is_allowed(self) -> None:
        """Путь без хранилища (демо, тесты) должен работать без записи."""
        processor = _processor()
        session = _session()

        result = await processor.process_batch(
            session, "s", [_Call("llm_1")], AsyncMock(), None, None, None
        )

        assert result.pending_permission is False

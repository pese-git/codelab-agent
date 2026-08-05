"""Пошаговые записи turn'а: гейты команд (ADR-006, фаза D шаг 4; ADR-007).

До фазы D turn копил мутации в своей копии и писал их отдельным `persist`-ом:
на живом прогоне копия расходилась с диском 39 секунд, а запись документа,
пережившего `await`, приходилось примирять слиянием.

Теперь запись — не послесловие, а сама операция: каждое изменение состояния
применяется к агрегату, загруженному в момент применения, и коммитится своей
короткой транзакцией. Гейты ниже проверяют именно это, и на `JsonFileStorage`,
а не на памяти: на in-memory backend класс дефектов «мутировали и не сохранили»
невидим (P1-49).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.session import TurnState
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
)
from codelab.server.protocol.session_commands import SessionCommands
from codelab.server.storage import JsonFileStorage, SessionRepository
from tests.server._domain_sessions import make_domain_session


def _processor() -> ToolCallProcessor:
    return ToolCallProcessor(
        tool_registry=MagicMock(),
        tool_call_handler=MagicMock(),
        permission_manager=MagicMock(),
        content_extractor=AsyncMock(),
        content_validator=MagicMock(),
        plan_builder=MagicMock(),
        global_policy_manager=MagicMock(),
    )


def _session() -> DomainSession:
    # plan: вызовы отклоняются политикой, то есть обрабатываются без реального
    # исполнения инструмента — достаточно, чтобы проверить точки записи
    session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])
    session.set_config_value("mode", "plan")
    session.active_turn = TurnState(prompt_request_id="req_1", session_id="s")
    return session


async def _seeded(
    tmp_path: Path, session: DomainSession
) -> tuple[SessionRepository, SessionCommands]:
    """Репозиторий поверх файлового backend'а с посеянной сессией."""
    repository = SessionRepository(JsonFileStorage(tmp_path))
    state = SessionMapper.to_protocol(session)
    await repository._backend.save_session(state)
    session.revision = state.revision
    return repository, SessionCommands(repository, session)


async def _on_disk(repository: SessionRepository) -> DomainSession:
    """Сессия, прочитанная с диска, — единственный источник правды для гейтов."""
    stored = await repository.load_session("s")
    assert stored is not None
    return stored


class _Call:
    def __init__(self, id_: str) -> None:
        self.id = id_
        self.name = "fs/read_text_file"
        self.arguments = {"path": "a.md"}


class TestEveryStepReachesDisk:
    @pytest.mark.asyncio
    async def test_each_processed_call_is_on_disk(self, tmp_path: Path) -> None:
        """Каждый обработанный вызов лежит на диске, а не ждёт конца turn'а."""
        processor = _processor()
        session = _session()
        repository, commands = await _seeded(tmp_path, session)

        await processor.process_batch(
            commands, "s", [_Call("llm_1"), _Call("llm_2")], AsyncMock(), None, None
        )

        stored = await _on_disk(repository)
        answered = [
            message
            for message in SessionMapper.to_protocol(stored).history
            if getattr(message, "role", None) == "tool"
        ]
        assert len(answered) == 2, "оба вызова отвечены модели и это видно на диске"

    @pytest.mark.asyncio
    async def test_deferred_tail_is_on_disk_before_pause(self, tmp_path: Path) -> None:
        """Отложенный хвост ложится на диск до паузы.

        Ответ на разрешение придёт отдельным запросом и загрузит сессию заново —
        если хвост остался только в памяти, он потеряется (P2-40 живёт в
        состоянии).
        """
        processor = _processor()
        session = _session()
        repository, commands = await _seeded(tmp_path, session)

        async def _pause_first(*args, **kwargs):
            from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
                _ToolCallStep,
            )

            return _ToolCallStep(pause_tool_call_id="call_001")

        processor._process_single_tool_call = _pause_first  # type: ignore[method-assign]

        await processor.process_batch(
            commands,
            "s",
            [_Call("llm_1"), _Call("llm_2"), _Call("llm_3")],
            AsyncMock(),
            None,
            None,
        )

        stored = await _on_disk(repository)
        assert stored.active_turn is not None
        assert len(stored.active_turn.pending_batch) == 2, "хвост из двух вызовов на диске"

    @pytest.mark.asyncio
    async def test_write_failure_is_visible_to_caller(self, tmp_path: Path) -> None:
        """Сбой записи не проглатывается.

        Раньше запись была послесловием, и её ошибку можно было залогировать и
        продолжить — финальное сохранение давало второй шанс. Теперь второго шанса
        нет: несостоявшаяся команда означает, что состояния turn'а не существует, и
        молчать об этом — это ровно та потеря решений, что была P2-42.
        """
        processor = _processor()
        session = _session()
        repository, commands = await _seeded(tmp_path, session)

        async def _failing(_state: object) -> None:
            raise OSError("диск недоступен")

        repository._backend.save_session = _failing  # type: ignore[method-assign]

        with pytest.raises(OSError, match="диск недоступен"):
            await processor.process_batch(
                commands, "s", [_Call("llm_1")], AsyncMock(), None, None
            )

    @pytest.mark.asyncio
    async def test_one_command_one_revision(self, tmp_path: Path) -> None:
        """Одна команда — одна ревизия, и рабочая копия знает состоявшуюся.

        Вторая половина — не деталь: `save_session` штампует ревизию на
        wire-документе, а turn держит агрегат. Без возврата штампа копия навсегда
        осталась бы на ревизии загрузки, и следующая запись упёрлась бы в
        compare-and-set (на шаге 3 этот же класс дал зависший turn).
        """
        session = _session()
        repository, commands = await _seeded(tmp_path, session)
        before = (await _on_disk(repository)).revision

        await commands.apply(lambda target: target.set_title("одна команда"), name="title_set")

        after = (await _on_disk(repository)).revision
        assert after - before == 1
        assert session.revision == after

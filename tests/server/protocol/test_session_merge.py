"""Слияние состояния сессии при конфликте ревизий (ADR-007).

Воспроизводимый до правки сценарий: `session/prompt` держит копию весь turn (по
живым логам 7–52 с), посреди turn'а приходит `session/cancel` и сохраняет свою
копию, финальная запись turn'а отклоняется по ревизии — и накопленные результаты
инструментов теряются. Обернуть turn в транзакцию нельзя: блокировка удерживалась бы
весь turn, и отмена перестала бы работать.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.server.models import HistoryMessage
from codelab.server.protocol.session_merge import (
    merge_session_states,
    save_session_merging,
)
from codelab.server.protocol.state import ActiveTurnState, SessionState, ToolCallState
from codelab.server.storage import JsonFileStorage


def _session() -> SessionState:
    return SessionState(session_id="sess_x", cwd="/w", mcp_servers=[])


class TestTurnResultsSurviveCancel:
    """Главный сценарий: результаты turn'а не теряются, решения отмены сохраняются."""

    @pytest.mark.asyncio
    async def test_turn_history_and_cancel_decision_both_survive(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())

        turn_copy = await storage.load_session("sess_x")
        assert turn_copy is not None
        turn_copy.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_x")

        cancel_copy = await storage.load_session("sess_x")
        assert cancel_copy is not None
        cancel_copy.active_turn = None
        cancel_copy.history.append(
            {"role": "tool", "tool_call_id": "llm_9", "content": "Вызов не выполнялся: отменён"}
        )
        await storage.save_session(cancel_copy)

        turn_copy.history.append(
            {"role": "tool", "tool_call_id": "llm_1", "content": "результат работы"}
        )
        await save_session_merging(storage, turn_copy)

        on_disk = await storage.load_session("sess_x")
        assert on_disk is not None
        answered = {
            m.get("tool_call_id") if isinstance(m, dict) else m.tool_call_id
            for m in on_disk.history
        }
        assert answered == {"llm_1", "llm_9"}, "должны сохраниться обе стороны"
        assert on_disk.active_turn is None, "turn не должен воскресать после отмены"

    @pytest.mark.asyncio
    async def test_plain_save_when_no_conflict(self, tmp_path: Path) -> None:
        """Без конфликта — обычная запись, без лишнего чтения."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        session = await storage.load_session("sess_x")
        assert session is not None
        loads = 0
        original = storage.load_session

        async def _counting(session_id: str):
            nonlocal loads
            loads += 1
            return await original(session_id)

        storage.load_session = _counting  # type: ignore[method-assign]
        session.set_title("T")
        await save_session_merging(storage, session)

        assert loads == 0

    @pytest.mark.asyncio
    async def test_deleted_session_is_not_resurrected(self, tmp_path: Path) -> None:
        """Сессию удалили, пока turn работал — слияние не должно её вернуть."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        turn_copy = await storage.load_session("sess_x")
        assert turn_copy is not None
        other = await storage.load_session("sess_x")
        assert other is not None
        await storage.save_session(other)
        await storage.delete_session("sess_x")

        await save_session_merging(storage, turn_copy)

        assert await storage.load_session("sess_x") is None


class TestMergeRules:
    """Правила слияния зафиксированы: «слить как-нибудь» — тихая потеря решений."""

    def test_cancelled_status_is_not_overwritten_by_turn_result(self) -> None:
        base, mine = _session(), _session()
        base.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1", title="terminal/create", kind="execute", status="cancelled"
        )
        mine.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1",
            title="terminal/create",
            kind="execute",
            status="completed",
            content=[{"type": "content"}],
        )

        merged = merge_session_states(base=base, mine=mine)

        assert merged.tool_calls["call_1"].status == "cancelled", "отмена главнее"
        # Содержимое берём: оно описывает, чем вызов успел закончиться
        assert merged.tool_calls["call_1"].content == [{"type": "content"}]

    def test_non_cancelled_status_is_taken_from_turn(self) -> None:
        base, mine = _session(), _session()
        base.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1", title="fs/read", kind="read", status="pending"
        )
        mine.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1", title="fs/read", kind="read", status="completed"
        )

        merged = merge_session_states(base=base, mine=mine)

        assert merged.tool_calls["call_1"].status == "completed"

    def test_active_turn_comes_from_fresh_copy(self) -> None:
        base, mine = _session(), _session()
        base.active_turn = None
        mine.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_x")

        merged = merge_session_states(base=base, mine=mine)

        assert merged.active_turn is None

    def test_append_only_logs_keep_both_tails_in_order(self) -> None:
        base, mine = _session(), _session()
        ancestor = [{"role": "user", "content": "общий"}]
        base.history = [*ancestor, {"role": "assistant", "text": "чужая"}]
        mine.history = [*ancestor, {"role": "assistant", "text": "своя"}]

        merged = merge_session_states(base=base, mine=mine)

        texts = [m.get("text") for m in merged.history if isinstance(m, dict)]
        assert texts == [None, "чужая", "своя"], "предок один, чужой хвост раньше своего"

    def test_no_duplicate_when_mine_is_ahead_of_base(self) -> None:
        """Если чужих добавлений не было, свой журнал переносится без дублей."""
        base, mine = _session(), _session()
        base.history = [{"role": "user", "content": "a"}]
        mine.history = [{"role": "user", "content": "a"}, {"role": "assistant", "text": "b"}]

        merged = merge_session_states(base=base, mine=mine)

        assert len(merged.history) == 2

    def test_mixed_entry_forms_are_recognized_as_the_same_record(self) -> None:
        """Одна и та же запись в двух формах — не повод считать её разной.

        Прежние тесты сравнивали dict с dict и потому дефекта не видели: в бою
        запись, добавленная в этом процессе, — плоский dict, а прочитанная с
        диска — `HistoryMessage` (tech-debt P1-45).
        """
        base, mine = _session(), _session()
        entry = {"role": "tool", "tool_call_id": "llm_1", "content": "результат"}
        base.history = [HistoryMessage.model_validate(entry)]
        mine.history = [dict(entry)]

        merged = merge_session_states(base=base, mine=mine)

        assert len(merged.history) == 1, "запись в двух формах не должна задвоиться"

    @pytest.mark.asyncio
    async def test_tail_already_on_disk_is_not_duplicated(self, tmp_path: Path) -> None:
        """Пошаговые записи turn'а не должны приводить к дублям при слиянии.

        Сценарий с живого прогона `sess_ffff9be366bd`: turn пишет состояние на
        каждом шаге, поэтому его хвост УЖЕ на диске; затем приходит отмена, и
        финальная запись turn'а конфликтует. До правки правило «дописать свой
        хвост» дописывало его повторно — пять `tool_call_id` получали по два
        ответа `role: tool`, что нарушает контракт LLM-API (родня P2-38).
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())

        turn_copy = await storage.load_session("sess_x")
        assert turn_copy is not None
        turn_copy.add_assistant_message("вызываю инструмент")
        turn_copy.add_tool_result("llm_1", "результат работы")
        # Пошаговая запись turn'а: хвост оказывается на диске
        await storage.save_session(turn_copy)

        cancel_copy = await storage.load_session("sess_x")
        assert cancel_copy is not None
        cancel_copy.add_tool_result("llm_2", "Вызов не выполнялся: turn отменён")
        cancel_copy.active_turn = None
        await storage.save_session(cancel_copy)

        # Финальная запись turn'а: его копия устарела на ревизию отмены
        await save_session_merging(storage, turn_copy)

        on_disk = await storage.load_session("sess_x")
        assert on_disk is not None
        answers = [
            m.tool_call_id if isinstance(m, HistoryMessage) else m.get("tool_call_id")
            for m in on_disk.history
            if (m.role if isinstance(m, HistoryMessage) else m.get("role")) == "tool"
        ]
        assert answers == ["llm_1", "llm_2"], "на каждый вызов ровно один ответ"
        assert len(on_disk.history) == 3, "дублей записей быть не должно"

    def test_counters_take_maximum(self) -> None:
        """Иначе следующий вызов получил бы занятый идентификатор."""
        base, mine = _session(), _session()
        base.tool_call_counter, mine.tool_call_counter = 3, 7
        base.terminal_counter, mine.terminal_counter = 5, 2

        merged = merge_session_states(base=base, mine=mine)

        assert merged.tool_call_counter == 7
        assert merged.terminal_counter == 5

    def test_events_history_merged_too(self) -> None:
        """Реплей клиенту не должен терять события ни одной из сторон."""
        base, mine = _session(), _session()
        shared = [{"type": "session_update", "update": {"sessionUpdate": "tool_call"}}]
        base.events_history = [*shared, {"type": "session_update", "update": {"n": "чужое"}}]
        mine.events_history = [*shared, {"type": "session_update", "update": {"n": "своё"}}]

        merged = merge_session_states(base=base, mine=mine)

        assert len(merged.events_history) == 3

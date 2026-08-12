"""Матрица переходов фазы turn'а — на доменном API (`TurnState.transition_to`).

**Перенесено из `tests/server/test_turn_lifecycle_manager.py` (P2-54, 2026-08-12), а не
переписано.** Правила и формулировки сохранены дословно: тесты сертифицировали матрицу
через `TurnLifecycleManager.set_turn_phase` — мёртвый метод, у которого не было
вызывающих в проде. Матрица живёт в агрегате с шага 2 ADR-008, поэтому и проверять её
надо там, где её применяет живой путь. Удалить эти тесты вместе с методом означало бы
потерять единственное покрытие матрицы: доменные тесты покрывали только чтение фазы из
wire (`turn_phase_from_wire`).

Добавлено то, что прежде проверить было нечем: отказ перехода **логируется**. Пока
единственным входом был мёртвый метод, событие `turn_phase_transition_rejected` было
недостижимо — ровно тот класс «код без наблюдаемого следствия», который проект уже
находил шесть раз.
"""

from __future__ import annotations

import structlog

from codelab.server.domain.session import TurnState
from codelab.server.domain.value_objects import (
    AwaitingClientRpc,
    AwaitingPermission,
    Completing,
    Running,
    TurnCancelled,
    TurnPhase,
)


def _turn(phase: TurnPhase) -> TurnState:
    return TurnState(prompt_request_id="req_1", session_id="sess_1", phase=phase)


class TestAllowedTransitions:
    def test_running_to_any_phase(self) -> None:
        """От running можно перейти в любую фазу."""
        for target in (
            AwaitingPermission.of(request_id="perm_1", tool_call_id="call_1"),
            AwaitingClientRpc(),
            TurnCancelled(),
            Completing(),
        ):
            turn = _turn(Running())
            assert turn.transition_to(target) is True
            assert turn.phase == target

    def test_awaiting_permission_to_valid_phases(self) -> None:
        """От ожидания разрешения — только running, cancelled или completing."""
        awaiting = AwaitingPermission.of(request_id="perm_1", tool_call_id="call_1")
        for target in (Running(), TurnCancelled(), Completing()):
            turn = _turn(awaiting)
            assert turn.transition_to(target) is True
            assert turn.phase == target

    def test_second_permission_wait_is_allowed(self) -> None:
        """Повторное ожидание из ожидания РАЗРЕШЕНО (P1-61).

        Незакрытых разрешений может быть несколько, и спецификация этого прямо требует.
        Прежний запрет был **неверным правилом**: второй запрос уходил клиенту, а его
        идентификатор терялся вместе с отклонённым переходом.
        """
        turn = _turn(AwaitingPermission.of(request_id="perm_1", tool_call_id="call_1"))
        second = AwaitingPermission.of(request_id="perm_2", tool_call_id="call_2")
        assert turn.transition_to(second) is True
        assert turn.phase == second

    def test_awaiting_client_rpc_to_valid_phases(self) -> None:
        """От ожидания ответа клиента — running, cancelled или completing."""
        for target in (Running(), TurnCancelled(), Completing()):
            turn = _turn(AwaitingClientRpc())
            assert turn.transition_to(target) is True
            assert turn.phase == target

    def test_awaiting_permission_derived_reads(self) -> None:
        """Выводимые чтения — те же, что были у плоских полей."""
        turn = _turn(Running())
        phase = AwaitingPermission.of(request_id="perm_1", tool_call_id="call_1")
        turn.transition_to(phase)
        assert turn.permission_request_id == "perm_1"
        assert turn.permission_tool_call_id == "call_1"


class TestRejectedTransitions:
    def test_terminal_phases_are_final(self) -> None:
        """Из терминальных фаз выхода нет, и состояние остаётся как было."""
        for terminal in (TurnCancelled(), Completing()):
            turn = _turn(terminal)
            assert turn.transition_to(Running()) is False
            assert turn.phase == terminal

    def test_rejected_transition_is_logged(self) -> None:
        """Отказ обязан быть наблюдаемым.

        Пока единственным входом в матрицу был мёртвый `set_turn_phase`, событие
        `turn_phase_transition_rejected` не могло сработать ни разу.
        """
        turn = _turn(TurnCancelled())

        with structlog.testing.capture_logs() as logs:
            turn.transition_to(Running())

        rejected = [e for e in logs if e["event"] == "turn_phase_transition_rejected"]
        assert len(rejected) == 1
        assert rejected[0]["from_phase"] == "cancelled"
        assert rejected[0]["to_phase"] == "running"

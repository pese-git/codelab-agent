"""Одновременных разрешений может быть несколько (P1-61, шаг 5 ADR-008).

Гейт воспроизводит потерю, измеренную живьём 2026-08-07 (`sess_3c411dd82bae`): два
цикла агента разошлись на 110 мс, оба запросили разрешение, матрица отклонила
переход `awaiting_permission → awaiting_permission`, второй запрос ушёл клиенту, а
его идентификатор сервер забыл. Вызов `call_008` остался `pending` навсегда и без
`role: tool`.

Требование не наше, а протокола (`05-Prompt Turn.md`): «The Client MUST respond to
**all pending** `session/request_permission` requests with the `cancelled` outcome».
Множественное число здесь — контракт, поэтому проверяется именно оно.

Тесты ниже намеренно живут в домене: потеря произошла в модели состояния, а не в
транспорте, и повторить её дешевле всего на агрегате.
"""

from __future__ import annotations

import pytest

from codelab.server.domain.session import TurnState
from codelab.server.domain.value_objects import (
    AwaitingPermission,
    Completing,
    PermissionWait,
    Running,
    TurnCancelled,
)


def _turn() -> TurnState:
    return TurnState(session_id="sess_1")


class TestSecondPermissionIsNotLost:
    """Ровно тот сценарий, что потерял `call_008`."""

    def test_second_request_joins_instead_of_being_rejected(self) -> None:
        turn = _turn()

        assert turn.await_permission(PermissionWait("f5614636", "call_007"))
        assert turn.await_permission(PermissionWait("aaaa1111", "call_008"))

        assert [w.request_id for w in turn.outstanding_permissions] == ["f5614636", "aaaa1111"]
        assert [w.tool_call_id for w in turn.outstanding_permissions] == ["call_007", "call_008"]

    def test_answering_one_keeps_the_other(self) -> None:
        """Ответ на первый запрос не должен будить turn, ждущий второго решения."""
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))
        turn.await_permission(PermissionWait("aaaa1111", "call_008"))

        turn.close_permission("f5614636")

        assert isinstance(turn.phase, AwaitingPermission)
        assert [w.request_id for w in turn.outstanding_permissions] == ["aaaa1111"]

    def test_closing_the_last_returns_to_running(self) -> None:
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))
        turn.await_permission(PermissionWait("aaaa1111", "call_008"))

        turn.close_permission("f5614636")
        turn.close_permission("aaaa1111")

        assert isinstance(turn.phase, Running)
        assert turn.outstanding_permissions == ()

    def test_wait_is_addressed_by_its_own_request_id(self) -> None:
        """Возобновляется вызов **этого** запроса, а не «текущего» ожидания turn'а.

        Ответы приходят в произвольном порядке; до P1-61 путь возобновления брал
        `permission_tool_call_id` фазы и выполнил бы чужой вызов.
        """
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))
        turn.await_permission(PermissionWait("aaaa1111", "call_008"))

        assert turn.permission_wait_for("f5614636").tool_call_id == "call_007"
        assert turn.permission_wait_for("aaaa1111").tool_call_id == "call_008"
        assert turn.permission_wait_for("не-наш-запрос") is None

    def test_closing_unknown_request_leaves_waits_intact(self) -> None:
        """Поздний ответ на чужой запрос не должен снимать живое ожидание."""
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))

        turn.close_permission("посторонний")

        assert [w.request_id for w in turn.outstanding_permissions] == ["f5614636"]


class TestPhaseInvariants:
    """Инвариант шага 2 обязан пережить множественность."""

    def test_empty_awaiting_is_not_representable(self) -> None:
        """Пустое ожидание — это и есть `Running`, отдельным состоянием быть не может."""
        with pytest.raises(ValueError):
            AwaitingPermission(())

    def test_repeated_request_id_replaces_instead_of_duplicating(self) -> None:
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))
        turn.await_permission(PermissionWait("f5614636", "call_007", keep_tool_pending=True))

        assert len(turn.outstanding_permissions) == 1
        assert turn.outstanding_permissions[0].keep_tool_pending is True

    @pytest.mark.parametrize("terminal", [TurnCancelled(), Completing()])
    def test_terminal_phases_still_close_the_door(self, terminal: object) -> None:
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))
        turn.transition_to(terminal)

        assert turn.outstanding_permissions == ()
        assert not turn.await_permission(PermissionWait("aaaa1111", "call_008"))


class TestCancelClosesEveryWait:
    """Спецификация требует ответить на все незакрытые запросы, а не на последний."""

    def test_all_outstanding_are_visible_to_the_canceller(self) -> None:
        turn = _turn()
        turn.await_permission(PermissionWait("f5614636", "call_007"))
        turn.await_permission(PermissionWait("aaaa1111", "call_008"))
        turn.await_permission(PermissionWait("bbbb2222", "call_009"))

        outstanding = [w.request_id for w in turn.outstanding_permissions]

        assert outstanding == ["f5614636", "aaaa1111", "bbbb2222"]

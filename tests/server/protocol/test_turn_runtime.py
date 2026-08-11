"""Завершение turn'а — один владелец (ADR-008, шаг 5.2).

Гейт возвратом дефекта: вернуть `session.clear_active_turn()` любому из восьми
прежних мест — и `test_seam_cannot_be_bypassed` падает. Без него работа конца
turn'а (освобождение терминалов, шаг 5.3) досталась бы не всем путям: ровно тот
класс, что рукописная граница каталога в двух обработчиках (ADR-009, шаг 2б) и
`terminal_counter` (P2-58).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.server.protocol.turn_runtime import TurnEndCause, finish_turn
from codelab.server.storage.document import ActiveTurnState
from tests.server._domain_sessions import make_domain_session

SRC = Path("src/codelab/server")


def _session_with_turn(prompt_request_id: str | None = "req_1"):
    session = make_domain_session(session_id="sess_1", cwd="/work")
    session.active_turn = ActiveTurnState(
        prompt_request_id=prompt_request_id,
        session_id="sess_1",
    )
    return session


class TestFinishTurn:
    """Поведение шва — то же, что было у прежних вызывающих."""

    def test_clears_the_turn(self) -> None:
        session = _session_with_turn()

        finish_turn(session, cause=TurnEndCause.CANCELLED)

        assert session.active_turn is None

    def test_builds_response_when_stop_reason_given(self) -> None:
        """Идентификатор читается до снятия — после него отвечать было бы некому."""
        session = _session_with_turn()

        response = finish_turn(session, cause=TurnEndCause.COMPLETED, stop_reason="end_turn")

        assert response is not None
        assert response.id == "req_1"
        assert response.result == {"stopReason": "end_turn"}

    def test_no_response_without_stop_reason(self) -> None:
        """Пути без ответа (переключение сессии, stale) turn снимают молча."""
        session = _session_with_turn()

        assert finish_turn(session, cause=TurnEndCause.SESSION_SWITCHED) is None
        assert session.active_turn is None

    def test_no_response_without_request_id(self) -> None:
        """Turn без идентификатора запроса снимается, но отвечать нечему."""
        session = _session_with_turn(prompt_request_id=None)

        assert finish_turn(session, cause=TurnEndCause.CANCELLED, stop_reason="cancelled") is None
        assert session.active_turn is None

    def test_idempotent_without_active_turn(self) -> None:
        """Повторное завершение безвредно: пути завершения пересекаются."""
        session = make_domain_session(session_id="sess_1", cwd="/work")

        assert finish_turn(session, cause=TurnEndCause.STALE) is None

    @pytest.mark.parametrize("cause", list(TurnEndCause))
    def test_every_cause_is_usable(self, cause: TurnEndCause) -> None:
        """Причина — наблюдаемость, а не ветвление: снятие одинаково для всех."""
        session = _session_with_turn()

        finish_turn(session, cause=cause)

        assert session.active_turn is None


class TestSeamOwnership:
    """Владелец снятия один — иначе шаг 5.3 достанется не всем путям."""

    def test_seam_cannot_be_bypassed(self) -> None:
        """`clear_active_turn` вызывается только внутри шва.

        Доменный метод остаётся операцией агрегата — запрещён не он, а прямой
        вызов мимо владельца.
        """
        offenders = []
        for path in SRC.rglob("*.py"):
            if path.name == "turn_runtime.py" or path.parts[-2:] == ("domain", "session.py"):
                continue
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#") or "clear_active_turn(" not in stripped:
                    continue
                if "def clear_active_turn" in stripped:
                    continue
                offenders.append(f"{path}:{number}")

        assert offenders == [], (
            "снятие turn'а мимо шва: работа конца turn'а этим путям не достанется"
        )

"""Unit-тесты для `TurnLifecycleManager` — создание turn'а и нормализация stop reason.

**Файл сведён к живой поверхности (P2-54, 2026-08-12).** Из восьми методов класса
вызывающих в проде имели два; тесты остальных шести проверяли код, который не исполнялся
ни на одном пути. Проверяемое поведение не потеряно, а перенесено туда, где живёт:

* матрица переходов фазы → `tests/server/domain/test_turn_phase_transitions.py`
  (`TurnState.transition_to`), плюс новый гейт на логирование отказа;
* флаг отмены → `tests/server/domain/test_session.py::test_mark_cancel_requested`;
* выбор stop reason из директив → `tests/server/test_prompt_directives.py`
  (`resolve_prompt_stop_reason`);
* нормализация неподдержанного значения и её предупреждение →
  `tests/server/protocol/test_prompt_remaining.py::TestNormalizeStopReason`.
"""

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager
from codelab.server.protocol.turn_runtime import TurnEndCause, finish_turn
from codelab.server.storage.document import ActiveTurnState
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def lifecycle_manager() -> TurnLifecycleManager:
    """Создает экземпляр TurnLifecycleManager для тестов."""
    return TurnLifecycleManager()


@pytest.fixture
def session() -> DomainSession:
    """Создает экземпляр DomainSession для тестов."""
    return make_domain_session(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestLiveSurfaceOnly:
    """Гейт: у класса нет второй двери к состоянию turn'а.

    Шесть методов класса не имели вызывающих в проде и были удалены (P2-54). Гейт
    фиксирует границу: возвращённый `set_turn_phase` — второй путь записи фазы мимо
    матрицы агрегата, `resolve_stop_reason` — вторая копия нормализатора. Именно так
    накопились прежние шесть: каждый переезд оставлял копию, копия переставала
    вызываться, но не удалялась.
    """

    def test_public_surface_is_exactly_two_methods(self) -> None:
        surface = {
            name
            for name in vars(TurnLifecycleManager)
            if callable(getattr(TurnLifecycleManager, name)) and not name.startswith("_")
        }
        assert surface == {"create_active_turn", "finalize_turn"}


class TestTurnLifecycleCreation:
    """Тесты создания active turn."""

    def test_create_active_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
    ) -> None:
        """Создаёт turn в фазе running с идентификатором запроса."""
        turn = lifecycle_manager.create_active_turn("sess_1", "req_1")

        assert turn.session_id == "sess_1"
        assert turn.prompt_request_id == "req_1"
        assert turn.phase.wire_name == "running"

    def test_create_active_turn_no_request_id(
        self,
        lifecycle_manager: TurnLifecycleManager,
    ) -> None:
        """Промпт-нотификация без id — законный случай, turn создаётся."""
        turn = lifecycle_manager.create_active_turn("sess_1", None)

        assert turn.prompt_request_id is None
        assert turn.phase.wire_name == "running"


class TestTurnLifecycleFinalization:
    """Тесты финализации turn."""

    def test_finalize_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Финализирует turn и возвращает stop reason."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )
        stop_reason = lifecycle_manager.finalize_turn(session, "end_turn")

        assert stop_reason == "end_turn"

    def test_finalize_turn_no_active_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает None если нет active turn."""
        session.active_turn = None
        stop_reason = lifecycle_manager.finalize_turn(session, "end_turn")
        assert stop_reason is None

    def test_finalize_turn_different_stop_reasons(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Финализирует turn с разными stop reasons ACP."""
        for stop_reason in ["end_turn", "max_tokens", "cancelled"]:
            session.active_turn = ActiveTurnState(
                prompt_request_id="req_1",
                session_id="sess_1",
            )
            finalized_reason = lifecycle_manager.finalize_turn(session, stop_reason)
            assert finalized_reason == stop_reason

    def test_finalize_turn_normalizes_stop_reason(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Нормализует неподдерживаемый stop reason при финализации.

        Нормализатор теперь общий (`prompt.normalization`), а не вторая копия здесь.
        """
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )
        stop_reason = lifecycle_manager.finalize_turn(session, "unsupported")
        assert stop_reason == "end_turn"


class TestTurnLifecycleClear:
    """Тесты очистки active turn."""

    def test_clear_active_turn(
        self,
        session: DomainSession,
    ) -> None:
        """Снимает turn — но владелец снятия теперь шов (ADR-008, шаг 5)."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )
        finish_turn(session, cause=TurnEndCause.PIPELINE_CLOSED)
        assert session.active_turn is None

    def test_clear_active_turn_already_none(
        self,
        session: DomainSession,
    ) -> None:
        """Не падает если active_turn уже None."""
        session.active_turn = None
        finish_turn(session, cause=TurnEndCause.PIPELINE_CLOSED)
        assert session.active_turn is None

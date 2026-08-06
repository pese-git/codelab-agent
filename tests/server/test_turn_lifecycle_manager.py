"""Unit-тесты для TurnLifecycleManager.

Проверяет корректность управления фазами turn и жизненным циклом.
"""

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.session import TurnState
from codelab.server.domain.value_objects import (
    AwaitingClientRpc,
    AwaitingPermission,
    Completing,
    Running,
    TurnCancelled,
    TurnPhase,
)
from codelab.server.protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager
from codelab.server.protocol.state import PromptDirectives
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


@pytest.fixture
def directives() -> PromptDirectives:
    """Создает экземпляр PromptDirectives для тестов."""
    return PromptDirectives()


class TestTurnLifecycleCreation:
    """Тесты создания active turn."""

    def test_create_active_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
    ) -> None:
        """Создает новый active turn."""
        turn = lifecycle_manager.create_active_turn("sess_1", "req_1")
        assert turn.session_id == "sess_1"
        assert turn.prompt_request_id == "req_1"
        assert turn.phase == Running()
        assert turn.cancel_requested is False

    def test_create_active_turn_no_request_id(
        self,
        lifecycle_manager: TurnLifecycleManager,
    ) -> None:
        """Создает turn без request_id."""
        turn = lifecycle_manager.create_active_turn("sess_1", None)
        assert turn.prompt_request_id is None
        assert turn.phase == Running()


class TestTurnLifecycleCancel:
    """Тесты обработки cancel requests."""

    def test_mark_cancel_requested(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Устанавливает cancel_requested флаг."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )
        lifecycle_manager.mark_cancel_requested(session)
        assert session.active_turn.cancel_requested is True

    def test_mark_cancel_without_active_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Не падает если нет active turn."""
        session.active_turn = None
        lifecycle_manager.mark_cancel_requested(session)
        assert session.active_turn is None

    def test_is_cancel_requested_true(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает True если cancel был запрошен."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            cancel_requested=True,
        )
        assert lifecycle_manager.is_cancel_requested(session) is True

    def test_is_cancel_requested_false(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает False если cancel не был запрошен."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            cancel_requested=False,
        )
        assert lifecycle_manager.is_cancel_requested(session) is False

    def test_is_cancel_requested_no_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает False если нет active turn."""
        session.active_turn = None
        assert lifecycle_manager.is_cancel_requested(session) is False


class TestTurnLifecyclePhases:
    """Тесты управления фазами.

    Фаза — типизированный `TurnPhase` (ADR-008, шаг 2), а проверка перехода живёт в
    агрегате. Раньше эти тесты подавали wire-документ и строки, и сертифицировали
    матрицу, которая в продакшене не применялась ни разу.
    """

    def _turn(self, phase: TurnPhase | None = None) -> TurnState:
        return TurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            phase=phase if phase is not None else Running(),
        )

    def test_set_turn_phase_running(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Устанавливает фазу running."""
        session.active_turn = self._turn()
        lifecycle_manager.set_turn_phase(session, Running())
        assert session.active_turn.phase == Running()

    def test_set_turn_phase_awaiting_permission(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Переходит в фазу ожидания разрешения вместе с её идентификаторами."""
        session.active_turn = self._turn()
        phase = AwaitingPermission(request_id="perm_1", tool_call_id="call_1")
        lifecycle_manager.set_turn_phase(session, phase)
        assert session.active_turn.phase == phase
        # Выводимые чтения — те же, что были у плоских полей.
        assert session.active_turn.permission_request_id == "perm_1"
        assert session.active_turn.permission_tool_call_id == "call_1"

    def test_set_turn_phase_awaiting_client_rpc(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Переходит в фазу ожидания ответа клиента."""
        session.active_turn = self._turn()
        lifecycle_manager.set_turn_phase(session, AwaitingClientRpc())
        assert session.active_turn.phase == AwaitingClientRpc()

    def test_set_turn_phase_completing(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Переходит в фазу completing."""
        session.active_turn = self._turn()
        lifecycle_manager.set_turn_phase(session, Completing())
        assert session.active_turn.phase == Completing()

    def test_set_turn_phase_rejected_transition_keeps_phase(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Недопустимый переход не меняет фазу.

        Заменяет прежний тест «невалидная строка фазы»: набор фаз теперь закрыт
        типом, поэтому проверять нечего — невыразимо. Проверяемое осталось: отказ
        матрицы оставляет состояние как было. `cancelled` — терминальная фаза.
        """
        session.active_turn = self._turn(TurnCancelled())
        lifecycle_manager.set_turn_phase(session, Running())
        assert session.active_turn.phase == TurnCancelled()

    def test_get_turn_phase(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает имя текущей фазы."""
        session.active_turn = self._turn(
            AwaitingPermission(request_id="perm_1", tool_call_id="call_1")
        )
        assert lifecycle_manager.get_turn_phase(session) == "awaiting_permission"

    def test_get_turn_phase_no_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает 'unknown' если нет active turn."""
        session.active_turn = None
        assert lifecycle_manager.get_turn_phase(session) == "unknown"

    def test_set_turn_phase_no_active_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Не падает если нет active turn."""
        session.active_turn = None
        lifecycle_manager.set_turn_phase(session, Running())
        assert session.active_turn is None


class TestTurnLifecycleStopReason:
    """Тесты определения stop reason."""

    def test_resolve_stop_reason_forced(
        self,
        lifecycle_manager: TurnLifecycleManager,
        directives: PromptDirectives,
    ) -> None:
        """Использует forced_stop_reason если установлен."""
        directives.forced_stop_reason = "cancelled"
        reason = lifecycle_manager.resolve_stop_reason(directives)
        assert reason == "cancelled"

    def test_resolve_stop_reason_keep_tool_pending(
        self,
        lifecycle_manager: TurnLifecycleManager,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает 'end_turn' если keep_tool_pending=True."""
        directives.keep_tool_pending = True
        reason = lifecycle_manager.resolve_stop_reason(directives)
        assert reason == "end_turn"

    def test_resolve_stop_reason_default(
        self,
        lifecycle_manager: TurnLifecycleManager,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает 'end_turn' по умолчанию."""
        reason = lifecycle_manager.resolve_stop_reason(directives)
        assert reason == "end_turn"

    def test_resolve_stop_reason_unsupported_normalized(
        self,
        lifecycle_manager: TurnLifecycleManager,
        directives: PromptDirectives,
    ) -> None:
        """Нормализует неподдерживаемый stop reason."""
        directives.forced_stop_reason = "unsupported_reason"
        reason = lifecycle_manager.resolve_stop_reason(directives)
        assert reason == "end_turn"

    def test_resolve_stop_reason_supported_values(
        self,
        lifecycle_manager: TurnLifecycleManager,
        directives: PromptDirectives,
    ) -> None:
        """Поддерживает все определенные stop reasons."""
        supported = {
            "end_turn",
            "max_tokens",
            "max_turn_requests",
            "refusal",
            "cancelled",
        }
        for reason in supported:
            directives.forced_stop_reason = reason
            result = lifecycle_manager.resolve_stop_reason(directives)
            assert result == reason


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
        """Нормализует неподдерживаемый stop reason при финализации."""
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
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Очищает active turn."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )
        lifecycle_manager.clear_active_turn(session)
        assert session.active_turn is None

    def test_clear_active_turn_already_none(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Не падает если active_turn уже None."""
        session.active_turn = None
        lifecycle_manager.clear_active_turn(session)
        assert session.active_turn is None


class TestTurnLifecycleShouldHandleCancel:
    """Тесты should_handle_cancel."""

    def test_should_handle_cancel_true(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает True если есть active turn и cancel_requested."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            cancel_requested=True,
        )
        assert lifecycle_manager.should_handle_cancel(session) is True

    def test_should_handle_cancel_false_no_request(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает False если cancel_requested=False."""
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            cancel_requested=False,
        )
        assert lifecycle_manager.should_handle_cancel(session) is False

    def test_should_handle_cancel_false_no_turn(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Возвращает False если нет active turn."""
        session.active_turn = None
        assert lifecycle_manager.should_handle_cancel(session) is False


class TestTurnLifecyclePhaseTransitions:
    """Тесты валидности переходов между фазами.

    Правила сохранены от строковой матрицы и дополнены `TurnCancelled`: его писали,
    но в матрице не перечисляли (ADR-008, шаг 2).
    """

    def _turn(self, phase: TurnPhase) -> TurnState:
        return TurnState(prompt_request_id="req_1", session_id="sess_1", phase=phase)

    def test_running_to_any_phase(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """От running можно перейти в любую фазу."""
        for target in (
            AwaitingPermission(request_id="perm_1", tool_call_id="call_1"),
            AwaitingClientRpc(),
            TurnCancelled(),
            Completing(),
        ):
            session.active_turn = self._turn(Running())
            lifecycle_manager.set_turn_phase(session, target)
            assert session.active_turn.phase == target

    def test_awaiting_permission_to_valid_phases(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """От ожидания разрешения — только running, cancelled или completing."""
        awaiting = AwaitingPermission(request_id="perm_1", tool_call_id="call_1")
        for target in (Running(), TurnCancelled(), Completing()):
            session.active_turn = self._turn(awaiting)
            lifecycle_manager.set_turn_phase(session, target)
            assert session.active_turn.phase == target

        # Повторное ожидание из ожидания запрещено: сначала ответ, потом новый запрос.
        session.active_turn = self._turn(awaiting)
        lifecycle_manager.set_turn_phase(
            session, AwaitingPermission(request_id="perm_2", tool_call_id="call_2")
        )
        assert session.active_turn.phase == awaiting

    def test_awaiting_client_rpc_to_valid_phases(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """От ожидания ответа клиента — running, cancelled или completing."""
        for target in (Running(), TurnCancelled(), Completing()):
            session.active_turn = self._turn(AwaitingClientRpc())
            lifecycle_manager.set_turn_phase(session, target)
            assert session.active_turn.phase == target

    def test_terminal_phases_are_final(
        self,
        lifecycle_manager: TurnLifecycleManager,
        session: DomainSession,
    ) -> None:
        """Из терминальных фаз выхода нет."""
        for terminal in (TurnCancelled(), Completing()):
            session.active_turn = self._turn(terminal)
            lifecycle_manager.set_turn_phase(session, Running())
            assert session.active_turn.phase == terminal

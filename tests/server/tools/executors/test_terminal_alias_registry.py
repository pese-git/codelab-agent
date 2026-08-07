"""Тесты TerminalAliasRegistry (tech-debt #18)."""

from __future__ import annotations

from codelab.server.domain.session import Session as DomainSession
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry
from tests.server._domain_sessions import make_domain_session


def _session() -> DomainSession:
    return make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])


class TestTerminalAliasRegistry:
    def test_register_returns_short_alias_with_process_epoch(self) -> None:
        """Alias несёт эпоху процесса: `term_<epoch>_<n>` (ADR-008, раздел 4)."""
        session = _session()
        registry = TerminalAliasRegistry(epoch="7")

        alias1 = registry.register(session, "6c8323e0-08bb-4a20-944e-1aeb85afedb1")
        alias2 = registry.register(session, "af3167b3-f16a-4c00-9b00-000000000000")

        assert alias1 == "term_7_1"
        assert alias2 == "term_7_2"

    def test_alias_stays_short(self) -> None:
        """Исходное ограничение (#18) — краткость: модель теряла символы на UUID."""
        session = _session()

        alias = TerminalAliasRegistry(epoch="99999").register(session, "6c8323e0-08bb-4a20")

        assert len(alias) <= 14
        assert len(alias) < len("6c8323e0-08bb-4a20-944e-1aeb85afedb1")

    def test_counter_is_per_session(self) -> None:
        """Счётчик живёт у процесса, но нумерация — своя на сессию, как и связка."""
        registry = TerminalAliasRegistry(epoch="7")
        first = make_domain_session(session_id="s1", cwd="/tmp", mcp_servers=[])
        second = make_domain_session(session_id="s2", cwd="/tmp", mcp_servers=[])

        assert registry.register(first, "a") == "term_7_1"
        assert registry.register(second, "b") == "term_7_1"
        assert registry.register(first, "c") == "term_7_2"

    def test_counter_not_reused_after_release(self) -> None:
        """Освобождение не откатывает счётчик — иначе новый терминал занял бы чужой alias."""
        session = _session()
        registry = TerminalAliasRegistry(epoch="7")
        alias = registry.register(session, "uuid-a")
        registry.release(session, alias)

        assert registry.register(session, "uuid-b") == "term_7_2"

    def test_aggregate_carries_no_terminal_state(self) -> None:
        """Ни связки, ни счётчика на агрегате: иначе они снова уедут на диск.

        Счётчик жил в документе, и его инкремент терялся на пути Context Manager'а —
        отсюда один alias у двух терминалов (P2-58, замер 2026-08-06).
        """
        session = _session()

        TerminalAliasRegistry(epoch="7").register(session, "uuid-a")

        assert not hasattr(session.runtime, "terminals")
        assert not hasattr(session.runtime, "terminals_owner")
        assert not hasattr(session.runtime, "terminal_counter")
        assert not hasattr(session, "allocate_terminal_alias")

    def test_resolve_returns_client_terminal_id(self) -> None:
        session = _session()
        registry = TerminalAliasRegistry()
        client_id = "6c8323e0-08bb-4a20-944e-1aeb85afedb1"

        alias = registry.register(session, client_id)

        assert registry.resolve(session, alias) == client_id

    def test_resolve_unknown_alias_returns_none(self) -> None:
        session = _session()
        registry = TerminalAliasRegistry()

        assert registry.resolve(session, "term_999") is None

    def test_resolve_truncated_alias_is_a_miss_not_wrong_terminal(self) -> None:
        """Alias короткий и не режется LLM: усечённый alias — промах, а не чужой терминал."""
        session = _session()
        registry = TerminalAliasRegistry()
        alias = registry.register(session, "client-uuid")

        assert registry.resolve(session, alias[:-1]) is None

    def test_release_removes_mapping_and_returns_client_id(self) -> None:
        session = _session()
        registry = TerminalAliasRegistry()
        alias = registry.register(session, "client-uuid")

        released = registry.release(session, alias)

        assert released == "client-uuid"
        assert registry.resolve(session, alias) is None

    def test_release_unknown_alias_returns_none(self) -> None:
        session = _session()
        registry = TerminalAliasRegistry()

        assert registry.release(session, "term_404") is None


class TestOwnershipMeasurement:
    """Замер владения (P2-58, вторая половина).

    Реестр отвечает на два вопроса замера: сколько терминалов осталось за сессией и
    сколько из них никто не дождался. Второй и решает, законно ли освобождать остаток
    на границе turn'а: освобождение убивает ещё идущую команду.
    """

    def test_unwaited_lists_live_aliases_without_completed_wait(self) -> None:
        session = _session()
        registry = TerminalAliasRegistry(epoch="7")
        waited = registry.register(session, "uuid-a")
        registry.register(session, "uuid-b")

        registry.mark_waited(session, waited)

        assert registry.unwaited_aliases(session) == ["term_7_2"]

    def test_release_drops_alias_from_both_views(self) -> None:
        """Освобождённый терминал не попадает ни в живые, ни в недожданные."""
        session = _session()
        registry = TerminalAliasRegistry(epoch="7")
        alias = registry.register(session, "uuid-a")

        registry.release(session, alias)

        assert registry.known_aliases(session) == []
        assert registry.unwaited_aliases(session) == []

    def test_waited_then_released_does_not_resurface(self) -> None:
        """Отметка уходит вместе с alias'ом — по построению, а не согласованием.

        Признак лежит в записи alias'а, поэтому «отметка пережила освобождение»
        невыразимо. Прежняя форма (отдельное множество) требовала строки согласования
        в `release`, и **гейт её не поймал**: alias'ы монотонны в пределах эпохи, так
        что осиротевшая отметка не совпадает ни с одним будущим alias'ом. Тест остался
        как утверждение о состоянии после освобождения, а не о снятии отметки.
        """
        session = _session()
        registry = TerminalAliasRegistry(epoch="7")
        alias = registry.register(session, "uuid-a")
        registry.mark_waited(session, alias)

        registry.release(session, alias)
        again = registry.register(session, "uuid-b")

        assert registry.unwaited_aliases(session) == [again]

    def test_measurement_is_per_session(self) -> None:
        first = make_domain_session(session_id="s1", cwd="/tmp", mcp_servers=[])
        second = make_domain_session(session_id="s2", cwd="/tmp", mcp_servers=[])
        registry = TerminalAliasRegistry(epoch="7")
        registry.register(first, "uuid-a")
        alias_second = registry.register(second, "uuid-b")
        registry.mark_waited(second, alias_second)

        assert registry.unwaited_aliases(first) == ["term_7_1"]
        assert registry.unwaited_aliases(second) == []

    def test_mark_waited_on_unknown_alias_does_not_invent_a_terminal(self) -> None:
        """Отметка не создаёт записи: живость определяет связка, а не отметка."""
        session = _session()
        registry = TerminalAliasRegistry(epoch="7")

        registry.mark_waited(session, "term_7_404")

        assert registry.known_aliases(session) == []
        assert registry.unwaited_aliases(session) == []


class TestEpochSeparatesProcesses:
    """Ради чего вводилась эпоха: alias прошлого процесса не занимает нынешний.

    Раньше это держалось на персистируемом счётчике — дисциплинарная гарантия,
    которая однажды не сработала. Теперь alias'ы различаются по построению.
    """

    def test_new_process_does_not_reissue_old_aliases(self) -> None:
        session = _session()
        before_restart = TerminalAliasRegistry(epoch="7")
        old_alias = before_restart.register(session, "uuid-old")

        after_restart = TerminalAliasRegistry(epoch="8")
        new_alias = after_restart.register(session, "uuid-new")

        assert old_alias != new_alias
        assert (old_alias, new_alias) == ("term_7_1", "term_8_1")

    def test_alias_from_restored_history_resolves_to_nothing(self) -> None:
        """Модель, сославшаяся на alias из истории, получает промах, а не чужой терминал."""
        session = _session()
        old_alias = TerminalAliasRegistry(epoch="7").register(session, "uuid-old")

        after_restart = TerminalAliasRegistry(epoch="8")
        after_restart.register(session, "uuid-new")

        assert after_restart.resolve(session, old_alias) is None

"""Тесты TerminalAliasRegistry (tech-debt #18)."""

from __future__ import annotations

from codelab.server.domain.session import Session as DomainSession
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry
from tests.server._domain_sessions import make_domain_session


def _session() -> DomainSession:
    return make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])


class TestTerminalAliasRegistry:
    def test_register_returns_short_deterministic_alias(self) -> None:
        session = _session()
        registry = TerminalAliasRegistry()

        alias1 = registry.register(session, "6c8323e0-08bb-4a20-944e-1aeb85afedb1")
        alias2 = registry.register(session, "af3167b3-f16a-4c00-9b00-000000000000")

        assert alias1 == "term_1"
        assert alias2 == "term_2"
        assert session.runtime.terminal_counter == 2

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

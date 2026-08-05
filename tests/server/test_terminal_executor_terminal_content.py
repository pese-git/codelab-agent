"""Unit тесты для TerminalToolExecutor — terminal embedding.

Проверяет:
- execute_create() возвращает terminal content в ToolExecutionResult
- Terminal content содержит terminalId
- Text content обёрнут в ToolCallContent.content wrapper
- Порядок content items: terminal первым, затем text
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def session() -> DomainSession:
    """Создает тестовую сессию."""
    return make_domain_session(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        config_values={},
    )


@pytest.fixture
def executor() -> TerminalToolExecutor:
    """Создает executor с mock зависимостями."""
    mock_bridge = MagicMock(spec=ClientRPCBridge)
    mock_checker = MagicMock(spec=PermissionChecker)
    return TerminalToolExecutor(mock_bridge, mock_checker)


class TestTerminalExecutorCreateTerminalContent:
    """Тесты terminal content в execute_create()."""

    @pytest.mark.asyncio
    async def test_execute_create_returns_terminal_content(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """execute_create() возвращает content с terminal и text items."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_xyz789")

        result = await executor.execute_create(
            session=session,
            command="ls -la",
        )

        assert result.success is True
        assert result.content is not None
        assert len(result.content) == 2

    @pytest.mark.asyncio
    async def test_execute_create_terminal_content_has_terminal_id(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """Terminal content содержит terminalId."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_abc123")

        result = await executor.execute_create(
            session=session,
            command="echo hello",
        )

        assert result.content is not None
        terminal_item = result.content[0]
        assert terminal_item["type"] == "terminal"
        assert terminal_item["terminalId"] == "term_abc123"

    @pytest.mark.asyncio
    async def test_execute_create_text_content_wrapped(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """Text content обёрнут в ToolCallContent.content wrapper."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_test")

        result = await executor.execute_create(
            session=session,
            command="pwd",
        )

        assert result.content is not None
        text_item = result.content[1]
        assert text_item["type"] == "content"
        assert "content" in text_item
        assert text_item["content"]["type"] == "text"
        # LLM видит короткий alias (term_1), а не сырой client terminalId (см. #18).
        assert "Terminal term_1 created" in text_item["content"]["text"]

    @pytest.mark.asyncio
    async def test_execute_create_terminal_content_first(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """Terminal content идёт первым для быстрого отображения клиентом."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_first")

        result = await executor.execute_create(
            session=session,
            command="test",
        )

        assert result.content is not None
        assert result.content[0]["type"] == "terminal"
        assert result.content[1]["type"] == "content"

    @pytest.mark.asyncio
    async def test_execute_create_content_includes_command(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """Text content содержит информацию о команде."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_cmd")

        result = await executor.execute_create(
            session=session,
            command="npm test",
        )

        assert result.content is not None
        text_content = result.content[1]["content"]["text"]
        assert "npm test" in text_content


class TestTerminalAliasRoundTrip:
    """Регресс tech-debt #18: alias для LLM ↔ настоящий client terminalId."""

    @pytest.mark.asyncio
    async def test_wait_for_exit_resolves_alias_to_client_id(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """LLM возвращает alias; bridge адресуется настоящим client terminalId."""
        client_id = "6c8323e0-08bb-4a20-944e-1aeb85afedb1"
        executor._bridge.create_terminal = AsyncMock(return_value=client_id)
        executor._bridge.terminal_output = AsyncMock(
            return_value={"output": "done", "is_complete": True, "exit_code": 0}
        )

        create = await executor.execute_create(session=session, command="ls")
        alias = create.metadata["terminal_id"]
        assert alias == "term_1"

        result = await executor.execute_wait_for_exit(session=session, terminal_id=alias)

        assert result.success is True
        executor._bridge.terminal_output.assert_awaited_once_with(
            session=session,
            terminal_id=client_id,
        )

    @pytest.mark.asyncio
    async def test_unknown_alias_fails_without_touching_bridge(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """Неизвестный alias → failed с внятной ошибкой, без вызова bridge (нет recreate-loop)."""
        executor._bridge.terminal_output = AsyncMock()
        executor._bridge.wait_terminal_exit = AsyncMock()

        result = await executor.execute_wait_for_exit(
            session=session, terminal_id="term_hallucinated"
        )

        assert result.success is False
        assert result.error is not None
        assert "term_hallucinated" in result.error
        executor._bridge.terminal_output.assert_not_awaited()
        executor._bridge.wait_terminal_exit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_release_removes_alias_from_registry(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """После release alias снимается — повторное обращение даёт ошибку контракта."""
        executor._bridge.create_terminal = AsyncMock(return_value="client-uuid")
        executor._bridge.release_terminal = AsyncMock(return_value=True)

        create = await executor.execute_create(session=session, command="ls")
        alias = create.metadata["terminal_id"]

        released = await executor.execute_release(session=session, terminal_id=alias)
        assert released.success is True
        assert executor._aliases.known_aliases(session) == []

        again = await executor.execute_release(session=session, terminal_id=alias)
        assert again.success is False

    @pytest.mark.asyncio
    async def test_execute_create_preserves_output_and_metadata(
        self,
        executor: TerminalToolExecutor,
        session: DomainSession,
    ) -> None:
        """execute_create() сохраняет output и metadata."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_full")

        result = await executor.execute_create(
            session=session,
            command="ls",
        )

        assert result.success is True
        assert result.output is not None
        # Наружу (output/metadata/raw_output) идёт alias, а не сырой client id (см. #18).
        assert "term_1" in result.output
        assert result.metadata is not None
        assert result.metadata["terminal_id"] == "term_1"
        assert result.metadata["command"] == "ls"
        assert result.raw_output == {"terminal_id": "term_1"}
        # Client-facing terminal content-item сохраняет родной client terminalId.
        assert result.content is not None
        assert result.content[0]["terminalId"] == "term_full"
        # Связка alias → client id зарегистрирована в процессном реестре (ADR-007, шаг A).
        assert executor._aliases.resolve(session, "term_1") == "term_full"

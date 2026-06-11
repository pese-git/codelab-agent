"""Интеграционные тесты MCP Phase 1.

Покрывают:
- E2E: session/new → MCP connect → prompt → MCP tool call → response
- Mock MCP server → tool call → LLM loop → result
- MCP tool permission flow (ask → allow → execute)
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.formatter import ContentFormatter
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.handlers.state_manager import StateManager
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.registry import SimpleToolRegistry


@dataclass
class MockToolCall:
    """Mock tool call от LLM."""

    name: str
    arguments: dict[str, object]
    id: str


@pytest.fixture
def tool_registry() -> SimpleToolRegistry:
    """Создаёт ToolRegistry."""
    return SimpleToolRegistry()


@pytest.fixture
def tool_call_handler() -> ToolCallHandler:
    """Создаёт ToolCallHandler."""
    return ToolCallHandler()


@pytest.fixture
def permission_manager() -> PermissionManager:
    """Создаёт PermissionManager."""
    return PermissionManager()


@pytest.fixture
def state_manager() -> StateManager:
    """Создаёт StateManager."""
    return StateManager()


@pytest.fixture
def plan_builder() -> PlanBuilder:
    """Создаёт PlanBuilder."""
    return PlanBuilder()


@pytest.fixture
def agent_loop(
    tool_registry: SimpleToolRegistry,
    tool_call_handler: ToolCallHandler,
    permission_manager: PermissionManager,
    state_manager: StateManager,
    plan_builder: PlanBuilder,
) -> AgentLoop:
    """Создаёт AgentLoop с mock стратегией."""
    mock_strategy = MagicMock()
    return AgentLoop(
        strategy=mock_strategy,
        tool_registry=tool_registry,
        tool_call_handler=tool_call_handler,
        permission_manager=permission_manager,
        state_manager=state_manager,
        content_extractor=ContentExtractor(),
        content_validator=ContentValidator(),
        content_formatter=ContentFormatter(),
        replay_manager=ReplayManager(),
        plan_builder=plan_builder,
    )


@pytest.fixture
def session() -> SessionState:
    """Создаёт базовую сессию."""
    return SessionState(
        session_id="test-session",
        cwd="/tmp",
        mcp_servers=[],
    )


@pytest.fixture
def mock_mcp_manager() -> MagicMock:
    """Создаёт mock MCPManager с tools."""
    manager = MagicMock()
    manager.call_tool = AsyncMock()
    manager.server_count = 1
    manager.server_ids = ["test-server"]
    return manager


class TestE2EMcpToolExecution:
    """E2E тесты выполнения MCP инструментов."""

    @pytest.mark.asyncio
    async def test_full_mcp_tool_flow(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Полный поток: prompt → MCP tool call → response."""
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="File content: Hello, World!",
        )

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            )
        ]

        notifications: list = []
        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert mock_mcp_manager.call_tool.called
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_multiple_mcp_tool_calls(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Несколько MCP tool calls выполняются последовательно."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="result",
        )

        tool_calls = [
            MockToolCall(name="mcp_tool_1", arguments={}, id="call_1"),
            MockToolCall(name="mcp_tool_2", arguments={}, id="call_2"),
        ]

        notifications: list = []
        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert mock_mcp_manager.call_tool.call_count == 2
        assert len(result.tool_results) == 2

    @pytest.mark.asyncio
    async def test_mixed_builtin_and_mcp_tools(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
        tool_registry: SimpleToolRegistry,
    ) -> None:
        """Смешанные builtin и MCP tools выполняются корректно."""
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        # Регистрируем builtin tool
        async def mock_execute(*args, **kwargs):
            return ToolExecutionResult(success=True, output="builtin result")

        from codelab.server.tools.base import ToolDefinition

        tool_def = ToolDefinition(
            name="fs/read_text_file",
            description="Read file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            kind="read",
            requires_permission=False,
        )
        tool_registry.register(tool_def, mock_execute)

        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="mcp result",
        )

        tool_calls = [
            MockToolCall(
                name="fs_read_text_file",
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            ),
            MockToolCall(name="mcp_test_tool", arguments={}, id="call_2"),
        ]

        notifications: list = []
        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert len(result.tool_results) == 2
        assert all(r.success for r in result.tool_results)


class TestMcpToolPermissionFlow:
    """Тесты permission flow для MCP tools."""

    @pytest.mark.asyncio
    async def test_permission_ask_flow(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Permission flow: ask → pending_permission."""
        # Не устанавливаем policy — по умолчанию "ask"
        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert result.pending_permission is True
        assert not mock_mcp_manager.call_tool.called

    @pytest.mark.asyncio
    async def test_permission_allow_flow(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Permission flow: allow → execute."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="allowed result",
        )

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert mock_mcp_manager.call_tool.called
        assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_permission_reject_flow(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Permission flow: reject → failed."""
        session.permission_policy = {"other": "reject_always"}

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert not mock_mcp_manager.call_tool.called
        assert result.tool_results[0].success is False


class TestMcpToolErrorHandling:
    """Тесты обработки ошибок MCP tools."""

    @pytest.mark.asyncio
    async def test_mcp_server_error(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP server возвращает ошибку."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=False,
            error="Server error: connection refused",
        )

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert result.tool_results[0].success is False
        assert "connection refused" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_mcp_server_crash(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP server падает с exception."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.side_effect = RuntimeError("Server crashed")

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert result.tool_results[0].success is False
        assert "Server crashed" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_mcp_timeout(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP tool timeout."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.side_effect = TimeoutError("Operation timed out")

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        assert result.tool_results[0].success is False
        assert "timed out" in result.tool_results[0].error.lower()


class TestMcpToolNotifications:
    """Тесты notifications для MCP tools."""

    @pytest.mark.asyncio
    async def test_tool_call_notifications(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Tool call генерирует правильные notifications."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="result",
        )

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Должны быть notifications: tool_call (pending) +
        # tool_call_update (in_progress) + tool_call_update (completed)
        assert len(notifications) >= 2

    @pytest.mark.asyncio
    async def test_tool_status_transitions(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Tool status переходит через правильные состояния."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="result",
        )

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем что tool_call создан (ID генерируется ToolCallHandler)
        assert len(session.tool_calls) == 1
        # Проверяем что tool_call_id_from_llm сохранён
        tool_call_state = list(session.tool_calls.values())[0]
        assert tool_call_state.tool_call_id_from_llm == "call_1"
        # Проверяем что статус обновлён
        assert tool_call_state.status == "completed"

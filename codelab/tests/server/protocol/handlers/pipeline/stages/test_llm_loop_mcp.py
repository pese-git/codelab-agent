"""Тесты MCP интеграции в AgentLoop.

Покрывают:
- MCP tool call recognition (namespace mcp:)
- Делегирование в MCPToolExecutor
- Tool call lifecycle: pending → in_progress → completed/failed
- Permission flow для MCP tools
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
    """Создаёт пустой ToolRegistry."""
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
    from codelab.server.agent.system_prompt_builder import SystemPromptBuilder

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
        system_prompt_builder=SystemPromptBuilder(global_prompt=""),
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
    """Создаёт mock MCPManager."""
    manager = MagicMock()
    manager.call_tool = AsyncMock()
    return manager


class TestMcpToolRecognition:
    """Тесты распознавания MCP инструментов."""

    def test_mcp_tool_with_full_namespace(self) -> None:
        """MCP инструмент с полным namespace mcp:server:tool распознаётся."""
        from codelab.server.tools.executors.mcp_executor import MCPToolExecutor

        assert MCPToolExecutor.is_mcp_tool("mcp:filesystem:read_file") is True
        assert MCPToolExecutor.is_mcp_tool("mcp:sqlite:query") is True

    def test_mcp_tool_with_simple_namespace(self) -> None:
        """MCP инструмент с простым namespace mcp:tool распознаётся."""
        from codelab.server.tools.executors.mcp_executor import MCPToolExecutor

        assert MCPToolExecutor.is_mcp_tool("mcp:read_file") is True

    def test_builtin_tool_not_recognized_as_mcp(self) -> None:
        """Встроенные инструменты не распознаются как MCP."""
        from codelab.server.tools.executors.mcp_executor import MCPToolExecutor

        assert MCPToolExecutor.is_mcp_tool("fs/read_text_file") is False
        assert MCPToolExecutor.is_mcp_tool("terminal/create") is False
        assert MCPToolExecutor.is_mcp_tool("update_plan") is False


class TestMcpToolDelegation:
    """Тесты делегирования MCP инструментов в MCPToolExecutor."""

    @pytest.mark.asyncio
    async def test_mcp_tool_delegated_to_executor(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент делегируется в MCPToolExecutor."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        # Настраиваем mock MCPManager
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="MCP tool result",
        )

        # Вызываем _process_tool_calls напрямую
        tool_calls = [
            MockToolCall(
                name="mcp_fs_read_file",  # LLM имя (с подчёркиваниями)
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

        # Проверяем что MCP manager был вызван
        assert mock_mcp_manager.call_tool.called
        # Проверяем что результат получен
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_mcp_tool_without_manager_fails(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
    ) -> None:
        """MCP инструмент без MCPManager завершается ошибкой."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        tool_calls = [
            MockToolCall(
                name="mcp_fs_read_file",
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
            mcp_manager=None,  # Нет MCP manager
        )

        # Проверяем что инструмент завершился ошибкой
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is False
        assert "MCP manager not available" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_builtin_tool_not_delegated_to_mcp(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        tool_registry: SimpleToolRegistry,
    ) -> None:
        """Встроенные инструменты не делегируются в MCP."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        # Регистрируем встроенный инструмент
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

        tool_calls = [
            MockToolCall(
                name="fs_read_text_file",
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
            mcp_manager=None,
        )

        # Проверяем что инструмент выполнен через tool_registry
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True


class TestMcpToolLifecycle:
    """Тесты жизненного цикла MCP tool calls."""

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_success(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Успешный lifecycle: pending → in_progress → completed."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="result",
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

        # Проверяем notifications
        assert len(notifications) >= 2  # pending + completed
        # Проверяем tool result
        assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_failure(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Failed lifecycle: pending → in_progress → failed."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=False,
            error="Tool failed",
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
        assert result.tool_results[0].error == "Tool failed"

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_exception(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Exception lifecycle: pending → failed (exception)."""
        session.permission_policy = {"other": "allow_always"}
        mock_mcp_manager.call_tool.side_effect = RuntimeError("Connection lost")

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
        assert "Connection lost" in result.tool_results[0].error


class TestMcpToolPermission:
    """Тесты permission flow для MCP tools."""

    @pytest.mark.asyncio
    async def test_mcp_tool_requires_permission(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент требует permission по умолчанию."""
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

        # Проверяем что запрашивается permission
        assert result.pending_permission is True
        # MCP manager не должен быть вызван
        assert not mock_mcp_manager.call_tool.called

    @pytest.mark.asyncio
    async def test_mcp_tool_allowed_by_policy(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент выполняется при allow политике."""
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Allowed result",
        )

        # Устанавливаем policy на allow
        session.permission_policy = {"other": "allow_always"}

        tool_calls = [MockToolCall(name="mcp_test_tool", arguments={}, id="call_1")]
        notifications: list = []

        result = await agent_loop._process_tool_calls(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # MCP manager должен быть вызван
        assert mock_mcp_manager.call_tool.called
        assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_mcp_tool_rejected_by_policy(
        self,
        agent_loop: AgentLoop,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент отклоняется при reject политике."""
        # Устанавливаем policy на reject
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

        # MCP manager не должен быть вызван
        assert not mock_mcp_manager.call_tool.called
        # Tool result должен быть failed
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is False
        assert "rejected" in result.tool_results[0].error.lower()

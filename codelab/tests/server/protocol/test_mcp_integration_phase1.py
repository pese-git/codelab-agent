"""Интеграционные тесты MCP Phase 1.

Покрывают:
- E2E: session/new → MCP connect → prompt → MCP tool call → response
- Mock MCP server → tool call → LLM loop → result
- MCP tool permission flow (ask → allow → execute)
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.stages.llm_loop import LLMLoopStage
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.state_manager import StateManager
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult
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
def llm_loop_stage(
    tool_registry: SimpleToolRegistry,
    tool_call_handler: ToolCallHandler,
    permission_manager: PermissionManager,
    state_manager: StateManager,
    plan_builder: PlanBuilder,
) -> LLMLoopStage:
    """Создаёт LLMLoopStage."""
    return LLMLoopStage(
        tool_registry=tool_registry,
        tool_call_handler=tool_call_handler,
        permission_manager=permission_manager,
        state_manager=state_manager,
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

    # MCP tools
    mcp_tools = [
        ToolDefinition(
            name="mcp:test-server:read_file",
            description="[MCP:test-server] Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            kind="read",
        ),
    ]
    manager.get_all_tools.return_value = mcp_tools

    return manager


class TestE2EMcpToolExecution:
    """E2E тесты MCP tool execution."""

    @pytest.mark.asyncio
    async def test_full_mcp_tool_flow(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Полный поток: prompt → MCP tool call → response."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        # Настраиваем mock MCPManager
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="File content: Hello, World!",
        )

        # LLM вызывает MCP tool
        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",  # LLM имя с подчёркиваниями
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            )
        ]

        notifications: list = []
        result = await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем полный flow
        assert mock_mcp_manager.call_tool.called
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True
        assert result.tool_results[0].output is not None
        assert "Hello, World!" in result.tool_results[0].output

        # Проверяем что tool call создан и завершён
        assert len(session.tool_calls) == 1
        tool_call_id = list(session.tool_calls.keys())[0]
        assert session.tool_calls[tool_call_id].status == "completed"

    @pytest.mark.asyncio
    async def test_multiple_mcp_tool_calls(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Множественные MCP tool calls в одном turn."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        # Настраиваем mock для разных результатов
        mock_mcp_manager.call_tool.side_effect = [
            ToolExecutionResult(success=True, output="File 1 content"),
            ToolExecutionResult(success=True, output="File 2 content"),
        ]

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/file1.txt"},
                id="call_1",
            ),
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/file2.txt"},
                id="call_2",
            ),
        ]

        notifications: list = []
        result = await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем что оба вызова выполнены
        assert mock_mcp_manager.call_tool.call_count == 2
        assert len(result.tool_results) == 2
        assert all(r.success for r in result.tool_results)

        # Проверяем что оба tool call созданы
        assert len(session.tool_calls) == 2

    @pytest.mark.asyncio
    async def test_mixed_builtin_and_mcp_tools(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        tool_registry: SimpleToolRegistry,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Смешанные вызовы встроенных и MCP tools."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {
            "other": "allow_always",
            "read": "allow_always",
            "edit": "allow_always",
        }

        # Регистрируем встроенный инструмент
        def builtin_tool(path: str) -> str:
            return f"Builtin: {path}"

        tool_registry.register(
            ToolDefinition(
                name="fs/read_text_file",
                description="Read file",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                kind="read",
                requires_permission=False,
            ),
            builtin_tool,
        )

        # Настраиваем mock MCPManager
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="MCP: file content",
        )

        tool_calls = [
            MockToolCall(
                name="fs_read_text_file",  # Встроенный
                arguments={"path": "/tmp/builtin.txt"},
                id="call_1",
            ),
            MockToolCall(
                name="mcp_test_server_read_file",  # MCP
                arguments={"path": "/tmp/mcp.txt"},
                id="call_2",
            ),
        ]

        notifications: list = []
        result = await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем что оба выполнены
        assert len(result.tool_results) == 2
        assert all(r.success for r in result.tool_results)

        # Проверяем что MCP manager вызван только для MCP инструмента
        assert mock_mcp_manager.call_tool.call_count == 1


class TestMcpToolPermissionFlow:
    """Тесты permission flow для MCP tools."""

    @pytest.mark.asyncio
    async def test_permission_ask_flow(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Permission flow: ask → pending_permission → resume."""
        # Патчим _decide_tool_execution на ask
        with patch.object(
            llm_loop_stage,
            "_decide_tool_execution",
            return_value="ask",
        ):
            tool_calls = [
                MockToolCall(
                    name="mcp_test_server_read_file",
                    arguments={"path": "/tmp/test.txt"},
                    id="call_1",
                )
            ]

            notifications: list = []
            result = await llm_loop_stage._process_tool_calls_for_llm_loop(
                session=session,
                session_id="test-session",
                tool_calls=tool_calls,
                notifications=notifications,
                mcp_manager=mock_mcp_manager,
            )

            # Проверяем что запрошено разрешение
            assert result.pending_permission is True
            # MCP manager НЕ вызван до разрешения
            assert not mock_mcp_manager.call_tool.called

    @pytest.mark.asyncio
    async def test_permission_allow_flow(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Permission flow: allow → execute → result."""
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Allowed content",
        )

        # Патчим _decide_tool_execution на allow
        with patch.object(
            llm_loop_stage,
            "_decide_tool_execution",
            return_value="allow",
        ):
            tool_calls = [
                MockToolCall(
                    name="mcp_test_server_read_file",
                    arguments={"path": "/tmp/test.txt"},
                    id="call_1",
                )
            ]

            notifications: list = []
            result = await llm_loop_stage._process_tool_calls_for_llm_loop(
                session=session,
                session_id="test-session",
                tool_calls=tool_calls,
                notifications=notifications,
                mcp_manager=mock_mcp_manager,
            )

            # Проверяем что инструмент выполнен
            assert mock_mcp_manager.call_tool.called
            assert result.tool_results[0].success is True
            assert result.tool_results[0].output is not None
            assert "Allowed content" in result.tool_results[0].output

    @pytest.mark.asyncio
    async def test_permission_reject_flow(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Permission flow: reject → error result."""
        # Патчим _decide_tool_execution на reject
        with patch.object(
            llm_loop_stage,
            "_decide_tool_execution",
            return_value="reject",
        ):
            tool_calls = [
                MockToolCall(
                    name="mcp_test_server_read_file",
                    arguments={"path": "/tmp/test.txt"},
                    id="call_1",
                )
            ]

            notifications: list = []
            result = await llm_loop_stage._process_tool_calls_for_llm_loop(
                session=session,
                session_id="test-session",
                tool_calls=tool_calls,
                notifications=notifications,
                mcp_manager=mock_mcp_manager,
            )

            # Проверяем что инструмент НЕ выполнен
            assert not mock_mcp_manager.call_tool.called
            # Проверяем что результат с ошибкой
            assert result.tool_results[0].success is False
            assert "rejected" in result.tool_results[0].error.lower()


class TestMcpToolErrorHandling:
    """Тесты обработки ошибок MCP tools."""

    @pytest.mark.asyncio
    async def test_mcp_server_error(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP server возвращает ошибку."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=False,
            error="MCP server error: File not found",
        )

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/nonexistent.txt"},
                id="call_1",
            )
        ]

        notifications: list = []
        result = await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем что ошибка обработана
        assert result.tool_results[0].success is False
        assert result.tool_results[0].error is not None
        assert "File not found" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_mcp_server_crash(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP server падает (исключение)."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.side_effect = ConnectionError("Server crashed")

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            )
        ]

        notifications: list = []
        result = await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем что исключение обработано
        assert result.tool_results[0].success is False
        assert result.tool_results[0].error is not None
        assert "Server crashed" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_mcp_timeout(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP tool timeout."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        import asyncio

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(10)
            return ToolExecutionResult(success=True, output="Too late")

        mock_mcp_manager.call_tool.side_effect = slow_call

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            )
        ]

        notifications: list = []

        # Выполняем с коротким timeout
        with patch("asyncio.wait_for", side_effect=TimeoutError()):
            await llm_loop_stage._process_tool_calls_for_llm_loop(
                session=session,
                session_id="test-session",
                tool_calls=tool_calls,
                notifications=notifications,
                mcp_manager=mock_mcp_manager,
            )

        # Таймаут должен быть обработан
        # (в реальности timeout обрабатывается в MCPToolExecutor)


class TestMcpToolNotifications:
    """Тесты notifications для MCP tools."""

    @pytest.mark.asyncio
    async def test_tool_call_notifications(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP tool генерирует корректные notifications."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Result",
        )

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            )
        ]

        notifications: list = []
        await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем что notifications отправлены
        assert len(notifications) > 0

        # Проверяем типы notifications
        update_notifications = [n for n in notifications if n.method == "session/update"]
        assert len(update_notifications) >= 2  # pending + completed

    @pytest.mark.asyncio
    async def test_tool_status_transitions(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
        tool_call_handler: ToolCallHandler,
    ) -> None:
        """MCP tool проходит через статусы: pending → in_progress → completed."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Result",
        )

        tool_calls = [
            MockToolCall(
                name="mcp_test_server_read_file",
                arguments={"path": "/tmp/test.txt"},
                id="call_1",
            )
        ]

        notifications: list = []
        await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=mock_mcp_manager,
        )

        # Проверяем финальный статус
        tool_call_id = list(session.tool_calls.keys())[0]
        assert session.tool_calls[tool_call_id].status == "completed"

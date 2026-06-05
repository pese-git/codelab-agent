"""Тесты MCP интеграции в LLMLoopStage.

Покрывают:
- MCP tool call recognition (namespace mcp:)
- Делегирование в MCPToolExecutor
- Tool call lifecycle: pending → in_progress → completed/failed
- Permission flow для MCP tools
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
from codelab.server.protocol.state import SessionState, ToolCallState
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
        llm_loop_stage: LLMLoopStage,
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

        # Вызываем _process_tool_calls_for_llm_loop напрямую
        tool_calls = [
            MockToolCall(
                name="mcp_fs_read_file",  # LLM имя (с подчёркиваниями)
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

        # Проверяем что MCP manager был вызван
        assert mock_mcp_manager.call_tool.called
        # Проверяем что результат получен
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_mcp_tool_without_manager_fails(
        self,
        llm_loop_stage: LLMLoopStage,
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
        result = await llm_loop_stage._process_tool_calls_for_llm_loop(
            session=session,
            session_id="test-session",
            tool_calls=tool_calls,
            notifications=notifications,
            mcp_manager=None,  # Нет MCP manager
        )

        # Проверяем что инструмент завершился ошибкой
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is False
        assert result.tool_results[0].error is not None
        assert "MCP manager not available" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_builtin_tool_not_delegated_to_mcp(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        tool_registry: SimpleToolRegistry,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Встроенный инструмент не делегируется в MCPToolExecutor."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        # Регистрируем встроенный инструмент
        def builtin_tool(path: str) -> str:
            return f"File content: {path}"

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

        tool_calls = [
            MockToolCall(
                name="fs_read_text_file",  # LLM имя
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

        # MCP manager НЕ должен быть вызван для встроенного инструмента
        assert not mock_mcp_manager.call_tool.called
        # Но результат должен быть успешным (встроенный инструмент выполнился)
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True


class TestMcpToolLifecycle:
    """Тесты lifecycle MCP инструментов: pending → in_progress → completed/failed."""

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_success(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
        tool_call_handler: ToolCallHandler,
    ) -> None:
        """MCP инструмент проходит полный lifecycle при успехе."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Success output",
        )

        tool_calls = [
            MockToolCall(
                name="mcp_fs_read_file",
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

        # Проверяем что tool call создан в сессии
        assert len(session.tool_calls) == 1
        tool_call_id = list(session.tool_calls.keys())[0]
        tool_call_state = session.tool_calls[tool_call_id]

        # Проверяем статус completed
        assert tool_call_state.status == "completed"

        # Проверяем notifications
        notification_types = [n.method for n in notifications]
        assert "session/update" in notification_types

        # Проверяем результат
        assert result.tool_results[0].success is True
        assert result.tool_results[0].output == "Success output"

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_failure(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент проходит lifecycle при ошибке."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=False,
            error="File not found",
        )

        tool_calls = [
            MockToolCall(
                name="mcp_fs_read_file",
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

        # Проверяем статус failed
        tool_call_id = list(session.tool_calls.keys())[0]
        tool_call_state = session.tool_calls[tool_call_id]
        assert tool_call_state.status == "failed"

        # Проверяем результат
        assert result.tool_results[0].success is False
        assert result.tool_results[0].error is not None
        assert "File not found" in result.tool_results[0].error

    @pytest.mark.asyncio
    async def test_mcp_tool_lifecycle_exception(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент проходит lifecycle при исключении."""
        # Настраиваем session permission policy на allow
        session.permission_policy = {"other": "allow_always", "read": "allow_always"}

        mock_mcp_manager.call_tool.side_effect = Exception("Connection lost")

        tool_calls = [
            MockToolCall(
                name="mcp_fs_read_file",
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

        # Проверяем статус failed
        tool_call_id = list(session.tool_calls.keys())[0]
        tool_call_state = session.tool_calls[tool_call_id]
        assert tool_call_state.status == "failed"

        # Проверяем результат с исключением
        assert result.tool_results[0].success is False
        assert result.tool_results[0].error is not None
        assert "Connection lost" in result.tool_results[0].error


class TestMcpToolPermission:
    """Тесты permission flow для MCP инструментов."""

    @pytest.mark.asyncio
    async def test_mcp_tool_requires_permission(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент запрашивает разрешение (по умолчанию)."""
        # Патчим _decide_tool_execution на ask
        with patch.object(
            llm_loop_stage,
            "_decide_tool_execution",
            return_value="ask",
        ):
            tool_calls = [
                MockToolCall(
                    name="mcp_fs_read_file",
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

            # MCP инструмент должен запросить разрешение
            assert result.pending_permission is True
            # MCP manager НЕ должен быть вызван до получения разрешения
            assert not mock_mcp_manager.call_tool.called

    @pytest.mark.asyncio
    async def test_mcp_tool_allowed_by_policy(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент выполняется при allow политике."""
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Allowed result",
        )

        # Патчим _decide_tool_execution на allow
        with patch.object(
            llm_loop_stage,
            "_decide_tool_execution",
            return_value="allow",
        ):
            tool_calls = [
                MockToolCall(
                    name="mcp_fs_read_file",
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

            # MCP manager должен быть вызван
            assert mock_mcp_manager.call_tool.called
            # Результат успешный
            assert result.tool_results[0].success is True

    @pytest.mark.asyncio
    async def test_mcp_tool_rejected_by_policy(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент отклоняется при reject политике."""
        # Патчим _decide_tool_execution на reject
        with patch.object(
            llm_loop_stage,
            "_decide_tool_execution",
            return_value="reject",
        ):
            tool_calls = [
                MockToolCall(
                    name="mcp_fs_read_file",
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

            # MCP manager НЕ должен быть вызван
            assert not mock_mcp_manager.call_tool.called
            # Результат с ошибкой
            assert result.tool_results[0].success is False
            assert "rejected" in result.tool_results[0].error.lower()


class TestExecutePendingToolMcpManager:
    """Тесты передачи mcp_manager в execute_pending_tool()."""

    @pytest.mark.asyncio
    async def test_execute_pending_tool_passes_mcp_manager_to_run_llm_loop(
        self,
        llm_loop_stage: LLMLoopStage,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """execute_pending_tool() передаёт mcp_manager в _run_llm_loop().

        Регрессионный тест: ранее mcp_manager терялся после выполнения
        инструмента, из-за чего LLM терял контекст MCP инструментов
        при продолжении диалога.
        """
        # Создаём pending tool call в сессии
        tool_call_id = "call_pending_1"
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="mcp:fs:read_file",
            kind="read",
            tool_name="mcp:fs:read_file",
            tool_arguments={"path": "/tmp/test.txt"},
            status="pending",
        )

        # Патчим _run_llm_loop чтобы проверить вызов
        with patch.object(
            llm_loop_stage,
            "_run_llm_loop",
            new_callable=AsyncMock,
        ) as mock_run_llm_loop:
            # Настраиваем mock чтобы вернуть пустой результат
            from codelab.server.protocol.state import LLMLoopResult
            mock_run_llm_loop.return_value = LLMLoopResult(
                notifications=[],
                stop_reason="end_turn",
            )

            # Патчим tool_registry.execute_tool для успешного выполнения
            with patch.object(
                llm_loop_stage._tool_registry,
                "execute_tool",
                new_callable=AsyncMock,
                return_value=ToolExecutionResult(
                    success=True,
                    output="File content",
                ),
            ):
                await llm_loop_stage.execute_pending_tool(
                    session=session,
                    session_id="test-session",
                    tool_call_id=tool_call_id,
                    agent_orchestrator=MagicMock(),
                    mcp_manager=mock_mcp_manager,
                )

            # Проверяем что _run_llm_loop был вызван с mcp_manager
            mock_run_llm_loop.assert_called_once()
            call_kwargs = mock_run_llm_loop.call_args[1]
            assert call_kwargs.get("mcp_manager") is mock_mcp_manager, (
                "mcp_manager должен быть передан в _run_llm_loop() "
                "для сохранения контекста MCP инструментов"
            )

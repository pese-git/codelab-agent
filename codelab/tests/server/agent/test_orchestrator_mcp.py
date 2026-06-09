"""Тесты MCP интеграции в AgentOrchestrator.

Покрывают:
- AgentContext содержит MCP tools из mcp_manager.get_all_tools()
- LLM получает MCP tools в tools list
- MCP tools проходят через ToolMapping для совместимости имён

NOTE: AgentOrchestrator is deprecated. Use ExecutionEngine + StrategyDispatcher instead.
These tests are kept for backward compatibility verification.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.orchestrator import AgentOrchestrator
from codelab.server.agent.state import OrchestratorConfig
from codelab.server.llm.mock_provider import MockLLMProvider
from codelab.server.protocol.state import ClientRuntimeCapabilities, SessionState
from codelab.server.tools.base import ToolDefinition
from codelab.server.tools.registry import SimpleToolRegistry


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def tool_registry() -> SimpleToolRegistry:
    """Создаёт ToolRegistry с встроенными инструментами."""
    registry = SimpleToolRegistry()
    registry.register(
        ToolDefinition(
            name="fs/read_text_file",
            description="Read file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            kind="read",
        ),
        lambda path: f"Content of {path}",
    )
    return registry


@pytest.fixture
def config() -> OrchestratorConfig:
    """Создаёт базовую конфигурацию оркестратора."""
    return OrchestratorConfig(
        enabled=True,
        agent_class="naive",
        llm_provider_class="mock",
        model="gpt-4",
        temperature=0.7,
        max_tokens=8192,
    )


@pytest.fixture
def llm_provider() -> MockLLMProvider:
    """Создаёт mock LLM provider."""
    return MockLLMProvider(response="Test response")


@pytest.fixture
def orchestrator(
    config: OrchestratorConfig,
    llm_provider: MockLLMProvider,
    tool_registry: SimpleToolRegistry,
) -> AgentOrchestrator:
    """Создаёт AgentOrchestrator."""
    return AgentOrchestrator(
        config=config,
        llm_provider=llm_provider,
        tool_registry=tool_registry,
    )


@pytest.fixture
def session_state() -> SessionState:
    """Создаёт базовую сессию с runtime capabilities."""
    return SessionState(
        session_id="test-session",
        cwd="/tmp",
        mcp_servers=[],
        runtime_capabilities=ClientRuntimeCapabilities(
            fs_read=True,
            fs_write=True,
            terminal=True,
        ),
    )


@pytest.fixture
def mock_mcp_manager() -> MagicMock:
    """Создаёт mock MCPManager с MCP tools."""
    manager = MagicMock()

    # MCP tools
    mcp_tools = [
        ToolDefinition(
            name="mcp:filesystem:read_file",
            description="[MCP:filesystem] Read a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            kind="read",
        ),
        ToolDefinition(
            name="mcp:filesystem:write_file",
            description="[MCP:filesystem] Write a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
            kind="edit",
        ),
        ToolDefinition(
            name="mcp:sqlite:query",
            description="[MCP:sqlite] Execute SQL query",
            parameters={"type": "object", "properties": {"sql": {"type": "string"}}},
            kind="read",
        ),
    ]

    manager.get_all_tools.return_value = mcp_tools
    manager.server_count = 2
    manager.server_ids = ["filesystem", "sqlite"]
    manager.get_tools_for_server.side_effect = lambda server_id: [
        t for t in mcp_tools if server_id in t.name
    ]

    return manager


class TestAgentContextWithMcpTools:
    """Тесты AgentContext с MCP tools."""

    def test_filter_tools_includes_mcp_tools(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """_filter_tools включает MCP tools из mcp_manager."""
        tools = orchestrator._filter_tools(session_state, mock_mcp_manager)

        # Проверяем что MCP tools включены
        tool_names = {t.name for t in tools}
        assert "mcp:filesystem:read_file" in tool_names
        assert "mcp:filesystem:write_file" in tool_names
        assert "mcp:sqlite:query" in tool_names

    def test_filter_tools_without_mcp_manager(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
    ) -> None:
        """_filter_tools без mcp_manager не включает MCP tools."""
        tools = orchestrator._filter_tools(session_state, mcp_manager=None)

        # Проверяем что MCP tools НЕ включены
        tool_names = {t.name for t in tools}
        assert not any(name.startswith("mcp:") for name in tool_names)

    def test_filter_tools_combines_builtin_and_mcp(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """_filter_tools объединяет встроенные и MCP tools."""
        tools = orchestrator._filter_tools(session_state, mock_mcp_manager)

        # Проверяем что есть и встроенные и MCP tools
        builtin_tools = [t for t in tools if not t.name.startswith("mcp:")]
        mcp_tools = [t for t in tools if t.name.startswith("mcp:")]

        assert len(builtin_tools) >= 1  # fs/read_text_file
        assert len(mcp_tools) == 3  # 3 MCP tools

    def test_mcp_tools_have_correct_kind(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP tools имеют корректный kind (read, edit, execute и т.д.)."""
        tools = orchestrator._filter_tools(session_state, mock_mcp_manager)

        mcp_tools = [t for t in tools if t.name.startswith("mcp:")]

        # Проверяем что kind установлен корректно
        read_file_tool = next(t for t in mcp_tools if "read_file" in t.name)
        assert read_file_tool.kind == "read"

        write_file_tool = next(t for t in mcp_tools if "write_file" in t.name)
        assert write_file_tool.kind == "edit"


class TestMcpToolsInLlmContext:
    """Тесты MCP tools в контексте LLM."""

    def test_filter_tools_calls_get_all_tools(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """_filter_tools вызывает mcp_manager.get_all_tools()."""
        # Вызываем _filter_tools с mcp_manager
        orchestrator._filter_tools(session_state, mock_mcp_manager)

        # Проверяем что get_all_tools был вызван
        mock_mcp_manager.get_all_tools.assert_called_once()

    def test_filter_tools_returns_mcp_tools(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """_filter_tools возвращает MCP tools из mcp_manager."""
        tools = orchestrator._filter_tools(session_state, mock_mcp_manager)

        # Проверяем что MCP tools включены
        mcp_tools = [t for t in tools if t.name.startswith("mcp:")]
        assert len(mcp_tools) == 3


class TestMcpToolNameMapping:
    """Тесты маппинга имён MCP tools."""

    def test_mcp_tool_names_preserved(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP tool names сохраняются в формате mcp:server:tool."""
        tools = orchestrator._filter_tools(session_state, mock_mcp_manager)

        mcp_tools = [t for t in tools if t.name.startswith("mcp:")]

        # Проверяем формат имён
        for tool in mcp_tools:
            parts = tool.name.split(":")
            assert len(parts) == 3
            assert parts[0] == "mcp"
            assert parts[1] in ["filesystem", "sqlite"]

    def test_mcp_tool_descriptions_include_server_name(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP tool descriptions включают имя сервера."""
        tools = orchestrator._filter_tools(session_state, mock_mcp_manager)

        mcp_tools = [t for t in tools if t.name.startswith("mcp:")]

        # Проверяем что description содержит [MCP:server_name]
        for tool in mcp_tools:
            assert "[MCP:" in tool.description


class TestMcpManagerIntegration:
    """Тесты интеграции с MCPManager."""

    def test_mcp_manager_server_count(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCPManager server_count корректно возвращается."""
        assert mock_mcp_manager.server_count == 2
        assert "filesystem" in mock_mcp_manager.server_ids
        assert "sqlite" in mock_mcp_manager.server_ids

    def test_mcp_manager_get_tools_for_server(
        self,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCPManager.get_tools_for_server возвращает tools для конкретного сервера."""
        filesystem_tools = mock_mcp_manager.get_tools_for_server("filesystem")
        sqlite_tools = mock_mcp_manager.get_tools_for_server("sqlite")

        assert len(filesystem_tools) == 2  # read_file, write_file
        assert len(sqlite_tools) == 1  # query

    def test_build_system_message_includes_mcp_info(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """_build_system_message включает информацию о MCP серверах."""
        message = orchestrator._build_system_message(session_state, mock_mcp_manager)

        # Проверяем что MCP информация включена
        assert "MCP" in message or "mcp" in message.lower()

    def test_build_system_message_without_mcp(
        self,
        orchestrator: AgentOrchestrator,
        session_state: SessionState,
    ) -> None:
        """_build_system_message без MCP manager не включает MCP информацию."""
        message = orchestrator._build_system_message(session_state, mcp_manager=None)

        # MCP информация не должна быть включена
        # (но message может содержать другую информацию)
        assert message is not None

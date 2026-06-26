"""Тесты для SystemPromptBuilder."""

from unittest.mock import MagicMock

from codelab.server.agent.system_prompt_builder import SystemPromptBuilder


class TestSystemPromptBuilderBase:
    """Базовые тесты формирования system prompt."""

    def test_empty_global_prompt_no_mcp(self):
        builder = SystemPromptBuilder(global_prompt="")
        session = _mock_session(config_values={})
        result = builder.build(session)
        assert result is None

    def test_global_prompt_only(self):
        builder = SystemPromptBuilder(global_prompt="You are a helpful assistant.")
        session = _mock_session(config_values={})
        result = builder.build(session)
        assert result == "You are a helpful assistant."

    def test_empty_global_prompt_returns_none(self):
        builder = SystemPromptBuilder(global_prompt="")
        session = _mock_session(config_values={})
        result = builder.build(session)
        assert result is None


class TestSystemPromptBuilderAgentPrompt:
    """Тесты agent prompt из AgentRegistry."""

    def test_agent_prompt_from_registry(self):
        mock_registry = _mock_agent_registry("coder", "Ты — агент-программист.")
        builder = SystemPromptBuilder(global_prompt="", agent_registry=mock_registry)
        session = _mock_session(config_values={"_agent": "coder"})
        result = builder.build(session)
        assert result == "Ты — агент-программист."

    def test_agent_prompt_combined_with_global(self):
        mock_registry = _mock_agent_registry("coder", "Ты — агент-программист.")
        builder = SystemPromptBuilder(
            global_prompt="Используй update_plan.",
            agent_registry=mock_registry,
        )
        session = _mock_session(config_values={"_agent": "coder"})
        result = builder.build(session)
        assert "Ты — агент-программист." in result
        assert "Используй update_plan." in result
        assert "\n\n" in result

    def test_agent_not_in_registry(self):
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        builder = SystemPromptBuilder(global_prompt="", agent_registry=mock_registry)
        session = _mock_session(config_values={"_agent": "unknown"})
        result = builder.build(session)
        assert result is None

    def test_no_agent_in_config(self):
        mock_registry = _mock_agent_registry("coder", "coder prompt")
        builder = SystemPromptBuilder(global_prompt="global", agent_registry=mock_registry)
        session = _mock_session(config_values={})
        result = builder.build(session)
        assert result == "global"

    def test_agent_has_empty_prompt(self):
        mock_registry = _mock_agent_registry("coder", "")
        builder = SystemPromptBuilder(global_prompt="global", agent_registry=mock_registry)
        session = _mock_session(config_values={"_agent": "coder"})
        result = builder.build(session)
        assert result == "global"

    def test_no_registry_returns_empty(self):
        builder = SystemPromptBuilder(global_prompt="", agent_registry=None)
        session = _mock_session(config_values={"_agent": "coder"})
        result = builder.build(session)
        assert result is None


class TestSystemPromptBuilderMCP:
    """Тесты MCP информации в system prompt."""

    def test_mcp_manager_none(self):
        builder = SystemPromptBuilder(global_prompt="Base prompt")
        session = _mock_session(config_values={})
        result = builder.build(session, mcp_manager=None)
        assert result == "Base prompt"

    def test_mcp_manager_zero_servers(self):
        builder = SystemPromptBuilder(global_prompt="Base prompt")
        mock_mcp = _create_mock_mcp(server_count=0, server_ids=[])
        session = _mock_session(config_values={})
        result = builder.build(session, mcp_manager=mock_mcp)
        assert result == "Base prompt"

    def test_mcp_manager_with_servers(self):
        builder = SystemPromptBuilder(global_prompt="Base prompt")
        mock_mcp = _create_mock_mcp(
            server_count=1,
            server_ids=["github"],
            tools={"github": ["list_repos", "create_issue"]},
        )
        session = _mock_session(config_values={})
        result = builder.build(session, mcp_manager=mock_mcp)

        assert "Base prompt" in result
        assert "You have access to the following MCP" in result
        assert "**github** (2 tools): list_repos, create_issue" in result
        assert "reference these servers and their tools" in result

    def test_mcp_manager_multiple_servers(self):
        builder = SystemPromptBuilder(global_prompt="")
        mock_mcp = _create_mock_mcp(
            server_count=2,
            server_ids=["github", "filesystem"],
            tools={
                "github": ["list_repos"],
                "filesystem": ["read", "write"],
            },
        )
        session = _mock_session(config_values={})
        result = builder.build(session, mcp_manager=mock_mcp)

        assert "**github** (1 tools): list_repos" in result
        assert "**filesystem** (2 tools): read, write" in result

    def test_full_combination_agent_global_mcp(self):
        mock_registry = _mock_agent_registry("coder", "Ты — программист.")
        builder = SystemPromptBuilder(
            global_prompt="Используй инструменты.",
            agent_registry=mock_registry,
        )
        mock_mcp = _create_mock_mcp(
            server_count=1,
            server_ids=["github"],
            tools={"github": ["list_repos"]},
        )
        session = _mock_session(config_values={"_agent": "coder"})
        result = builder.build(session, mcp_manager=mock_mcp)

        assert "Ты — программист." in result
        assert "Используй инструменты." in result
        assert "You have access to the following MCP" in result
        assert "github" in result


class TestSystemPromptBuilderCwd:
    """Тесты рабочей директории в system prompt."""

    def test_cwd_included_in_prompt(self):
        """cwd включается в system prompt."""
        builder = SystemPromptBuilder(global_prompt="Base prompt")
        session = _mock_session(config_values={}, cwd="/home/user/project")
        result = builder.build(session)

        assert "Working directory: /home/user/project" in result
        assert "CRITICAL FILE SYSTEM CONSTRAINTS" in result
        assert "MUST ONLY work within the working directory" in result
        assert "Base prompt" in result

    def test_cwd_is_first_section(self):
        """cwd идёт первым в system prompt (до agent prompt)."""
        mock_registry = _mock_agent_registry("coder", "Agent prompt")
        builder = SystemPromptBuilder(
            global_prompt="Global prompt",
            agent_registry=mock_registry,
        )
        session = _mock_session(
            config_values={"_agent": "coder"},
            cwd="/project",
        )
        result = builder.build(session)

        assert result.startswith("Working directory: /project")
        assert result.index("Working directory") < result.index("Agent prompt")
        assert result.index("Agent prompt") < result.index("Global prompt")

    def test_empty_cwd_not_included(self):
        """Пустой cwd не добавляется в system prompt."""
        builder = SystemPromptBuilder(global_prompt="Base prompt")
        session = _mock_session(config_values={}, cwd="")
        result = builder.build(session)

        assert "Working directory" not in result
        assert result == "Base prompt"

    def test_cwd_only_returns_prompt(self):
        """Только cwd без других промптов возвращает cwd секцию."""
        builder = SystemPromptBuilder(global_prompt="")
        session = _mock_session(config_values={}, cwd="/project")
        result = builder.build(session)

        assert result is not None
        assert "Working directory: /project" in result


class TestSystemPromptBuilderFormatMCPInfo:
    """Тесты форматирования MCP информации."""

    def test_format_mcp_info_empty_server_ids(self):
        builder = SystemPromptBuilder(global_prompt="")
        mock_mcp = _create_mock_mcp(server_count=0, server_ids=[])
        result = builder._format_mcp_info(mock_mcp)
        assert result == ""

    def test_format_mcp_info_tool_name_extraction(self):
        builder = SystemPromptBuilder(global_prompt="")
        mock_mcp = _create_mock_mcp(
            server_count=1,
            server_ids=["my-server"],
            tools={"my-server": ["mcp:my-server:read_file", "mcp:my-server:write_file"]},
        )
        result = builder._format_mcp_info(mock_mcp)
        assert "read_file" in result
        assert "write_file" in result
        assert "mcp:" not in result.split(":")[-1]


def _mock_session(config_values: dict | None = None, cwd: str = "") -> MagicMock:
    """Создать mock SessionState."""
    session = MagicMock()
    session.config_values = config_values or {}
    session.cwd = cwd
    return session


def _mock_agent_registry(agent_name: str, agent_prompt: str) -> MagicMock:
    """Создать mock AgentRegistry."""
    mock_registry = MagicMock()
    mock_agent = MagicMock()
    mock_agent.prompt = agent_prompt
    mock_registry.get.return_value = mock_agent
    return mock_registry


def _create_mock_mcp(
    server_count: int,
    server_ids: list[str],
    tools: dict[str, list[str]] | None = None,
):
    """Создать mock MCP manager для тестов."""
    tools = tools or {}

    class MockTool:
        def __init__(self, name: str):
            self.name = name

    class MockMCPManager:
        def __init__(self):
            self.server_count = server_count
            self.server_ids = server_ids
            self._tools = tools

        def get_tools_for_server(self, server_id: str) -> list[MockTool]:
            tool_names = self._tools.get(server_id, [])
            return [MockTool(name) for name in tool_names]

    return MockMCPManager()

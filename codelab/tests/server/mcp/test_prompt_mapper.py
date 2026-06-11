"""Тесты для маппинга MCP Prompt → ACP AvailableCommand."""

from codelab.server.mcp.models import (
    MCPPrompt,
    MCPPromptArgument,
)
from codelab.server.mcp.prompt_mapper import (
    mcp_prompt_to_available_command,
    mcp_prompts_to_available_commands,
)


class TestMcpPromptToAvailableCommand:
    """Тесты функции mcp_prompt_to_available_command."""

    def test_minimal_mapping(self):
        """Маппинг с минимальными полями."""
        prompt = MCPPrompt(name="code_review")
        cmd = mcp_prompt_to_available_command(prompt)

        assert cmd.name == "code_review"
        assert cmd.description == "MCP prompt: code_review"
        assert cmd.input is None

    def test_full_mapping(self):
        """Маппинг со всеми полями."""
        prompt = MCPPrompt(
            name="plan-vacation",
            title="Plan a vacation",
            description="Guide through vacation planning",
            arguments=[
                MCPPromptArgument(name="destination", required=True),
                MCPPromptArgument(name="duration", required=False),
            ],
        )
        cmd = mcp_prompt_to_available_command(prompt)

        assert cmd.name == "plan-vacation"
        assert cmd.description == "Plan a vacation"
        assert cmd.input is not None
        assert cmd.input.hint == "<destination> [duration]"

    def test_title_priority(self):
        """title используется как description, если есть."""
        prompt = MCPPrompt(
            name="test",
            title="Display Title",
            description="Fallback Description",
        )
        cmd = mcp_prompt_to_available_command(prompt)
        assert cmd.description == "Display Title"

    def test_description_fallback(self):
        """Если нет title, используется description."""
        prompt = MCPPrompt(
            name="test",
            description="Fallback Description",
        )
        cmd = mcp_prompt_to_available_command(prompt)
        assert cmd.description == "Fallback Description"

    def test_no_arguments(self):
        """prompt без arguments → input=None."""
        prompt = MCPPrompt(name="simple", description="Simple prompt")
        cmd = mcp_prompt_to_available_command(prompt)
        assert cmd.input is None

    def test_required_arguments_hint(self):
        """Required args в <>, optional в []."""
        prompt = MCPPrompt(
            name="test",
            arguments=[
                MCPPromptArgument(name="required_arg", required=True),
                MCPPromptArgument(name="optional_arg", required=False),
                MCPPromptArgument(name="another_required", required=True),
            ],
        )
        cmd = mcp_prompt_to_available_command(prompt)
        assert cmd.input is not None
        assert cmd.input.hint == "<required_arg> [optional_arg] <another_required>"

    def test_all_required_arguments(self):
        """Все аргументы обязательные."""
        prompt = MCPPrompt(
            name="test",
            arguments=[
                MCPPromptArgument(name="arg1", required=True),
                MCPPromptArgument(name="arg2", required=True),
            ],
        )
        cmd = mcp_prompt_to_available_command(prompt)
        assert cmd.input.hint == "<arg1> <arg2>"

    def test_all_optional_arguments(self):
        """Все аргументы опциональные."""
        prompt = MCPPrompt(
            name="test",
            arguments=[
                MCPPromptArgument(name="arg1", required=False),
                MCPPromptArgument(name="arg2", required=False),
            ],
        )
        cmd = mcp_prompt_to_available_command(prompt)
        assert cmd.input.hint == "[arg1] [arg2]"


class TestMcpPromptsToAvailableCommands:
    """Тесты функции mcp_prompts_to_available_commands."""

    def test_empty_list(self):
        """Пустой список."""
        result = mcp_prompts_to_available_commands([])
        assert result == []

    def test_multiple_prompts(self):
        """Несколько prompts."""
        prompts = [
            MCPPrompt(name="prompt1", description="First"),
            MCPPrompt(
                name="prompt2",
                title="Second Prompt",
                arguments=[MCPPromptArgument(name="arg", required=True)],
            ),
        ]
        commands = mcp_prompts_to_available_commands(prompts)

        assert len(commands) == 2
        assert commands[0].name == "prompt1"
        assert commands[0].description == "First"
        assert commands[0].input is None

        assert commands[1].name == "prompt2"
        assert commands[1].description == "Second Prompt"
        assert commands[1].input.hint == "<arg>"

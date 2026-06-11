"""Тесты для MCPPromptCommandHandler."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.mcp.models import (
    MCPGetPromptResult,
    MCPPrompt,
    MCPPromptArgument,
)
from codelab.server.protocol.handlers.slash_commands.builtin.mcp_prompt import (
    MCPPromptCommandHandler,
)


class TestMCPPromptCommandHandlerDefinition:
    """Тесты get_definition()."""

    def test_get_definition_minimal(self):
        """Определение с минимальными полями."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="simple",
            mcp_manager=MagicMock(),
            description="Simple prompt",
        )
        cmd = handler.get_definition()

        assert cmd.name == "simple"
        assert cmd.description == "Simple prompt"
        assert cmd.input is None

    def test_get_definition_with_hint(self):
        """Определение с arguments_hint."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="code_review",
            mcp_manager=MagicMock(),
            description="Review code",
            arguments_hint="<language> [style]",
        )
        cmd = handler.get_definition()

        assert cmd.name == "code_review"
        assert cmd.description == "Review code"
        assert cmd.input is not None
        assert cmd.input.hint == "<language> [style]"


class TestMCPPromptCommandHandlerMapArguments:
    """Тесты _map_arguments()."""

    def test_map_arguments_positional(self):
        """Маппинг позиционных аргументов."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        prompt_def = MCPPrompt(
            name="test",
            arguments=[
                MCPPromptArgument(name="language", required=True),
                MCPPromptArgument(name="style", required=False),
            ],
        )

        result = handler._map_arguments(["python", "pep8"], prompt_def)

        assert result == {"language": "python", "style": "pep8"}

    def test_map_arguments_excess(self):
        """Лишние аргументы игнорируются."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        prompt_def = MCPPrompt(
            name="test",
            arguments=[
                MCPPromptArgument(name="language", required=True),
            ],
        )

        result = handler._map_arguments(["python", "extra", "ignored"], prompt_def)

        assert result == {"language": "python"}

    def test_map_arguments_no_definition(self):
        """Без определения prompt → None."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )

        result = handler._map_arguments(["arg1", "arg2"], None)

        assert result is None

    def test_map_arguments_empty_args(self):
        """Пустые args → None."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        prompt_def = MCPPrompt(
            name="test",
            arguments=[MCPPromptArgument(name="arg", required=True)],
        )

        result = handler._map_arguments([], prompt_def)

        assert result is None

    def test_map_arguments_no_prompt_arguments(self):
        """Prompt без аргументов → None."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        prompt_def = MCPPrompt(name="test", arguments=[])

        result = handler._map_arguments(["arg1"], prompt_def)

        assert result is None


class TestMCPPromptCommandHandlerConvertMessages:
    """Тесты _convert_messages_to_content()."""

    def test_convert_messages_user_role(self):
        """User messages форматируются с '**User:**'."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        messages = [
            {"role": "user", "content": {"type": "text", "text": "Help me"}},
        ]

        result = handler._convert_messages_to_content(messages)

        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert "**User:**" in result[0]["text"]
        assert "Help me" in result[0]["text"]

    def test_convert_messages_assistant_role(self):
        """Assistant messages без префикса."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        messages = [
            {"role": "assistant", "content": {"type": "text", "text": "I'll help"}},
        ]

        result = handler._convert_messages_to_content(messages)

        assert len(result) == 1
        assert result[0]["text"] == "I'll help"
        assert "**User:**" not in result[0]["text"]

    def test_convert_messages_mixed_roles(self):
        """Смешанные роли."""
        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="test",
            mcp_manager=MagicMock(),
            description="Test",
        )
        messages = [
            {"role": "user", "content": {"type": "text", "text": "Question"}},
            {"role": "assistant", "content": {"type": "text", "text": "Answer"}},
        ]

        result = handler._convert_messages_to_content(messages)

        assert len(result) == 2
        assert "**User:**" in result[0]["text"]
        assert result[1]["text"] == "Answer"


class TestMCPPromptCommandHandlerExecuteAsync:
    """Тесты execute_async()."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Успешный вызов prompt."""
        mock_manager = AsyncMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "server1": [
                MCPPrompt(
                    name="code_review",
                    arguments=[
                        MCPPromptArgument(name="language", required=True),
                    ],
                ),
            ],
        })
        mock_manager.get_prompt = AsyncMock(return_value=MCPGetPromptResult(
            description="Code review prompt",
            messages=[
                {"role": "assistant", "content": {"type": "text", "text": "Reviewing..."}},
            ],
        ))

        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="code_review",
            mcp_manager=mock_manager,
            description="Review code",
        )

        session = MagicMock()
        result = await handler.execute_async(["python"], session)

        assert len(result.content) == 1
        assert result.content[0]["text"] == "Reviewing..."
        mock_manager.get_prompt.assert_called_once_with(
            server_id="server1",
            name="code_review",
            arguments={"language": "python"},
        )

    @pytest.mark.asyncio
    async def test_execute_server_not_found(self):
        """Ошибка при отсутствии сервера."""
        mock_manager = AsyncMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={})
        mock_manager.get_prompt = AsyncMock(side_effect=Exception("Server not found"))

        handler = MCPPromptCommandHandler(
            server_id="missing_server",
            prompt_name="test",
            mcp_manager=mock_manager,
            description="Test",
        )

        session = MagicMock()
        result = await handler.execute_async([], session)

        assert len(result.content) == 1
        assert "❌" in result.content[0]["text"]
        assert "test" in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_prompt_not_found(self):
        """Ошибка при отсутствии prompt."""
        mock_manager = AsyncMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={"server1": []})
        mock_manager.get_prompt = AsyncMock(side_effect=Exception("Prompt not found"))

        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="missing_prompt",
            mcp_manager=mock_manager,
            description="Test",
        )

        session = MagicMock()
        result = await handler.execute_async([], session)

        assert len(result.content) == 1
        assert "❌" in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_execute_no_arguments(self):
        """Вызов без аргументов."""
        mock_manager = AsyncMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "server1": [MCPPrompt(name="simple")],
        })
        mock_manager.get_prompt = AsyncMock(return_value=MCPGetPromptResult(
            messages=[
                {"role": "assistant", "content": {"type": "text", "text": "Result"}},
            ],
        ))

        handler = MCPPromptCommandHandler(
            server_id="server1",
            prompt_name="simple",
            mcp_manager=mock_manager,
            description="Simple prompt",
        )

        session = MagicMock()
        result = await handler.execute_async([], session)

        assert len(result.content) == 1
        mock_manager.get_prompt.assert_called_once_with(
            server_id="server1",
            name="simple",
            arguments=None,
        )

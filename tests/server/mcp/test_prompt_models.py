"""Тесты для MCP Prompt моделей."""

import pytest
from pydantic import ValidationError

from codelab.server.mcp.models import (
    MCPGetPromptParams,
    MCPGetPromptResult,
    MCPListPromptsParams,
    MCPListPromptsResult,
    MCPPrompt,
    MCPPromptArgument,
    MCPPromptMessage,
)


class TestMCPPromptArgument:
    """Тесты модели MCPPromptArgument."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        arg = MCPPromptArgument(name="language")
        assert arg.name == "language"
        assert arg.title is None
        assert arg.description is None
        assert arg.required is False

    def test_create_full(self):
        """Создание со всеми полями."""
        arg = MCPPromptArgument(
            name="language",
            title="Programming Language",
            description="The programming language to use",
            required=True,
        )
        assert arg.name == "language"
        assert arg.title == "Programming Language"
        assert arg.description == "The programming language to use"
        assert arg.required is True

    def test_deserialization(self):
        """Десериализация из dict."""
        data = {
            "name": "destination",
            "title": "Destination",
            "description": "Where to go",
            "required": True,
        }
        arg = MCPPromptArgument.model_validate(data)
        assert arg.name == "destination"
        assert arg.title == "Destination"
        assert arg.required is True


class TestMCPPrompt:
    """Тесты модели MCPPrompt."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        prompt = MCPPrompt(name="code_review")
        assert prompt.name == "code_review"
        assert prompt.title is None
        assert prompt.description is None
        assert prompt.arguments == []

    def test_create_full(self):
        """Создание со всеми полями."""
        prompt = MCPPrompt(
            name="code_review",
            title="Code Review",
            description="Review code for best practices",
            arguments=[
                MCPPromptArgument(name="language", required=True),
                MCPPromptArgument(name="style", required=False),
            ],
        )
        assert prompt.name == "code_review"
        assert prompt.title == "Code Review"
        assert prompt.description == "Review code for best practices"
        assert len(prompt.arguments) == 2
        assert prompt.arguments[0].name == "language"
        assert prompt.arguments[0].required is True

    def test_deserialization_with_arguments(self):
        """Десериализация с аргументами."""
        data = {
            "name": "plan-vacation",
            "title": "Plan a vacation",
            "description": "Guide through vacation planning",
            "arguments": [
                {
                    "name": "destination",
                    "title": "Destination",
                    "description": "Where to go",
                    "required": True,
                },
                {
                    "name": "duration",
                    "description": "Number of days",
                    "required": False,
                },
            ],
        }
        prompt = MCPPrompt.model_validate(data)
        assert prompt.name == "plan-vacation"
        assert prompt.title == "Plan a vacation"
        assert len(prompt.arguments) == 2
        assert prompt.arguments[0].title == "Destination"
        assert prompt.arguments[0].required is True
        assert prompt.arguments[1].required is False

    def test_requires_name(self):
        """name обязателен."""
        with pytest.raises(ValidationError):
            MCPPrompt()


class TestMCPListPromptsParams:
    """Тесты модели MCPListPromptsParams."""

    def test_create_empty(self):
        """Создание без cursor."""
        params = MCPListPromptsParams()
        assert params.cursor is None

    def test_create_with_cursor(self):
        """Создание с cursor."""
        params = MCPListPromptsParams(cursor="page2cursor")
        assert params.cursor == "page2cursor"

    def test_serialization_exclude_none(self):
        """Сериализация exclude_none убирает cursor."""
        params = MCPListPromptsParams()
        data = params.model_dump(exclude_none=True)
        assert data == {}

    def test_serialization_with_cursor(self):
        """Сериализация с cursor."""
        params = MCPListPromptsParams(cursor="next_page")
        data = params.model_dump(exclude_none=True)
        assert data == {"cursor": "next_page"}


class TestMCPListPromptsResult:
    """Тесты модели MCPListPromptsResult."""

    def test_empty_list(self):
        """Пустой список промптов."""
        result = MCPListPromptsResult(prompts=[])
        assert result.prompts == []
        assert result.next_cursor is None

    def test_with_prompts(self):
        """Список с промптами."""
        result = MCPListPromptsResult(
            prompts=[
                MCPPrompt(name="prompt1"),
                MCPPrompt(name="prompt2"),
            ]
        )
        assert len(result.prompts) == 2
        assert result.prompts[0].name == "prompt1"

    def test_with_next_cursor(self):
        """Результат с nextCursor для пагинации."""
        result = MCPListPromptsResult(
            prompts=[MCPPrompt(name="prompt1")],
            next_cursor="page2cursor",
        )
        assert result.next_cursor == "page2cursor"

    def test_deserialization(self):
        """Десериализация из dict."""
        data = {
            "prompts": [
                {"name": "code_review", "description": "Review code"},
                {"name": "summarize"},
            ],
            "nextCursor": "next123",
        }
        result = MCPListPromptsResult.model_validate(data)
        assert len(result.prompts) == 2
        assert result.prompts[0].name == "code_review"
        assert result.next_cursor == "next123"

    def test_deserialization_no_cursor(self):
        """Десериализация без nextCursor (конец результатов)."""
        data = {
            "prompts": [{"name": "prompt1"}],
        }
        result = MCPListPromptsResult.model_validate(data)
        assert result.next_cursor is None


class TestMCPGetPromptParams:
    """Тесты модели MCPGetPromptParams."""

    def test_create_minimal(self):
        """Создание только с name."""
        params = MCPGetPromptParams(name="code_review")
        assert params.name == "code_review"
        assert params.arguments is None

    def test_create_with_arguments(self):
        """Создание с аргументами."""
        params = MCPGetPromptParams(
            name="plan-vacation",
            arguments={"destination": "Barcelona", "duration": "7"},
        )
        assert params.name == "plan-vacation"
        assert params.arguments == {"destination": "Barcelona", "duration": "7"}

    def test_serialization_exclude_none(self):
        """Сериализация exclude_none убирает arguments если None."""
        params = MCPGetPromptParams(name="simple_prompt")
        data = params.model_dump(exclude_none=True)
        assert data == {"name": "simple_prompt"}
        assert "arguments" not in data

    def test_serialization_with_arguments(self):
        """Сериализация с аргументами."""
        params = MCPGetPromptParams(
            name="plan-vacation",
            arguments={"destination": "Paris"},
        )
        data = params.model_dump(exclude_none=True)
        assert data == {
            "name": "plan-vacation",
            "arguments": {"destination": "Paris"},
        }

    def test_requires_name(self):
        """name обязателен."""
        with pytest.raises(ValidationError):
            MCPGetPromptParams()


class TestMCPPromptMessage:
    """Тесты модели MCPPromptMessage."""

    def test_create_user_message(self):
        """Создание пользовательского сообщения."""
        msg = MCPPromptMessage(
            role="user",
            content={"type": "text", "text": "Help me plan a trip"},
        )
        assert msg.role == "user"
        assert msg.content["type"] == "text"
        assert msg.content["text"] == "Help me plan a trip"

    def test_create_assistant_message(self):
        """Создание сообщения ассистента."""
        msg = MCPPromptMessage(
            role="assistant",
            content={"type": "text", "text": "I'll help you with that"},
        )
        assert msg.role == "assistant"

    def test_deserialization(self):
        """Десериализация из dict."""
        data = {
            "role": "user",
            "content": {"type": "text", "text": "Hello"},
        }
        msg = MCPPromptMessage.model_validate(data)
        assert msg.role == "user"
        assert msg.content["text"] == "Hello"

    def test_requires_role_and_content(self):
        """role и content обязательны."""
        with pytest.raises(ValidationError):
            MCPPromptMessage()
        with pytest.raises(ValidationError):
            MCPPromptMessage(role="user")


class TestMCPGetPromptResult:
    """Тесты модели MCPGetPromptResult."""

    def test_empty_messages(self):
        """Пустой результат."""
        result = MCPGetPromptResult()
        assert result.messages == []
        assert result.description is None

    def test_with_description(self):
        """Результат с описанием."""
        result = MCPGetPromptResult(
            description="A helpful prompt for code review",
            messages=[],
        )
        assert result.description == "A helpful prompt for code review"

    def test_with_dict_messages(self):
        """Результат с dict messages."""
        result = MCPGetPromptResult(
            messages=[
                {"role": "user", "content": {"type": "text", "text": "Review this"}},
                {"role": "assistant", "content": {"type": "text", "text": "OK"}},
            ]
        )
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "user"

    def test_with_typed_messages(self):
        """Результат с типизированными messages."""
        result = MCPGetPromptResult(
            messages=[
                MCPPromptMessage(
                    role="user",
                    content={"type": "text", "text": "Help me"},
                ),
            ]
        )
        assert len(result.messages) == 1
        assert isinstance(result.messages[0], MCPPromptMessage)
        assert result.messages[0].role == "user"

    def test_deserialization(self):
        """Десериализация из dict."""
        data = {
            "description": "Code review prompt",
            "messages": [
                {"role": "user", "content": {"type": "text", "text": "Review"}},
            ],
        }
        result = MCPGetPromptResult.model_validate(data)
        assert result.description == "Code review prompt"
        assert len(result.messages) == 1

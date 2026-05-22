"""Тесты для моделей данных LLM."""


from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMMessage,
    LLMToolCall,
    ModelInfo,
    ProviderInfo,
    StopReason,
)


class TestStopReason:
    """Тесты для enum StopReason."""

    def test_stop_reason_values(self) -> None:
        """Проверить значения StopReason."""
        assert StopReason.END_TURN.value == "end_turn"
        assert StopReason.TOOL_USE.value == "tool_use"
        assert StopReason.MAX_TOKENS.value == "max_tokens"
        assert StopReason.STOP_SEQUENCE.value == "stop_sequence"
        assert StopReason.ERROR.value == "error"
        assert StopReason.CANCELLED.value == "cancelled"
        assert StopReason.STREAMING.value == "streaming"

    def test_stop_reason_is_string_enum(self) -> None:
        """Проверить что StopReason — str enum."""
        assert StopReason.END_TURN == "end_turn"
        assert StopReason.TOOL_USE == "tool_use"

    def test_stop_reason_from_string(self) -> None:
        """Проверить создание StopReason из строки."""
        assert StopReason("end_turn") == StopReason.END_TURN
        assert StopReason("tool_use") == StopReason.TOOL_USE


class TestLLMToolCall:
    """Тесты для LLMToolCall."""

    def test_create_tool_call(self) -> None:
        """Проверить создание LLMToolCall."""
        tool_call = LLMToolCall(id="1", name="test_tool", arguments={"arg": "value"})
        assert tool_call.id == "1"
        assert tool_call.name == "test_tool"
        assert tool_call.arguments == {"arg": "value"}

    def test_tool_call_default_arguments(self) -> None:
        """Проверить arguments по умолчанию."""
        tool_call = LLMToolCall(id="1", name="test_tool")
        assert tool_call.arguments == {}

    def test_tool_call_serialization(self) -> None:
        """Проверить что LLMToolCall — dataclass с полями."""
        tool_call = LLMToolCall(id="1", name="test", arguments={"key": "value"})
        assert hasattr(tool_call, "id")
        assert hasattr(tool_call, "name")
        assert hasattr(tool_call, "arguments")


class TestLLMMessage:
    """Тесты для LLMMessage."""

    def test_create_user_message(self) -> None:
        """Проверить создание user сообщения."""
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None

    def test_create_system_message(self) -> None:
        """Проверить создание system сообщения."""
        msg = LLMMessage(role="system", content="You are helpful")
        assert msg.role == "system"
        assert msg.content == "You are helpful"

    def test_create_assistant_message_with_tools(self) -> None:
        """Проверить создание assistant сообщения с tool_calls."""
        tool_call = LLMToolCall(id="1", name="read_file", arguments={"path": "test.py"})
        msg = LLMMessage(
            role="assistant",
            content="Reading file",
            tool_calls=[tool_call],
        )
        assert msg.role == "assistant"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "read_file"

    def test_create_tool_message(self) -> None:
        """Проверить создание tool сообщения."""
        msg = LLMMessage(
            role="tool",
            content="File content",
            tool_call_id="1",
            name="read_file",
        )
        assert msg.role == "tool"
        assert msg.tool_call_id == "1"
        assert msg.name == "read_file"

    def test_message_optional_fields(self) -> None:
        """Проверить опциональные поля сообщения."""
        msg = LLMMessage(role="user")
        assert msg.content is None
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert msg.name is None


class TestCompletionRequest:
    """Тесты для CompletionRequest."""

    def test_create_request(self) -> None:
        """Проверить создание CompletionRequest."""
        messages = [LLMMessage(role="user", content="Hello")]
        request = CompletionRequest(model="gpt-4o", messages=messages)
        assert request.model == "gpt-4o"
        assert len(request.messages) == 1
        assert request.temperature == 0.7
        assert request.max_tokens == 8192
        assert request.stream is False

    def test_request_with_tools(self) -> None:
        """Проверить request с инструментами."""
        messages = [LLMMessage(role="user", content="Hello")]
        tools = [{"name": "read_file", "description": "Read a file"}]
        request = CompletionRequest(
            model="gpt-4o",
            messages=messages,
            tools=tools,
        )
        assert request.tools == tools

    def test_request_custom_params(self) -> None:
        """Проверить request с кастомными параметрами."""
        messages = [LLMMessage(role="user", content="Hello")]
        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=messages,
            temperature=0.5,
            max_tokens=4096,
            stream=True,
        )
        assert request.temperature == 0.5
        assert request.max_tokens == 4096
        assert request.stream is True

    def test_request_extra_params(self) -> None:
        """Проверить request с extra параметрами."""
        messages = [LLMMessage(role="user", content="Hello")]
        request = CompletionRequest(
            model="gpt-4o",
            messages=messages,
            extra={"top_p": 0.9, "frequency_penalty": 0.1},
        )
        assert request.extra["top_p"] == 0.9
        assert request.extra["frequency_penalty"] == 0.1

    def test_request_default_extra(self) -> None:
        """Проверить extra по умолчанию."""
        messages = [LLMMessage(role="user", content="Hello")]
        request = CompletionRequest(model="gpt-4o", messages=messages)
        assert request.extra == {}


class TestCompletionResponse:
    """Тесты для CompletionResponse."""

    def test_create_response(self) -> None:
        """Проверить создание CompletionResponse."""
        response = CompletionResponse(text="Hello!", stop_reason=StopReason.END_TURN)
        assert response.text == "Hello!"
        assert response.stop_reason == StopReason.END_TURN
        assert response.tool_calls == []

    def test_response_with_tool_calls(self) -> None:
        """Проверить response с tool_calls."""
        tool_call = LLMToolCall(id="1", name="read_file", arguments={"path": "test.py"})
        response = CompletionResponse(
            text="",
            tool_calls=[tool_call],
            stop_reason=StopReason.TOOL_USE,
        )
        assert len(response.tool_calls) == 1
        assert response.stop_reason == StopReason.TOOL_USE

    def test_response_with_model_name(self) -> None:
        """Проверить response с именем модели."""
        response = CompletionResponse(
            text="Hello",
            model="gpt-4o",
        )
        assert response.model == "gpt-4o"

    def test_response_with_usage(self) -> None:
        """Проверить response с usage информацией."""
        response = CompletionResponse(
            text="Hello",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["total_tokens"] == 15

    def test_response_default_values(self) -> None:
        """Проверить значения по умолчанию."""
        response = CompletionResponse(text="Hello")
        assert response.stop_reason == StopReason.END_TURN
        assert response.tool_calls == []
        assert response.model is None
        assert response.usage == {}
        assert response.extra == {}


class TestModelInfo:
    """Тесты для ModelInfo."""

    def test_create_model_info(self) -> None:
        """Проверить создание ModelInfo."""
        model = ModelInfo(id="gpt-4o", provider_id="openai", name="GPT-4o")
        assert model.id == "gpt-4o"
        assert model.provider_id == "openai"
        assert model.name == "GPT-4o"

    def test_model_full_id(self) -> None:
        """Проверить full_id property."""
        model = ModelInfo(id="gpt-4o", provider_id="openai")
        assert model.full_id == "openai/gpt-4o"

        model2 = ModelInfo(id="claude-sonnet-4", provider_id="anthropic")
        assert model2.full_id == "anthropic/claude-sonnet-4"

    def test_model_info_optional_fields(self) -> None:
        """Проверить опциональные поля ModelInfo."""
        model = ModelInfo(id="gpt-4o", provider_id="openai")
        assert model.description is None
        assert model.context_window is None
        assert model.cost_per_input_token is None

    def test_model_info_with_pricing(self) -> None:
        """Проверить ModelInfo с pricing."""
        model = ModelInfo(
            id="gpt-4o",
            provider_id="openai",
            context_window=128000,
            max_output_tokens=16384,
            cost_per_input_token=0.000005,
            cost_per_output_token=0.000015,
        )
        assert model.context_window == 128000
        assert model.max_output_tokens == 16384
        assert model.cost_per_input_token == 0.000005
        assert model.cost_per_output_token == 0.000015

    def test_model_info_capabilities(self) -> None:
        """Проверить capabilities ModelInfo."""
        model = ModelInfo(id="gpt-4o", provider_id="openai")
        assert model.supports_tools is True
        assert model.supports_streaming is True


class TestProviderInfo:
    """Тесты для ProviderInfo."""

    def test_create_provider_info(self) -> None:
        """Проверить создание ProviderInfo."""
        provider = ProviderInfo(id="openai", name="OpenAI")
        assert provider.id == "openai"
        assert provider.name == "OpenAI"

    def test_provider_info_with_models(self) -> None:
        """Проверить ProviderInfo со списком моделей."""
        models = [
            ModelInfo(id="gpt-4o", provider_id="openai"),
            ModelInfo(id="o3", provider_id="openai"),
        ]
        provider = ProviderInfo(id="openai", name="OpenAI", models=models)
        assert len(provider.models) == 2
        assert provider.models[0].id == "gpt-4o"

    def test_provider_info_default_models(self) -> None:
        """Проверить models по умолчанию."""
        provider = ProviderInfo(id="openai", name="OpenAI")
        assert provider.models == []

    def test_provider_info_with_base_url(self) -> None:
        """Проверить ProviderInfo с base_url."""
        provider = ProviderInfo(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com/v1",
        )
        assert provider.base_url == "https://api.openai.com/v1"

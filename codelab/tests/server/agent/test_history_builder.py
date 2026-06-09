"""Тесты для HistoryBuilder."""

import pytest

from codelab.server.agent.history_builder import HistoryBuilder


class TestHistoryBuilderConversion:
    """1.5 — конвертация различных форматов history."""

    @pytest.fixture
    def builder(self):
        return HistoryBuilder()

    def test_user_message_with_text(self, builder):
        history = [{"role": "user", "text": "Hello"}]
        messages = builder.build(history)
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"

    def test_user_message_with_content(self, builder):
        history = [{"role": "user", "content": "Hi there"}]
        messages = builder.build(history)
        assert messages[0].content == "Hi there"

    def test_user_message_with_content_list(self, builder):
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "image", "data": "..."},
                ],
            }
        ]
        messages = builder.build(history)
        assert messages[0].content == "Hello"

    def test_assistant_message(self, builder):
        history = [{"role": "assistant", "text": "Response"}]
        messages = builder.build(history)
        assert messages[0].role == "assistant"
        assert messages[0].content == "Response"

    def test_assistant_with_tool_calls(self, builder):
        history = [
            {
                "role": "assistant",
                "text": "",
                "tool_calls": [
                    {"id": "tc1", "name": "read_file", "arguments": {"path": "test.py"}}
                ],
            }
        ]
        messages = builder.build(history)
        assert messages[0].role == "assistant"
        assert messages[0].tool_calls is not None
        assert len(messages[0].tool_calls) == 1
        assert messages[0].tool_calls[0].id == "tc1"

    def test_tool_message(self, builder):
        history = [
            {
                "role": "tool",
                "tool_call_id": "tc1",
                "content": "file content",
                "name": "read_file",
            }
        ]
        messages = builder.build(history)
        assert messages[0].role == "tool"
        assert messages[0].tool_call_id == "tc1"
        assert messages[0].content == "file content"
        assert messages[0].name == "read_file"

    def test_invalid_role_defaults_to_user(self, builder):
        history = [{"role": "unknown", "text": "test"}]
        messages = builder.build(history)
        assert messages[0].role == "user"

    def test_empty_content_skipped(self, builder):
        history = [{"role": "user", "text": ""}]
        messages = builder.build(history)
        assert len(messages) == 0

    def test_pydantic_model_entry(self, builder):
        class MockEntry:
            def model_dump(self):
                return {"role": "user", "text": "from model"}

        history = [MockEntry()]
        messages = builder.build(history)
        assert messages[0].content == "from model"


class TestSystemPrompt:
    """1.6 — system prompt добавляется первым сообщением."""

    @pytest.fixture
    def builder(self):
        return HistoryBuilder()

    def test_system_prompt_first(self, builder):
        history = [{"role": "user", "text": "Hello"}]
        messages = builder.build(history, system_prompt="You are helpful.")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[0].content == "You are helpful."
        assert messages[1].role == "user"

    def test_no_system_prompt(self, builder):
        history = [{"role": "user", "text": "Hello"}]
        messages = builder.build(history)
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_empty_system_prompt(self, builder):
        history = [{"role": "user", "text": "Hello"}]
        messages = builder.build(history, system_prompt="")
        assert len(messages) == 1

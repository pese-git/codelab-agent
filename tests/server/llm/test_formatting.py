"""Unit-тесты для codelab.server.llm.formatting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.formatting import (
    content_parts_to_openai,
    extract_openai_usage,
    finish_reason_to_stop_reason,
    messages_to_openai_dict,
    parse_openai_tool_calls,
    validate_openai_message_history,
)
from codelab.server.llm.models import LLMMessage, LLMToolCall, StopReason


class TestMessagesToOpenAIDict:
    """messages_to_openai_dict: конвертация LLMMessage → OpenAI dict."""

    def test_text_message(self) -> None:
        msg = LLMMessage(role="user", content="hello")
        result = messages_to_openai_dict([msg])
        assert result == [{"role": "user", "content": "hello"}]

    def test_system_message(self) -> None:
        msg = LLMMessage(role="system", content="you are helpful")
        result = messages_to_openai_dict([msg])
        assert result == [{"role": "system", "content": "you are helpful"}]

    def test_assistant_with_tool_calls(self) -> None:
        msg = LLMMessage(
            role="assistant",
            content=None,
            tool_calls=[LLMToolCall(id="call_1", name="fn", arguments={"x": 1})],
        )
        result = messages_to_openai_dict([msg])
        assert result[0]["role"] == "assistant"
        assert result[0]["tool_calls"] == [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "fn", "arguments": '{"x": 1}'},
            }
        ]

    def test_tool_message(self) -> None:
        msg = LLMMessage(
            role="tool",
            content="42",
            tool_call_id="call_1",
            name="fn",
        )
        result = messages_to_openai_dict([msg])
        assert result == [
            {
                "role": "tool",
                "content": "42",
                "tool_call_id": "call_1",
                "name": "fn",
            }
        ]

    def test_multimodal_content(self) -> None:
        msg = LLMMessage(
            role="user",
            content=[
                ContentPart.make_text("describe"),
                ContentPart.make_image("BASE64DATA", "image/png"),
            ],
        )
        result = messages_to_openai_dict([msg])
        assert result[0]["content"] == [
            {"type": "text", "text": "describe"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,BASE64DATA"},
            },
        ]

    def test_empty_messages(self) -> None:
        assert messages_to_openai_dict([]) == []


class TestContentPartsToOpenAI:
    """content_parts_to_openai: конвертация ContentPart → OpenAI content."""

    def test_text_part(self) -> None:
        parts = [ContentPart.make_text("hi")]
        result = content_parts_to_openai(parts, supports_vision=True, supports_audio=True)
        assert result == [{"type": "text", "text": "hi"}]

    def test_image_part_default_mime(self) -> None:
        parts = [ContentPart(type="image", data="AAAA")]
        result = content_parts_to_openai(parts, supports_vision=True, supports_audio=True)
        assert result == [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AAAA"},
            }
        ]

    def test_image_part_skipped_when_no_vision(self) -> None:
        parts = [ContentPart.make_image("data", "image/jpeg")]
        result = content_parts_to_openai(parts, supports_vision=False, supports_audio=True)
        assert result == []

    def test_audio_part(self) -> None:
        parts = [ContentPart.make_audio("audiodata", "audio/wav")]
        result = content_parts_to_openai(parts, supports_vision=True, supports_audio=True)
        assert result == [
            {
                "type": "input_audio",
                "input_audio": {"data": "audiodata", "format": "wav"},
            }
        ]

    def test_audio_part_skipped_when_no_audio(self) -> None:
        parts = [ContentPart.make_audio("audiodata", "audio/mp3")]
        result = content_parts_to_openai(parts, supports_vision=True, supports_audio=False)
        assert result == []

    def test_empty_parts(self) -> None:
        assert content_parts_to_openai([], supports_vision=True, supports_audio=True) == []


class TestValidateOpenAIMessageHistory:
    """validate_openai_message_history: валидация структуры истории."""

    def test_valid_history(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {}}],
            },
            {"role": "tool", "content": "result", "tool_call_id": "call_1"},
        ]
        validate_openai_message_history(messages)

    def test_tool_without_tool_call_id_raises(self) -> None:
        messages = [
            {
                "role": "assistant",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {}}],
            },
            {"role": "tool", "content": "result"},
        ]
        with pytest.raises(ValueError, match="missing tool_call_id"):
            validate_openai_message_history(messages)

    def test_tool_without_preceding_assistant_raises(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "result", "tool_call_id": "call_1"},
        ]
        with pytest.raises(ValueError, match="must follow an assistant"):
            validate_openai_message_history(messages)

    def test_empty_history(self) -> None:
        validate_openai_message_history([])


class TestFinishReasonToStopReason:
    """finish_reason_to_stop_reason: маппинг OpenAI finish_reason → StopReason."""

    def test_tool_calls_finish_reason(self) -> None:
        assert finish_reason_to_stop_reason(
            "tool_calls", has_tool_calls=False
        ) == StopReason.TOOL_USE

    def test_has_tool_calls_overrides_none_finish(self) -> None:
        assert finish_reason_to_stop_reason(
            None, has_tool_calls=True
        ) == StopReason.TOOL_USE

    def test_length_finish(self) -> None:
        assert finish_reason_to_stop_reason(
            "length", has_tool_calls=False
        ) == StopReason.MAX_TOKENS

    def test_stop_finish(self) -> None:
        assert finish_reason_to_stop_reason(
            "stop", has_tool_calls=False
        ) == StopReason.STOP_SEQUENCE

    def test_unknown_finish(self) -> None:
        assert finish_reason_to_stop_reason(
            "mystery", has_tool_calls=False
        ) == StopReason.END_TURN

    def test_none_finish_no_tools(self) -> None:
        assert finish_reason_to_stop_reason(
            None, has_tool_calls=False
        ) == StopReason.END_TURN


@dataclass
class _FakeFunc:
    name: str
    arguments: str | dict[str, Any]


@dataclass
class _FakeToolCall:
    id: str
    type: str = "function"
    function: _FakeFunc | None = None


class TestParseOpenAIToolCalls:
    """parse_openai_tool_calls: парсинг tool_calls из ответа."""

    def test_string_args_valid_json(self) -> None:
        calls = [
            _FakeToolCall(id="c1", function=_FakeFunc(name="fn", arguments='{"a": 1}'))
        ]
        result = parse_openai_tool_calls(calls)
        assert len(result) == 1
        assert result[0].id == "c1"
        assert result[0].name == "fn"
        assert result[0].arguments == {"a": 1}

    def test_string_args_invalid_json(self) -> None:
        calls = [
            _FakeToolCall(id="c1", function=_FakeFunc(name="fn", arguments="not json"))
        ]
        result = parse_openai_tool_calls(calls)
        assert result[0].arguments == {}

    def test_dict_args(self) -> None:
        calls = [
            _FakeToolCall(id="c1", function=_FakeFunc(name="fn", arguments={"k": "v"}))
        ]
        result = parse_openai_tool_calls(calls)
        assert result[0].arguments == {"k": "v"}

    def test_skip_non_function_type(self) -> None:
        calls = [
            _FakeToolCall(
                id="c1", type="other", function=_FakeFunc(name="fn", arguments="{}")
            )
        ]
        assert parse_openai_tool_calls(calls) == []

    def test_skip_missing_function(self) -> None:
        calls = [_FakeToolCall(id="c1", function=None)]
        assert parse_openai_tool_calls(calls) == []

    def test_empty_args_string(self) -> None:
        calls = [_FakeToolCall(id="c1", function=_FakeFunc(name="fn", arguments=""))]
        result = parse_openai_tool_calls(calls)
        assert result[0].arguments == {}

    def test_none_args(self) -> None:
        calls = [_FakeToolCall(id="c1", function=_FakeFunc(name="fn", arguments=None))]
        result = parse_openai_tool_calls(calls)
        assert result[0].arguments == {}

    def test_empty_iterable(self) -> None:
        assert parse_openai_tool_calls([]) == []


@dataclass
class _FakeUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class TestExtractOpenAIUsage:
    """extract_openai_usage: нормализация usage."""

    def test_full_usage(self) -> None:
        usage = _FakeUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert extract_openai_usage(usage) == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }

    def test_none_usage(self) -> None:
        assert extract_openai_usage(None) == {}

    def test_missing_total_falls_back_to_sum(self) -> None:
        usage = _FakeUsage(prompt_tokens=5, completion_tokens=7, total_tokens=None)
        result = extract_openai_usage(usage)
        assert result == {
            "prompt_tokens": 5,
            "completion_tokens": 7,
            "total_tokens": 12,
        }

    def test_missing_prompt_and_completion(self) -> None:
        usage = _FakeUsage()
        assert extract_openai_usage(usage) == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

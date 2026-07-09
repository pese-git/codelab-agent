"""Unit тесты для TokenCounter."""

from unittest.mock import patch

from codelab.server.agent.context.token_counter import (
    ApproximateTokenCounter,
    TiktokenCounter,
    create_token_counter,
)
from codelab.server.llm.models import LLMMessage, LLMToolCall


class TestApproximateTokenCounter:
    """Тесты для ApproximateTokenCounter."""

    def test_count_empty_string(self):
        """Пустая строка = 0 токенов."""
        counter = ApproximateTokenCounter()
        assert counter.count("") == 0

    def test_count_short_text(self):
        """Короткий текст: len // 4."""
        counter = ApproximateTokenCounter()
        text = "hello"  # 5 chars
        assert counter.count(text) == 1  # 5 // 4 = 1

    def test_count_longer_text(self):
        """Более длинный текст."""
        counter = ApproximateTokenCounter()
        text = "a" * 100
        assert counter.count(text) == 25  # 100 // 4 = 25

    def test_count_messages_empty(self):
        """Пустой список сообщений = 0 токенов."""
        counter = ApproximateTokenCounter()
        assert counter.count_messages([]) == 0

    def test_count_messages_single(self):
        """Одно сообщение с content."""
        counter = ApproximateTokenCounter()
        messages = [LLMMessage(role="user", content="hello world")]
        # "hello world" = 11 chars // 4 = 2
        assert counter.count_messages(messages) == 2

    def test_count_messages_with_tool_calls(self):
        """Сообщение с tool_calls."""
        counter = ApproximateTokenCounter()
        messages = [
            LLMMessage(
                role="assistant",
                content="test",
                tool_calls=[LLMToolCall(id="1", name="read_file", arguments={"path": "/x"})],
            ),
        ]
        tokens = counter.count_messages(messages)
        # "test" = 4//4=1, "read_file"=9//4=2, "{'path': '/x'}"=15//4=3, "1"=1//4=0
        assert tokens > 0

    def test_count_messages_with_tool_call_id(self):
        """tool сообщение с tool_call_id и name."""
        counter = ApproximateTokenCounter()
        messages = [
            LLMMessage(
                role="tool",
                content="result",
                tool_call_id="call_123",
                name="read_file",
            ),
        ]
        tokens = counter.count_messages(messages)
        # "result"=6//4=1, "call_123"=8//4=2, "read_file"=9//4=2
        assert tokens == 5


class TestTiktokenCounter:
    """Тесты для TiktokenCounter."""

    def test_count_basic(self):
        """Tiktoken считает токены."""
        try:
            counter = TiktokenCounter()
        except ImportError:
            return  # tiktoken не установлен

        tokens = counter.count("hello world")
        assert tokens > 0
        assert tokens < 10  # sanity check

    def test_count_empty(self):
        """Пустая строка = 0 токенов."""
        try:
            counter = TiktokenCounter()
        except ImportError:
            return

        assert counter.count("") == 0

    def test_count_messages(self):
        """Подсчёт сообщений через tiktoken."""
        try:
            counter = TiktokenCounter()
        except ImportError:
            return

        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hello"),
        ]
        tokens = counter.count_messages(messages)
        assert tokens > 0

    def test_fallback_on_encoding_error(self):
        """При сбое encoding — fallback на approximate."""
        try:
            counter = TiktokenCounter()
        except ImportError:
            return

        # Мокаем encoding.encode чтобы выбрасывал исключение
        with patch.object(counter._encoding, "encode", side_effect=Exception("fail")):
            tokens = counter.count("test text")
            assert tokens == len("test text") // 4


class TestCreateTokenCounter:
    """Тесты для фабрики create_token_counter."""

    def test_returns_approximate_when_tiktoken_unavailable(self):
        """При отсутствии tiktoken — ApproximateTokenCounter."""
        with patch.dict("sys.modules", {"tiktoken": None}):
            counter = create_token_counter()
            assert isinstance(counter, ApproximateTokenCounter)

    def test_returns_tiktoken_when_available(self):
        """При наличии tiktoken — TiktokenCounter."""
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            return  # Тест работает только если tiktoken установлен

        counter = create_token_counter()
        assert isinstance(counter, TiktokenCounter)

    def test_approximate_counter_works(self):
        """ApproximateTokenCounter работает корректно."""
        counter = ApproximateTokenCounter()
        assert counter.count("test") == 1
        assert counter.count("") == 0
        assert counter.count("a" * 8) == 2

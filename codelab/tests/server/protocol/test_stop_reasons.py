"""Тесты для StopReason enum."""

import pytest

from codelab.server.protocol.stop_reasons import StopReason


class TestStopReason:
    """Тесты StopReason enum."""

    def test_end_turn_value(self):
        """END_TURN имеет правильное строковое значение."""
        assert StopReason.END_TURN == "end_turn"

    def test_max_tokens_value(self):
        """MAX_TOKENS имеет правильное строковое значение."""
        assert StopReason.MAX_TOKENS == "max_tokens"

    def test_max_turn_requests_value(self):
        """MAX_TURN_REQUESTS имеет правильное строковое значение."""
        assert StopReason.MAX_TURN_REQUESTS == "max_turn_requests"

    def test_refusal_value(self):
        """REFUSAL имеет правильное строковое значение."""
        assert StopReason.REFUSAL == "refusal"

    def test_cancelled_value(self):
        """CANCELLED имеет правильное строковое значение."""
        assert StopReason.CANCELLED == "cancelled"

    def test_is_str_enum(self):
        """StopReason является StrEnum."""
        assert isinstance(StopReason.END_TURN, str)
        assert isinstance(StopReason.MAX_TOKENS, str)

    def test_from_string(self):
        """Можно создать StopReason из строки."""
        assert StopReason("end_turn") == StopReason.END_TURN
        assert StopReason("max_turn_requests") == StopReason.MAX_TURN_REQUESTS

    def test_invalid_value_raises(self):
        """Невалидное значение вызывает ValueError."""
        with pytest.raises(ValueError):
            StopReason("invalid_reason")

    def test_all_values_present(self):
        """Все значения из ACP спецификации присутствуют."""
        expected = {"end_turn", "max_tokens", "max_turn_requests", "refusal", "cancelled"}
        actual = {reason.value for reason in StopReason}
        assert actual == expected

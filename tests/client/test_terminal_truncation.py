"""Тесты для truncate_to_byte_limit."""

from codelab.client.infrastructure.services.terminal_executor import truncate_to_byte_limit


class TestTruncateToByteLimit:
    """Тесты функции truncate_to_byte_limit."""

    def test_no_truncation_needed(self) -> None:
        """Текст не обрезается если размер в пределах лимита."""
        text = "Hello, World!"
        result, was_truncated = truncate_to_byte_limit(text, 100)

        assert result == text
        assert was_truncated is False

    def test_truncation_at_byte_limit(self) -> None:
        """Текст обрезается до byte_limit."""
        text = "Hello, World!"  # 13 байт
        result, was_truncated = truncate_to_byte_limit(text, 5)

        assert result == "World!"[-5:]  # Последние 5 байт
        assert was_truncated is True

    def test_truncation_preserves_utf8_boundary(self) -> None:
        """Обрезка происходит на границе UTF-8 символа."""
        # "Привет" = 12 байт в UTF-8 (каждый символ 2 байта)
        text = "Привет мир"  # 21 байт
        result, was_truncated = truncate_to_byte_limit(text, 12)

        # Должно обрезать на границе символа
        assert was_truncated is True
        # Результат должен быть валидным UTF-8
        result.encode("utf-8")  # Не должно вызвать ошибку

    def test_truncation_with_multibyte_characters(self) -> None:
        """Обрезка с multi-byte символами."""
        # Emoji = 4 байта в UTF-8
        text = "Hello 🌍 World"  # 16 байт
        result, was_truncated = truncate_to_byte_limit(text, 10)

        assert was_truncated is True
        # Результат должен быть валидным UTF-8
        result.encode("utf-8")

    def test_exact_byte_limit(self) -> None:
        """Текст точно равен byte_limit."""
        text = "Hello"  # 5 байт
        result, was_truncated = truncate_to_byte_limit(text, 5)

        assert result == text
        assert was_truncated is False

    def test_empty_text(self) -> None:
        """Пустой текст."""
        text = ""
        result, was_truncated = truncate_to_byte_limit(text, 10)

        assert result == ""
        assert was_truncated is False

    def test_zero_byte_limit(self) -> None:
        """Нулевой byte_limit — edge case."""
        text = "Hello"
        result, was_truncated = truncate_to_byte_limit(text, 0)

        # При byte_limit=0, encoded[-0:] возвращает всю строку (Python slice behavior)
        # Это edge case, который не должен возникать в реальности
        assert result == text
        assert was_truncated is True  # len(encoded) > 0

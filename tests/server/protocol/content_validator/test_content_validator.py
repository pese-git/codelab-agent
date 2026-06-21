"""Unit тесты для ContentValidator.

Проверяет:
- Валидацию стандартных типов (text, diff, image, audio)
- Валидацию ACP ToolCallContent типов (terminal, content)
- Обработку отсутствующих обязательных полей
- Обработку неизвестных типов
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.content.validator import ContentValidator


class TestContentValidatorTerminalType:
    """Тесты валидации terminal типа (ACP ToolCallContent.terminal)."""

    @pytest.fixture
    def validator(self) -> ContentValidator:
        """Создать валидатор."""
        return ContentValidator()

    def test_terminal_type_valid(self, validator: ContentValidator) -> None:
        """Terminal тип проходит валидацию с обязательными полями."""
        item = {
            "type": "terminal",
            "terminalId": "term_xyz789",
        }
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is True
        assert error is None

    def test_terminal_type_missing_terminal_id(self, validator: ContentValidator) -> None:
        """Terminal без terminalId не проходит валидацию."""
        item = {
            "type": "terminal",
        }
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is False
        assert error is not None
        assert "terminalId" in error

    def test_terminal_type_in_supported_types(self, validator: ContentValidator) -> None:
        """Terminal тип содержится в SUPPORTED_TYPES."""
        assert "terminal" in validator.SUPPORTED_TYPES

    def test_terminal_type_in_required_fields(self, validator: ContentValidator) -> None:
        """Terminal тип содержится в REQUIRED_FIELDS."""
        assert "terminal" in validator.REQUIRED_FIELDS
        assert validator.REQUIRED_FIELDS["terminal"] == {"type", "terminalId"}


class TestContentValidatorContentType:
    """Тесты валидации content типа (ACP ToolCallContent.content)."""

    @pytest.fixture
    def validator(self) -> ContentValidator:
        """Создать валидатор."""
        return ContentValidator()

    def test_content_type_valid(self, validator: ContentValidator) -> None:
        """Content тип проходит валидацию с обязательными полями."""
        item = {
            "type": "content",
            "content": {
                "type": "text",
                "text": "Hello, world!",
            },
        }
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is True
        assert error is None

    def test_content_type_missing_content_field(self, validator: ContentValidator) -> None:
        """Content без поля content не проходит валидацию."""
        item = {
            "type": "content",
        }
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is False
        assert error is not None
        assert "content" in error

    def test_content_type_in_supported_types(self, validator: ContentValidator) -> None:
        """Content тип содержится в SUPPORTED_TYPES."""
        assert "content" in validator.SUPPORTED_TYPES

    def test_content_type_in_required_fields(self, validator: ContentValidator) -> None:
        """Content тип содержится в REQUIRED_FIELDS."""
        assert "content" in validator.REQUIRED_FIELDS
        assert validator.REQUIRED_FIELDS["content"] == {"type", "content"}


class TestContentValidatorToolCallContentList:
    """Тесты валидации списка ToolCallContent items."""

    @pytest.fixture
    def validator(self) -> ContentValidator:
        """Создать валидатор."""
        return ContentValidator()

    def test_validate_tool_call_content_list_with_terminal(
        self, validator: ContentValidator
    ) -> None:
        """Список с terminal и content типами проходит валидацию."""
        content_items = [
            {
                "type": "terminal",
                "terminalId": "term_xyz789",
            },
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": "Terminal created",
                },
            },
        ]
        is_valid, errors = validator.validate_content_list(content_items)
        assert is_valid is True
        assert errors == []

    def test_validate_tool_call_content_list_with_invalid_terminal(
        self, validator: ContentValidator
    ) -> None:
        """Список с невалидным terminal не проходит валидацию."""
        content_items = [
            {
                "type": "terminal",
                # Отсутствует terminalId
            },
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": "Terminal created",
                },
            },
        ]
        is_valid, errors = validator.validate_content_list(content_items)
        assert is_valid is False
        assert len(errors) == 1
        assert "terminalId" in errors[0]


class TestContentValidatorExistingTypes:
    """Тесты существующих типов для обратной совместимости."""

    @pytest.fixture
    def validator(self) -> ContentValidator:
        """Создать валидатор."""
        return ContentValidator()

    def test_text_type_valid(self, validator: ContentValidator) -> None:
        """Text тип проходит валидацию."""
        item = {"type": "text", "text": "Hello"}
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is True

    def test_diff_type_valid(self, validator: ContentValidator) -> None:
        """Diff тип проходит валидацию."""
        item = {
            "type": "diff",
            "path": "/test.py",
            "newText": "new content",
        }
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is True

    def test_unknown_type_invalid(self, validator: ContentValidator) -> None:
        """Неизвестный тип не проходит валидацию."""
        item = {"type": "unknown_type", "data": "test"}
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is False
        assert "Unsupported content type" in error

    def test_missing_type_invalid(self, validator: ContentValidator) -> None:
        """Отсутствие type не проходит валидацию."""
        item = {"text": "Hello"}
        is_valid, error = validator.validate_content_item(item)
        assert is_valid is False
        assert "Missing 'type' field" in error

"""Тесты покрытия для MessageParser.

Покрывает ранее непокрытые ветки:
- ошибку валидации dict;
- ошибку парсинга authenticate-результата;
- успешный и неуспешный парсинг permission-запроса.
"""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.message_parser import MessageParser
from codelab.client.messages import ACPMessage


class TestMessageParserDict:
    """Тесты для parse_dict."""

    def test_parse_dict_raises_on_validation_error(self) -> None:
        """parse_dict выбрасывает ValueError при невалидном dict."""
        with pytest.raises(ValueError, match="Message validation failed"):
            MessageParser.parse_dict({})


class TestMessageParserAuthenticate:
    """Тесты для parse_authenticate_result."""

    def test_parse_authenticate_result_raises_on_invalid_result(self) -> None:
        """parse_authenticate_result выбрасывает ValueError при ошибке парсинга."""
        message = ACPMessage.model_validate(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "result": "not-a-dict",
            }
        )

        with pytest.raises(ValueError, match="Failed to parse authenticate result"):
            MessageParser.parse_authenticate_result(message)


class TestMessageParserPermissionRequest:
    """Тесты для parse_permission_request."""

    def test_parse_permission_request_returns_none_for_other_method(self) -> None:
        """parse_permission_request возвращает None для другого метода."""
        result = MessageParser.parse_permission_request(
            {"jsonrpc": "2.0", "method": "session/update", "params": {}}
        )

        assert result is None

    def test_parse_permission_request_success(self) -> None:
        """parse_permission_request успешно парсит валидный запрос."""
        message = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess_1",
                "toolCall": {"toolCallId": "call_001"},
                "options": [
                    {
                        "optionId": "allow_once",
                        "name": "Allow once",
                        "kind": "allow_once",
                    }
                ],
            },
        }

        result = MessageParser.parse_permission_request(message)

        assert result is not None
        assert result.id == "req-1"
        assert result.method == "session/request_permission"

    def test_parse_permission_request_raises_on_invalid_payload(self) -> None:
        """parse_permission_request выбрасывает ValueError при невалидном payload."""
        message = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "session/request_permission",
            "params": {},
        }

        with pytest.raises(ValueError, match="Failed to parse permission request"):
            MessageParser.parse_permission_request(message)

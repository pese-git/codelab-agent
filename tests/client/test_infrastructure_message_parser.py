"""Тесты для infrastructure.message_parser модуля.

Тестирует:
- Парсинг JSON-сообщений
- Валидацию JSON-RPC схемы
- Классификацию сообщений
- Парсинг специфичных результатов
"""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.message_parser import MessageParser
from codelab.client.messages import ACPMessage


class TestMessageParserJsonParsing:
    """Тесты парсинга JSON-сообщений."""

    def test_parse_json_request(self) -> None:
        """Проверяет парсинг JSON-запроса."""
        parser = MessageParser()
        json_str = (
            '{"jsonrpc": "2.0", "id": "1", "method": "initialize", '
            '"params": {"protocolVersion": 1}}'
        )
        message = parser.parse_json(json_str)

        assert message.jsonrpc == "2.0"
        assert message.id == "1"
        assert message.method == "initialize"
        assert "protocolVersion" in message.params

    def test_parse_json_response_with_result(self) -> None:
        """Проверяет парсинг JSON-ответа с result."""
        parser = MessageParser()
        json_str = '{"jsonrpc": "2.0", "id": "1", "result": {"status": "ok"}}'
        message = parser.parse_json(json_str)

        assert message.jsonrpc == "2.0"
        assert message.id == "1"
        assert message.result == {"status": "ok"}
        assert message.error is None

    def test_parse_json_response_with_error(self) -> None:
        """Проверяет парсинг JSON-ответа с error."""
        parser = MessageParser()
        json_str = (
            '{"jsonrpc": "2.0", "id": "1", '
            '"error": {"code": -32600, "message": "Invalid Request"}}'
        )
        message = parser.parse_json(json_str)

        assert message.jsonrpc == "2.0"
        assert message.id == "1"
        assert message.error is not None
        assert message.error.code == -32600
        assert message.error.message == "Invalid Request"

    def test_parse_json_invalid_json(self) -> None:
        """Проверяет что невалидный JSON выбрасывает ValueError."""
        parser = MessageParser()
        with pytest.raises(ValueError):
            parser.parse_json('{"invalid": json}')

    def test_parse_json_invalid_schema(self) -> None:
        """Проверяет что невалидная схема выбрасывает ValueError."""
        parser = MessageParser()
        # Ответ не может содержать и result и error
        with pytest.raises(ValueError):
            parser.parse_json(
                '{"jsonrpc": "2.0", "id": "1", "result": {}, '
                '"error": {"code": -1, "message": "err"}}'
            )


class TestMessageParserDictParsing:
    """Тесты парсинга dict-сообщений."""

    def test_parse_dict_request(self) -> None:
        """Проверяет парсинг dict-запроса."""
        parser = MessageParser()
        payload = {
            "jsonrpc": "2.0", "id": "1", "method": "initialize",
            "params": {"protocolVersion": 1},
        }
        message = parser.parse_dict(payload)

        assert message.method == "initialize"
        assert message.id == "1"

    def test_parse_dict_response(self) -> None:
        """Проверяет парсинг dict-ответа."""
        parser = MessageParser()
        payload = {"jsonrpc": "2.0", "id": "1", "result": {"status": "ok"}}
        message = parser.parse_dict(payload)

        assert message.result == {"status": "ok"}
        assert message.error is None


class TestMessageParserClassification:
    """Тесты классификации сообщений."""

    def test_classify_request(self) -> None:
        """Проверяет классификацию запроса."""
        parser = MessageParser()
        message = ACPMessage.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        assert parser.classify_message(message) == "request"

    def test_classify_notification(self) -> None:
        """Проверяет классификацию уведомления."""
        parser = MessageParser()
        # Уведомление имеет method но нет id
        message = ACPMessage(
            method="session/update",
            params={},
            jsonrpc="2.0",
        )
        assert parser.classify_message(message) == "notification"

    def test_classify_response(self) -> None:
        """Проверяет классификацию ответа."""
        parser = MessageParser()
        message = ACPMessage.response("1", {"status": "ok"})
        assert parser.classify_message(message) == "response"


class TestMessageParserParseResults:
    """Тесты парсинга специфичных результатов."""

    def test_parse_initialize_result_success(self) -> None:
        """Проверяет успешный парсинг initialize result."""
        parser = MessageParser()
        message = ACPMessage(
            id="1",
            result={
                "protocolVersion": 1,
                "agentCapabilities": {},
                "authMethods": [],
            },
        )
        result = parser.parse_initialize_result(message)

        assert result.protocolVersion == 1
        assert result.agentCapabilities is not None

    def test_parse_initialize_result_error(self) -> None:
        """Проверяет что ошибка парсинга initialize выбрасывает ValueError."""
        parser = MessageParser()
        message = ACPMessage(id="1", result={"invalid": "data"})

        with pytest.raises(ValueError, match="Failed to parse initialize"):
            parser.parse_initialize_result(message)

    def test_parse_authenticate_result_success(self) -> None:
        """Проверяет успешный парсинг authenticate result."""
        parser = MessageParser()
        message = ACPMessage(id="1", result={"authenticated": True})
        result = parser.parse_authenticate_result(message)

        assert result.authenticated is True

    def test_parse_session_setup_result_success(self) -> None:
        """Проверяет успешный парсинг session setup result."""
        parser = MessageParser()
        message = ACPMessage(
            id="1",
            result={
                "configOptions": [],
                "modes": {"availableModes": [], "currentModeId": "ask"},
            },
        )
        result = parser.parse_session_setup_result(message, method_name="session/new")

        assert result is not None

    def test_parse_session_setup_result_error(self) -> None:
        """Проверяет что ошибка парсинга session setup выбрасывает ValueError."""
        parser = MessageParser()
        message = ACPMessage(id="1", result={"invalid": "data"})

        with pytest.raises(ValueError, match="Failed to parse session setup"):
            parser.parse_session_setup_result(message)

    def test_parse_session_list_result_success(self) -> None:
        """Проверяет успешный парсинг session list result."""
        parser = MessageParser()
        message = ACPMessage(
            id="1",
            result={
                "sessions": [
                    {"sessionId": "sess_1", "cwd": "/tmp", "title": "Test"},
                ],
            },
        )
        result = parser.parse_session_list_result(message)

        assert len(result.sessions) == 1
        assert result.sessions[0].sessionId == "sess_1"

    def test_parse_session_list_result_error(self) -> None:
        """Проверяет что ошибка парсинга session list выбрасывает ValueError."""
        parser = MessageParser()
        message = ACPMessage(id="1", result={"invalid": "data"})

        with pytest.raises(ValueError, match="Failed to parse session list"):
            parser.parse_session_list_result(message)

    def test_parse_prompt_result_success(self) -> None:
        """Проверяет успешный парсинг prompt result."""
        parser = MessageParser()
        message = ACPMessage(
            id="1",
            result={
                "stopReason": "end_turn",
                "content": [{"type": "text", "text": "Response"}],
            },
        )
        result = parser.parse_prompt_result(message)

        assert result.stopReason == "end_turn"

    def test_parse_prompt_result_error(self) -> None:
        """Проверяет что ошибка парсинга prompt выбрасывает ValueError."""
        parser = MessageParser()
        message = ACPMessage(id="1", result={"invalid": "data"})

        with pytest.raises(ValueError, match="Failed to parse prompt"):
            parser.parse_prompt_result(message)

    def test_parse_session_update_success(self) -> None:
        """Проверяет успешный парсинг session update."""
        parser = MessageParser()
        update_dict = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_1",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello"},
                },
            },
        }
        result = parser.parse_session_update(update_dict)

        assert result is not None

    def test_parse_session_update_error(self) -> None:
        """Проверяет что ошибка парсинга session update выбрасывает ValueError."""
        parser = MessageParser()
        # SessionUpdateNotification требует определённые поля
        update_dict = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"invalid": "data"},
        }

        with pytest.raises(ValueError, match="Failed to parse session update"):
            parser.parse_session_update(update_dict)

    def test_parse_permission_request_not_permission(self) -> None:
        """Проверяет что не-permission запрос возвращает None."""
        parser = MessageParser()
        message_dict = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {},
        }
        result = parser.parse_permission_request(message_dict)

        assert result is None


class TestMessageParserEdgeCases:
    """Тесты граничных случаев."""

    def test_parse_json_empty_string(self) -> None:
        """Проверяет парсинг пустой строки."""
        parser = MessageParser()
        with pytest.raises(ValueError):
            parser.parse_json("")

    def test_parse_json_with_unicode(self) -> None:
        """Проверяет парсинг JSON с unicode."""
        parser = MessageParser()
        json_str = '{"jsonrpc": "2.0", "id": "1", "result": {"message": "Привет"}}'
        message = parser.parse_json(json_str)

        assert message.result["message"] == "Привет"

    def test_parse_dict_with_none_values(self) -> None:
        """Проверяет парсинг dict с None значениями."""
        parser = MessageParser()
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "result": None,
            "error": None,
        }
        message = parser.parse_dict(payload)

        assert message.result is None
        assert message.error is None

    def test_classify_message_with_error(self) -> None:
        """Проверяет классификацию сообщения с error."""
        parser = MessageParser()
        from codelab.client.messages import JsonRpcError
        message = ACPMessage(id="1", error=JsonRpcError(code=-32600, message="Invalid Request"))
        assert parser.classify_message(message) == "response"

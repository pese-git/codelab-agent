"""Дополнительные тесты покрытия для `src/codelab/client/messages.py`.

Покрывают непротестированные ветки валидации `ACPMessage`, сериализации,
парсеров `session/update` и парсеров JSON-RPC response.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from codelab.client.messages import (
    ACPMessage,
    JsonRpcError,
    PlanUpdate,
    ToolCallCreatedUpdate,
    ToolCallStateUpdate,
    parse_authenticate_result,
    parse_initialize_result,
    parse_json_params,
    parse_plan_update,
    parse_prompt_result,
    parse_session_list_result,
    parse_session_setup_result,
    parse_session_update_notification,
    parse_structured_session_update,
    parse_tool_call_update,
)


def _session_update_notification(update: dict[str, Any]) -> Any:
    """Вспомогательная функция для создания `session/update` notification."""
    return parse_session_update_notification(
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_1",
                "update": update,
            },
        }
    )


class TestACPMessageValidation:
    """Тесты валидации формы JSON-RPC сообщения."""

    def test_request_with_result_raises_validation_error(self) -> None:
        """Request не может содержать поле `result`."""
        with pytest.raises(ValidationError, match="must not contain result or error"):
            ACPMessage(method="ping", result={})

    def test_response_without_result_or_error_raises_validation_error(self) -> None:
        """Response должен содержать либо `result`, либо `error`."""
        with pytest.raises(ValidationError, match="must contain result or error"):
            ACPMessage(id="1")


class TestACPMessageSerialization:
    """Тесты создания и сериализации `ACPMessage`."""

    def test_notification_factory(self) -> None:
        """Фабрика notification создает сообщение без `id`."""
        notification = ACPMessage.notification("session/cancel", {"sessionId": "s1"})

        assert notification.id is None
        assert notification.method == "session/cancel"
        assert notification.params == {"sessionId": "s1"}

    def test_from_json_deserializes_response(self) -> None:
        """`from_json` преобразует JSON-строку в `ACPMessage`."""
        message = ACPMessage.from_json('{"jsonrpc":"2.0","id":"r1","result":{}}')

        assert message.id == "r1"
        assert message.result == {}

    def test_to_json_uses_compact_format(self) -> None:
        """`to_json` сериализует сообщение в компактный JSON."""
        request = ACPMessage.request("ping", {"x": 1})

        wire = request.to_json()

        assert json.loads(wire) == {
            "jsonrpc": "2.0",
            "id": request.id,
            "method": "ping",
            "params": {"x": 1},
        }

    def test_to_dict_includes_error_payload(self) -> None:
        """`to_dict` включает сериализованный объект ошибки."""
        message = ACPMessage(
            id="1",
            error=JsonRpcError(code=-1, message="boom", data={"detail": "x"}),
        )

        payload = message.to_dict()

        assert payload["error"] == {"code": -1, "message": "boom", "data": {"detail": "x"}}


class TestSessionUpdateParsers:
    """Тесты парсеров `session/update`."""

    def test_parse_tool_call_update_returns_none_for_other_update(self) -> None:
        """`parse_tool_call_update` возвращает `None` для не-tool-call событий."""
        notification = _session_update_notification(
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hi"}}
        )

        assert parse_tool_call_update(notification) is None

    def test_parse_plan_update_returns_none_for_other_update(self) -> None:
        """`parse_plan_update` возвращает `None`, если update не `plan`."""
        notification = _session_update_notification(
            {"sessionUpdate": "tool_call", "toolCallId": "tc_1", "title": "Read"}
        )

        assert parse_plan_update(notification) is None

    def test_parse_structured_session_update_for_tool_call(self) -> None:
        """`parse_structured_session_update` распознает `tool_call`."""
        notification = _session_update_notification(
            {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc_1",
                "title": "Read",
                "kind": "read",
                "status": "pending",
            }
        )

        parsed = parse_structured_session_update(notification)

        assert isinstance(parsed, ToolCallCreatedUpdate)
        assert parsed.toolCallId == "tc_1"

    def test_parse_structured_session_update_for_tool_call_update(self) -> None:
        """`parse_structured_session_update` распознает `tool_call_update`."""
        notification = _session_update_notification(
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tc_1",
                "status": "completed",
            }
        )

        parsed = parse_structured_session_update(notification)

        assert isinstance(parsed, ToolCallStateUpdate)
        assert parsed.status == "completed"

    def test_parse_structured_session_update_for_plan(self) -> None:
        """`parse_structured_session_update` распознает `plan`."""
        notification = _session_update_notification(
            {
                "sessionUpdate": "plan",
                "entries": [
                    {"content": "step", "priority": "medium", "status": "pending"}
                ],
            }
        )

        parsed = parse_structured_session_update(notification)

        assert isinstance(parsed, PlanUpdate)
        assert parsed.entries[0].content == "step"

    def test_parse_structured_session_update_returns_none_for_unknown(self) -> None:
        """`parse_structured_session_update` возвращает `None` для неизвестного типа."""
        notification = _session_update_notification(
            {"sessionUpdate": "unknown", "content": {"text": "ignored"}}
        )

        assert parse_structured_session_update(notification) is None


class TestResultParsers:
    """Тесты парсеров JSON-RPC response."""

    def test_parse_initialize_result_requires_object_result(self) -> None:
        """`parse_initialize_result` требует объект в `result`."""
        message = ACPMessage.response("init_1", None)

        with pytest.raises(ValueError, match="must contain object result"):
            parse_initialize_result(message)

    def test_parse_session_list_result_requires_object_result(self) -> None:
        """`parse_session_list_result` требует объект в `result`."""
        message = ACPMessage.response("list_1", "bad")

        with pytest.raises(ValueError, match="must contain object result"):
            parse_session_list_result(message)

    def test_parse_session_setup_result_requires_object_result(self) -> None:
        """`parse_session_setup_result` требует объект в `result`."""
        message = ACPMessage.response("new_1", ["sessions"])

        with pytest.raises(ValueError, match="session/new response must contain object result"):
            parse_session_setup_result(message, method_name="session/new")

    def test_parse_prompt_result_error_response_raises(self) -> None:
        """`parse_prompt_result` бросает исключение при `error`."""
        message = ACPMessage(
            id="prompt_1",
            error=JsonRpcError(code=-1, message="prompt failed"),
        )

        with pytest.raises(ValueError, match="prompt failed"):
            parse_prompt_result(message)

    def test_parse_prompt_result_requires_object_result(self) -> None:
        """`parse_prompt_result` требует объект в `result`."""
        message = ACPMessage.response("prompt_1", 123)

        with pytest.raises(ValueError, match="must contain object result"):
            parse_prompt_result(message)

    def test_parse_authenticate_result_error_response_raises(self) -> None:
        """`parse_authenticate_result` бросает исключение при `error`."""
        message = ACPMessage(
            id="auth_1",
            error=JsonRpcError(code=-1, message="auth failed"),
        )

        with pytest.raises(ValueError, match="auth failed"):
            parse_authenticate_result(message)

    def test_parse_authenticate_result_requires_object_result(self) -> None:
        """`parse_authenticate_result` требует объект в `result`."""
        message = ACPMessage.response("auth_1", "bad")

        with pytest.raises(ValueError, match="must contain object result"):
            parse_authenticate_result(message)


class TestJsonParams:
    """Тесты парсера JSON-параметров CLI."""

    def test_parse_json_params_returns_empty_dict_for_none(self) -> None:
        """При отсутствии значения возвращается пустой словарь."""
        assert parse_json_params(None) == {}

    def test_parse_json_params_raises_on_invalid_json(self) -> None:
        """Невалидный JSON преобразуется в `ValueError`."""
        with pytest.raises(ValueError, match="Invalid JSON in --params"):
            parse_json_params("{not json}")

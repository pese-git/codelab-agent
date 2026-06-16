"""Тесты для проверки совместимости ACPMessage с различными клиентами.

Особенно важно для клиентов, которые добавляют дополнительные поля
в JSON-RPC сообщения (например, IntelliJ IDEA с полем type).
"""


from codelab.shared.messages import ACPMessage


def test_acp_message_ignores_extra_fields_from_intellij() -> None:
    """IntelliJ IDEA добавляет поле type в JSON-RPC сообщения.
    
    ACPMessage должен игнорировать это поле, а не отклонять сообщение.
    """
    # IntelliJ отправляет сообщения с дополнительным полем type
    payload = {
        "jsonrpc": "2.0",
        "id": "req_1",
        "method": "initialize",
        "params": {"protocolVersion": 1, "clientCapabilities": {}},
        "type": "com.agentclientprotocol.rpc.JsonRpcRequest",
    }
    
    # Должно успешно распарситься, игнорируя поле type
    msg = ACPMessage.model_validate(payload)
    assert msg.method == "initialize"
    assert msg.id == "req_1"
    assert msg.params == {"protocolVersion": 1, "clientCapabilities": {}}


def test_acp_message_from_json_with_extra_fields() -> None:
    """from_json должен работать с сообщениями содержащими дополнительные поля."""
    raw = '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{},"type":"request"}'
    
    msg = ACPMessage.from_json(raw)
    assert msg.method == "initialize"
    assert msg.id == "1"


def test_acp_message_notification_with_extra_fields() -> None:
    """Notification с дополнительными полями должен работать."""
    payload = {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": "sess_1", "update": {"sessionUpdate": "agent_message_chunk"}},
        "type": "com.agentclientprotocol.rpc.JsonRpcNotification",
    }
    
    msg = ACPMessage.model_validate(payload)
    assert msg.is_notification
    assert msg.method == "session/update"


def test_acp_message_response_with_extra_fields() -> None:
    """Response с дополнительными полями должен работать."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req_1",
        "result": {"sessionId": "sess_1"},
        "type": "com.agentclientprotocol.rpc.JsonRpcResponse",
    }
    
    msg = ACPMessage.model_validate(payload)
    assert msg.id == "req_1"
    assert msg.result == {"sessionId": "sess_1"}


def test_acp_message_error_response_with_extra_fields() -> None:
    """Error response с дополнительными полями должен работать."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req_1",
        "error": {"code": -32601, "message": "Method not found"},
        "type": "com.agentclientprotocol.rpc.JsonRpcResponse",
    }
    
    msg = ACPMessage.model_validate(payload)
    assert msg.id == "req_1"
    assert msg.error is not None
    assert msg.error.code == -32601


def test_acp_message_to_json_strips_extra_fields() -> None:
    """to_json не должен включать дополнительные поля в вывод."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req_1",
        "method": "initialize",
        "params": {},
        "type": "request",
        "custom_field": "should_be_ignored",
    }
    
    msg = ACPMessage.model_validate(payload)
    output = msg.to_json()
    
    # Поле type и custom_field не должны быть в выводе
    assert "type" not in output
    assert "custom_field" not in output
    assert "initialize" in output


def test_acp_message_multiple_extra_fields() -> None:
    """Сообщение с несколькими дополнительными полями должно работать."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req_1",
        "method": "test",
        "params": {},
        "type": "request",
        "trace_id": "abc123",
        "span_id": "def456",
        "custom_metadata": {"key": "value"},
    }
    
    msg = ACPMessage.model_validate(payload)
    assert msg.method == "test"
    assert msg.id == "req_1"

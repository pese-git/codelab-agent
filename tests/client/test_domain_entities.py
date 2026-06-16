"""Тесты для Domain entities."""

from __future__ import annotations

from datetime import datetime

from codelab.client.domain import Message, Permission, Session, ToolCall


class TestSession:
    """Тесты для Session entity."""
    
    def test_session_create(self) -> None:
        """Тест создания новой сессии."""
        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={"fs": {"readTextFile": True}},
            server_capabilities={"tools": ["read", "write"]},
        )
        
        assert session.server_host == "127.0.0.1"
        assert session.server_port == 8765
        assert session.client_capabilities == {"fs": {"readTextFile": True}}
        assert session.server_capabilities == {"tools": ["read", "write"]}
        assert session.is_authenticated is False
    
    def test_session_with_custom_id(self) -> None:
        """Тест создания сессии с кастомным ID."""
        session_id = "custom-session-id"
        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id=session_id,
        )
        
        assert session.id == session_id
    
    def test_session_has_timestamp(self) -> None:
        """Тест что у сессии есть timestamp создания."""
        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
        )
        
        assert isinstance(session.created_at, datetime)


class TestMessage:
    """Тесты для Message entity."""
    
    def test_message_request(self) -> None:
        """Тест создания request сообщения."""
        msg = Message.request("initialize", {"capabilities": {}})
        
        assert msg.message_type == "request"
        assert msg.method == "initialize"
        assert msg.params == {"capabilities": {}}
        assert msg.result is None
        assert msg.error is None
    
    def test_message_response(self) -> None:
        """Тест создания response сообщения."""
        result = {"sessionId": "123"}
        msg = Message.response(result=result)
        
        assert msg.message_type == "response"
        assert msg.result == result
        assert msg.error is None
        assert msg.method is None
    
    def test_message_notification(self) -> None:
        """Тест создания notification сообщения."""
        msg = Message.notification("session/update", {"status": "active"})
        
        assert msg.message_type == "notification"
        assert msg.method == "session/update"
        assert msg.params == {"status": "active"}
        assert msg.result is None


class TestPermission:
    """Тесты для Permission entity."""
    
    def test_permission_create(self) -> None:
        """Тест создания запроса разрешения."""
        perm = Permission.create(
            action="read_file",
            resource="/tmp/test.txt",
            session_id="session-123",
            details={"reason": "User requested"},
        )
        
        assert perm.action == "read_file"
        assert perm.resource == "/tmp/test.txt"
        assert perm.session_id == "session-123"
        assert perm.details == {"reason": "User requested"}
        assert isinstance(perm.created_at, datetime)
    
    def test_permission_default_details(self) -> None:
        """Тест что details по умолчанию пусты."""
        perm = Permission.create(
            action="terminal",
            resource="bash",
            session_id="session-123",
        )
        
        assert perm.details == {}


class TestToolCall:
    """Тесты для ToolCall entity."""
    
    def test_tool_call_create(self) -> None:
        """Тест создания вызова инструмента."""
        tool_call = ToolCall.create(
            tool_name="python_repl",
            tool_use_id="tool-use-123",
            input_schema={"type": "object"},
            input_data={"code": "print('hello')"},
            session_id="session-123",
        )
        
        assert tool_call.tool_name == "python_repl"
        assert tool_call.tool_use_id == "tool-use-123"
        assert tool_call.input == {"code": "print('hello')"}
        assert tool_call.session_id == "session-123"
        assert tool_call.result is None
        assert tool_call.error is None
    
    def test_tool_call_with_result(self) -> None:
        """Тест что результат может быть установлен после создания."""
        tool_call = ToolCall.create(
            tool_name="python_repl",
            tool_use_id="tool-use-123",
            input_schema={},
            input_data={},
            session_id="session-123",
        )
        
        tool_call.result = "hello"
        assert tool_call.result == "hello"

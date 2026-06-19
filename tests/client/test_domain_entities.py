"""Тесты для Domain entities."""

from __future__ import annotations

from datetime import datetime

from codelab.client.domain import ClientCapabilities, Permission, Session


class TestSession:
    """Тесты для Session entity."""
    
    def test_session_create(self) -> None:
        """Тест создания новой сессии."""
        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={"fs_read": True},
            server_capabilities={"tools": ["read", "write"]},
        )
        
        assert session.server_host == "127.0.0.1"
        assert session.server_port == 8765
        assert isinstance(session.client_capabilities, ClientCapabilities)
        assert session.client_capabilities.fs_read is True
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

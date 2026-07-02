"""Тесты для иерархии MCP исключений."""

from __future__ import annotations

import pytest

from codelab.server.exceptions import ToolExecutionError
from codelab.server.mcp.exceptions import (
    MCPConnectionError,
    MCPError,
    MCPServerError,
    MCPTimeoutError,
    MCPValidationError,
)


class TestMCPErrorHierarchy:
    """Тесты иерархии MCP исключений."""
    
    def test_mcp_error_inherits_from_tool_execution_error(self) -> None:
        """MCPError наследуется от ToolExecutionError."""
        assert issubclass(MCPError, ToolExecutionError)
    
    def test_mcp_timeout_error_inherits_from_mcp_error(self) -> None:
        """MCPTimeoutError наследуется от MCPError."""
        assert issubclass(MCPTimeoutError, MCPError)
        assert issubclass(MCPTimeoutError, ToolExecutionError)
    
    def test_mcp_connection_error_inherits_from_mcp_error(self) -> None:
        """MCPConnectionError наследуется от MCPError."""
        assert issubclass(MCPConnectionError, MCPError)
        assert issubclass(MCPConnectionError, ToolExecutionError)
    
    def test_mcp_validation_error_inherits_from_mcp_error(self) -> None:
        """MCPValidationError наследуется от MCPError."""
        assert issubclass(MCPValidationError, MCPError)
        assert issubclass(MCPValidationError, ToolExecutionError)
    
    def test_mcp_server_error_inherits_from_mcp_error(self) -> None:
        """MCPServerError наследуется от MCPError."""
        assert issubclass(MCPServerError, MCPError)
        assert issubclass(MCPServerError, ToolExecutionError)


class TestMCPTimeoutError:
    """Тесты для MCPTimeoutError."""
    
    def test_timeout_error_message(self) -> None:
        """MCPTimeoutError содержит корректное сообщение."""
        error = MCPTimeoutError("mcp:server:tool", 30.0)
        
        assert "mcp:server:tool" in str(error)
        assert "30.0" in str(error)
        assert "timed out" in str(error)
    
    def test_timeout_error_attributes(self) -> None:
        """MCPTimeoutError сохраняет атрибуты."""
        error = MCPTimeoutError("test_tool", 60.0)
        
        assert error.tool_name == "test_tool"
        assert error.timeout == 60.0
    
    def test_timeout_error_can_be_caught_as_mcp_error(self) -> None:
        """MCPTimeoutError можно поймать как MCPError."""
        with pytest.raises(MCPError):
            raise MCPTimeoutError("tool", 30.0)
    
    def test_timeout_error_can_be_caught_as_tool_execution_error(self) -> None:
        """MCPTimeoutError можно поймать как ToolExecutionError."""
        with pytest.raises(ToolExecutionError):
            raise MCPTimeoutError("tool", 30.0)


class TestMCPConnectionError:
    """Тесты для MCPConnectionError."""
    
    def test_connection_error_message(self) -> None:
        """MCPConnectionError содержит корректное сообщение."""
        error = MCPConnectionError("server_1")
        
        assert "server_1" in str(error)
        assert "Failed to connect" in str(error)
    
    def test_connection_error_with_original_error(self) -> None:
        """MCPConnectionError включает оригинальную ошибку."""
        original = ConnectionRefusedError("Connection refused")
        error = MCPConnectionError("server_1", original)
        
        assert "server_1" in str(error)
        assert "Connection refused" in str(error)
        assert error.original_error is original
    
    def test_connection_error_attributes(self) -> None:
        """MCPConnectionError сохраняет атрибуты."""
        error = MCPConnectionError("test_server")
        
        assert error.server_id == "test_server"
        assert error.original_error is None


class TestMCPValidationError:
    """Тесты для MCPValidationError."""
    
    def test_validation_error_message(self) -> None:
        """MCPValidationError содержит корректное сообщение."""
        error = MCPValidationError("test_tool")
        
        assert "test_tool" in str(error)
        assert "Validation failed" in str(error)
    
    def test_validation_error_with_errors_list(self) -> None:
        """MCPValidationError включает список ошибок валидации."""
        errors = ["Missing required field 'path'", "Invalid type for 'content'"]
        error = MCPValidationError("test_tool", errors)
        
        assert "Missing required field 'path'" in str(error)
        assert "Invalid type for 'content'" in str(error)
        assert error.validation_errors == errors
    
    def test_validation_error_attributes(self) -> None:
        """MCPValidationError сохраняет атрибуты."""
        error = MCPValidationError("test_tool", ["error1"])
        
        assert error.tool_name == "test_tool"
        assert error.validation_errors == ["error1"]


class TestMCPServerError:
    """Тесты для MCPServerError."""
    
    def test_server_error_message(self) -> None:
        """MCPServerError содержит корректное сообщение."""
        error = MCPServerError(
            server_id="server_1",
            tool_name="test_tool",
            error_message="Internal server error",
        )
        
        assert "server_1" in str(error)
        assert "test_tool" in str(error)
        assert "Internal server error" in str(error)
    
    def test_server_error_with_code(self) -> None:
        """MCPServerError включает код ошибки."""
        error = MCPServerError(
            server_id="server_1",
            tool_name="test_tool",
            error_message="Not found",
            error_code=404,
        )
        
        assert "404" in str(error)
        assert error.error_code == 404
    
    def test_server_error_attributes(self) -> None:
        """MCPServerError сохраняет атрибуты."""
        error = MCPServerError(
            server_id="test_server",
            tool_name="test_tool",
            error_message="Error message",
            error_code=500,
        )
        
        assert error.server_id == "test_server"
        assert error.tool_name == "test_tool"
        assert error.error_message == "Error message"
        assert error.error_code == 500

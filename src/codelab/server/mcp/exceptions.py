"""Иерархия исключений для MCP (Model Context Protocol).

Предоставляет специализированные классы исключений для различных типов ошибок,
возникающих при работе с MCP серверами и инструментами.

Иерархия наследуется от ToolExecutionError для интеграции с существующей
системой обработки ошибок инструментов.
"""

from __future__ import annotations

from ..exceptions import ToolExecutionError


class MCPError(ToolExecutionError):
    """Базовое исключение для всех ошибок MCP.
    
    Наследуется от ToolExecutionError для интеграции с существующей
    системой обработки ошибок инструментов.
    """
    
    pass


class MCPTimeoutError(MCPError):
    """Timeout при вызове MCP инструмента.
    
    Возникает когда выполнение инструмента превышает заданный timeout.
    
    Attributes:
        tool_name: Имя инструмента, который вызвал timeout.
        timeout: Значение timeout в секундах.
    """
    
    def __init__(self, tool_name: str, timeout: float) -> None:
        """Инициализация исключения.
        
        Args:
            tool_name: Имя инструмента.
            timeout: Значение timeout в секундах.
        """
        self.tool_name = tool_name
        self.timeout = timeout
        super().__init__(
            f"MCP tool '{tool_name}' timed out after {timeout}s"
        )


class MCPConnectionError(MCPError):
    """Ошибка соединения с MCP сервером.
    
    Возникает при проблемах с сетью или когда MCP сервер недоступен.
    
    Attributes:
        server_id: ID сервера, с которым возникла проблема.
        original_error: Оригинальное исключение (опционально).
    """
    
    def __init__(
        self,
        server_id: str,
        original_error: Exception | None = None,
    ) -> None:
        """Инициализация исключения.
        
        Args:
            server_id: ID MCP сервера.
            original_error: Оригинальное исключение (опционально).
        """
        self.server_id = server_id
        self.original_error = original_error
        
        error_msg = f"Failed to connect to MCP server '{server_id}'"
        if original_error:
            error_msg += f": {original_error}"
        
        super().__init__(error_msg)


class MCPValidationError(MCPError):
    """Ошибка валидации аргументов MCP инструмента.
    
    Возникает когда переданные аргументы не соответствуют схеме инструмента.
    
    Attributes:
        tool_name: Имя инструмента.
        validation_errors: Список ошибок валидации.
    """
    
    def __init__(
        self,
        tool_name: str,
        validation_errors: list[str] | None = None,
    ) -> None:
        """Инициализация исключения.
        
        Args:
            tool_name: Имя инструмента.
            validation_errors: Список ошибок валидации (опционально).
        """
        self.tool_name = tool_name
        self.validation_errors = validation_errors or []
        
        error_msg = f"Validation failed for MCP tool '{tool_name}'"
        if self.validation_errors:
            error_msg += ": " + "; ".join(self.validation_errors)
        
        super().__init__(error_msg)


class MCPServerError(MCPError):
    """Ошибка на стороне MCP сервера.
    
    Возникает когда MCP сервер возвращает ошибку выполнения.
    
    Attributes:
        server_id: ID сервера.
        tool_name: Имя инструмента.
        error_code: Код ошибки от сервера (опционально).
        error_message: Сообщение об ошибке от сервера.
    """
    
    def __init__(
        self,
        server_id: str,
        tool_name: str,
        error_message: str,
        error_code: int | None = None,
    ) -> None:
        """Инициализация исключения.
        
        Args:
            server_id: ID MCP сервера.
            tool_name: Имя инструмента.
            error_message: Сообщение об ошибке.
            error_code: Код ошибки (опционально).
        """
        self.server_id = server_id
        self.tool_name = tool_name
        self.error_code = error_code
        self.error_message = error_message
        
        error_msg = f"MCP server '{server_id}' returned error for tool '{tool_name}'"
        if error_code is not None:
            error_msg += f" (code: {error_code})"
        error_msg += f": {error_message}"
        
        super().__init__(error_msg)

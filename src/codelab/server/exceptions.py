"""Иерархия исключений для ACP Server.

Предоставляет специализированные классы исключений для различных типов ошибок,
возникающих при работе с протоколом ACP.
"""


class ACPError(Exception):
    """Базовое исключение для всех ошибок ACP."""

    pass


class ValidationError(ACPError):
    """Ошибка валидации данных (некорректные параметры, формат и т.д.)."""

    pass


class AuthenticationError(ACPError):
    """Ошибка аутентификации (неверные credentials, истекший токен и т.д.)."""

    pass


class AuthorizationError(ACPError):
    """Ошибка авторизации (недостаточно прав для операции)."""

    pass


class PermissionDeniedError(AuthorizationError):
    """Отказ в разрешении на выполнение операции (tool call, file access и т.д.)."""

    pass


class StorageError(ACPError):
    """Ошибка при работе с хранилищем сессий."""

    pass


class SessionNotFoundError(StorageError):
    """Сессия не найдена в хранилище."""

    pass


class SessionAlreadyExistsError(StorageError):
    """Попытка создать сессию с уже существующим ID."""

    pass


class AgentProcessingError(ACPError):
    """Ошибка при обработке запроса агентом (LLM, tool execution и т.д.)."""

    pass


class ToolExecutionError(AgentProcessingError):
    """Ошибка при выполнении tool call."""

    pass


class ProtocolError(ACPError):
    """Ошибка протокола ACP (неизвестный метод, некорректное состояние и т.д.)."""

    pass


class InvalidStateError(ProtocolError):
    """Операция невозможна в текущем состоянии сессии."""

    pass

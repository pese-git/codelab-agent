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


class SessionRevisionConflictError(StorageError):
    """Запись отклонена: документ сессии изменился с момента загрузки.

    Возникает, когда пишущий держит копию с устаревшей ревизией — например
    фоновое исполнение turn'а, чья копия живёт через `await`, пока другой запрос
    успел сохранить свои решения. Отклонение вместо перезаписи выбрано осознанно
    (ADR-007): молчаливое затирание уже дважды стоило нам потерянных решений
    (P0-39, P2-42), а конфликт должен быть видимым.
    """

    def __init__(self, session_id: str, expected: int, actual: int) -> None:
        self.session_id = session_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Session {session_id} changed since load: "
            f"ожидалась ревизия {expected}, на диске {actual}"
        )


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

"""Исключения для RPC вызовов на клиент.

Содержит специализированные исключения для обработки ошибок при взаимодействии
с клиентом через JSON-RPC протокол.
"""

from __future__ import annotations


class ClientRPCError(Exception):
    """Базовое исключение для RPC вызовов на клиенте.
    
    Используется для всех ошибок, связанных с вызовом методов на клиентской стороне.
    """

    pass


class ClientRPCTimeoutError(ClientRPCError):
    """Timeout при ожидании ответа от клиента.
    
    Возникает, когда время ожидания ответа на JSON-RPC request превышает timeout.
    """

    pass


class ClientRPCCancelledError(ClientRPCError):
    """RPC запрос был отменён.
    
    Возникает, когда RPC запрос был явно отменён через cancellation_event,
    например при session/cancel или disconnect клиента.
    """

    pass


class ClientCapabilityMissingError(ClientRPCError):
    """Клиент не поддерживает требуемую capability.
    
    Возникает при попытке вызвать метод, который не поддерживается клиентом
    согласно его capabilities, переданным при инициализации.
    """

    pass


class ClientRPCResponseError(ClientRPCError):
    """Клиент вернул ошибку в JSON-RPC response.
    
    Содержит код ошибки и дополнительные данные от клиента.
    
    Attributes:
        code: JSON-RPC код ошибки
        message: Описание ошибки
        data: Дополнительные данные об ошибке (опционально)
    """

    def __init__(
        self, code: int, message: str, data: dict | None = None
    ) -> None:
        """Инициализировать ошибку RPC ответа.
        
        Args:
            code: JSON-RPC код ошибки (обычно отрицательное число)
            message: Текстовое описание ошибки
            data: Дополнительные данные об ошибке (опционально)
        """
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"RPC Error {code}: {message}")

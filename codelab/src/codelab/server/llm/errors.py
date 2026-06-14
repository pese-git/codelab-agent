"""Исключения для мульти-провайдер LLM архитектуры.

Определяет иерархию исключений для обработки ошибок провайдеров:
- ProviderErrorType — enum типов ошибок
- ProviderError — базовое исключение ошибок провайдера
- ProviderNotFoundError — провайдер не найден в registry
- ModelNotFoundError — модель не найдена у провайдера
- AllProvidersFailed — все провайдеры в fallback цепочке упали
"""

from __future__ import annotations

from enum import StrEnum


class ProviderErrorType(StrEnum):
    """Типы ошибок LLM провайдера.

    Атрибуты:
        RATE_LIMIT: Превышен лимит запросов (retry-able)
        TIMEOUT: Таймаут запроса (retry-able)
        AUTH_ERROR: Ошибка аутентификации (NOT retry-able)
        INVALID_REQUEST: Некорректный запрос (NOT retry-able)
        SERVICE_UNAVAILABLE: Сервис недоступен (retry-able)
        INTERNAL_ERROR: Внутренняя ошибка провайдера (retry-able)
        MODEL_UNAVAILABLE: Модель временно недоступна (retry-able)
        UNKNOWN: Неизвестная ошибка
    """

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    INVALID_REQUEST = "invalid_request"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL_ERROR = "internal_error"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNKNOWN = "unknown"


class ProviderError(Exception):
    """Базовое исключение для ошибок LLM провайдера.

    Атрибуты:
        message: Описание ошибки
        error_type: Тип ошибки
        provider_id: ID провайдера, вызвавшего ошибку
        retryable: Можно ли повторить запрос
    """

    def __init__(
        self,
        message: str,
        error_type: ProviderErrorType = ProviderErrorType.UNKNOWN,
        provider_id: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.provider_id = provider_id
        # По умолчанию определяем retryable по типу ошибки
        self.retryable = retryable if retryable is not None else self._default_retryable()

    def _default_retryable(self) -> bool:
        """Определить, можно ли повторить запрос по умолчанию."""
        retryable_types = {
            ProviderErrorType.RATE_LIMIT,
            ProviderErrorType.TIMEOUT,
            ProviderErrorType.SERVICE_UNAVAILABLE,
            ProviderErrorType.INTERNAL_ERROR,
            ProviderErrorType.MODEL_UNAVAILABLE,
        }
        return self.error_type in retryable_types

    def __str__(self) -> str:
        provider = f" [{self.provider_id}]" if self.provider_id else ""
        return f"{self.__class__.__name__}{provider}: {self.message} (type={self.error_type.value})"


class ProviderNotFoundError(ProviderError):
    """Провайдер не найден в registry.

    Возникает когда запрошенный provider_id не зарегистрирован.
    """

    def __init__(self, provider_id: str, message: str | None = None) -> None:
        msg = message or f"Provider '{provider_id}' not found in registry"
        super().__init__(
            message=msg,
            error_type=ProviderErrorType.INVALID_REQUEST,
            provider_id=provider_id,
            retryable=False,
        )


class ModelNotFoundError(ProviderError):
    """Модель не найдена у провайдера.

    Возникает когда запрошенная модель недоступна у данного провайдера.
    """

    def __init__(
        self,
        model_id: str,
        provider_id: str,
        message: str | None = None,
    ) -> None:
        msg = message or f"Model '{model_id}' not found for provider '{provider_id}'"
        super().__init__(
            message=msg,
            error_type=ProviderErrorType.MODEL_UNAVAILABLE,
            provider_id=provider_id,
            retryable=False,
        )
        self.model_id = model_id


class AllProvidersFailed(ProviderError):
    """Все провайдеры в fallback цепочке упали.

    Содержит список всех ошибок, произошедших при попытке fallback.
    """

    def __init__(
        self,
        errors: list[ProviderError],
        message: str | None = None,
    ) -> None:
        msg = message or f"All {len(errors)} providers failed"
        super().__init__(
            message=msg,
            error_type=ProviderErrorType.SERVICE_UNAVAILABLE,
            retryable=False,
        )
        self.errors = errors

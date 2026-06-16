"""Тесты для исключений LLM провайдеров."""

import pytest

from codelab.server.llm.errors import (
    AllProvidersFailed,
    ModelNotFoundError,
    ProviderError,
    ProviderErrorType,
    ProviderNotFoundError,
)


class TestProviderErrorType:
    """Тесты для enum ProviderErrorType."""

    def test_error_type_values(self) -> None:
        """Проверить значения ProviderErrorType."""
        assert ProviderErrorType.RATE_LIMIT.value == "rate_limit"
        assert ProviderErrorType.TIMEOUT.value == "timeout"
        assert ProviderErrorType.AUTH_ERROR.value == "auth_error"
        assert ProviderErrorType.INVALID_REQUEST.value == "invalid_request"
        assert ProviderErrorType.SERVICE_UNAVAILABLE.value == "service_unavailable"
        assert ProviderErrorType.INTERNAL_ERROR.value == "internal_error"
        assert ProviderErrorType.MODEL_UNAVAILABLE.value == "model_unavailable"
        assert ProviderErrorType.UNKNOWN.value == "unknown"

    def test_error_type_is_string_enum(self) -> None:
        """Проверить что ProviderErrorType — str enum."""
        assert ProviderErrorType.RATE_LIMIT == "rate_limit"
        assert ProviderErrorType.TIMEOUT == "timeout"


class TestProviderError:
    """Тесты для ProviderError."""

    def test_create_provider_error(self) -> None:
        """Проверить создание ProviderError."""
        error = ProviderError("Test error")
        assert error.message == "Test error"
        assert error.error_type == ProviderErrorType.UNKNOWN
        assert error.provider_id is None

    def test_provider_error_with_provider_id(self) -> None:
        """Проверить ProviderError с provider_id."""
        error = ProviderError("Test error", provider_id="openai")
        assert error.provider_id == "openai"

    def test_provider_error_with_error_type(self) -> None:
        """Проверить ProviderError с error_type."""
        error = ProviderError(
            "Rate limited",
            error_type=ProviderErrorType.RATE_LIMIT,
            provider_id="openai",
        )
        assert error.error_type == ProviderErrorType.RATE_LIMIT

    def test_provider_error_retryable_default(self) -> None:
        """Проверить retryable по умолчанию для разных типов."""
        # Retryable errors
        assert ProviderError("rate", error_type=ProviderErrorType.RATE_LIMIT).retryable is True
        assert ProviderError("timeout", error_type=ProviderErrorType.TIMEOUT).retryable is True
        assert (
            ProviderError("unavailable", error_type=ProviderErrorType.SERVICE_UNAVAILABLE).retryable
            is True
        )
        assert (
            ProviderError("internal", error_type=ProviderErrorType.INTERNAL_ERROR).retryable is True
        )
        assert (
            ProviderError("model_unavail", error_type=ProviderErrorType.MODEL_UNAVAILABLE).retryable
            is True
        )

        # Non-retryable errors
        assert ProviderError("auth", error_type=ProviderErrorType.AUTH_ERROR).retryable is False
        assert (
            ProviderError("invalid", error_type=ProviderErrorType.INVALID_REQUEST).retryable
            is False
        )
        assert ProviderError("unknown", error_type=ProviderErrorType.UNKNOWN).retryable is False

    def test_provider_error_retryable_override(self) -> None:
        """Проверить переопределение retryable."""
        error = ProviderError(
            "Test",
            error_type=ProviderErrorType.RATE_LIMIT,
            retryable=False,
        )
        assert error.retryable is False

        error2 = ProviderError(
            "Test",
            error_type=ProviderErrorType.AUTH_ERROR,
            retryable=True,
        )
        assert error2.retryable is True

    def test_provider_error_str(self) -> None:
        """Проверить строковое представление."""
        error = ProviderError("Test error", provider_id="openai")
        str_repr = str(error)
        assert "ProviderError" in str_repr
        assert "openai" in str_repr
        assert "Test error" in str_repr

    def test_provider_error_str_without_provider(self) -> None:
        """Проверить строковое представление без provider_id."""
        error = ProviderError("Test error")
        str_repr = str(error)
        assert "ProviderError" in str_repr
        assert "Test error" in str_repr

    def test_provider_error_is_exception(self) -> None:
        """Проверить что ProviderError — Exception."""
        error = ProviderError("Test")
        assert isinstance(error, Exception)

    def test_provider_error_can_be_raised(self) -> None:
        """Проверить что ProviderError можно raise."""
        with pytest.raises(ProviderError, match="Test error"):
            raise ProviderError("Test error")


class TestProviderNotFoundError:
    """Тесты для ProviderNotFoundError."""

    def test_create_provider_not_found_error(self) -> None:
        """Проверить создание ProviderNotFoundError."""
        error = ProviderNotFoundError("unknown_provider")
        assert error.provider_id == "unknown_provider"
        assert error.retryable is False
        assert "unknown_provider" in str(error)

    def test_provider_not_found_error_default_message(self) -> None:
        """Проверить сообщение по умолчанию."""
        error = ProviderNotFoundError("anthropic")
        assert "anthropic" in error.message
        assert "not found" in error.message.lower()

    def test_provider_not_found_error_custom_message(self) -> None:
        """Проверить кастомное сообщение."""
        error = ProviderNotFoundError("openai", message="Custom message")
        assert error.message == "Custom message"

    def test_provider_not_found_error_type(self) -> None:
        """Проверить тип ошибки."""
        error = ProviderNotFoundError("test")
        assert error.error_type == ProviderErrorType.INVALID_REQUEST

    def test_provider_not_found_is_provider_error(self) -> None:
        """Проверить наследование от ProviderError."""
        error = ProviderNotFoundError("test")
        assert isinstance(error, ProviderError)


class TestModelNotFoundError:
    """Тесты для ModelNotFoundError."""

    def test_create_model_not_found_error(self) -> None:
        """Проверить создание ModelNotFoundError."""
        error = ModelNotFoundError(model_id="gpt-5", provider_id="openai")
        assert error.model_id == "gpt-5"
        assert error.provider_id == "openai"
        assert error.retryable is False

    def test_model_not_found_error_default_message(self) -> None:
        """Проверить сообщение по умолчанию."""
        error = ModelNotFoundError(model_id="gpt-5", provider_id="openai")
        assert "gpt-5" in error.message
        assert "openai" in error.message

    def test_model_not_found_error_custom_message(self) -> None:
        """Проверить кастомное сообщение."""
        error = ModelNotFoundError(
            model_id="gpt-5",
            provider_id="openai",
            message="Model discontinued",
        )
        assert error.message == "Model discontinued"

    def test_model_not_found_error_type(self) -> None:
        """Проверить тип ошибки."""
        error = ModelNotFoundError(model_id="gpt-5", provider_id="openai")
        assert error.error_type == ProviderErrorType.MODEL_UNAVAILABLE

    def test_model_not_found_is_provider_error(self) -> None:
        """Проверить наследование от ProviderError."""
        error = ModelNotFoundError(model_id="test", provider_id="test")
        assert isinstance(error, ProviderError)


class TestAllProvidersFailed:
    """Тесты для AllProvidersFailed."""

    def test_create_all_providers_failed(self) -> None:
        """Проверить создание AllProvidersFailed."""
        errors = [
            ProviderError("Error 1", provider_id="openai"),
            ProviderError("Error 2", provider_id="anthropic"),
        ]
        error = AllProvidersFailed(errors=errors)
        assert len(error.errors) == 2
        assert error.retryable is False

    def test_all_providers_failed_default_message(self) -> None:
        """Проверить сообщение по умолчанию."""
        errors = [ProviderError("Error 1"), ProviderError("Error 2")]
        error = AllProvidersFailed(errors=errors)
        assert "2" in error.message
        assert "failed" in error.message.lower()

    def test_all_providers_failed_custom_message(self) -> None:
        """Проверить кастомное сообщение."""
        errors = [ProviderError("Error 1")]
        error = AllProvidersFailed(errors=errors, message="All providers down")
        assert error.message == "All providers down"

    def test_all_providers_failed_error_type(self) -> None:
        """Проверить тип ошибки."""
        errors = [ProviderError("Error 1")]
        error = AllProvidersFailed(errors=errors)
        assert error.error_type == ProviderErrorType.SERVICE_UNAVAILABLE

    def test_all_providers_failed_is_provider_error(self) -> None:
        """Проверить наследование от ProviderError."""
        errors = [ProviderError("Error 1")]
        error = AllProvidersFailed(errors=errors)
        assert isinstance(error, ProviderError)

    def test_all_providers_failed_empty_errors(self) -> None:
        """Проверить с пустым списком ошибок."""
        error = AllProvidersFailed(errors=[])
        assert len(error.errors) == 0
        assert "0" in error.message

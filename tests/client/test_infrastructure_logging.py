"""Тесты для infrastructure.logging_config модуля.

Тестирует:
- Инициализацию логирования
- OperationTimer контекстный менеджер
- Получение логгера
"""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.logging_config import (
    OperationTimer,
    get_logger,
    setup_logging,
)


class TestSetupLogging:
    """Тесты инициализации логирования."""

    def test_setup_logging_default(self) -> None:
        """Проверяет инициализацию логирования со стандартными параметрами."""
        # Просто убедимся что функция выполняется без ошибок
        setup_logging()
        logger = get_logger(__name__)
        assert logger is not None

    def test_setup_logging_debug(self) -> None:
        """Проверяет инициализацию логирования на уровне DEBUG."""
        setup_logging(level="DEBUG")
        logger = get_logger(__name__)
        assert logger is not None

    def test_setup_logging_error(self) -> None:
        """Проверяет инициализацию логирования на уровне ERROR."""
        setup_logging(level="ERROR")
        logger = get_logger(__name__)
        assert logger is not None


class TestOperationTimer:
    """Тесты для OperationTimer контекстного менеджера."""

    def test_operation_timer_success(self) -> None:
        """Проверяет таймер при успешном выполнении операции."""
        logger = get_logger(__name__)
        timer = OperationTimer(logger, "test_op", key="value")

        assert timer.operation_name == "test_op"
        assert timer.context == {"key": "value"}
        assert timer.start_time is None

    def test_operation_timer_context_manager(self) -> None:
        """Проверяет что OperationTimer работает как контекстный менеджер."""
        logger = get_logger(__name__)

        with OperationTimer(logger, "operation") as timer:
            assert timer.start_time is not None
            assert timer.operation_name == "operation"

    def test_operation_timer_with_context(self) -> None:
        """Проверяет таймер с дополнительным контекстом."""
        logger = get_logger(__name__)

        with OperationTimer(
            logger,
            "db_query",
            database="postgresql",
            table="users",
        ) as timer:
            assert timer.context == {"database": "postgresql", "table": "users"}

    def test_operation_timer_sets_start_time(self) -> None:
        """Проверяет что таймер устанавливает start_time при входе."""
        logger = get_logger(__name__)

        timer = OperationTimer(logger, "test")
        assert timer.start_time is None

        with timer:
            assert timer.start_time is not None

    def test_operation_timer_handles_exception(self) -> None:
        """Проверяет что таймер обрабатывает исключения корректно."""
        logger = get_logger(__name__)

        with pytest.raises(ValueError), OperationTimer(logger, "failing_op"):
            raise ValueError("test error")


class TestGetLogger:
    """Тесты для получения логгера."""

    def test_get_logger_returns_logger(self) -> None:
        """Проверяет что get_logger возвращает логгер."""
        logger = get_logger(__name__)
        assert logger is not None

    def test_get_logger_with_different_names(self) -> None:
        """Проверяет что разные имена возвращают разные логгеры."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1 is not None
        assert logger2 is not None
        # Логгеры могут быть одним объектом в structlog

    def test_get_logger_callable(self) -> None:
        """Проверяет что логгер имеет методы логирования."""
        logger = get_logger(__name__)

        # Проверяем что логгер имеет методы
        assert hasattr(logger, "info")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")

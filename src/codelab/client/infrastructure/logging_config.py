"""Конфигурация structured logging для ACP-клиента.

Модуль предоставляет:
- Инициализацию structlog с форматированием
- Логирование операций с контекстом
- Отслеживание времени выполнения
- Все логи записываются в файлы, вывод в stdout отключен

Пример использования:
    from codelab.client.infrastructure.logging_config import setup_logging
    setup_logging(level="INFO")
    logger = structlog.get_logger(__name__)
    logger.info("operation_started", operation_id="op_123")
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import structlog


class Logger(Protocol):
    """Интерфейс структурированного логгера."""

    def info(self, event: str, **kw: Any) -> None:
        """Логирует info сообщение."""
        ...

    def debug(self, event: str, **kw: Any) -> None:
        """Логирует debug сообщение."""
        ...

    def warning(self, event: str, **kw: Any) -> None:
        """Логирует warning сообщение."""
        ...

    def error(self, event: str, **kw: Any) -> None:
        """Логирует error сообщение."""
        ...


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    log_file: str | None = None,
) -> None:
    """Инициализирует структурированное логирование для клиента.

    Настраивает:
    - Structlog для JSON-подобного логирования
    - Форматирование времени в ISO 8601
    - Вывод только в стандартный logging Python (без stdout)
    - Стандартное логирование Python как fallback
    - Опциональное логирование в файл для отладки

    Args:
        level: Уровень логирования (по умолчанию INFO)
        log_file: Путь к файлу логов (по умолчанию ./acp_client.log)

    Пример:
        setup_logging(level="DEBUG", log_file="/tmp/acp_client.log")
        logger = structlog.get_logger(__name__)
        logger.debug("test_message", key="value")
    """
    # Создаем список обработчиков для логирования
    handlers_list: list[logging.Handler] = []

    # Добавляем файловый логер если указан путь
    if log_file is not None:
        # Создаем директорию для логов если её нет
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Файловый логер сротацией (максимум 5 файлов по 10MB каждый)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,  # Хранить 5 файлов (текущий + 4 архива)
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers_list.append(file_handler)

    # Стандартное логирование Python как fallback
    # Если нет файлового логера - логи сбрасываются в никуда
    logging.basicConfig(
        format="%(message)s",
        handlers=handlers_list,
        level=getattr(logging, level),
    )

    # Structlog конфигурация с использованием stdlib logger factory
    # для интеграции с стандартным logging
    structlog.configure(
        processors=[
            # Добавляем текущее время
            structlog.processors.TimeStamper(fmt="iso"),
            # Добавляем информацию об логгере
            structlog.processors.add_log_level,
            # Выделение exception traceback-а
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Сортировка ключей для читаемости
            structlog.processors.KeyValueRenderer(
                key_order=["timestamp", "level", "event"],
            ),
        ],
        context_class=dict,
        # Используем StandardLibLoggerFactory для записи логов через стандартный logging
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class OperationTimer:
    """Контекстный менеджер для отслеживания времени операций.

    Логирует время начала, окончания и продолжительность операции.

    Пример использования:
        logger = structlog.get_logger(__name__)
        with OperationTimer(logger, "fetch_data", datasource="api"):
            # выполнение операции
            data = fetch_from_api()
    """

    def __init__(
        self,
        logger: Any,
        operation_name: str,
        **context: Any,
    ) -> None:
        """Инициализирует таймер операции.

        Args:
            logger: Structlog логгер
            operation_name: Имя операции для логирования
            **context: Дополнительный контекст для логирования

        Пример:
            with OperationTimer(logger, "api_call", endpoint="/users"):
                ...
        """
        self.logger = logger
        self.operation_name = operation_name
        self.context: dict[str, Any] = context
        self.start_time: float | None = None

    def __enter__(self) -> OperationTimer:
        """Логирует начало операции."""
        import time

        self.start_time = time.time()
        self.logger.info(
            f"{self.operation_name}_started",
            **self.context,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Логирует окончание операции и время выполнения."""
        import time

        if self.start_time is None:
            return

        duration = time.time() - self.start_time

        if exc_type is not None:
            # Ошибка при выполнении
            self.logger.error(
                f"{self.operation_name}_failed",
                duration_ms=round(duration * 1000, 2),
                error_type=exc_type.__name__,
                **self.context,
            )
        else:
            # Успешное завершение
            self.logger.info(
                f"{self.operation_name}_completed",
                duration_ms=round(duration * 1000, 2),
                **self.context,
            )


def get_logger(name: str) -> Logger:
    """Возвращает настроенный структурированный логгер.

    Args:
        name: Имя логгера (обычно __name__)

    Returns:
        Готовый к использованию structlog логгер

    Пример:
        logger = get_logger(__name__)
        logger.info("operation_started")
    """
    return cast(Logger, structlog.get_logger(name))

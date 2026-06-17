"""Circuit breaker для LLM провайдеров.

Отслеживает ошибки провайдеров и открывает circuit при превышении порога.
Extension point для MVP — в future можно добавить временное открытие circuit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

import structlog

from codelab.server.llm.errors import ProviderError

logger = structlog.get_logger()


class CircuitState(StrEnum):
    """Состояние circuit breaker."""

    CLOSED = "closed"  # Нормальная работа, запросы проходят
    OPEN = "open"  # Circuit открыт, запросы блокируются
    HALF_OPEN = "half_open"  # Проверка восстановления, один запрос разрешён


@dataclass
class CircuitInfo:
    """Информация о circuit для провайдера."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0


class CircuitBreaker:
    """Circuit breaker для LLM провайдеров.

    Отслеживает ошибки и открывает circuit при превышении failure_threshold.
    В состоянии OPEN запросы блокируются.
    В состоянии HALF_OPEN разрешается один запрос для проверки.

    Extension point: в MVP circuit не закрывается автоматически,
    только через record_success().
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ) -> None:
        """Инициализация.

        Args:
            failure_threshold: Количество ошибок для открытия circuit
            reset_timeout: Время (секунды) до попытки восстановления
        """
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._circuits: dict[str, CircuitInfo] = {}

    def is_circuit_open(self, provider_id: str) -> bool:
        """Проверить, открыт ли circuit для провайдера.

        Args:
            provider_id: ID провайдера

        Returns:
            True если circuit открыт и запросы блокируются
        """
        info = self._circuits.get(provider_id)
        if not info:
            return False

        if info.state == CircuitState.OPEN:
            # Проверить timeout для восстановления
            if time.time() - info.opened_at > self._reset_timeout:
                info.state = CircuitState.HALF_OPEN
                logger.info(
                    "circuit transitioning to half-open",
                    provider_id=provider_id,
                )
                return False
            return True

        return False

    def record_success(self, provider_id: str) -> None:
        """Записать успешный запрос.

        Закрывает circuit если был в HALF_OPEN или OPEN.

        Args:
            provider_id: ID провайдера
        """
        info = self._get_or_create(provider_id)
        info.failure_count = 0
        info.last_success_time = time.time()

        if info.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            info.state = CircuitState.CLOSED
            logger.info("circuit closed after success", provider_id=provider_id)

    def record_failure(self, provider_id: str, error: ProviderError) -> None:
        """Записать.failed запрос.

        Открывает circuit при превышении failure_threshold.

        Args:
            provider_id: ID провайдера
            error: Ошибка
        """
        info = self._get_or_create(provider_id)
        info.failure_count += 1
        info.last_failure_time = time.time()

        if info.failure_count >= self._failure_threshold and info.state != CircuitState.OPEN:
            info.state = CircuitState.OPEN
            info.opened_at = time.time()
            logger.warning(
                "circuit opened",
                provider_id=provider_id,
                failure_count=info.failure_count,
            )

    def get_state(self, provider_id: str) -> CircuitState:
        """Получить текущее состояние circuit.

        Args:
            provider_id: ID провайдера

        Returns:
            Текущее состояние
        """
        info = self._circuits.get(provider_id)
        return info.state if info else CircuitState.CLOSED

    def reset(self, provider_id: str) -> None:
        """Сбросить circuit для провайдера.

        Args:
            provider_id: ID провайдера
        """
        if provider_id in self._circuits:
            del self._circuits[provider_id]
            logger.info("circuit reset", provider_id=provider_id)

    def _get_or_create(self, provider_id: str) -> CircuitInfo:
        """Получить или создать CircuitInfo."""
        if provider_id not in self._circuits:
            self._circuits[provider_id] = CircuitInfo()
        return self._circuits[provider_id]

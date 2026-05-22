"""Конфигурация model discovery."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiscoveryConfig:
    """Конфигурация обнаружения моделей.

    Атрибуты:
        enabled: Включён ли dynamic discovery
        refresh_interval: Интервал обновления (секунды)
        default_models: Модели по умолчанию если discovery недоступен
    """

    enabled: bool = False
    refresh_interval: float = 300.0  # 5 минут
    default_models: list[str] = field(default_factory=list)

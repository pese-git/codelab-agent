"""Static model discovery.

Возвращает предопределённый список моделей.
Используется для MVP и провайдеров без динамического discovery.
"""

from __future__ import annotations

from codelab.server.llm.discovery.base import ModelDiscovery
from codelab.server.llm.models import ModelInfo


class StaticDiscovery(ModelDiscovery):
    """Статическое обнаружение моделей.

    Возвращает заранее определённый список моделей.
    """

    def __init__(self, models: list[ModelInfo] | None = None) -> None:
        """Инициализация.

        Args:
            models: Список моделей (по умолчанию пустой)
        """
        self._models = models or []

    async def discover_models(self) -> list[ModelInfo]:
        """Вернуть статический список моделей.

        Returns:
            Список моделей
        """
        return self._models

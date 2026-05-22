"""Базовый класс для model discovery."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codelab.server.llm.models import ModelInfo


class ModelDiscovery(ABC):
    """Абстрактный класс для обнаружения доступных моделей.

    Реализации:
    - StaticDiscovery: статический список моделей (MVP)
    - OllamaDiscovery: динамическое обнаружение через Ollama API (future)
    - LMStudioDiscovery: динамическое обнаружение через LMStudio API (future)
    """

    @abstractmethod
    async def discover_models(self) -> list[ModelInfo]:
        """Обнаружить доступные модели.

        Returns:
            Список доступных моделей
        """
        ...

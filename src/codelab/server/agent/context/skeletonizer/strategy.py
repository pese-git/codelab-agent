"""SkeletonizerStrategy — ABC для стратегий скелетирования.

Strategy pattern: каждая стратегия обрабатывает определённый набор языков.
CompositeSkeletonizer выбирает стратегию по расширению файла.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SkeletonizerStrategy(ABC):
    """Абстрактная стратегия скелетирования кода."""

    @abstractmethod
    def can_handle(self, path: str) -> bool:
        """Поддерживается ли язык файла данной стратегией."""

    @abstractmethod
    def skeletonize(self, code: str, path: str) -> str:
        """Сжать код до сигнатур. Детерминированно.

        Args:
            code: Исходный код.
            path: Путь к файлу (для определения языка).

        Returns:
            Скелетированный код.
        """

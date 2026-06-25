"""TokenBudgetManager — управление бюджетом токенов.

Распределяет доступный бюджет токенов между компонентами контекста:
- system: системный промпт
- history: история диалога
- tool_output: результаты инструментов
- response_buffer: резерв для ответа модели

Также обеспечивает усечение контента с сохранением начала и конца.

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codelab.server.agent.context.interfaces import TokenBudgetManager
from codelab.server.agent.context.models import BudgetAllocation, ContextConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DefaultTokenBudgetManager(TokenBudgetManager):
    """Менеджер бюджета токенов с распределением по долям."""

    def __init__(self, config: ContextConfig | None = None) -> None:
        self._config = config or ContextConfig()

    def allocate(self, total_tokens: int) -> BudgetAllocation:
        """Распределить бюджет токенов по категориям.

        Args:
            total_tokens: Общий доступный бюджет токенов

        Returns:
            BudgetAllocation с распределением по категориям
        """
        system_tokens = int(total_tokens * self._config.system_share)
        history_tokens = int(total_tokens * self._config.history_share)
        tool_output_tokens = int(total_tokens * self._config.tool_output_share)
        response_buffer_tokens = int(total_tokens * self._config.response_buffer_share)

        allocated = system_tokens + history_tokens + tool_output_tokens + response_buffer_tokens
        if allocated < total_tokens:
            history_tokens += total_tokens - allocated

        return BudgetAllocation(
            system_tokens=system_tokens,
            history_tokens=history_tokens,
            tool_output_tokens=tool_output_tokens,
            response_buffer_tokens=response_buffer_tokens,
        )

    def bound_content(self, content: str, max_tokens: int) -> str:
        """Усечь содержимое до лимита токенов, сохраняя начало и конец.

        Использует приближённую оценку: ~4 символа на токен.

        Args:
            content: Содержимое для усечения
            max_tokens: Максимальное количество токенов

        Returns:
            Усечённое содержимое
        """
        max_chars = max_tokens * 4

        if len(content) <= max_chars:
            return content

        if max_chars <= 20:
            return content[:max_chars]

        head_size = int(max_chars * 0.7)
        tail_size = max_chars - head_size - 30

        head = content[:head_size]
        tail = content[-tail_size:] if tail_size > 0 else ""

        return f"{head}\n\n... [truncated {len(content) - max_chars} chars] ...\n\n{tail}"

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Приближённая оценка количества токенов.

        Args:
            text: Текст для оценки

        Returns:
            Приблизительное количество токенов
        """
        return len(text) // 4

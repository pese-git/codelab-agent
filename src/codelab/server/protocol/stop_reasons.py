"""Stop reasons для prompt turn (ACP 05-Prompt Turn.md).

Определяет причины остановки prompt turn согласно спецификации
Agent Client Protocol.

See Also:
    doc/Agent Client Protocol/protocol/05-Prompt Turn.md
"""

from __future__ import annotations

from enum import StrEnum


class StopReason(StrEnum):
    """Причины остановки prompt turn.

    Согласно ACP спецификации (05-Prompt Turn.md:265-283),
    Agent MUST указать stop reason при завершении turn.

    Attributes:
        END_TURN: LLM завершил генерацию без запроса дополнительных tools.
        MAX_TOKENS: Достигнут максимальный лимит токенов.
        MAX_TURN_REQUESTS: Превышено максимальное количество запросов к LLM
            в рамках одного turn.
        REFUSAL: Agent отказался продолжать выполнение.
        CANCELLED: Client отменил turn через session/cancel.
    """

    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"
    MAX_TURN_REQUESTS = "max_turn_requests"
    REFUSAL = "refusal"
    CANCELLED = "cancelled"

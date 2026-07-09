"""EpochManager — управление жизненным циклом контекстных эпох.

Слой B — Жизненный цикл (Phase 4).

EpochManager:
- Создаёт новую эпоху при старте сессии или разрыве
- Фиксирует baseline и baseline_fingerprint один раз за эпоху
- Аккумулирует mid_conversation_messages между ходами
- Ограничивает разрывы эпох (не более одного за ход)
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.context.models import ContextEpoch

if TYPE_CHECKING:
    from codelab.server.llm.models import LLMMessage

logger = structlog.get_logger(__name__)


class EpochManager:
    """Управление жизненным циклом контекстных эпох.

    Одна эпоха = один стабильный baseline. При изменении baseline-источников
    эпоха ломается (epoch_broken=True) и создаётся новая.

    Attributes:
        _current_epoch: Текущая активная эпоха
        _epoch_breaks_this_turn: Количество разрывов в текущем ходе (ограничение: <=1)
    """

    def __init__(self) -> None:
        self._current_epoch: ContextEpoch | None = None
        self._epoch_breaks_this_turn: int = 0

    @property
    def current_epoch(self) -> ContextEpoch | None:
        """Текущая активная эпоха."""
        return self._current_epoch

    @property
    def is_active(self) -> bool:
        """Есть ли активная эпоха."""
        return self._current_epoch is not None

    def start_epoch(
        self,
        baseline: list[LLMMessage],
        baseline_fingerprint: str,
    ) -> ContextEpoch:
        """Создать новую эпоху с фиксированным baseline.

        Args:
            baseline: Иммутабельный baseline эпохи
            baseline_fingerprint: Codec-отпечаток baseline

        Returns:
            Новая ContextEpoch
        """
        epoch_id = str(uuid.uuid4())[:8]

        self._current_epoch = ContextEpoch(
            epoch_id=epoch_id,
            baseline=list(baseline),
            baseline_fingerprint=baseline_fingerprint,
            mid_conversation_messages=[],
        )
        self._epoch_breaks_this_turn = 0

        logger.info(
            "epoch.started",
            epoch_id=epoch_id,
            baseline_messages=len(baseline),
            baseline_fingerprint=baseline_fingerprint,
        )

        return self._current_epoch

    def break_epoch(
        self,
        new_baseline: list[LLMMessage],
        new_baseline_fingerprint: str,
    ) -> ContextEpoch | None:
        """Сломать текущую эпоху и создать новую.

        Ограничение: не более одного разрыва за ход.

        Args:
            new_baseline: Новый baseline для эпохи
            new_baseline_fingerprint: Codec-отпечаток нового baseline

        Returns:
            Новая ContextEpoch или None если разрыв уже был в этом ходу
        """
        if self._current_epoch is None:
            logger.warning("epoch.break.no_active_epoch")
            return None

        if self._epoch_breaks_this_turn >= 1:
            logger.warning(
                "epoch.break_limit_reached",
                current_epoch_id=self._current_epoch.epoch_id,
                breaks_this_turn=self._epoch_breaks_this_turn,
            )
            return None

        old_epoch_id = self._current_epoch.epoch_id
        self._epoch_breaks_this_turn += 1

        epoch_id = str(uuid.uuid4())[:8]
        self._current_epoch = ContextEpoch(
            epoch_id=epoch_id,
            baseline=list(new_baseline),
            baseline_fingerprint=new_baseline_fingerprint,
            mid_conversation_messages=[],
        )

        logger.info(
            "epoch.broken",
            old_epoch_id=old_epoch_id,
            new_epoch_id=epoch_id,
            baseline_messages=len(new_baseline),
            baseline_fingerprint=new_baseline_fingerprint,
        )

        return self._current_epoch

    def add_mid_conversation_message(self, message: LLMMessage) -> None:
        """Добавить сообщение в mid_conversation_messages текущей эпохи.

        Args:
            message: Сообщение для добавления
        """
        if self._current_epoch is None:
            logger.warning("epoch.add_message.no_active_epoch")
            return

        self._current_epoch.mid_conversation_messages.append(message)

    def reset_turn_counter(self) -> None:
        """Сбросить счётчик разрывов за ход.

        Вызывается в начале каждого нового хода.
        """
        self._epoch_breaks_this_turn = 0

    def clear(self) -> None:
        """Очистить текущую эпоху."""
        if self._current_epoch is not None:
            logger.info(
                "epoch.cleared",
                epoch_id=self._current_epoch.epoch_id,
            )
        self._current_epoch = None
        self._epoch_breaks_this_turn = 0

    @staticmethod
    def compute_baseline_fingerprint(baseline: list[LLMMessage]) -> str:
        """Вычислить детерминированный fingerprint для baseline.

        Канонизация: стабильный порядок сообщений, нормализованные пробелы.

        Args:
            baseline: Список сообщений baseline

        Returns:
            Детерминированный hex-отпечаток
        """
        content_parts: list[str] = []
        for msg in baseline:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            normalized = " ".join(content.split())
            content_parts.append(f"{msg.role}:{normalized}")

        combined = "|".join(content_parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

"""Процессный реестр отмены turn'ов.

Отмена не может жить в `SessionState`: каждый JSON-RPC запрос получает от
`JsonFileStorage` **свою** копию сессии, десериализованную с диска, поэтому
in-memory сигнал, записанный обработчиком `session/cancel`, никогда не виден
идущему turn'у. Это подтверждено пробами id объектов на e2e-прогоне (P0-39):
turn держал копию с `epoch=0`, отмена инкрементировала другую копию.

Реестр живёт в процессе и адресуется `session_id`, поэтому от числа копий
состояния не зависит. Тот же приём уже используется для отмены исходящих
клиентских RPC (`ClientRPCService.cancel_all_pending_requests`) — единственной
части отмены, которая работала до этой правки.

Схлопывание копий сессии — отдельная задача (транзакция `session/load`,
ADR-006); когда она будет сделана, реестр останется корректным, но перестанет
быть единственным работающим каналом.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class TurnCancellationRegistry:
    """Монотонные поколения отмены по `session_id`.

    Цикл запоминает поколение на входе в turn и сверяет его на каждом шаге:
    расхождение означает «этот turn отменён». Монотонный счётчик, а не флаг,
    чтобы отмена одного turn'а не гасила следующий.
    """

    def __init__(self) -> None:
        self._generations: dict[str, int] = {}

    def generation(self, session_id: str) -> int:
        """Текущее поколение отмены сессии."""
        return self._generations.get(session_id, 0)

    def cancel(self, session_id: str) -> int:
        """Отменить всё, что начиналось до этого момента. Возвращает новое поколение."""
        generation = self._generations.get(session_id, 0) + 1
        self._generations[session_id] = generation
        logger.debug("turn_cancellation_registered", session_id=session_id, generation=generation)
        return generation

    def is_cancelled(self, session_id: str, started_generation: int) -> bool:
        """Отменён ли turn, начавшийся с поколением `started_generation`."""
        return self.generation(session_id) != started_generation

    def forget(self, session_id: str) -> None:
        """Забыть сессию (её состояние больше не нужно — сессия удалена)."""
        self._generations.pop(session_id, None)

"""Реестр исходящих запросов сервера к клиенту (корреляция ответов).

Хранит runtime-факты, которые не могут быть сериализованы и не должны лежать в
персистируемом `SessionDocument`: какие запросы сервер отправил и ждёт по ним
ответа. Корреляция ответа с запросом принадлежит уровню протокола и ключуется
идентификатором запроса — это обычное устройство JSON-RPC-пира, а не наша
особенность (ADR-008, раздел 7).

Почему не в документе: рестарт убивает все незакрытые запросы по определению —
продолжений, которые их ждали, больше не существует. `session/load` это и делает,
очищая turn. То есть персистированная корреляция переживала рестарт ровно затем,
чтобы быть выброшенной.

Реестр процессный и живёт на соединение. При перезапуске сервера — пустой.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from ..messages import JsonRpcId

logger = structlog.get_logger()


class PendingRequestRegistry:
    """Хранилище asyncio.Future для ожидающих permission requests.

    Жизненный цикл: создаётся в ACPProtocol, не персистируется.
    При перезапуске сервера — пересоздаётся пустым.
    """

    def __init__(self) -> None:
        self._futures: dict[JsonRpcId, asyncio.Future[Any]] = {}
        # Корреляция «исходящий запрос → сессия». Отдельно от futures: ими владеет
        # ожидающий вызывающий, а этой картой — маршрутизация ответов, и у неё
        # ответ приходит отдельным сообщением, а не возвратом из await.
        self._outgoing: dict[JsonRpcId, str] = {}

    def create(self, request_id: JsonRpcId) -> asyncio.Future[Any]:
        """Создать и зарегистрировать Future для request_id."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._futures[request_id] = future
        logger.debug("pending_request_created", request_id=request_id)
        return future

    def resolve(self, request_id: JsonRpcId, result: Any) -> bool:
        """Завершить Future с результатом. Возвращает True если Future найден."""
        future = self._futures.pop(request_id, None)
        if future is None:
            return False
        if not future.done():
            future.set_result(result)
            logger.debug("pending_request_resolved", request_id=request_id)
        return True

    def cancel(self, request_id: JsonRpcId) -> bool:
        """Отменить Future. Возвращает True если Future найден."""
        future = self._futures.pop(request_id, None)
        if future is None:
            return False
        if not future.done():
            future.cancel()
            logger.debug("pending_request_cancelled", request_id=request_id)
        return True

    def has(self, request_id: JsonRpcId) -> bool:
        """Ждём ли мы ответа на этот запрос — по futures либо по корреляции.

        Отвечает на вопрос «этот запрос ещё наш?»: им пользуется `session/load`,
        чтобы отличить живое ожидание от осиротевшего после рестарта. Пока
        писателя не было, ответ всегда был `False`, и сиротой считалось любое
        незакрытое разрешение.
        """
        return request_id in self._futures or request_id in self._outgoing

    def record_outgoing(self, request_id: JsonRpcId, session_id: str) -> None:
        """Запомнить отправленный клиенту запрос и сессию, которой он принадлежит.

        Пишется на границе транспорта — там, где запрос действительно уходит, —
        поэтому ни один путь его не минует: и outcome, и шина нотификаций ведут
        в один и тот же `send`.
        """
        self._outgoing[request_id] = session_id
        logger.debug(
            "outgoing_request_recorded",
            request_id=request_id,
            session_id=session_id,
            outstanding=len(self._outgoing),
        )

    def session_for(self, request_id: JsonRpcId) -> str | None:
        """Сессия, которой принадлежит исходящий запрос; `None` — запрос не наш.

        Заменяет полный скан хранилища: тот сравнивал единственный
        `permission_request_id` из документа, поэтому ответ на любой запрос,
        кроме последнего, сессию не находил (P1-61).
        """
        return self._outgoing.get(request_id)

    def forget(self, request_id: JsonRpcId) -> bool:
        """Забыть закрытый запрос. Возвращает True, если он был известен."""
        return self._outgoing.pop(request_id, None) is not None

    def forget_session(self, session_id: str) -> int:
        """Забыть все запросы сессии; возвращает их количество.

        Нужна отмене и переключению сессии: спецификация требует закрыть **все**
        незакрытые запросы, а не последний.
        """
        stale = [rid for rid, sid in self._outgoing.items() if sid == session_id]
        for request_id in stale:
            del self._outgoing[request_id]
        return len(stale)

    def cancel_all(self) -> int:
        """Отменить все ожидающие futures. Возвращает количество отменённых."""
        count = 0
        for request_id in list(self._futures.keys()):
            if self.cancel(request_id):
                count += 1
        return count

    def __len__(self) -> int:
        return len(self._futures)

    @property
    def outstanding_outgoing(self) -> int:
        """Сколько исходящих запросов ждут ответа — для диагностики."""
        return len(self._outgoing)

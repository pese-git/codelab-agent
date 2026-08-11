"""Завершение turn'а — один владелец вместо семи снятий (ADR-008, шаг 5).

Turn кончается в семи местах: штатное завершение, закрывающая стадия пайплайна,
отмена, отказ в разрешении, переключение/загрузка сессии, ответ клиента и снятие
устаревшего turn'а при новом промпте. Каждое из них снимало `active_turn` само,
поэтому «turn закончился» не было событием, у которого есть владелец, — а без
такого владельца некуда повесить работу конца turn'а. Первый её потребитель —
освобождение остатка терминалов (вторая половина P2-58): по спецификации
освобождает **агент** (`10-Terminal.md:109-111`), фактический приобретатель
ресурса от лица модели — turn, а не сессия и не процесс.

**Разведка по коду поправила премису ADR (2026-08-11).** ADR называл четыре
выхода, «все синхронные, клиентский RPC из них не сделать». По коду выходов
семь, а три штатных уже сведены в один асинхронный шов
(`BackgroundExecutor.complete_active_turn`), из которого клиентский RPC как раз
возможен. Существенным осталось «владельца нет», а не «выходов четыре».

**Объём шага — шов, а не политика.** Здесь только снятие turn'а и наблюдаемость
причины; освобождение терминалов — шаг 5.3, и оно требует `await`, поэтому
появится у тех вызывающих, чей контекст асинхронен. Смешение сделало бы
расхождение на живом прогоне необъяснимым однозначно — тот же порядок, что у
шага 1 ADR-009.

Форма — модуль, а не объект: сегодня у завершения нет ни одной зависимости, и
класс с семью точками внедрения был бы абстракцией ради названия. Объект
появится в шаге 5.3, когда завершению понадобятся реестр alias'ов и клиентский
RPC.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import structlog

from codelab.server.messages import ACPMessage

if TYPE_CHECKING:
    from codelab.server.domain.session import Session as DomainSession

logger = structlog.get_logger()


class TurnEndCause(Enum):
    """Почему turn закончился.

    Причина существует не для ветвления, а для наблюдаемости: до этого шага в
    логах не было видно, **кто** снял turn, и разбор прогонов приходилось вести
    по косвенным следам (так искались P2-62 и P2-46).
    """

    COMPLETED = "completed"
    PIPELINE_CLOSED = "pipeline_closed"
    PIPELINE_ERROR = "pipeline_error"
    CANCELLED = "cancelled"
    PERMISSION_DENIED = "permission_denied"
    SESSION_SWITCHED = "session_switched"
    CLIENT_RPC_FINISHED = "client_rpc_finished"
    STALE = "stale"


def finish_turn(
    session: DomainSession,
    *,
    cause: TurnEndCause,
    stop_reason: str | None = None,
) -> ACPMessage | None:
    """Снять активный turn и, если нужно, построить ответ на `session/prompt`.

    Единственная точка снятия: вызывающие обязаны проходить через неё, иначе
    работа конца turn'а (шаг 5.3) достанется не всем путям — тот же класс, что
    рукописная граница каталога в двух обработчиках (ADR-009, шаг 2б).

    Порядок сохранён от прежних вызывающих дословно: идентификатор запроса
    читается **до** снятия — после него `active_turn` уже нет, и отвечать было бы
    некому.

    Args:
        session: Доменный агрегат сессии.
        cause: Почему turn закончился (наблюдаемость).
        stop_reason: ACP-значение для ответа. `None` — вызывающий отвечает сам
            или ответа не требуется (переключение сессии, снятие устаревшего).

    Returns:
        Ответ на исходный `session/prompt` либо `None`.
    """
    active_turn = session.active_turn
    if active_turn is None:
        return None

    prompt_request_id = active_turn.prompt_request_id
    session.clear_active_turn()

    logger.info(
        "turn_finished",
        session_id=str(session.id),
        cause=cause.value,
        stop_reason=stop_reason,
        answered=stop_reason is not None and prompt_request_id is not None,
    )

    if stop_reason is None or prompt_request_id is None:
        return None
    return ACPMessage.response(prompt_request_id, {"stopReason": stop_reason})

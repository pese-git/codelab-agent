"""Слияние состояния сессии при конфликте ревизий (ADR-007).

Зачем. `session/prompt` и фоновое исполнение держат свою копию сессии весь turn —
по живым логам от 7 до 52 секунд. Если за это время придёт `session/cancel`, он
сохранит свою копию, и финальная запись turn'а окажется устаревшей. С
compare-and-set она отклоняется, и накопленные результаты инструментов теряются:
воспроизведено на коде до этой правки (история на диске пуста, хотя turn отработал).

Обернуть turn в транзакцию нельзя: блокировка удерживалась бы весь turn, и отмена
не обработалась бы, пока turn не кончится — то есть отмена перестала бы работать.
Поэтому turn остаётся владельцем своей копии, а конфликт разрешается слиянием.

Это защита, а не цель. Цель — пошаговые записи turn'а (ADR-007, «turn —
последовательность транзакций»): тогда несохранённое окно измеряется миллисекундами
и конфликт почти не возникает. Слияние этому не мешает и снимается вместе с
переходом.

Правила слияния явные, потому что «слить как-нибудь» — это тихая потеря решений,
ровно то, от чего уходим:

* **Отмена главнее.** Статус вызова, поставленный отменой (`cancelled`), не
  перезаписывается результатом turn'а: клиент уже увидел `cancelled`, и вернуть
  вызову `completed` значило бы солгать ему задним числом.
* **`active_turn` берётся из свежей копии.** Если отмена его очистила, turn не
  вправе воскресить: воскресший turn — отдельный дефект, который мы уже чинили
  (P0-39).
* **Append-only журналы сливаются по общему префиксу.** `history` и
  `events_history` только дополняются, обе копии выросли из одного предка, поэтому
  общий префикс — это предок, а хвосты обеих сторон дописываются по порядку:
  сначала чужой, затем свой.
* **Счётчики — максимум**, иначе следующий вызов получил бы занятый идентификатор.
* **Остальные поля — из свежей копии**: их меняют короткие запросы осознанно
  (`cwd`, `config_values`, `title`, `permission_policy`), и turn их не трогает.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import ValidationError

from ..exceptions import SessionRevisionConflictError
from ..models import HistoryMessage
from ..storage.base import SessionStorage
from .state import SessionState

logger = structlog.get_logger()

# Статусы, поставленные отменой: их результат turn'а не перезаписывает.
_CANCEL_OWNED_STATUSES = frozenset({"cancelled"})


def _canonical_entry(entry: Any) -> Any:
    """Одна форма записи журнала для сравнения копий.

    `SessionState.history` объявлена союзом `HistoryMessage | dict`: запись,
    добавленную в этом процессе, писатели кладут плоским dict, а та же запись,
    прочитанная с диска, валидируется в модель. Сравнение «как есть» давало
    неравенство на первой же записи текущего turn'а, префикс обрывался, и хвост
    дописывался повторно — в истории появлялись дубли, включая два ответа
    `role: tool` на один `tool_call_id` (tech-debt P1-45, воспроизведено на
    живом прогоне `sess_ffff9be366bd`).

    Приведение — защита, а не решение: корень (союз типов) снимается переводом
    истории на одну форму вместе с turn-путём в фазе D ADR-006.
    """
    if isinstance(entry, HistoryMessage):
        return entry
    if isinstance(entry, dict):
        try:
            return HistoryMessage.model_validate(entry)
        except ValidationError:
            # Не запись истории (или несовместимая форма) — сравниваем как есть.
            return entry
    return entry


def _common_prefix_length(base: list[Any], mine: list[Any]) -> int:
    """Длина общего префикса двух append-only журналов — это их общий предок."""
    limit = min(len(base), len(mine))
    for index in range(limit):
        if _canonical_entry(base[index]) != _canonical_entry(mine[index]):
            return index
    return limit


def _merge_append_only(base: list[Any], mine: list[Any]) -> list[Any]:
    """Слить журнал: общий предок, затем чужой хвост, затем свой.

    Порядок хвостов — «чужой раньше своего»: чужая запись уже на диске и уже
    отдана клиенту, поэтому она старше по факту.
    """
    prefix = _common_prefix_length(base, mine)
    return list(base) + list(mine[prefix:])


def merge_session_states(base: SessionState, mine: SessionState) -> SessionState:
    """Слить свою (устаревшую) копию поверх свежей.

    `base` — состояние с диска, `mine` — копия, которую держал писатель. Результат
    пишется в `base`: он несёт актуальную ревизию, поэтому запись пройдёт сверку.

    Пример использования:
        merged = merge_session_states(base=await storage.load_session(sid), mine=turn_copy)
    """
    base.history = _merge_append_only(base.history, mine.history)
    base.events_history = _merge_append_only(base.events_history, mine.events_history)

    for tool_call_id, mine_call in mine.tool_calls.items():
        base_call = base.tool_calls.get(tool_call_id)
        if base_call is not None and base_call.status in _CANCEL_OWNED_STATUSES:
            # Отмена главнее: статус не трогаем, но содержимое результата берём —
            # оно описывает, чем вызов успел закончиться.
            if mine_call.content and not base_call.content:
                base_call.content = mine_call.content
            continue
        base.tool_calls[tool_call_id] = mine_call

    base.tool_call_counter = max(base.tool_call_counter, mine.tool_call_counter)
    base.terminal_counter = max(base.terminal_counter, mine.terminal_counter)
    base.terminals = {**mine.terminals, **base.terminals}

    if mine.latest_plan and not base.latest_plan:
        base.latest_plan = mine.latest_plan

    return base


async def save_session_merging(storage: SessionStorage, session: SessionState) -> None:
    """Сохранить копию, слив её со свежей при конфликте ревизий.

    В отсутствие конфликта — обычная запись без лишнего чтения. При конфликте:
    загрузить свежую, слить, записать. Конфликт логируется — он остаётся видимым,
    просто перестаёт означать потерю.

    Повтор один: если и слитая запись конфликтует, значит запись идёт под гонкой,
    которую слияние не разрешает — такое лучше увидеть как ошибку.
    """
    try:
        await storage.save_session(session)
        return
    except SessionRevisionConflictError as conflict:
        logger.info(
            "session_save_merging_after_conflict",
            session_id=session.session_id,
            expected_revision=conflict.expected,
            actual_revision=conflict.actual,
        )

    base = await storage.load_session(session.session_id)
    if base is None:
        # Сессию удалили, пока turn работал — воскрешать её слиянием неправильно.
        logger.warning(
            "session_save_skipped_session_gone",
            session_id=session.session_id,
        )
        return

    merged = merge_session_states(base=base, mine=session)
    await storage.save_session(merged)
    logger.info(
        "session_save_merged",
        session_id=session.session_id,
        revision=merged.revision,
        history_entries=len(merged.history),
    )

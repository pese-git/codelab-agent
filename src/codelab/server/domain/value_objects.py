"""Domain value objects и enums.

Содержит неизменяемые объекты и перечисления для domain layer сервера.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NewType

SessionId = NewType("SessionId", str)


@dataclass(frozen=True)
class FileLocation:
    """Domain model для file location."""

    path: str
    line: int | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("path must not be empty")


class ToolCallStatus(enum.StrEnum):
    """Domain enum для статуса tool call.

    Значения совпадают с ACP `ToolCallStatus` (wire), потому что маппер отдаёт
    `.value` напрямую. Прежний доменный `RUNNING = "running"` был артефактом: в
    ACP это `in_progress`, и любое его попадание в wire дало бы невалидный
    статус. `CANCELLED` и `IN_PROGRESS` обязательны — без них
    `ToolCallMapper.to_domain` понижал их до `PENDING` (потеря round-trip).
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


# Матрица допустимых переходов статуса tool call — единственный источник (фаза D
# ADR-006). Прежде она существовала в трёх копиях (`ToolCallHandler`,
# `prompt.tool_call_state`, неявно в `ToolCall.is_terminal`), причём одна из них
# не логировала отказ — и молчаливый пропуск однажды рассинхронизировал состояние
# с wire-историей. `ToolCallStatus` — `StrEnum`, поэтому таблица одинаково
# отвечает на доменный член и на wire-строку.
ALLOWED_TOOL_CALL_TRANSITIONS: Mapping[ToolCallStatus, frozenset[ToolCallStatus]] = {
    ToolCallStatus.PENDING: frozenset(
        {ToolCallStatus.IN_PROGRESS, ToolCallStatus.CANCELLED, ToolCallStatus.FAILED}
    ),
    ToolCallStatus.IN_PROGRESS: frozenset(
        {ToolCallStatus.COMPLETED, ToolCallStatus.CANCELLED, ToolCallStatus.FAILED}
    ),
    ToolCallStatus.COMPLETED: frozenset(),
    ToolCallStatus.CANCELLED: frozenset(),
    ToolCallStatus.FAILED: frozenset(),
}

TERMINAL_TOOL_CALL_STATUSES: frozenset[ToolCallStatus] = frozenset(
    status for status, next_states in ALLOWED_TOOL_CALL_TRANSITIONS.items() if not next_states
)


@dataclass(frozen=True)
class Running:
    """Turn исполняется: ничего внешнего не ожидается."""

    wire_name = "running"


@dataclass(frozen=True)
class AwaitingPermission:
    """Turn приостановлен до решения пользователя по конкретному вызову.

    Идентификаторы — часть значения фазы, а не соседние поля: пока они лежали
    рядом, состояние «жду разрешения, но не знаю какого» было выразимо и
    наблюдалось живьём (`phase = awaiting_permission` при обоих идентификаторах
    `null`, прогон 2026-08-06). Ответ на разрешение снимает идентификаторы, и
    снятие теперь **есть** переход в `Running` — забыть его нельзя.

    Обязателен именно `request_id`: от него зависит **корреляция** — ответ клиента
    ищет сессию по нему, и отмена пишет tombstone по нему же. Поэтому невыразимым
    становится ровно наблюдавшийся дефект («жду разрешения» вообще без
    идентификаторов), а не любая неполнота. `tool_call_id` может отсутствовать в
    документах, записанных когда поля выставлялись по частям: без него нельзя
    возобновить конкретный вызов, но отменить ожидание можно.

    `keep_tool_pending` различает две ветки одного состояния. Раньше их
    различали **именем фазы** (`waiting_tool_completion` против
    `waiting_permission`/`awaiting_permission`), из-за чего одно состояние
    писалось тремя строками из двух модулей.
    """

    request_id: str | int
    tool_call_id: str | None = None
    keep_tool_pending: bool = False

    @property
    def wire_name(self) -> str:
        """Имя фазы в документе сессии.

        Обратная совместимость: `waiting_tool_completion` читает
        `should_auto_complete_active_turn`, поэтому имя сохраняется.
        """
        return "waiting_tool_completion" if self.keep_tool_pending else "awaiting_permission"


@dataclass(frozen=True)
class AwaitingClientRpc:
    """Turn приостановлен до ответа клиента на исходящий запрос (`fs/*`).

    Своих идентификаторов не несёт: исходящий запрос целиком живёт в
    `TurnState.pending_external_request`, и вторая копия развела бы их.
    """

    wire_name = "waiting_client_rpc"


@dataclass(frozen=True)
class TurnCancelled:
    """Turn отменён: дальнейших переходов нет."""

    wire_name = "cancelled"


@dataclass(frozen=True)
class Completing:
    """Turn завершается: дальнейших переходов нет."""

    wire_name = "completing"


type TurnPhase = Running | AwaitingPermission | AwaitingClientRpc | TurnCancelled | Completing

# Матрица переходов фазы turn'а. Раньше жила в `turn_lifecycle_manager` строками и
# **не применялась ни разу**: единственный вход `set_turn_phase` не имел вызывающих в
# продакшене, а все пять записей фазы были прямыми присваиваниями. Правила сохранены
# как были, и добавлено `TurnCancelled` — его писали (`session.py`), но в матрице не
# перечисляли (ADR-008, шаг 2).
ALLOWED_TURN_PHASE_TRANSITIONS: Mapping[type, frozenset[type]] = {
    Running: frozenset({Running, AwaitingPermission, AwaitingClientRpc, TurnCancelled, Completing}),
    AwaitingPermission: frozenset({Running, TurnCancelled, Completing}),
    AwaitingClientRpc: frozenset({Running, TurnCancelled, Completing}),
    TurnCancelled: frozenset({TurnCancelled}),
    Completing: frozenset({Completing}),
}


def turn_phase_from_wire(
    name: str,
    *,
    permission_request_id: str | int | None,
    permission_tool_call_id: str | None,
) -> TurnPhase:
    """Восстановить фазу из документа сессии, терпимо к прежним значениям.

    Терпимость обязательна и не является техническим долгом: на диске лежат
    документы, записанные когда одно состояние имело три написания. `waiting_permission`
    — прежнее имя `awaiting_permission` (его писал `directives`), `awaiting_client_rpc`
    — значение, которое числилось в матрице, но не писалось никем.

    Ожидание разрешения без идентификаторов **вырождается в `Running`**: это ровно то
    несогласованное состояние, которое наблюдалось живьём, и восстанавливать его как
    ожидание значило бы считать turn приостановленным навсегда.
    """
    if name == "cancelled":
        return TurnCancelled()
    if name == "completing":
        return Completing()

    # Идентификаторы важнее имени фазы. На диске встречается `phase = running` при
    # заполненных идентификаторах: до типизации их писал `permission_manager`, а фазу —
    # отдельно `tool_processor`, поэтому запись «по частям» могла остаться незавершённой.
    # Ответ клиента ищет сессию именно по `permission_request_id`, так что потеря
    # идентификаторов сделала бы такое разрешение необрабатываемым — уже сохранённые
    # сессии перестали бы отвечать.
    if permission_request_id is not None:
        return AwaitingPermission(
            request_id=permission_request_id,
            tool_call_id=permission_tool_call_id,
            keep_tool_pending=name == "waiting_tool_completion",
        )

    if name in {"waiting_client_rpc", "awaiting_client_rpc"}:
        return AwaitingClientRpc()
    return Running()


class MessageRole(enum.StrEnum):
    """Domain enum для роли сообщения."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class PlanPriority(enum.StrEnum):
    """Domain enum для приоритета плана."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PlanStatus(enum.StrEnum):
    """Domain enum для статуса шага плана."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


# Префикс alias'а терминала, который сервер выдаёт модели вместо 36-символьного
# client-side `terminalId` (tech-debt #18: LLM теряла символы при ретрансляции).
# Единственный источник: значение попадает в историю и на диск, поэтому вторая
# копия развела бы alias'ы прошлых сессий с новыми.
TERMINAL_ALIAS_PREFIX = "term_"

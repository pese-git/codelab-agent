"""Доменные события журнала сессии (шаг 3a ADR-008).

Журнал — упорядоченная последовательность фактов диалога. ACP-нотификация и
LLM-история из него **выводятся**, поэтому событие описано в терминах домена и
ничего не знает ни о `sessionUpdate`, ни о camelCase: форму wire знает проекция
(`mapping/journal_mapper.py`). Этим отменяется запись ADR-006 о том, что
`events_history` — постоянная wire-граница.

Шаг 3a вводит только модель: на диск по-прежнему уезжает нынешняя форма, её
отдаёт та же проекция. Смена формата документа — шаг 3b.

Гранулярность — **сообщение**, не чанк потока. Это замер, а не допущение: на
живом документе `agent_message_chunk` пришёлся ровно по одному на текст
ассистента, `user_message_chunk` — по одному на блок промпта (разведка формы
события, 2026-08-06). ACP-чанк остаётся деталью проекции.

Блоки контента остаются непрозрачными `dict`: их форма принадлежит ACP Content
Types, домен их не интерпретирует и не пересобирает — иначе проекция перестала
бы быть байт-идентичной.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = [
    "AgentMessageRecorded",
    "JournalEntry",
    "PlanRecorded",
    "SessionEvent",
    "SessionInfoRecorded",
    "ToolCallStarted",
    "ToolCallStatusChanged",
    "UnknownUpdateRecorded",
    "UserMessageRecorded",
]


@dataclass(frozen=True)
class UserMessageRecorded:
    """Блок промпта пользователя.

    Пишется по одному событию на блок: реплей отдаёт блоки в исходном порядке,
    поэтому склейка недопустима.
    """

    content: dict[str, Any]


@dataclass(frozen=True)
class AgentMessageRecorded:
    """Блок ответа модели."""

    content: dict[str, Any]


@dataclass(frozen=True)
class ToolCallStarted:
    """Вызов инструмента заявлен.

    `status` — строка пространства ACP `ToolCallStatus`. Сужение до доменного
    `ToolCallStatus` отложено до шага 4, где статус становится проекцией: сегодня
    один из писателей (`prompt_orchestrator`, ретрансляция при resume) передаёт
    строку из чужой нотификации, и коэрция на горячем пути дала бы новую точку
    отказа там, где сейчас значение проходит дословно.
    """

    tool_call_id: str
    title: str
    kind: str
    status: str
    content: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class ToolCallStatusChanged:
    """Статус вызова изменился; результат приложен, если он появился."""

    tool_call_id: str
    status: str
    content: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class PlanRecorded:
    """Полный снимок плана. ACP передаёт план целиком, а не приращением."""

    entries: list[dict[str, Any]]


@dataclass(frozen=True)
class SessionInfoRecorded:
    """Метаданные сессии: заголовок и время активности.

    Единственное событие журнала **без** реплей-проекции: по ACP это
    патч-канал метаданных, а не conversation, и к моменту загрузки значение уже
    устарело — `session/load` в конце реплея эмитит свежее. Шаг 3a закрепляет
    это решение конструкцией: у события нет реплей-формы, вместо прежнего
    перечисления пяти видов из шести в наборе строк.
    """

    title: str | None
    updated_at: str | None


@dataclass(frozen=True)
class UnknownUpdateRecorded:
    """Запись журнала, которую модель не описывает — отдаётся дословно.

    Нужна терпимости к уже записанным сессиям: журнал писали и более ранние
    версии, и набор полей в их записях мог отличаться от нынешнего. Такая запись
    проходит проекцию без изменений, поэтому поток загрузки старой сессии
    остаётся байт-идентичным. Для того, что пишем мы, событие не возникает —
    это проверяется тестом.
    """

    update: dict[str, Any]


type SessionEvent = (
    UserMessageRecorded
    | AgentMessageRecorded
    | ToolCallStarted
    | ToolCallStatusChanged
    | PlanRecorded
    | SessionInfoRecorded
    | UnknownUpdateRecorded
)


@dataclass(frozen=True)
class JournalEntry:
    """Событие с меткой времени — единица журнала.

    Метка — поле журнала, а не факта диалога, поэтому она не участвует ни в одной
    проекции. `None` допустим: старая запись может её не иметь.
    """

    event: SessionEvent
    timestamp: datetime | None = None

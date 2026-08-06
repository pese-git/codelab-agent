"""Проекция журнала сессии в ACP и разбор уже записанного журнала (шаг 3a ADR-008).

Единственный владелец формы записи `events_history` и формы `session/update`,
построенной по журналу. До шага 3a форму знал писатель (`EventHistoryWriter`), а
реплей был pass-through — элемент журнала уходил клиенту дословно. Теперь запись
и чтение идут через одну проекцию, поэтому расхождение между тем, что клиент
видел в turn-е, и тем, что он получает на `session/load`, перестаёт быть
выразимым.

Формат документа шагом 3a не меняется: `to_wire` отдаёт ту же запись, что
писалась раньше. Смена формата на доменный — шаг 3b (`schema_version` 10→11).

Терпимость к записанному: `from_wire` возвращает `UnknownUpdateRecorded` для
всего, чего модель не описывает **точно** — включая знакомый `sessionUpdate` с
незнакомым набором полей. Дословный проход такой записи сохраняет поток загрузки
сессий, записанных прежними версиями.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from codelab.server.domain.journal import (
    AgentMessageRecorded,
    JournalEntry,
    PlanRecorded,
    SessionEvent,
    SessionInfoRecorded,
    ToolCallStarted,
    ToolCallStatusChanged,
    UnknownUpdateRecorded,
    UserMessageRecorded,
)

_ENTRY_TYPE = "session_update"


class JournalMapper:
    """Журнал ↔ ACP: запись в документ, разбор документа, поток реплея.

    Пример использования:
        >>> entry = JournalEntry(UserMessageRecorded({"type": "text", "text": "привет"}))
        >>> JournalMapper.to_wire(entry)["update"]["sessionUpdate"]
        'user_message_chunk'
    """

    @staticmethod
    def to_wire(entry: JournalEntry) -> dict[str, Any]:
        """Запись журнала в форме документа сессии (нынешний формат, v10)."""
        wire: dict[str, Any] = {
            "type": _ENTRY_TYPE,
            "update": JournalMapper.to_acp_update(entry.event),
        }
        if entry.timestamp is not None:
            wire["timestamp"] = entry.timestamp.isoformat()
        return wire

    @staticmethod
    def to_acp_update(event: SessionEvent) -> dict[str, Any]:
        """Событие как ACP `session/update`.

        Порядок ключей повторяет прежнего писателя, а опциональные поля
        опускаются, а не заполняются `null`: элемент попадает в документ, и
        стабильность его формы — часть обратной совместимости.
        """
        match event:
            case UserMessageRecorded(content=content):
                return {"sessionUpdate": "user_message_chunk", "content": content}
            case AgentMessageRecorded(content=content):
                return {"sessionUpdate": "agent_message_chunk", "content": content}
            case ToolCallStarted(
                tool_call_id=tool_call_id, title=title, kind=kind, status=status, content=content
            ):
                update: dict[str, Any] = {
                    "sessionUpdate": "tool_call",
                    "toolCallId": tool_call_id,
                    "title": title,
                    "kind": kind,
                    "status": status,
                }
                if content:
                    update["content"] = content
                return update
            case ToolCallStatusChanged(tool_call_id=tool_call_id, status=status, content=content):
                changed: dict[str, Any] = {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": tool_call_id,
                    "status": status,
                }
                if content:
                    changed["content"] = content
                return changed
            case PlanRecorded(entries=entries):
                return {"sessionUpdate": "plan", "entries": entries}
            case SessionInfoRecorded(title=title, updated_at=updated_at):
                return {
                    "sessionUpdate": "session_info_update",
                    "title": title,
                    "updatedAt": updated_at,
                }
            case UnknownUpdateRecorded(update=raw):
                return raw

    @staticmethod
    def to_replay_update(event: SessionEvent) -> dict[str, Any] | None:
        """Событие как нотификация реплея; `None` — событие в реплей не входит.

        `SessionInfoRecorded` реплей-формы не имеет (см. его докстринг). Для
        нераспознанной записи решение принимается по её `sessionUpdate`: так
        сохраняется прежний набор реплеируемых видов для старых сессий.
        """
        match event:
            case SessionInfoRecorded():
                return None
            case UnknownUpdateRecorded(update=raw):
                if raw.get("sessionUpdate") in _REPLAYABLE_UNKNOWN_KINDS:
                    return raw
                return None
            case _:
                return JournalMapper.to_acp_update(event)

    @staticmethod
    def from_wire(wire: dict[str, Any]) -> JournalEntry | None:
        """Запись документа как событие журнала; `None` — это не запись журнала."""
        if wire.get("type") != _ENTRY_TYPE:
            return None

        update = wire.get("update")
        if not isinstance(update, dict) or not update:
            return None

        return JournalEntry(
            event=_event_from_update(update),
            timestamp=_timestamp_from_wire(wire.get("timestamp")),
        )


# Виды, которые реплеились до шага 3a и остаются реплеируемыми у нераспознанных
# записей. Модель этот набор не использует: для описанных событий реплеируемость
# определяет наличие реплей-формы, а не строка.
_REPLAYABLE_UNKNOWN_KINDS: frozenset[str] = frozenset(
    {
        "user_message_chunk",
        "agent_message_chunk",
        "tool_call",
        "tool_call_update",
        "plan",
    }
)


_TOOL_CALL_KEYS: frozenset[str] = frozenset(
    {"sessionUpdate", "toolCallId", "title", "kind", "status"}
)
_TOOL_CALL_UPDATE_KEYS: frozenset[str] = frozenset({"sessionUpdate", "toolCallId", "status"})


def _strings(update: dict[str, Any], *names: str) -> bool:
    """Все перечисленные поля — строки."""
    return all(isinstance(update.get(name), str) for name in names)


def _content_ok(update: dict[str, Any]) -> bool:
    """Контент отсутствует либо непустой список.

    Пустой или `None` в записанном обновлении модель описать не может: проекция
    опускает пустой контент, и разбор такой записи перестал бы быть обратимым.
    """
    if "content" not in update:
        return True
    content = update["content"]
    return isinstance(content, list) and bool(content)


def _event_from_update(update: dict[str, Any]) -> SessionEvent:
    """Разбор ACP-обновления в доменное событие; иначе — дословная запись.

    Совпадение проверяется по **точному** набору ключей: обновление со знакомым
    `sessionUpdate` и лишним полем остаётся `UnknownUpdateRecorded`, потому что
    модель его не описывает и пересборка потеряла бы это поле.
    """
    keys = frozenset(update)

    match update.get("sessionUpdate"):
        case "user_message_chunk" if keys == {"sessionUpdate", "content"}:
            content = update["content"]
            if isinstance(content, dict):
                return UserMessageRecorded(content=content)
        case "agent_message_chunk" if keys == {"sessionUpdate", "content"}:
            content = update["content"]
            if isinstance(content, dict):
                return AgentMessageRecorded(content=content)
        case "tool_call" if (
            keys
            in (
                _TOOL_CALL_KEYS,
                _TOOL_CALL_KEYS | {"content"},
            )
            and _strings(update, "toolCallId", "title", "kind", "status")
            and _content_ok(update)
        ):
            return ToolCallStarted(
                tool_call_id=update["toolCallId"],
                title=update["title"],
                kind=update["kind"],
                status=update["status"],
                content=update.get("content"),
            )
        case "tool_call_update" if (
            keys
            in (
                _TOOL_CALL_UPDATE_KEYS,
                _TOOL_CALL_UPDATE_KEYS | {"content"},
            )
            and _strings(update, "toolCallId", "status")
            and _content_ok(update)
        ):
            return ToolCallStatusChanged(
                tool_call_id=update["toolCallId"],
                status=update["status"],
                content=update.get("content"),
            )
        case "plan" if keys == {"sessionUpdate", "entries"}:
            entries = update["entries"]
            if isinstance(entries, list):
                return PlanRecorded(entries=entries)
        case "session_info_update" if keys == {"sessionUpdate", "title", "updatedAt"}:
            return SessionInfoRecorded(title=update["title"], updated_at=update["updatedAt"])

    return UnknownUpdateRecorded(update=update)


def _timestamp_from_wire(raw: object) -> datetime | None:
    """Метка времени записи; нераспознанная метка не повод терять событие."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None

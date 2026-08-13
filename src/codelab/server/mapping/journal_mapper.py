"""Проекция журнала сессии в ACP и разбор уже записанного журнала (шаг 3a ADR-008).

Единственный владелец формы записи `events_history` и формы `session/update`,
построенной по журналу. До шага 3a форму знал писатель (`EventHistoryWriter`), а
реплей был pass-through — элемент журнала уходил клиенту дословно. Теперь запись
и чтение идут через одну проекцию, поэтому расхождение между тем, что клиент
видел в turn-е, и тем, что он получает на `session/load`, перестаёт быть
выразимым.

Шаг 3b сделал доменным и **формат хранения**: запись документа v11 —
`{event, at, data}` с доменным именем вида и `snake_case`-полями, вместо прежней
готовой ACP-нотификации. Поток `session/load` при этом не изменился: он строится
проекцией из события, а не переписыванием записи.

Читаются **оба** формата. v10 поднимает миграция документа (`_migrate_to_v11` в
`storage/document.py`), но ветка v10 в `from_wire` нужна и помимо неё — доменные
сессии собираются в обход хранилища, и разбор обязан быть идемпотентным.

Терпимость к записанному: `from_wire` возвращает `UnknownUpdateRecorded` для
всего, чего модель не описывает **точно** — включая знакомый `sessionUpdate` с
незнакомым набором полей. Такая запись хранится дословно (вид
`acp_update_verbatim`) и дословно же уходит в реплей, поэтому загрузка сессий от
прежних версий ничего не теряет.
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
    UnexecutedToolCallAnswered,
    UnknownUpdateRecorded,
    UserMessageRecorded,
)

_ENTRY_TYPE = "session_update"

# Имена видов записи в документе v11. Держатся отдельной таблицей, а не
# выводятся из имён классов: имя класса — деталь реализации, а это формат на
# диске, и переименование класса не должно ломать чтение записанного.
_EVENT_NAMES: dict[type, str] = {
    UserMessageRecorded: "user_message_recorded",
    AgentMessageRecorded: "agent_message_recorded",
    ToolCallStarted: "tool_call_started",
    ToolCallStatusChanged: "tool_call_status_changed",
    UnexecutedToolCallAnswered: "unexecuted_tool_call_answered",
    PlanRecorded: "plan_recorded",
    SessionInfoRecorded: "session_info_recorded",
    UnknownUpdateRecorded: "acp_update_verbatim",
}


class JournalMapper:
    """Журнал ↔ документ и журнал ↔ ACP: запись, разбор, поток реплея.

    Пример использования:
        >>> entry = JournalEntry(UserMessageRecorded({"type": "text", "text": "привет"}))
        >>> JournalMapper.to_wire(entry)["event"]
        'user_message_recorded'
    """

    @staticmethod
    def to_wire(entry: JournalEntry) -> dict[str, Any]:
        """Запись журнала в форме документа v11: `{event, at, data}`.

        Оболочка журнала отделена от полей события намеренно: `kind` вызова
        инструмента и вид записи иначе делили бы одно пространство имён, а
        добавление поля журнала (`seq` в шаге 6) рисковало бы столкнуться с полем
        события.
        """
        wire: dict[str, Any] = {"event": _EVENT_NAMES[type(entry.event)]}
        if entry.timestamp is not None:
            wire["at"] = entry.timestamp.isoformat()
        wire["data"] = _data_of(entry.event)
        return wire

    @staticmethod
    def to_acp_update(event: SessionEvent) -> dict[str, Any] | None:
        """Событие как ACP `session/update`; `None` — у события нет ACP-формы.

        Порядок ключей повторяет прежнего писателя, а опциональные поля
        опускаются, а не заполняются `null`: элемент попадает в документ, и
        стабильность его формы — часть обратной совместимости.

        `None` возвращается для факта, которого в ACP нет вовсе: ответ модели на
        невыполненный вызов адресован LLM-истории, а не клиенту. Это не то же
        самое, что «событие не реплеится» (`to_replay_update`): `session_info`
        ACP-форму имеет, просто не воспроизводится.
        """
        match event:
            case UserMessageRecorded(content=content):
                return {"sessionUpdate": "user_message_chunk", "content": content}
            case AgentMessageRecorded(content=content):
                return {"sessionUpdate": "agent_message_chunk", "content": content}
            case ToolCallStarted(
                tool_call_id=tool_call_id, title=title, kind=kind, status=status, content=content
            ):
                return _with_content(
                    {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call_id,
                        "title": title,
                        "kind": kind,
                        "status": status,
                    },
                    content,
                )
            case ToolCallStatusChanged(tool_call_id=tool_call_id, status=status, content=content):
                return _with_content(
                    {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call_id,
                        "status": status,
                    },
                    content,
                )
            case UnexecutedToolCallAnswered():
                return None
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

        `SessionInfoRecorded` реплей-формы не имеет (см. его докстринг), а
        `UnexecutedToolCallAnswered` не имеет и ACP-формы. Для нераспознанной
        записи решение принимается по её `sessionUpdate`: так сохраняется прежний
        набор реплеируемых видов для старых сессий.
        """
        match event:
            case SessionInfoRecorded() | UnexecutedToolCallAnswered():
                return None
            case UnknownUpdateRecorded(update=raw):
                if raw.get("sessionUpdate") in _REPLAYABLE_UNKNOWN_KINDS:
                    return raw
                return None
            case _:
                return JournalMapper.to_acp_update(event)

    @staticmethod
    def from_wire(wire: dict[str, Any]) -> JournalEntry | None:
        """Запись документа как событие журнала; `None` — это не запись журнала.

        Читает **оба** формата: v11 (`{event, at, data}`) и v10
        (`{type: session_update, update, timestamp}`). Ветка v10 нужна не только
        документам с диска — их поднимает миграция, — а доменным сессиям, которые
        собираются в обход хранилища (тесты, дочерние сессии), и делает разбор
        идемпотентным.
        """
        if isinstance(wire.get("event"), str):
            return _entry_from_v11(wire)

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


def _with_content(
    projection: dict[str, Any], content: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Дописать контент, если он есть.

    Пустой контент опускается, а не заполняется `null`: проекция попадает в
    документ, и стабильность её формы — часть обратной совместимости.
    """
    if content:
        projection["content"] = content
    return projection


def _data_of(event: SessionEvent) -> dict[str, Any]:
    """Полезная нагрузка события в форме v11 — доменные имена, `snake_case`.

    Блоки контента остаются как есть: их форма принадлежит ACP Content Types, и
    домен их не переписывает (см. `domain/journal.py`).
    """
    match event:
        case UserMessageRecorded(content=content) | AgentMessageRecorded(content=content):
            return {"content": content}
        case ToolCallStarted(
            tool_call_id=tool_call_id, title=title, kind=kind, status=status, content=content
        ):
            data: dict[str, Any] = {
                "tool_call_id": tool_call_id,
                "title": title,
                "kind": kind,
                "status": status,
            }
            if content:
                data["content"] = content
            return data
        case ToolCallStatusChanged(tool_call_id=tool_call_id, status=status, content=content):
            changed: dict[str, Any] = {"tool_call_id": tool_call_id, "status": status}
            if content:
                changed["content"] = content
            return changed
        case UnexecutedToolCallAnswered(tool_call_id=tool_call_id, text=text):
            return {"tool_call_id": tool_call_id, "text": text}
        case PlanRecorded(entries=entries):
            return {"entries": entries}
        case SessionInfoRecorded(title=title, updated_at=updated_at):
            return {"title": title, "updated_at": updated_at}
        case UnknownUpdateRecorded(update=raw):
            return {"update": raw}


def _entry_from_v11(wire: dict[str, Any]) -> JournalEntry | None:
    """Разбор записи v11; `None` — вид записи неизвестен.

    Неизвестный вид пропускается, а не роняет загрузку: документ мог быть записан
    более новой версией, и потерять на этом всю сессию было бы хуже, чем потерять
    одну запись. Форма самой записи при этом сохраняется в документе — реплей её
    просто не отдаёт.
    """
    data = wire.get("data")
    if not isinstance(data, dict):
        return None

    timestamp = _timestamp_from_wire(wire.get("at"))
    content = data.get("content")
    entries = data.get("entries")

    match wire["event"]:
        case "user_message_recorded" if isinstance(content, dict):
            return JournalEntry(UserMessageRecorded(content=content), timestamp)
        case "agent_message_recorded" if isinstance(content, dict):
            return JournalEntry(AgentMessageRecorded(content=content), timestamp)
        case "tool_call_started" if _strings(data, "tool_call_id", "title", "kind", "status"):
            return JournalEntry(
                ToolCallStarted(
                    tool_call_id=data["tool_call_id"],
                    title=data["title"],
                    kind=data["kind"],
                    status=data["status"],
                    content=data.get("content"),
                ),
                timestamp,
            )
        case "tool_call_status_changed" if _strings(data, "tool_call_id", "status"):
            return JournalEntry(
                ToolCallStatusChanged(
                    tool_call_id=data["tool_call_id"],
                    status=data["status"],
                    content=data.get("content"),
                ),
                timestamp,
            )
        case "unexecuted_tool_call_answered" if _strings(data, "tool_call_id", "text"):
            return JournalEntry(
                UnexecutedToolCallAnswered(
                    tool_call_id=data["tool_call_id"],
                    text=data["text"],
                ),
                timestamp,
            )
        case "plan_recorded" if isinstance(entries, list):
            return JournalEntry(PlanRecorded(entries=entries), timestamp)
        case "session_info_recorded":
            return JournalEntry(
                SessionInfoRecorded(title=data.get("title"), updated_at=data.get("updated_at")),
                timestamp,
            )
        case "acp_update_verbatim" if isinstance(data.get("update"), dict):
            return JournalEntry(UnknownUpdateRecorded(update=data["update"]), timestamp)

    return None


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

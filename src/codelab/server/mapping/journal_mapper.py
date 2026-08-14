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
from typing import Any, cast

from codelab.server.domain.journal import (
    AgentMessageRecorded,
    JournalEntry,
    PlanRecorded,
    RequestedToolCall,
    SessionEvent,
    SessionInfoRecorded,
    ToolCallAnswered,
    ToolCallStarted,
    ToolCallStatusChanged,
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
    ToolCallAnswered: "tool_call_answered",
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
    def to_acp_updates(event: SessionEvent) -> list[dict[str, Any]]:
        """Событие как ACP `session/update`; пустой список — ACP-формы нет.

        Список, а не одна нотификация: событие описывает **сообщение**, а ACP
        передаёт текст чанками — многоблочный промпт даёт по чанку на блок
        (шаг 4e). Прежняя подпись `dict | None` этого выразить не могла, и именно
        поэтому пользовательская сторона хранила событие на блок.

        Порядок ключей повторяет прежнего писателя, а опциональные поля
        опускаются, а не заполняются `null`: элемент попадает в документ, и
        стабильность его формы — часть обратной совместимости.

        `None` возвращается для факта, которого в ACP нет вовсе: ответ модели на
        вызов адресован LLM-истории, а не клиенту. Это не то же
        самое, что «событие не реплеится» (`to_replay_update`): `session_info`
        ACP-форму имеет, просто не воспроизводится.
        """
        match event:
            case UserMessageRecorded(blocks=blocks):
                return [
                    {"sessionUpdate": "user_message_chunk", "content": block} for block in blocks
                ]
            case AgentMessageRecorded(content=content):
                # Вызовы модели ACP-формы не имеют: клиент узнаёт о них
                # нотификациями `tool_call`, а не чанком сообщения.
                if content is None:
                    return []
                return [{"sessionUpdate": "agent_message_chunk", "content": content}]
            case ToolCallStarted(
                tool_call_id=tool_call_id, title=title, kind=kind, status=status, content=content
            ):
                return _one(
                    _with_content(
                        {
                            "sessionUpdate": "tool_call",
                            "toolCallId": tool_call_id,
                            "title": title,
                            "kind": kind,
                            "status": status,
                        },
                        content,
                    )
                )
            case ToolCallStatusChanged(tool_call_id=tool_call_id, status=status, content=content):
                return _one(
                    _with_content(
                        {
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": tool_call_id,
                            "status": status,
                        },
                        content,
                    )
                )
            case ToolCallAnswered():
                return []
            case PlanRecorded(entries=entries):
                return _one({"sessionUpdate": "plan", "entries": entries})
            case SessionInfoRecorded(title=title, updated_at=updated_at):
                return _one(
                    {
                        "sessionUpdate": "session_info_update",
                        "title": title,
                        "updatedAt": updated_at,
                    }
                )
            case UnknownUpdateRecorded(update=raw):
                return _one(raw)

    @staticmethod
    def to_replay_updates(event: SessionEvent) -> list[dict[str, Any]]:
        """Событие как нотификации реплея; пустой список — событие не реплеится.

        `SessionInfoRecorded` реплей-формы не имеет (см. его докстринг), а
        `ToolCallAnswered` не имеет и ACP-формы. Для нераспознанной
        записи решение принимается по её `sessionUpdate`: так сохраняется прежний
        набор реплеируемых видов для старых сессий.
        """
        match event:
            case SessionInfoRecorded() | ToolCallAnswered():
                return []
            case UnknownUpdateRecorded(update=raw):
                if raw.get("sessionUpdate") in _REPLAYABLE_UNKNOWN_KINDS:
                    return [raw]
                return []
            case _:
                return JournalMapper.to_acp_updates(event)

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


def _agent_data(
    content: dict[str, Any] | None, tool_calls: list[RequestedToolCall]
) -> dict[str, Any]:
    """Полезная нагрузка ответа модели: текст и запрошенные вызовы.

    Отсутствующие части опускаются, а не заполняются `null`: запись попадает в
    документ, и стабильность её формы — часть обратной совместимости.
    """
    data: dict[str, Any] = {}
    if content is not None:
        data["content"] = content
    if tool_calls:
        data["tool_calls"] = [
            {"id": call.id, "name": call.name, "arguments": call.arguments} for call in tool_calls
        ]
    return data


def _one(update: dict[str, Any]) -> list[dict[str, Any]]:
    """Событие с единственной ACP-формой. Явная обёртка вместо ветвления у вызывающего."""
    return [update]


def _data_of(event: SessionEvent) -> dict[str, Any]:
    """Полезная нагрузка события в форме v11 — доменные имена, `snake_case`.

    Блоки контента остаются как есть: их форма принадлежит ACP Content Types, и
    домен их не переписывает (см. `domain/journal.py`).
    """
    match event:
        case UserMessageRecorded(blocks=blocks):
            return {"blocks": blocks}
        case AgentMessageRecorded(content=content, tool_calls=tool_calls):
            return _agent_data(content, tool_calls)
        case ToolCallStarted():
            return _started_data(event)
        case ToolCallStatusChanged(tool_call_id=tool_call_id, status=status, content=content):
            return _with_content({"tool_call_id": tool_call_id, "status": status}, content)
        case ToolCallAnswered(tool_call_id=tool_call_id, text=text):
            return {"tool_call_id": tool_call_id, "text": text}
        case PlanRecorded(entries=entries):
            return {"entries": entries}
        case SessionInfoRecorded(title=title, updated_at=updated_at):
            return {"title": title, "updated_at": updated_at}
        case UnknownUpdateRecorded(update=raw):
            return {"update": raw}


def _started_data(event: ToolCallStarted) -> dict[str, Any]:
    """Полезная нагрузка `tool_call_started`.

    Поля без значения не пишутся: у вызовов client-RPC их нет вовсе, и `None` в
    документе от их отсутствия ничем бы не отличался.
    """
    data = _with_content(
        {
            "tool_call_id": event.tool_call_id,
            "title": event.title,
            "kind": event.kind,
            "status": event.status,
        },
        event.content,
    )
    if event.tool_name is not None:
        data["tool_name"] = event.tool_name
    if event.arguments is not None:
        data["arguments"] = event.arguments
    if event.tool_call_id_from_llm is not None:
        data["tool_call_id_from_llm"] = event.tool_call_id_from_llm
    return data


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
    entries = data.get("entries")

    message = _message_entry_from_v11(wire["event"], data, timestamp)
    if message is not None:
        return message

    match wire["event"]:
        case "tool_call_started" if _strings(data, "tool_call_id", "title", "kind", "status"):
            return JournalEntry(
                ToolCallStarted(
                    tool_call_id=data["tool_call_id"],
                    title=data["title"],
                    kind=data["kind"],
                    status=data["status"],
                    content=data.get("content"),
                    tool_name=_optional_str(data.get("tool_name")),
                    arguments=_optional_dict(data.get("arguments")),
                    tool_call_id_from_llm=_optional_str(data.get("tool_call_id_from_llm")),
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
        # Старое имя вида читается наравне с нынешним: событий ответа было два, и
        # различались они лишь тем, выполнялся ли вызов (шаг 4a). Обобщение в одно
        # (шаг 4) не должно терять записи документов, уже лежащих на диске, —
        # миграции у него нет и не нужно, форма данных та же.
        case "tool_call_answered" | "unexecuted_tool_call_answered" if _strings(
            data, "tool_call_id", "text"
        ):
            return JournalEntry(
                ToolCallAnswered(
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


def _message_entry_from_v11(
    kind: object, data: dict[str, Any], timestamp: datetime | None
) -> JournalEntry | None:
    """Записи сообщений диалога; `None` — вид записи не про сообщение.

    Вынесено из общего разбора, потому что у обеих сторон есть форма до шага 4e и
    после, и ветвление читается только рядом само с собой.
    """
    content = data.get("content")
    blocks = data.get("blocks")

    match kind:
        case "user_message_recorded" if isinstance(blocks, list):
            return JournalEntry(UserMessageRecorded(blocks=blocks), timestamp)
        # Форма v13 и раньше: событие на блок. Такая запись читается как сообщение
        # из одного блока — это всё, что о её границах известно. Промпт из
        # нескольких блоков, записанный прежней версией, останется разложенным на
        # сообщения: границу восстановить нечем, и притворяться, что можно, хуже.
        case "user_message_recorded" if isinstance(content, dict):
            return JournalEntry(UserMessageRecorded(blocks=[content]), timestamp)
        case "agent_message_recorded" if isinstance(content, dict) or data.get("tool_calls"):
            return JournalEntry(
                AgentMessageRecorded(
                    content=content if isinstance(content, dict) else None,
                    tool_calls=_requested_calls(data.get("tool_calls")),
                ),
                timestamp,
            )
    return None


def _requested_calls(raw: object) -> list[RequestedToolCall]:
    """Вызовы, запрошенные моделью; нераспознанная запись даёт пустой список.

    Пустой список неотличим от отсутствия поля намеренно: assistant-сообщение без
    вызовов — обычный случай, и `tool_calls` в такой записи не пишется вовсе.
    """
    if not isinstance(raw, list):
        return []

    calls: list[RequestedToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        # Элемент прочитан с диска, поэтому его тип известен только по проверке
        # выше; поля валидируются здесь же, ниже.
        fields = cast(dict[str, Any], item)
        call_id = fields.get("id")
        name = fields.get("name")
        arguments = fields.get("arguments")
        if not isinstance(call_id, str) or not isinstance(name, str):
            continue
        calls.append(
            RequestedToolCall(
                id=call_id,
                name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


def _strings(update: dict[str, Any], *names: str) -> bool:
    """Все перечисленные поля — строки."""
    return all(isinstance(update.get(name), str) for name in names)


def _optional_str(raw: object) -> str | None:
    """Строка либо `None`; чужая форма — как отсутствие поля.

    Запись могла прийти от более новой версии или от чужого писателя, и ронять
    на ней загрузку сессии нельзя: потеря вызова дешевле потери сессии.
    """
    return raw if isinstance(raw, str) else None


def _optional_dict(raw: object) -> dict[str, Any] | None:
    """Словарь либо `None`; чужая форма — как отсутствие поля."""
    return dict(raw) if isinstance(raw, dict) else None


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
                return UserMessageRecorded(blocks=[content])
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

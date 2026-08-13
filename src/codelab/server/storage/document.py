"""Документ сессии: форма, в которой сессия лежит на диске.

Дом этой модели — хранилище, а не протокол: документ описывает сериализацию, а
не ACP-обмен. Пока он жил в `protocol/state.py`, хранилищу приходилось
импортировать протокол — единственная протечка, которую import-linter держал в
`ignore_imports` (ADR-006, фаза D шаг 5).

Имя `SessionDocument` уехало вместе с модулем: состояние сессии — это доменный
`Session`, а здесь документ. Два «state» рядом были главным источником путаницы
всей фазы D, поэтому модель называется `SessionDocument`.

НЕ доменная модель. Для бизнес-логики использовать `domain.session.Session`,
конвертация — через `SessionMapper`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from ..agent.config.models import SessionMetrics
from ..messages import JsonRpcId
from ..models import AvailableCommand, HistoryMessage, PlanStep

_ACP_PRIORITIES = {"low", "medium", "high"}
_ACP_STATUSES = {"pending", "in_progress", "completed"}


def _migrate_plan_entry_to_acp(entry: Any) -> dict[str, Any]:
    """Приводит одну plan-запись к ACP-форме ``{content, priority, status}`` (P2-26).

    Legacy-форма ``{title, description}`` (невалидна по ACP 11-Agent Plan) конвертируется:
    ``title``/``description`` → ``content``. Уже-ACP записи и `PlanStep`-подобные
    (`description` как основной текст) сохраняют доступную информацию; отсутствующие
    ``priority``/``status`` заполняются валидными дефолтами.
    """
    if not isinstance(entry, dict):
        return entry
    content = entry.get("content") or entry.get("title") or entry.get("description") or ""
    priority = entry.get("priority")
    if priority not in _ACP_PRIORITIES:
        priority = "medium"
    status = entry.get("status")
    if status not in _ACP_STATUSES:
        status = "pending"
    return {"content": content, "priority": priority, "status": status}


def _migrate_to_v1(data: dict[str, Any]) -> None:
    """v0 → v1: events_history, config_values."""
    data.setdefault("events_history", [])
    data.setdefault("config_values", {})


def _migrate_to_v3(data: dict[str, Any]) -> None:
    """v1 → v3: поля мультиагентного режима."""
    data.setdefault("active_strategy", "single")
    data.setdefault("active_agents", [])
    data.setdefault("session_metrics", None)
    data.setdefault("correlation_id", None)
    data.setdefault("parent_session_id", None)
    data.setdefault("child_session_ids", [])
    data.setdefault("is_child_session", False)
    data.setdefault("task_result", None)
    data.setdefault("sliced_summary", None)


def _migrate_to_v4(data: dict[str, Any]) -> None:
    """v3 → v4: разделение доменной модели — структура не менялась.

    Совместимость обеспечивает `SessionMapper`, поэтому шаг только поднимает версию.
    """


def _migrate_to_v5(data: dict[str, Any]) -> None:
    """v4 → v5: реестр alias'ов терминалов (tech-debt #18)."""
    data.setdefault("terminals", {})
    data.setdefault("terminal_counter", 0)


def _migrate_to_v6(data: dict[str, Any]) -> None:
    """v5 → v6: `latest_plan` в ACP-форме {content,priority,status} (P2-26).

    Ранее часть путей хранила невалидный по ACP {title,description} — конвертируем,
    чтобы replay на `session/load` отдавал ACP-валидные entries со статусами.
    """
    data["latest_plan"] = [
        _migrate_plan_entry_to_acp(entry) for entry in data.get("latest_plan", [])
    ]


def _migrate_to_v7(data: dict[str, Any]) -> None:
    """v6 → v7: ревизия документа для compare-and-set (ADR-007).

    Старые файлы начинают с 0 — первая же запись поднимет её до 1.
    """
    data.setdefault("revision", 0)


def _migrate_to_v8(data: dict[str, Any]) -> None:
    """v7 → v8: владелец реестра терминалов (P2-44).

    Поле удалено в v9 — шаг оставлен как есть, чтобы цепочка миграций читалась
    подряд; выставленный ключ отбрасывается моделью как лишний.
    """
    data.setdefault("terminals_owner", None)


def _migrate_to_v9(data: dict[str, Any]) -> None:
    """v8 → v9: связка alias'ов терминалов уезжает в процессный реестр (ADR-007, шаг A).

    Структура не меняется — шаг удаляет то, чего не должно было persist'иться.
    `terminals` и `terminals_owner` отбрасываются: связка осмысленна только внутри
    процесса, который её создал, а сами терминалы живут у клиента. Явный `pop`, а не
    опора на «лишние ключи игнорируются»: удаление данных должно быть видно в
    цепочке миграций, а не быть побочным эффектом настроек модели.

    `terminal_counter` тогда **остался** как распределитель идентификаторов сессии,
    обязанный быть монотонным через рестарт. В v13 он снят: alias несёт эпоху
    процесса, и персистировать счётчик стало незачем.
    """
    data.pop("terminals", None)
    data.pop("terminals_owner", None)


def _migrate_to_v10(data: dict[str, Any]) -> None:
    """v9 → v10: `result_content` вызовов удалён как поле без потребителя (ADR-007, шаг B1).

    Его писал только turn-путь (`_store_and_format`), а читал — никто: реплей и нотификации
    строятся из `content`, наружу в wire поле не уходило, клиент его не знает. На замеренном
    документе это 142 099 байт, 21% объёма, уезжавших на диск без пользы.

    Как и в v9, отбрасывание явное: удаление данных должно быть видно в цепочке миграций.
    """
    for call in data.get("tool_calls", {}).values():
        if isinstance(call, dict):
            call.pop("result_content", None)


def _migrate_to_v11(data: dict[str, Any]) -> None:
    """v10 → v11: журнал хранится доменными событиями, а не ACP-нотификациями (шаг 3b ADR-008).

    До v11 элемент `events_history` был готовой нотификацией `session/update` в
    camelCase, то есть формат хранения задавался внешним протоколом. Теперь запись
    имеет вид `{event, at, data}` с доменным именем вида, а ACP-поток строится
    проекцией при загрузке.

    Миграция **ничего не теряет**: то, что модель не описывает точно, переносится
    видом `acp_update_verbatim` с исходным обновлением внутри и дословно уходит в
    реплей. Записи, которые журналом не являются вовсе (`type` не
    `session_update`), остаются как были — журнал ими не владеет, и реплей их не
    отдавал и раньше.
    """
    from ..mapping.journal_mapper import JournalMapper

    journal = data.get("events_history")
    if not isinstance(journal, list):
        return

    migrated: list[Any] = []
    for record in journal:
        if not isinstance(record, dict):
            migrated.append(record)
            continue
        entry = JournalMapper.from_wire(record)
        migrated.append(JournalMapper.to_wire(entry) if entry is not None else record)
    data["events_history"] = migrated


def _migrate_to_v12(data: dict[str, Any]) -> None:
    """v11 → v12: незакрытые разрешения turn'а хранятся списком (шаг 5 ADR-008).

    До v12 ожидание описывалось парой плоских полей, поэтому переживало запись
    только последнее. Ответ на любой другой незакрытый запрос применить было не к
    чему: фаза, восстановленная из документа, о нём уже не знала — вызов оставался
    `pending` навсегда и без `role: tool` (P1-61, измерено живьём 2026-08-07).

    Множественность требует спецификация (`05-Prompt Turn.md`): клиент обязан
    ответить на **все** незакрытые `session/request_permission`.

    Пара полей отбрасывается явно, как в v9 и v10: удаление данных должно быть
    видно в цепочке миграций, а не быть побочным эффектом настроек модели.
    """
    turn = data.get("active_turn")
    if not isinstance(turn, dict):
        return

    request_id = turn.pop("permission_request_id", None)
    tool_call_id = turn.pop("permission_tool_call_id", None)
    if turn.get("permission_waits"):
        return
    if request_id is None:
        turn["permission_waits"] = []
        return

    turn["permission_waits"] = [
        {
            "request_id": request_id,
            "tool_call_id": tool_call_id,
            # Ветку хранило имя фазы — до типизации это было единственное место,
            # где две ветки одного состояния различались (шаг 2).
            "keep_tool_pending": turn.get("phase") == "waiting_tool_completion",
        }
    ]


def _migrate_to_v13(data: dict[str, Any]) -> None:
    """v12 → v13: счётчик alias'ов терминалов уезжает в процесс (шаг 5 ADR-008, раздел 4).

    ``terminal_counter`` персистился ради монотонности через рестарт: без неё
    ``term_1`` из восстановленной истории разрешился бы в терминал нового процесса.
    Гарантия была дисциплинарной и однажды не сработала — счётчик жил в документе, а
    Context Manager мутирует переданный объект сессии, и на его пути мутация не
    сохранялась: ``term_1`` достался двум терминалам при счётчике 2 вместо 3 (P2-58,
    замер 2026-08-06).

    Alias теперь несёт эпоху процесса (``term_<epoch>_<n>``), поэтому персистировать
    счётчик незачем: alias прошлого процесса отличается эпохой, а потерять запись
    негде — счётчик живёт рядом со связкой в ``TerminalAliasRegistry``.

    Отбрасывание явное, как в v9 и v10: удаление данных должно быть видно в цепочке
    миграций, а не быть побочным эффектом настроек модели.
    """
    data.pop("terminal_counter", None)


def _migrate_to_v14(data: dict[str, Any]) -> None:
    """v13 → v14: события диалога переходят на гранулярность сообщения (шаг 4e ADR-008).

    Промпт пользователя писался событием **на блок**, хотя `add_user_message`
    кладёт в историю **одно** сообщение из всех блоков. Проекция `history` из
    такой записи восстановила бы N сообщений вместо одного, то есть изменила бы
    форму диалога и сбросила prompt cache. Дефект латентный: во всех
    наблюдавшихся промптах был ровно один блок.

    **Миграция не склеивает записи, и это осознанно.** Границу сообщения в
    записанном документе восстановить нечем: два соседних события могут быть и
    одним промптом из двух блоков, и двумя промптами. Догадка здесь тем хуже, что
    ошибка молча изменила бы историю диалога. Поэтому каждая старая запись
    остаётся сообщением из одного блока — ровно то, что о ней известно, — а
    чтение этой формы держит `JournalMapper`, а не миграция.

    Записи ответа модели формат не меняют вовсе: `content` остаётся `content`, а
    `tool_calls` в старых документах просто нет.
    """
    return


# Актуальная версия формата документа. Названа константой, потому что число
# встречается и в модели, и в тестах миграций: раньше при поднятии версии его
# приходилось искать по литералам, и тесты падали пачкой, не объясняя причину.
CURRENT_SCHEMA_VERSION = 14

# Порядок обязателен: шаги применяются подряд от текущей версии документа.
_SCHEMA_MIGRATIONS: list[tuple[int, Callable[[dict[str, Any]], None]]] = [
    (1, _migrate_to_v1),
    (3, _migrate_to_v3),
    (4, _migrate_to_v4),
    (5, _migrate_to_v5),
    (6, _migrate_to_v6),
    (7, _migrate_to_v7),
    (8, _migrate_to_v8),
    (9, _migrate_to_v9),
    (10, _migrate_to_v10),
    (11, _migrate_to_v11),
    (12, _migrate_to_v12),
    (13, _migrate_to_v13),
    (14, _migrate_to_v14),
]


class ToolCallState(BaseModel):
    """ACP Protocol Model — контракт tool call согласно ACP 08-Tool Calls.

    Wire format для session/update notification с sessionUpdate="tool_call"
    и sessionUpdate="tool_call_update".

    НЕ является domain моделью. Для бизнес-логики использовать domain ToolCall.
    Конвертация через ToolCallMapper.

    Пример использования:
        call = ToolCallState("call_001", "Demo", "other", "pending")
    """

    # Идентификатор связывает `tool_call` и `tool_call_update` события.
    tool_call_id: str
    # Заголовок для отображения в клиенте.
    title: str
    # Категория вызова (например, other/execute/search).
    kind: str
    # Текущий статус жизненного цикла tool call.
    status: str
    # Контент, возвращенный при завершении (если есть).
    content: list[dict[str, Any]] = Field(default_factory=list)
    # Имя инструмента для выполнения (соответствует tool_name в registry).
    tool_name: str | None = None
    # Аргументы для выполнения инструмента (для отложенного выполнения после permission).
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    # Идентификатор tool_call из LLM ответа (для связки в истории диалога).
    # Может отличаться от tool_call_id, который генерируется нами.
    tool_call_id_from_llm: str | None = None
    # Затронутые файлы (ACP locations).
    locations: list[dict[str, Any]] = Field(default_factory=list)
    # Исходные аргументы инструмента (ACP rawInput).
    raw_input: dict[str, Any] = Field(default_factory=dict)
    # Исходный результат выполнения (ACP rawOutput).
    raw_output: dict[str, Any] = Field(default_factory=dict)


class PermissionWaitState(BaseModel):
    """Одно незакрытое разрешение в документе сессии (v12, шаг 5 ADR-008).

    Документ — носитель состояния turn'а между запросом и ответом: разрешение
    приходит следующим запросом, а тот получает свою копию сессии с диска (та же
    причина, по которой здесь живёт `pending_batch`). Пока ожидание хранилось
    двумя плоскими полями, переживало запись только последнее, и ответ на любой
    другой запрос применить было не к чему (P1-61).
    """

    request_id: JsonRpcId
    tool_call_id: str | None = None
    keep_tool_pending: bool = False


class ActiveTurnState(BaseModel):
    """Состояние текущего prompt-turn для корректной обработки cancel.

    Содержит идентификатор JSON-RPC запроса prompt и признак запроса отмены.

    Пример использования:
        turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
    """

    prompt_request_id: JsonRpcId | None
    session_id: str
    cancel_requested: bool = False
    # Незакрытые разрешения. Список, а не пара полей: одновременных ожиданий может
    # быть несколько, и спецификация этого прямо требует (`05-Prompt Turn.md` —
    # ответить на **все** незакрытые запросы). Прежние `permission_request_id` и
    # `permission_tool_call_id` остались как выводимые свойства: их читают около
    # десятка мест, и смысл у них прежний, пока ожидание одно.
    permission_waits: list[PermissionWaitState] = Field(default_factory=list)
    # Фаза жизненного цикла prompt-turn для детерминированного поведения.
    phase: str = "running"
    # Исходящий запрос к клиенту (fs/*), если turn ожидает его completion.
    pending_client_request: PendingClientRequestState | None = None
    # Остаток батча tool_calls, не обработанный из-за паузы на permission.
    # Раньше хвост выбрасывался: модель получала «вызов не выполнялся» и
    # перезапрашивала те же файлы (P2-40 — 80 брошенных вызовов за один turn).
    # Хранится в состоянии turn'а, потому что разрешение приходит следующим
    # запросом, а тот получает свою копию сессии с диска.
    pending_batch: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_permission_fields(cls, data: Any) -> Any:
        """Принимает прежнюю пару полей как вход и сворачивает её в список.

        Нужна не только документам с диска (их поднимает `_migrate_to_v12`), но и
        конструированию в коде: `ActiveTurnState(permission_request_id=...)` —
        привычная форма записи ожидания, и ломать её ради формата хранения значило
        бы менять публичный контракт модели без нужды.
        """
        if not isinstance(data, dict):
            return data
        if data.get("permission_waits"):
            data.pop("permission_request_id", None)
            data.pop("permission_tool_call_id", None)
            return data

        request_id = data.pop("permission_request_id", None)
        tool_call_id = data.pop("permission_tool_call_id", None)
        if request_id is not None:
            data["permission_waits"] = [
                {
                    "request_id": request_id,
                    "tool_call_id": tool_call_id,
                    "keep_tool_pending": data.get("phase") == "waiting_tool_completion",
                }
            ]
        return data

    @property
    def permission_request_id(self) -> JsonRpcId | None:
        """Идентификатор последнего заведённого ожидания, если оно есть.

        Выводимое свойство, а не поле: единственным источником стал
        `permission_waits`. Одно значение честно описывает turn лишь пока
        ожидание одно, поэтому решения по нему принимать нельзя — для этого есть
        сам список.
        """
        return self.permission_waits[-1].request_id if self.permission_waits else None

    @property
    def permission_tool_call_id(self) -> str | None:
        """Вызов последнего ожидания. Те же оговорки, что у `permission_request_id`."""
        return self.permission_waits[-1].tool_call_id if self.permission_waits else None

    def awaits_permission_request(self, request_id: JsonRpcId) -> bool:
        """Ждёт ли turn ответа именно на этот запрос.

        Поиск сессии по ответу обязан спрашивать **это**, а не сравнивать с
        последним идентификатором: иначе ответ на любой другой незакрытый запрос
        сессию не находит (P1-61).
        """
        return any(wait.request_id == request_id for wait in self.permission_waits)


class PendingClientRequestState(BaseModel):
    """Состояние исходящего agent->client request внутри активного turn.

    Нужно для корреляции входящего client response с ожидаемым действием
    (например, `fs/read_text_file` или `fs/write_text_file`).

    Пример использования:
        pending = PendingClientRequestState(
            request_id="req_1",
            kind="fs_read",
            tool_call_id="call_001",
            path="/tmp/README.md",
        )
    """

    request_id: JsonRpcId
    kind: str
    tool_call_id: str
    path: str
    expected_new_text: str | None = None
    terminal_id: str | None = None
    terminal_output: str | None = None
    terminal_exit_code: int | None = None
    terminal_signal: str | None = None
    terminal_truncated: bool | None = None


class ClientRuntimeCapabilities(BaseModel):
    """Согласованные на `initialize` возможности клиентского runtime.

    Используются как feature-gate для веток, где агент ожидает клиентские
    RPC-возможности (например, запуск инструментов через client-side runtime).

    Пример использования:
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=False, terminal=True)
    """

    fs_read: bool = False
    fs_write: bool = False
    terminal: bool = False


class SessionDocument(BaseModel):
    """ACP Protocol Model — контракт сессии согласно ACP 03-Session Setup.

    Wire format для хранения состояния сессии в storage.

    НЕ является domain моделью. Для бизнес-логики использовать domain Session.
    Конвертация через SessionMapper.

    Пример использования:
        state = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Версия схемы для миграций
    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION)
    # Ревизия документа: счётчик записей, растёт на каждое сохранение. Нужна для
    # compare-and-set: копия сессии живёт через `await` (фоновое исполнение turn'а),
    # и без сверки её запись молча затирала бы решения, принятые тем временем другим
    # запросом (ADR-007). Это не `schema_version` — та про формат, эта про документ.
    revision: int = Field(default=0)

    session_id: str
    cwd: str
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    # Заголовок сессии для UI; выставляется из первого пользовательского запроса.
    title: str | None = None
    # Время последнего изменения сессии в формате ISO 8601.
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Значения конфигурационных опций в рамках этой сессии.
    config_values: dict[str, str] = Field(default_factory=dict)
    # История сообщений в единственной форме (ADR-006, фаза D шаг 4). Раньше поле
    # было союзом `HistoryMessage | dict`: запись, добавленную в этом процессе,
    # писатели клали плоским dict'ом, а та же запись, прочитанная с диска,
    # валидировалась в модель. Две формы одной записи ломали сравнение по
    # префиксу при слиянии — корень P1-45. Форму теперь пишет только домен, а
    # документы прошлых версий приводятся к модели при валидации (`extra="allow"`
    # сохраняет поля вроде `tool_calls`).
    history: list[HistoryMessage] = Field(default_factory=list)
    # Текущее активное выполнение prompt-turn (если есть).
    # Сериализуется для корректного сопоставления permission/client_rpc ответов
    # с сессией через find_session_by_permission_request_id.
    # Очищается при старте нового prompt-turn (см. session_prompt).
    active_turn: ActiveTurnState | None = None
    # Отложенный response для prompt-turn (заполняется при cancel).
    pending_prompt_response: dict[str, Any] | None = None
    # Локальный счетчик для стабильной генерации toolCallId.
    tool_call_counter: int = 0
    # Реестр созданных tool calls и их состояний.
    tool_calls: dict[str, ToolCallState] = Field(default_factory=dict)
    # Набор доступных slash-команд для `available_commands_update`.
    available_commands: list[AvailableCommand | dict[str, Any]] = Field(default_factory=list)
    # Последний опубликованный план выполнения для `session/update: plan`.
    latest_plan: list[PlanStep | dict[str, Any]] = Field(default_factory=list)
    # Персистентные permission-решения по kind (например, allow_always).
    permission_policy: dict[str, str] = Field(default_factory=dict)
    # Идентификаторы permission-запросов, отмененных через `session/cancel`.
    # Нужны для детерминированного игнорирования поздних client-responses.
    cancelled_permission_requests: set[JsonRpcId] = Field(default_factory=set)
    # Идентификаторы agent->client RPC, отмененных через `session/cancel`.
    # Поздние ответы на такие запросы должны игнорироваться детерминированно.
    cancelled_client_rpc_requests: set[JsonRpcId] = Field(default_factory=set)
    # Runtime-capabilities клиента, зафиксированные для этой сессии.
    # Используется для фильтрации доступных tools согласно спецификации ACP:
    # "Clients and Agents MUST treat all capabilities omitted in the
    # initialize request as UNSUPPORTED"
    # Структура: {fs_read: bool, fs_write: bool, terminal: bool}
    runtime_capabilities: ClientRuntimeCapabilities | None = None
    # История событий: session/update, permission requests и т.д.
    # Используется для полного восстановления истории при перезагрузке сессии.
    events_history: list[dict[str, Any]] = Field(default_factory=list)

    # Multi-agent поддержка (spec: agent-config/spec.md)
    # Текущая активная стратегия выполнения сессии
    active_strategy: str = "single"
    # Список активных агентов в текущей сессии
    active_agents: list[str] = Field(default_factory=list)
    # Метрики сессии (время, токены, стоимость, успех задачи)
    session_metrics: SessionMetrics | None = None
    # Сквозной correlation_id для observability prompt turn
    correlation_id: str | None = None
    # ID родительской сессии (для child sessions в hierarchical/multi-orchestrated)
    parent_session_id: str | None = None
    # ID дочерних сессий (для orchestration/hierarchical)
    child_session_ids: list[str] = Field(default_factory=list)
    # Флаг child session (True если эта сессия создана другой сессией)
    is_child_session: bool = False
    # Результат делегирования от child session (HierarchicalStrategy)
    task_result: str | None = None
    # Суммаризированный ответ субагента (TokenSlicer output)
    sliced_summary: str | None = None

    @field_serializer("cancelled_permission_requests", "cancelled_client_rpc_requests")
    def serialize_set(self, value: set) -> list:
        """set не сериализуется в JSON напрямую — конвертируем в list."""
        return list(value)

    # Мутаторы permission-состояния. Одноимённы с `domain.Session` (write-фаза
    # pre-step D4-d, ADR-006): писатели зовут `session.<метод>()`, и на switch
    # резидента `SessionDocument → domain.Session` сайты не меняются — метод несёт
    # уже доменный объект. Инкапсулируют прямой доступ к полям (Tell-Don't-Ask).
    def set_permission_policy(self, kind: str, policy: str) -> None:
        """Установить персистентную permission-политику по kind."""
        self.permission_policy[kind] = policy

    def get_permission_policy(self, kind: str) -> str | None:
        """Персистентная permission-политика по kind (None — не запомнена)."""
        return self.permission_policy.get(kind)

    def cancel_permission_request(self, request_id: JsonRpcId) -> None:
        """Отметить permission-запрос отменённым (для игнорирования поздних ответов)."""
        self.cancelled_permission_requests.add(request_id)

    def uncancel_permission_request(self, request_id: JsonRpcId) -> None:
        """Снять отметку об отмене permission-запроса (идемпотентно)."""
        self.cancelled_permission_requests.discard(request_id)

    def is_permission_cancelled(self, request_id: JsonRpcId) -> bool:
        """Отмечен ли permission-запрос отменённым."""
        return request_id in self.cancelled_permission_requests

    def cancel_client_rpc_request(self, request_id: JsonRpcId) -> None:
        """Отметить agent->client RPC отменённым (для игнорирования поздних ответов)."""
        self.cancelled_client_rpc_requests.add(request_id)

    def uncancel_client_rpc_request(self, request_id: JsonRpcId) -> None:
        """Снять отметку об отмене agent->client RPC (идемпотентно)."""
        self.cancelled_client_rpc_requests.discard(request_id)

    def is_client_rpc_cancelled(self, request_id: JsonRpcId) -> bool:
        """Отмечен ли agent->client RPC отменённым."""
        return request_id in self.cancelled_client_rpc_requests

    def set_available_commands(
        self, commands: Sequence[AvailableCommand | dict[str, Any]]
    ) -> None:
        """Заменить набор доступных slash-команд."""
        self.available_commands = list(commands)

    def extend_available_commands(
        self, commands: Sequence[AvailableCommand | dict[str, Any]]
    ) -> None:
        """Добавить slash-команды к текущему набору."""
        self.available_commands.extend(commands)

    def set_config_value(self, key: str, value: str) -> None:
        """Установить значение config_values (persistent session-config)."""
        self.config_values[key] = value

    def get_config_value(self, key: str, default: str | None = None) -> str | None:
        """Значение config_values по ключу (persistent session-config)."""
        return self.config_values.get(key, default)

    # History-seam'ы (фаза B ADR-006). Одноимённы с `domain.Session`: форма записи
    # истории принадлежит носителю состояния, а не вызывающему — раньше
    # `StateManager` собирал сырой dict и знал раскладку слотов.
    def add_user_message(self, prompt: Sequence[Any]) -> None:
        """Добавить сообщение пользователя из ACP content blocks.

        `prompt` кладётся дословно: `HistoryMessage.content` допускает и строку,
        и список блоков, а копирование в список ломало нестандартный вход
        (строка распадалась на символы).
        """
        self.history.append(
            HistoryMessage(
                role="user",
                content=prompt if isinstance(prompt, str) else list(prompt),
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    def add_assistant_message(self, content: str | dict[str, Any]) -> None:
        """Добавить ответ ассистента.

        Строка идёт в плоский слот `text`, структурный контент — в `content`
        (та же роль-driven раскладка, что у `HistoryMapper`).
        """
        entry = HistoryMessage(role="assistant", timestamp=datetime.now(UTC).isoformat())
        if isinstance(content, str):
            entry.text = content
        else:
            # dict — одиночный ACP-блок, как в одноимённом доменном сейме.
            entry.content = [content]
        self.history.append(entry)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Добавить результат инструмента как ответ модели.

        Контракт LLM-API: за assistant-сообщением с `tool_calls` обязан следовать
        `role: tool` на каждый `tool_call_id`. Раньше форму этой записи знал только
        `ToolCallProcessor`, поэтому пути отмены её не писали и вызовы оставались
        без ответа (tech-debt P2-36/P2-38). `timestamp` не ставится: слот истории
        для tool-ответа его не несёт (ср. `HistoryMapper`).
        """
        self.history.append(
            HistoryMessage(role="tool", tool_call_id=tool_call_id, content=content)
        )

    def set_title(self, title: str) -> None:
        """Установить заголовок сессии."""
        self.title = title

    def mark_updated(self) -> None:
        """Отметить сессию изменённой сейчас (ACP `updatedAt`, UTC ISO 8601)."""
        self.updated_at = datetime.now(UTC).isoformat()

    @model_validator(mode="before")
    @classmethod
    def migrate_schema(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Автоматическая миграция старых файлов с данными.

        Шаги описаны таблицей, а не цепочкой ветвлений: цепочка росла с каждой
        версией и упёрлась в гейт сложности, а таблица делает добавление версии
        одной строкой и не даёт пропустить проставление `schema_version`.
        """
        if not isinstance(data, dict):
            return data

        for target_version, step in _SCHEMA_MIGRATIONS:
            if data.get("schema_version", 0) < target_version:
                step(data)
                data["schema_version"] = target_version

        # Normalize mode in config_values (backward compatibility)
        config_values = data.get("config_values", {})
        if "mode" in config_values:
            from ..domain.mode import normalize_mode

            old_mode = config_values["mode"]
            new_mode = normalize_mode(old_mode)
            if new_mode != old_mode:
                config_values["mode"] = new_mode

        return data


# Разрешаем forward references для Pydantic v2: `SessionDocument` ссылается на
# модели, объявленные ниже него в модуле.
SessionDocument.model_rebuild()

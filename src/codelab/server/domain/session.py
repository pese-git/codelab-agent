"""Domain models для Session агрегата.

Содержит aggregate root Session и value objects:
- SessionConfig
- ConversationHistory
- ToolCallRegistry
- PermissionState
- AgentPlan
- MultiAgentState
- TurnState (write-фаза, ADR-006)
- SessionRuntime (write-фаза, ADR-006)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from codelab.shared.capabilities import ClientCapabilities

from .conversation import ConversationMessage, MessageContent
from .plan import PlanEntry
from .tool_call import ToolCall, ToolResult
from .value_objects import (
    ALLOWED_TOOL_CALL_TRANSITIONS,
    FileLocation,
    MessageRole,
    PlanStatus,
    SessionId,
    ToolCallStatus,
)

logger = structlog.get_logger()


@dataclass(frozen=True)
class SessionConfig:
    """Конфигурация сессии."""

    cwd: str
    config_values: dict[str, str] = field(default_factory=dict)
    active_strategy: str = "single"
    runtime_capabilities: ClientCapabilities | None = None
    # MCP-серверы сессии (ACP session/new). Opaque-снимки конфигурации —
    # хранятся как plain dict, несутся round-trip без интерпретации.
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ConversationHistory:
    """История сообщений в сессии."""

    messages: list[ConversationMessage] = field(default_factory=list)

    def add(self, message: ConversationMessage) -> None:
        """Добавить сообщение в историю."""
        self.messages.append(message)

    def get_recent(self, n: int) -> list[ConversationMessage]:
        """Получить последние N сообщений."""
        return self.messages[-n:] if n > 0 else []

    def get_messages(self) -> list[ConversationMessage]:
        """Получить все сообщения."""
        return list(self.messages)


@dataclass
class ToolCallRegistry:
    """Реестр tool calls в сессии."""

    calls: dict[str, ToolCall] = field(default_factory=dict)
    counter: int = 0

    def create(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        title: str | None = None,
        kind: str = "other",
        tool_call_id_from_llm: str | None = None,
        locations: list[FileLocation] | None = None,
    ) -> ToolCall:
        """Создать новый tool call.

        Поверхность повторяет `ToolCallHandler.create_tool_call` (wire): `kind` —
        ключ permission-политики, `title` — display для replay,
        `tool_call_id_from_llm` — корреляция с историей LLM, `locations` — файлы
        для ACP. Без них доменный create не выражал создание из turn-пути
        (фаза B ADR-006). `arguments` служит и как ACP `rawInput` — маппер отдаёт
        его в `raw_input`, отдельного поля нет.
        """
        self.counter += 1
        tool_call_id = f"call_{self.counter:03d}"
        tool_call = ToolCall(
            id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            title=title,
            kind=kind,
            tool_call_id_from_llm=tool_call_id_from_llm,
            locations=list(locations) if locations else [],
        )
        self.calls[tool_call_id] = tool_call
        return tool_call

    def get(self, tool_call_id: str) -> ToolCall | None:
        """Получить tool call по ID."""
        return self.calls.get(tool_call_id)

    def update(self, tool_call_id: str, **kwargs: Any) -> None:
        """Обновить поля tool call на месте.

        Мутация вместо пересборки: пересборка перечисляла поля вручную и молча
        теряла всё не перечисленное (`kind`, `title`, `tool_call_id_from_llm`).
        Неизвестное имя поля — ошибка, а не тихий пропуск.
        """
        tool_call = self.calls.get(tool_call_id)
        if tool_call is None:
            return
        for name, value in kwargs.items():
            if not hasattr(tool_call, name):
                raise AttributeError(f"ToolCall has no field {name!r}")
            setattr(tool_call, name, value)

    def update_status(
        self,
        tool_call_id: str,
        status: ToolCallStatus,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Сменить статус tool call по матрице переходов.

        Парный сейм к wire-`ToolCallHandler.update_tool_call_status`; матрица одна
        (`ALLOWED_TOOL_CALL_TRANSITIONS`). Отказ логируется, а не пропускается
        молча: молчание однажды уже дало расхождение состояния с wire-историей.

        Returns:
            True, если статус изменён (или уже равен запрошенному).
        """
        tool_call = self.calls.get(tool_call_id)
        if tool_call is None:
            return False

        allowed = ALLOWED_TOOL_CALL_TRANSITIONS.get(tool_call.status, frozenset())
        if status not in allowed and status != tool_call.status:
            logger.warning(
                "tool_call_status_transition_rejected",
                tool_call_id=tool_call_id,
                current_status=tool_call.status.value,
                requested_status=ToolCallStatus(status).value,
            )
            return False

        tool_call.status = status
        if content is not None:
            # Контент результата живёт в `ToolResult`, поэтому его нельзя записать,
            # не сохранив остальные поля результата.
            previous = tool_call.result
            tool_call.result = ToolResult(
                locations=previous.locations if previous else list(tool_call.locations),
                raw_output=previous.raw_output if previous else dict(tool_call.raw_output),
                content=[dict(item) for item in content],
                result_content=previous.result_content if previous else [],
            )
        return True

    def get_all(self) -> list[ToolCall]:
        """Получить все tool calls."""
        return list(self.calls.values())


@dataclass
class PermissionState:
    """Состояние разрешений в сессии."""

    policy: dict[str, str] = field(default_factory=dict)
    # id — опаковый корреляционный токен; JSON-RPC допускает и строку, и число,
    # поэтому тип сохраняется как есть (ср. `TurnState.permission_request_id`).
    cancelled_requests: set[str | int] = field(default_factory=set)

    def is_allowed(self, kind: str) -> bool:
        """Проверить, разрешено ли действие."""
        return self.policy.get(kind) == "allow"

    def set_policy(self, kind: str, policy: str) -> None:
        """Установить политику для действия."""
        self.policy[kind] = policy

    def get_policy(self, kind: str) -> str | None:
        """Персистентная политика по kind (None — решение не запомнено)."""
        return self.policy.get(kind)

    def cancel_request(self, request_id: str | int) -> None:
        """Отменить запрос разрешения."""
        self.cancelled_requests.add(request_id)

    def uncancel_request(self, request_id: str | int) -> None:
        """Снять отметку об отмене запроса (идемпотентно)."""
        self.cancelled_requests.discard(request_id)

    def is_cancelled(self, request_id: str | int) -> bool:
        """Проверить, отменён ли запрос."""
        return request_id in self.cancelled_requests


@dataclass
class AgentPlan:
    """План выполнения агентом."""

    steps: list[PlanEntry] = field(default_factory=list)

    def add_step(self, step: PlanEntry) -> None:
        """Добавить шаг в план."""
        self.steps.append(step)

    def update_step(self, index: int, status: PlanStatus) -> None:
        """Обновить статус шага.

        Статус типизирован: прежняя строковая сигнатура молча откатывала
        нераспознанное значение к предыдущему, то есть write-операция могла
        ничего не сделать без единого признака (фаза B ADR-006). Выход за
        границы плана — ошибка вызывающего, а не допустимый no-op.
        """
        if not 0 <= index < len(self.steps):
            raise IndexError(f"plan step index out of range: {index} (steps={len(self.steps)})")
        old = self.steps[index]
        self.steps[index] = PlanEntry(
            content=old.content,
            priority=old.priority,
            status=status,
        )

    def get_steps(self) -> list[PlanEntry]:
        """Получить все шаги."""
        return list(self.steps)


@dataclass
class MultiAgentState:
    """Состояние мультиагентной сессии."""

    active_strategy: str = "single"
    active_agents: list[str] = field(default_factory=list)
    parent_session_id: str | None = None
    child_session_ids: list[str] = field(default_factory=list)
    is_child_session: bool = False
    # Результат делегирования и суммаризированный ответ субагента. В горячем пути
    # мёртвые; несутся как opaque для lossless round-trip и будущей миграции.
    task_result: str | None = None
    sliced_summary: str | None = None


@dataclass
class PendingExternalRequest:
    """Ожидаемый agent→client запрос внутри turn-а как доменный VO (фаза B ADR-006).

    Доменный аналог `protocol.state.PendingClientRequestState`: нужен для
    корреляции входящего ответа клиента с действием, которого turn ждёт
    (`fs_read`/`fs_write`/`terminal_create`). Раньше `TurnState` нёс это
    нетипизированным dict, из-за чего терялась статическая проверка на сайтах,
    читающих поля снимка.

    `request_id` — опаковый корреляционный токен: JSON-RPC допускает строку и
    число, поэтому тип сохраняется как есть (ср. `TurnState.permission_request_id`).
    Поля `terminal_*` наполняются из ответа клиента и несутся round-trip.
    """

    request_id: str | int
    kind: str
    tool_call_id: str
    path: str
    expected_new_text: str | None = None
    terminal_id: str | None = None
    terminal_output: str | None = None
    terminal_exit_code: int | None = None
    terminal_signal: str | None = None
    terminal_truncated: bool | None = None


@dataclass
class TurnState:
    """Состояние текущего prompt-turn как доменный VO (ADR-006, write-фаза).

    Переезжает из `protocol.state.ActiveTurnState`: это состояние сессии («где мы
    в turn-е»), а не wire-протокол. Идентификаторы — опаковые resume-токены
    (`str | int`).

    `session_id` обязателен, как и в wire-DTO: turn всегда принадлежит сессии.
    Значение должно совпадать с `Session.id` владельца — маппер отдаёт его в wire
    как есть, поэтому рассинхрон был бы виден снаружи.

    `phase` пока `str` (значения: running/waiting_permission/awaiting_permission/
    waiting_client_rpc/waiting_tool_completion/cancelled). Типизированный `TurnPhase`
    вводится на стадии b4/b8 (там же устраняется рассинхрон
    `waiting_permission`/`awaiting_permission`).
    """

    session_id: str
    prompt_request_id: str | int | None = None
    cancel_requested: bool = False
    permission_request_id: str | int | None = None
    permission_tool_call_id: str | None = None
    phase: str = "running"
    pending_external_request: PendingExternalRequest | None = None
    # Остаток батча tool_calls, ожидающий возобновления после permission (P2-40).
    pending_batch: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionRuntime:
    """Рантайм-состояние сессии как доменный VO (ADR-006, write-фаза).

    Переезжает из плоских runtime-полей `protocol.state.SessionState`
    (`terminals`, `events_history`, ...). Персистируемо (часть агрегата), кроме
    чисто transient `mcp_prompt_handlers` (`exclude=True`), который в домен НЕ
    переезжает и восстанавливается в `SessionRuntime`-компаньоне протокола.

    Опаковые снимки (`pending_prompt_response`, `session_metrics`) хранятся как
    plain dict — данные, не wire-семантика.
    """

    terminals: dict[str, str] = field(default_factory=dict)
    # Владелец реестра терминалов (P2-44): парное поле к `SessionState.terminals_owner`.
    terminals_owner: str | None = None
    terminal_counter: int = 0
    events_history: list[dict[str, Any]] = field(default_factory=list)
    cancelled_client_rpc_requests: set[str | int] = field(default_factory=set)
    pending_prompt_response: dict[str, Any] | None = None
    session_metrics: dict[str, Any] | None = None
    correlation_id: str | None = None


@dataclass
class Session:
    """Aggregate root для сессии.

    Инкапсулирует всю бизнес-логику сессии и координирует
    изменения в value objects.
    """

    id: SessionId
    config: SessionConfig
    history: ConversationHistory = field(default_factory=ConversationHistory)
    tool_calls: ToolCallRegistry = field(default_factory=ToolCallRegistry)
    permissions: PermissionState = field(default_factory=PermissionState)
    plan: AgentPlan = field(default_factory=AgentPlan)
    multi_agent: MultiAgentState = field(default_factory=MultiAgentState)
    active_turn: TurnState | None = None
    runtime: SessionRuntime = field(default_factory=SessionRuntime)
    # Storage-мета. Несётся round-trip как есть; `updated_at` НЕ регенерируется
    # при пересборке (регенерация = ложная «last activity», см. ACP updatedAt).
    # `available_commands` — wire-DTO, но нужен для lossless пересборки SessionState.
    title: str | None = None
    updated_at: str | None = None
    schema_version: int = 8
    # Ревизия документа (ADR-007): парное поле к `SessionState.revision`, несётся
    # round-trip как есть — инкрементирует её хранилище при записи.
    revision: int = 0
    available_commands: list[dict[str, Any]] = field(default_factory=list)

    def add_message(self, message: ConversationMessage) -> None:
        """Добавить сообщение в историю."""
        self.history.add(message)

    # History-seam'ы (фаза B ADR-006). Одноимённы с `SessionState`: писатель зовёт
    # `session.<метод>()` и при switch резидента не меняется. Форма записи истории
    # перестаёт быть известна вызывающему — раньше `StateManager` собирал сырой dict.
    def add_user_message(self, prompt: Sequence[Any]) -> None:
        """Добавить сообщение пользователя из ACP content blocks.

        Строка вместо списка блоков — нестандартный, но допустимый вход
        (`HistoryMessage.content` его принимает): она трактуется как текст,
        иначе разбор блоков распустил бы её на символы.
        """
        content = (
            MessageContent.from_text(prompt)
            if isinstance(prompt, str)
            else MessageContent.from_acp_blocks(prompt)
        )
        self.history.add(
            ConversationMessage(
                role=MessageRole.USER,
                content=content,
                timestamp=datetime.now(UTC),
            )
        )

    def add_assistant_message(self, content: str | dict[str, Any]) -> None:
        """Добавить ответ ассистента.

        Прод передаёт только строку; dict принимается как одиночный ACP-блок —
        поверхность сохранена одноимённой с wire-сеймом.
        """
        message_content = (
            MessageContent.from_text(content)
            if isinstance(content, str)
            else MessageContent.from_acp_blocks([content])
        )
        self.history.add(
            ConversationMessage(
                role=MessageRole.ASSISTANT,
                content=message_content,
                timestamp=datetime.now(UTC),
            )
        )

    def create_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        """Создать новый tool call."""
        return self.tool_calls.create(tool_name, arguments)

    def update_tool_call(self, tool_call_id: str, **kwargs: Any) -> None:
        """Обновить tool call."""
        self.tool_calls.update(tool_call_id, **kwargs)

    def set_permission_policy(self, kind: str, policy: str) -> None:
        """Установить политику разрешений."""
        self.permissions.set_policy(kind, policy)

    def get_permission_policy(self, kind: str) -> str | None:
        """Персистентная permission-политика по kind (None — не запомнена)."""
        return self.permissions.get_policy(kind)

    def cancel_permission_request(self, request_id: str | int) -> None:
        """Отметить permission-запрос отменённым (для игнорирования поздних ответов)."""
        self.permissions.cancel_request(request_id)

    def uncancel_permission_request(self, request_id: str | int) -> None:
        """Снять отметку об отмене permission-запроса (идемпотентно)."""
        self.permissions.uncancel_request(request_id)

    def is_permission_cancelled(self, request_id: str | int) -> bool:
        """Отмечен ли permission-запрос отменённым."""
        return self.permissions.is_cancelled(request_id)

    # Отмена agent->client RPC. Логика на агрегате, а не на `SessionRuntime`:
    # тот — набор опаковых рантайм-снимков, поведения он не несёт.
    def cancel_client_rpc_request(self, request_id: str | int) -> None:
        """Отметить agent->client RPC отменённым (для игнорирования поздних ответов)."""
        self.runtime.cancelled_client_rpc_requests.add(request_id)

    def uncancel_client_rpc_request(self, request_id: str | int) -> None:
        """Снять отметку об отмене agent->client RPC (идемпотентно)."""
        self.runtime.cancelled_client_rpc_requests.discard(request_id)

    def is_client_rpc_cancelled(self, request_id: str | int) -> bool:
        """Отмечен ли agent->client RPC отменённым."""
        return request_id in self.runtime.cancelled_client_rpc_requests

    # Жизненный цикл turn'а. Парные сеймы к `TurnLifecycleManager` (wire): дом
    # этих операций — агрегат, потому что они меняют только состояние turn'а.
    def mark_turn_cancel_requested(self) -> bool:
        """Отметить активный turn как запрошенный к отмене.

        Returns:
            False, если активного turn'а нет (отмечать нечего).
        """
        if self.active_turn is None:
            return False
        self.active_turn.cancel_requested = True
        return True

    def clear_active_turn(self) -> None:
        """Снять активный turn (идемпотентно)."""
        self.active_turn = None

    def answer_deferred_batch(self, *, reason: str) -> int:
        """Ответить модели на вызовы, отложенные в `active_turn.pending_batch`.

        Парный сейм к `prompt.turn_state.answer_deferred_batch`. Хвост батча ждёт
        возобновления после permission (P2-40); если turn обрывается, эти вызовы
        не выполнятся никогда, а их id уже лежат в assistant-сообщении истории.
        Без ответа они остаются без `role: tool`, и модель повторяет их (P2-38).

        Returns:
            Число отвеченных вызовов.
        """
        active_turn = self.active_turn
        if active_turn is None or not active_turn.pending_batch:
            return 0

        answered = 0
        for call in active_turn.pending_batch:
            tool_call_id = call.get("id")
            if not tool_call_id:
                continue
            self.add_tool_result(
                tool_call_id,
                f"Вызов не выполнялся: {reason}. Запроси его снова, если он всё ещё нужен.",
            )
            answered += 1

        active_turn.pending_batch = []
        if answered:
            logger.info(
                "deferred_tool_calls_answered_on_turn_end",
                session_id=str(self.id),
                count=answered,
                reason=reason,
            )
        return answered

    def set_available_commands(self, commands: Sequence[dict[str, Any]]) -> None:
        """Заменить набор доступных slash-команд (available_commands — opaque wire-DTO)."""
        self.available_commands = list(commands)

    def extend_available_commands(self, commands: Sequence[dict[str, Any]]) -> None:
        """Добавить slash-команды к текущему набору."""
        self.available_commands.extend(commands)

    def set_config_value(self, key: str, value: str) -> None:
        """Установить значение config_values (persistent session-config)."""
        self.config.config_values[key] = value

    def get_config_value(self, key: str, default: str | None = None) -> str | None:
        """Значение config_values по ключу (persistent session-config)."""
        return self.config.config_values.get(key, default)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Добавить результат инструмента как ответ модели.

        Парный сейм к `SessionState.add_tool_result`: контракт LLM-API требует
        `role: tool` на каждый `tool_call_id` из assistant-сообщения. `timestamp`
        не синтезируется — у tool-ответа его нет и в wire-форме.
        """
        self.history.add(
            ConversationMessage(
                role=MessageRole.TOOL,
                content=MessageContent.from_text(content),
                tool_call_id=tool_call_id,
            )
        )

    def set_title(self, title: str) -> None:
        """Установить заголовок сессии."""
        self.title = title

    def mark_updated(self) -> None:
        """Отметить сессию изменённой сейчас (ACP `updatedAt`, UTC ISO 8601).

        Явная мутация; НЕ путать с round-trip-переносом `updated_at` как есть
        (см. комментарий к полю — при пересборке метка не регенерируется).
        """
        self.updated_at = datetime.now(UTC).isoformat()

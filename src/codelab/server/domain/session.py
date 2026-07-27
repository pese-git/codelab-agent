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

from codelab.shared.capabilities import ClientCapabilities

from .conversation import ConversationMessage
from .plan import PlanEntry
from .tool_call import ToolCall
from .value_objects import SessionId


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

    def create(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        """Создать новый tool call."""
        self.counter += 1
        tool_call_id = f"call_{self.counter:03d}"
        tool_call = ToolCall(
            id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        self.calls[tool_call_id] = tool_call
        return tool_call

    def get(self, tool_call_id: str) -> ToolCall | None:
        """Получить tool call по ID."""
        return self.calls.get(tool_call_id)

    def update(self, tool_call_id: str, **kwargs: Any) -> None:
        """Обновить tool call."""
        if tool_call_id in self.calls:
            old = self.calls[tool_call_id]
            self.calls[tool_call_id] = ToolCall(
                id=old.id,
                tool_name=old.tool_name,
                arguments=old.arguments,
                status=kwargs.get("status", old.status),
                result=kwargs.get("result", old.result),
                locations=kwargs.get("locations", old.locations),
                raw_output=kwargs.get("raw_output", old.raw_output),
            )

    def get_all(self) -> list[ToolCall]:
        """Получить все tool calls."""
        return list(self.calls.values())


@dataclass
class PermissionState:
    """Состояние разрешений в сессии."""

    policy: dict[str, str] = field(default_factory=dict)
    cancelled_requests: set[str] = field(default_factory=set)

    def is_allowed(self, kind: str) -> bool:
        """Проверить, разрешено ли действие."""
        return self.policy.get(kind) == "allow"

    def set_policy(self, kind: str, policy: str) -> None:
        """Установить политику для действия."""
        self.policy[kind] = policy

    def cancel_request(self, request_id: str) -> None:
        """Отменить запрос разрешения."""
        self.cancelled_requests.add(request_id)

    def uncancel_request(self, request_id: str) -> None:
        """Снять отметку об отмене запроса (идемпотентно)."""
        self.cancelled_requests.discard(request_id)

    def is_cancelled(self, request_id: str) -> bool:
        """Проверить, отменён ли запрос."""
        return request_id in self.cancelled_requests


@dataclass
class AgentPlan:
    """План выполнения агентом."""

    steps: list[PlanEntry] = field(default_factory=list)

    def add_step(self, step: PlanEntry) -> None:
        """Добавить шаг в план."""
        self.steps.append(step)

    def update_step(self, index: int, status: str) -> None:
        """Обновить статус шага."""
        if 0 <= index < len(self.steps):
            old = self.steps[index]
            from .value_objects import PlanStatus

            try:
                new_status = PlanStatus(status)
            except ValueError:
                new_status = old.status
            self.steps[index] = PlanEntry(
                content=old.content,
                priority=old.priority,
                status=new_status,
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
class TurnState:
    """Состояние текущего prompt-turn как доменный VO (ADR-006, write-фаза).

    Переезжает из `protocol.state.ActiveTurnState`: это состояние сессии («где мы
    в turn-е»), а не wire-протокол. Идентификаторы — опаковые resume-токены
    (`str | int`); `pending_external_request` — опаковый снимок ожидаемого
    agent→client запроса (данные, не wire-семантика — см. ADR-006).

    `phase` пока `str` (значения: running/waiting_permission/awaiting_permission/
    waiting_client_rpc/waiting_tool_completion/cancelled). Типизированный `TurnPhase`
    вводится на стадии b4/b8 (там же устраняется рассинхрон
    `waiting_permission`/`awaiting_permission`).
    """

    prompt_request_id: str | int | None = None
    cancel_requested: bool = False
    permission_request_id: str | int | None = None
    permission_tool_call_id: str | None = None
    phase: str = "running"
    pending_external_request: dict[str, Any] | None = None


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
    schema_version: int = 6
    available_commands: list[dict[str, Any]] = field(default_factory=list)

    def add_message(self, message: ConversationMessage) -> None:
        """Добавить сообщение в историю."""
        self.history.add(message)

    def create_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> ToolCall:
        """Создать новый tool call."""
        return self.tool_calls.create(tool_name, arguments)

    def update_tool_call(self, tool_call_id: str, **kwargs: Any) -> None:
        """Обновить tool call."""
        self.tool_calls.update(tool_call_id, **kwargs)

    def set_permission_policy(self, kind: str, policy: str) -> None:
        """Установить политику разрешений."""
        self.permissions.set_policy(kind, policy)

    def cancel_permission_request(self, request_id: str) -> None:
        """Отметить permission-запрос отменённым (для игнорирования поздних ответов)."""
        self.permissions.cancel_request(request_id)

    def uncancel_permission_request(self, request_id: str) -> None:
        """Снять отметку об отмене permission-запроса (идемпотентно)."""
        self.permissions.uncancel_request(request_id)

    def set_available_commands(self, commands: Sequence[dict[str, Any]]) -> None:
        """Заменить набор доступных slash-команд (available_commands — opaque wire-DTO)."""
        self.available_commands = list(commands)

    def extend_available_commands(self, commands: Sequence[dict[str, Any]]) -> None:
        """Добавить slash-команды к текущему набору."""
        self.available_commands.extend(commands)

    def set_config_value(self, key: str, value: str) -> None:
        """Установить значение config_values (persistent session-config)."""
        self.config.config_values[key] = value

    def set_title(self, title: str) -> None:
        """Установить заголовок сессии."""
        self.title = title

    def mark_updated(self) -> None:
        """Отметить сессию изменённой сейчас (ACP `updatedAt`, UTC ISO 8601).

        Явная мутация; НЕ путать с round-trip-переносом `updated_at` как есть
        (см. комментарий к полю — при пересборке метка не регенерируется).
        """
        self.updated_at = datetime.now(UTC).isoformat()

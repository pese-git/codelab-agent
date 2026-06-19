"""Domain models для Session агрегата.

Содержит aggregate root Session и value objects:
- SessionConfig
- ConversationHistory
- ToolCallRegistry
- PermissionState
- AgentPlan
- MultiAgentState
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codelab.client.domain.entities import ClientCapabilities

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

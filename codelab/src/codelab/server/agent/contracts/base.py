"""Базовые контракты для мультиагентной шины событий.

Определяет:
- DomainEvent — базовый frozen dataclass для всех событий
- TokenUsage, ToolCall — утилитарные контракты
- AgentRequest, AgentResponse, AgentResult — контракты запросов/ответов
- ContextBroadcast, ChoreographyAnswer — контракты broadcast
- AgentRegistered, AgentUnregistered, AgentListChanged — lifecycle events
- AgentBusError и производные — исключения шины
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from codelab.server.llm.models import LLMMessage
    from codelab.server.tools.base import ToolDefinition


# ─────────────────────────────────────────────
# Base event class
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class DomainEvent:
    """Базовый класс всех событий шины.

    Все события наследуют от этого класса для типобезопасной подписки.
    Автоматически проставляет timestamp при создании.
    """

    session_id: str = ""
    timestamp: float = field(default_factory=time.time)


# ─────────────────────────────────────────────
# Utility contracts
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class TokenUsage:
    """Информация об использовании токенов.

    Сохраняется из ответа LLM провайдера, не теряется при обработке.
    """

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ToolCall:
    """Контракт шины для вызова инструмента.

    Отличается от LLMToolCall из server/llm/models.py — это
    контракт шины, не LLM-специфичный. Используется в AgentResponse,
    AgentResult, ChoreographyAnswer, TaskResult.
    """

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────
# Request/Response contracts
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class AgentRequest(DomainEvent):
    """Запрос к агенту через шину.

    Содержит всё необходимое для вызова LLM:
    историю сообщений, доступные инструменты, correlation_id для tracing.
    """

    target_agent: str = ""
    messages: list[LLMMessage] = field(default_factory=list)
    tools: list[ToolDefinition] = field(default_factory=list)
    correlation_id: str = ""


@dataclass(frozen=True)
class AgentResult:
    """Результат вызова агента (возвращаемое значение Agent.call()).

    LLMAdapter возвращает AgentResult, EventBus оборачивает его
    в AgentResponse (DomainEvent) с добавлением request_id.
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0, 0))
    stop_reason: str = ""
    agent_name: str = ""
    error: str | None = None


@dataclass(frozen=True)
class AgentResponse(DomainEvent):
    """DomainEvent для EventBus — обёртка AgentResult с request_id.

    Это НЕ AgentResponse из server/agent/base.py (результт LLMAgent).
    Создаётся шиной при возврате из send_request().
    """

    request_id: str = ""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0, 0))
    stop_reason: str = ""
    agent_name: str = ""


# ─────────────────────────────────────────────
# Broadcast contracts
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class ContextBroadcast(DomainEvent):
    """Broadcast контекста всем зарегистрированным агентам.

    Рассылается стратегией для получения ответов от всех агентов
    в режиме choreography.
    """

    context: list[LLMMessage] = field(default_factory=list)
    available_agents: list[str] = field(default_factory=list)
    step: int = 0
    correlation_id: str = ""


@dataclass(frozen=True)
class ChoreographyAnswer(DomainEvent):
    """Ответ агента на broadcast.

    Содержит решение агента: принял ли действие, reasoning,
    статус выполнения.

    Attributes:
        agent_name: Имя агента, ответившего на broadcast
        action_taken: Флаг — агент принял действие
        reasoning: Объяснение решения агента
        output: Текстовый вывод агента
        status_signal: Сигнал статуса (continue/completed)
        usage: Информация об использовании токенов
        tool_calls: Вызовы инструментов, запрошенные агентом
            (для future conflict resolution и анализа)
    """

    agent_name: str = ""
    action_taken: bool = False
    reasoning: str = ""
    output: str | None = None
    status_signal: Literal["continue", "completed"] = "continue"
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0, 0))
    tool_calls: list[ToolCall] = field(default_factory=list)


# ─────────────────────────────────────────────
# Lifecycle events
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class AgentRegistered(DomainEvent):
    """Событие: агент зарегистрирован в шине."""

    agent_name: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    mode: str = ""


@dataclass(frozen=True)
class AgentUnregistered(DomainEvent):
    """Событие: агент удалён из шины."""

    agent_name: str = ""


@dataclass(frozen=True)
class AgentListChanged(DomainEvent):
    """Событие: список агентов изменился (пакетная операция)."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────


class AgentBusError(Exception):
    """Базовое исключение для ошибок шины."""


class AgentNotFoundError(AgentBusError):
    """Агент с указанным именем не зарегистрирован."""


class AgentDispatchError(AgentBusError):
    """Ошибка dispatch после всех retry попыток."""


class BroadcastPartialFailure(AgentBusError):
    """Частичная ошибка broadcast — некоторые агенты упали."""

    def __init__(self, message: str, failed_agents: list[str]) -> None:
        super().__init__(message)
        self.failed_agents = failed_agents

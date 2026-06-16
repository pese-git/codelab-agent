"""Pydantic модели для типизации данных ACP Server.

Предоставляет строго типизированные модели для замены dict[str, Any]
в истории сообщений, командах, планах агента и других структурах данных.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# Модели для истории сообщений (history)
class MessageContent(BaseModel):
    """Содержимое сообщения в истории."""

    type: str
    text: str | None = None
    # Дополнительные поля для разных типов контента
    data: dict[str, Any] | None = None


class HistoryMessage(BaseModel):
    """Сообщение в истории сессии."""

    model_config = ConfigDict(extra="allow")

    role: Literal["user", "assistant", "system"] = "user"
    content: list[MessageContent] | str | list[dict[str, Any]] | None = None
    text: str | None = None
    timestamp: str | None = None


# Модели для команд (available_commands)
# Соответствует спецификации ACP Protocol 14-Slash Commands
class AvailableCommandInput(BaseModel):
    """Спецификация ввода для slash-команды.

    Соответствует спецификации ACP Protocol 14-Slash Commands.
    Определяет подсказку для неструктурированного текстового ввода.

    Пример использования:
        input_spec = AvailableCommandInput(hint="query to search for")
    """

    hint: str
    """Подсказка для пользователя о формате ввода."""


class AvailableCommand(BaseModel):
    """Доступная slash-команда.

    Соответствует спецификации ACP Protocol 14-Slash Commands.
    Команды объявляются агентом и отображаются клиенту для автодополнения.

    Пример использования:
        cmd = AvailableCommand(
            name="web",
            description="Search the web for information",
            input=AvailableCommandInput(hint="query to search for")
        )
    """

    model_config = ConfigDict(extra="allow")

    name: str
    """Имя команды без слеша, например: 'status', 'web'."""

    description: str
    """Человекочитаемое описание команды."""

    input: AvailableCommandInput | None = None
    """Опциональная спецификация ввода для команды."""


# Модели для плана агента (latest_plan)
class PlanStep(BaseModel):
    """Шаг в плане агента."""

    model_config = ConfigDict(extra="allow")

    step_number: int | None = None
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    result: str | None = None


class AgentPlan(BaseModel):
    """План выполнения задачи агентом."""

    model_config = ConfigDict(extra="allow")

    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


# Модели для tool calls
class ToolCallParameter(BaseModel):
    """Параметр вызова инструмента."""

    name: str
    value: Any


class ToolCall(BaseModel):
    """Вызов инструмента агентом."""

    id: str
    name: str
    parameters: list[ToolCallParameter] = Field(default_factory=list)
    status: Literal["pending", "approved", "denied", "completed", "failed"] = "pending"
    result: Any = None
    error: str | None = None


# Модели для разрешений (permissions)
class Permission(BaseModel):
    """Разрешение на выполнение операции."""

    id: str
    type: Literal["tool_call", "file_access", "terminal_access"]
    resource: str
    action: str
    status: Literal["pending", "granted", "denied"] = "pending"
    requested_at: str
    resolved_at: str | None = None

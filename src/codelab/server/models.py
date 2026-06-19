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
    """ACP Protocol Model — контракт сообщения истории согласно ACP 05-Prompt Turn.

    Wire format для хранения истории сообщений в SessionState.

    НЕ является domain моделью. Для бизнес-логики использовать domain ConversationMessage.
    Конвертация через HistoryMapper.
    """

    model_config = ConfigDict(extra="allow")

    role: Literal["user", "assistant", "system"] = "user"
    content: list[MessageContent] | str | list[dict[str, Any]] | None = None
    text: str | None = None
    timestamp: str | None = None
    tool_call_id: str | None = None


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
    """ACP Protocol Model — контракт шага плана согласно ACP 11-Agent Plan.

    Wire format для хранения плана в SessionState и отправки в session/update.

    НЕ является domain моделью. Для бизнес-логики использовать domain PlanEntry.
    Конвертация через PlanMapper.
    """

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

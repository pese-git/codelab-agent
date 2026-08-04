"""Pydantic-модели для состояния протокола ACP.

Содержит все структуры данных для хранения состояния сессий,
tool calls, и других компонентов протокола.

Использует Pydantic BaseModel для встроенной сериализации/десериализации
вместо ручных методов _serialize_* / _deserialize_*.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.session import PendingExternalRequest
from ..messages import ACPMessage


class PromptDirectives(BaseModel):
    """Нормализованные флаги поведения prompt-turn из пользовательского ввода.

    Используются для детерминированной slash-driven оркестрации prompt-turn
    без legacy marker-триггеров.

    Пример использования:
        directives = PromptDirectives(request_tool=True, keep_tool_pending=False)
    """

    request_tool: bool = False
    keep_tool_pending: bool = False
    publish_plan: bool = False
    plan_entries: list[dict[str, str]] | None = None
    tool_kind: str = "other"
    fs_read_path: str | None = None
    fs_write_path: str | None = None
    fs_write_content: str | None = None
    terminal_command: str | None = None
    forced_stop_reason: str | None = None


class PreparedFsClientRequest(BaseModel):
    """Подготовленный пакет сообщений для fs/* agent->client запроса.

    Пример использования:
        prepared = PreparedFsClientRequest(messages=[...], pending_request=pending)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: str
    messages: list[ACPMessage]
    # Доменное состояние ожидания: носитель turn-пути — агрегат (ADR-006, фаза D
    # шаг 3), а этот пакет живёт только внутри запроса и на диск не уезжает.
    pending_request: PendingExternalRequest


class PendingToolExecution(BaseModel):
    """Информация о pending tool execution после permission approval.

    Используется для передачи информации от permission handler к http_server
    для выполнения реального tool через tool_registry.
    """

    session_id: str
    tool_call_id: str


class ToolResult(BaseModel):
    """Результат выполнения tool для передачи в LLM.

    Используется в LLM loop для сбора результатов выполнения tool calls
    и отправки их обратно в LLM для продолжения обработки.

    Пример использования:
        result = ToolResult(
            tool_call_id="call_abc123",
            tool_name="fs/read_text_file",
            success=True,
            output="File contents here...",
            content=[{"type": "terminal", "terminalId": "term_123"}],
        )
    """

    tool_call_id: str
    tool_name: str
    success: bool
    output: str | None = None
    error: str | None = None
    content: list[dict[str, Any]] | None = None


class LLMLoopResult(BaseModel):
    """Результат выполнения LLM loop.

    Содержит накопленные notifications, статус завершения и информацию
    о pending состояниях (permission, tool calls).

    Пример использования:
        result = LLMLoopResult(
            notifications=[...],
            stop_reason="end_turn",
            final_text="Here is the answer...",
        )
    """

    notifications: list[Any] = Field(default_factory=list)
    # Причина завершения: "end_turn", "cancelled", "max_turn_requests", None (deferred)
    stop_reason: str | None = None
    # Финальный текстовый ответ от LLM
    final_text: str | None = None
    # Флаг ожидания permission response
    pending_permission: bool = False
    # Оставшиеся tool calls для обработки после permission
    pending_tool_calls: list[Any] = Field(default_factory=list)
    # Накопленные ToolResult для передачи в следующую итерацию
    tool_results: list[ToolResult] = Field(default_factory=list)


class ProtocolOutcome(BaseModel):
    """Результат обработки входящего ACP-сообщения.

    Включает финальный response (если нужен) и список промежуточных
    notifications, которые транспорт должен отправить в указанном порядке.

    Пример использования:
        outcome = ProtocolOutcome(response=ACPMessage.response("id", {}))
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    response: ACPMessage | None = None
    notifications: list[ACPMessage] = Field(default_factory=list)
    # Дополнительные response-сообщения для отложенных JSON-RPC запросов (WS).
    followup_responses: list[ACPMessage] = Field(default_factory=list)
    # Информация о pending tool execution (если требуется асинхронное выполнение после permission).
    pending_tool_execution: PendingToolExecution | None = None

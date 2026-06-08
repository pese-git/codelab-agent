# Spec: agent-message-contracts

## ДОБАВЛЕННЫЕ Требования

### Требование: Базовый DomainEvent

Все контракты сообщений ДОЛЖНЫ наследоваться от базового класса `DomainEvent` для типобезопасной подписки.

`DomainEvent` ДОЛЖЕН быть frozen dataclass с полями:
- `timestamp: float` — время создания события
- `session_id: str` — ID сессии

### Требование: Контракт TokenUsage

Система ДОЛЖНА определять `TokenUsage` как frozen dataclass с полями:
- `input_tokens: int` — количество входных токенов
- `output_tokens: int` — количество выходных токенов
- `total_tokens: int` — общее количество токенов

> **Примечание:** Информация сохраняется из ответа LLM провайдера. Не теряется при обработке (было потеряно в NaiveAgent).

### Требование: Контракт ToolCall (для шины)

Система ДОЛЖНА определять `ToolCall` как frozen dataclass с полями:
- `id: str` — уникальный ID вызова
- `name: str` — имя инструмента
- `arguments: dict` — аргументы вызова

> **Примечание:** Это контракт шины событий, отличается от `LLMToolCall` из `server/llm/models.py`. Используется в `AgentResponse`, `AgentResult`, `ChoreographyAnswer`, `TaskResult`.

### Требование: Контракт AgentRequest

Система ДОЛЖНА определять `AgentRequest` как frozen dataclass (DomainEvent) с полями:
- `target_agent: str` — имя целевого агента
- `messages: list[LLMMessage]` — история сообщений для LLM
- `tools: list[ToolDefinition]` — доступные инструменты
- `correlation_id: str` — ID для tracing
- `session_id: str` — ID сессии

> **Примечание:** Использовать `LLMMessage` из `server/llm/models.py` и `ToolDefinition` из `server/tools/base.py`.

### Требование: Контракт AgentResponse (DomainEvent для EventBus)

Система ДОЛЖНА определять `AgentResponse` как frozen dataclass (DomainEvent) с полями:
- `request_id: str` — ID исходного запроса
- `text: str` — текстовый ответ
- `tool_calls: list[ToolCall]` — запрошенные tool calls
- `usage: TokenUsage` — информация о токенах
- `stop_reason: str` — причина остановки
- `agent_name: str` — имя агента

> **Важно:** Это НЕ `AgentResponse` из `server/agent/base.py`. Это DomainEvent для EventBus. `AgentResult` от LLMAdapter оборачивается в этот `AgentResponse` шиной при возврате из `send_request()`.

### Требование: Контракт AgentResult (возвращаемое значение Agent.call())

Система ДОЛЖНА определять `AgentResult` как frozen dataclass с полями:
- `text: str` — текстовый ответ
- `tool_calls: list[ToolCall]` — запрошенные tool calls
- `usage: TokenUsage` — информация о токенах
- `stop_reason: str` — "end_turn", "cancelled", "max_iterations", "tool_use"
- `agent_name: str` — имя агента
- `error: str | None = None`

> **Примечание:** Это возвращаемое значение `Agent.call()`. LLMAdapter возвращает `AgentResult`, EventBus оборачивает его в `AgentResponse` (DomainEvent) с добавлением `request_id`.

### Требование: Контракт ContextBroadcast

Система ДОЛЖНА определять `ContextBroadcast` как frozen dataclass (DomainEvent) с полями:
- `context: list[LLMMessage]` — контекст для всех агентов
- `available_agents: list[str]` — список доступных агентов
- `step: int` — шаг выполнения
- `correlation_id: str` — ID для tracing
- `session_id: str` — ID сессии

### Требование: Контракт ChoreographyAnswer

Система ДОЛЖНА определять `ChoreographyAnswer` как frozen dataclass (DomainEvent) с полями:
- `agent_name: str`
- `action_taken: bool`
- `reasoning: str`
- `output: str | None`
- `status_signal: Literal["continue", "completed"]`
- `usage: TokenUsage`

### Требование: Lifecycle events

Система ДОЛЖНА определять следующие DomainEvent для жизненного цикла агентов:

- `AgentRegistered`: `agent_name: str`, `capabilities: dict`, `mode: str`
- `AgentUnregistered`: `agent_name: str`
- `AgentListChanged`: `added: list[str]`, `removed: list[str]`

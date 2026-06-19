# Spec: agent-message-contracts

## Purpose

Domain contracts for agent message bus communication. Defines base events, tool call contracts, request/response models, and lifecycle events for multi-agent orchestration.
## Requirements
### Requirement: Базовый DomainEvent

Все контракты сообщений SHALL наследоваться от базового класса `DomainEvent` для типобезопасной подписки.

`DomainEvent` SHALL быть frozen dataclass с полями:
- `timestamp: float` — время создания события
- `session_id: str` — ID сессии

#### Scenario: Создание DomainEvent
- **WHEN** создается DomainEvent
- **THEN** объект содержит поля `timestamp` и `session_id`

### Requirement: Контракт TokenUsage

Система SHALL определять `TokenUsage` как frozen dataclass с полями:
- `input_tokens: int` — количество входных токенов
- `output_tokens: int` — количество выходных токенов
- `total_tokens: int` — общее количество токенов

> **Примечание:** Информация сохраняется из ответа LLM провайдера. Не теряется при обработке (было потеряно в NaiveAgent).

#### Scenario: Создание TokenUsage
- **WHEN** создается TokenUsage
- **THEN** объект содержит поля `input_tokens`, `output_tokens`, `total_tokens`

### Requirement: Контракт ToolCall (для шины)

Система SHALL определять `ToolCall` как frozen dataclass с полями:
- `id: str` — уникальный ID вызова
- `name: str` — имя инструмента
- `arguments: dict` — аргументы вызова

> **Примечание:** Это контракт шины событий, отличается от `LLMToolCall` из `server/llm/models.py`. Используется в `AgentResponse`, `AgentResult`, `ChoreographyAnswer`, `TaskResult`.

#### Scenario: Создание ToolCall для шины
- **WHEN** создается ToolCall для шины
- **THEN** объект содержит поля `id`, `name`, `arguments`

### Requirement: Контракт AgentRequest

Система SHALL определять `AgentRequest` как frozen dataclass (DomainEvent) с полями:
- `target_agent: str` — имя целевого агента
- `messages: list[LLMMessage]` — история сообщений для LLM
- `tools: list[ToolDefinition]` — доступные инструменты
- `correlation_id: str` — ID для tracing
- `session_id: str` — ID сессии

> **Примечание:** Использовать `LLMMessage` из `server/llm/models.py` и `ToolDefinition` из `server/tools/base.py`.

#### Scenario: Создание AgentRequest
- **WHEN** создается AgentRequest
- **THEN** объект содержит все поля для запроса к агенту

### Requirement: Контракт AgentResponse (DomainEvent для EventBus)

Система SHALL определять `AgentResponse` как frozen dataclass (DomainEvent) с полями:
- `request_id: str` — ID исходного запроса
- `text: str` — текстовый ответ
- `tool_calls: list[ToolCall]` — запрошенные tool calls
- `usage: TokenUsage` — информация о токенах
- `stop_reason: str` — причина остановки
- `agent_name: str` — имя агента

> **Важно:** Это НЕ `AgentResponse` из `server/agent/base.py`. Это DomainEvent для EventBus. `AgentResult` от LLMAdapter оборачивается в этот `AgentResponse` шиной при возврате из `send_request()`.

#### Scenario: Создание AgentResponse
- **WHEN** создается AgentResponse
- **THEN** объект содержит все поля ответа агента

### Requirement: Контракт AgentResult (возвращаемое значение Agent.call())

Система SHALL определять `AgentResult` как frozen dataclass с полями:
- `text: str` — текстовый ответ
- `tool_calls: list[ToolCall]` — запрошенные tool calls
- `usage: TokenUsage` — информация о токенах
- `stop_reason: str` — "end_turn", "cancelled", "max_iterations", "tool_use"
- `agent_name: str` — имя агента
- `error: str | None = None`

> **Примечание:** Это возвращаемое значение `Agent.call()`. LLMAdapter возвращает `AgentResult`, EventBus оборачивает его в `AgentResponse` (DomainEvent) с добавлением `request_id`.

#### Scenario: Создание AgentResult
- **WHEN** создается AgentResult
- **THEN** объект содержит все поля результата вызова агента

### Requirement: Контракт ContextBroadcast

Система SHALL определять `ContextBroadcast` как frozen dataclass (DomainEvent) с полями:
- `context: list[LLMMessage]` — контекст для всех агентов
- `available_agents: list[str]` — список доступных агентов
- `step: int` — шаг выполнения
- `correlation_id: str` — ID для tracing
- `session_id: str` — ID сессии

#### Scenario: Создание ContextBroadcast
- **WHEN** создается ContextBroadcast
- **THEN** объект содержит все поля для broadcast контекста

### Requirement: Контракт ChoreographyAnswer

Система SHALL определять `ChoreographyAnswer` как frozen dataclass (DomainEvent) с полями:
- `agent_name: str`
- `action_taken: bool`
- `reasoning: str`
- `output: str | None`
- `status_signal: Literal["continue", "completed"]`
- `usage: TokenUsage`

#### Scenario: Создание ChoreographyAnswer
- **WHEN** создается ChoreographyAnswer
- **THEN** объект содержит все поля ответа агента на broadcast

### Requirement: Lifecycle events

Система SHALL определять следующие DomainEvent для жизненного цикла агентов:

- `AgentRegistered`: `agent_name: str`, `capabilities: dict`, `mode: str`
- `AgentUnregistered`: `agent_name: str`
- `AgentListChanged`: `added: list[str]`, `removed: list[str]`

#### Scenario: Создание lifecycle events
- **WHEN** создаются lifecycle events
- **THEN** используются определенные DomainEvent классы

### Requirement: Устранение дублирования ToolCall

Система SHALL обновить контракты сообщений:
- Использовать domain `ToolCall` из `server/domain/tool_call.py`
- Удалить дублирующийся `ToolCall` из `server/agent/contracts/base.py`
- Все контракты используют единую domain модель

#### Scenario: Использование единой domain модели ToolCall
- **WHEN** контракты сообщений ссылаются на ToolCall
- **THEN** используется domain модель из `server/domain/tool_call.py`

#### Scenario: Удаление дублирующегося ToolCall
- **WHEN** код импортирует ToolCall
- **THEN** импорт происходит из `server/domain/tool_call.py`, а не из `server/agent/contracts/base.py`

### Requirement: AgentResponse с domain ToolCall

`AgentResponse` (DomainEvent для EventBus) SHALL использовать:
- `tool_calls: list[ToolCall]` — domain модель
- Вместо `list[LLMToolCall]` (LLM-specific)

#### Scenario: AgentResponse использует domain ToolCall
- **WHEN** создается AgentResponse
- **THEN** поле `tool_calls` имеет тип `list[ToolCall]` (domain модель)

### Requirement: AgentResult с domain ToolCall

`AgentResult` (возвращаемое значение Agent.call()) SHALL использовать:
- `tool_calls: list[ToolCall]` — domain модель
- Маппинг из `LLMToolCall` через `LLMResponseMapper`

#### Scenario: AgentResult использует domain ToolCall
- **WHEN** Agent.call() возвращает результат
- **THEN** поле `tool_calls` содержит domain модели ToolCall

#### Scenario: Маппинг LLMToolCall в ToolCall
- **WHEN** LLMAdapter получает LLMToolCall от провайдера
- **THEN** используется LLMResponseMapper для конвертации в domain ToolCall

### Requirement: LLMResponseMapper

Система SHALL предоставлять `LLMResponseMapper`:
- `to_domain(llm_calls: list[LLMToolCall]) -> list[ToolCall]` — конвертировать LLM в domain

#### Scenario: Конвертация LLM tool calls в domain
- **WHEN** вызывается `LLMResponseMapper.to_domain()` с LLM tool calls
- **THEN** возвращается список domain ToolCall объектов

### Requirement: Миграция контрактов

Система SHALL мигрировать все контракты:
- `AgentRequest` — использовать domain модели
- `AgentResponse` — использовать domain `ToolCall`
- `AgentResult` — использовать domain `ToolCall`
- `ContextBroadcast` — использовать domain модели
- `ChoreographyAnswer` — использовать domain модели

#### Scenario: Миграция AgentRequest
- **WHEN** используется AgentRequest
- **THEN** все поля используют domain модели

#### Scenario: Миграция AgentResponse и AgentResult
- **WHEN** используются AgentResponse или AgentResult
- **THEN** поле `tool_calls` содержит domain ToolCall объекты

#### Scenario: Миграция ContextBroadcast и ChoreographyAnswer
- **WHEN** используются ContextBroadcast или ChoreographyAnswer
- **THEN** все поля используют domain модели


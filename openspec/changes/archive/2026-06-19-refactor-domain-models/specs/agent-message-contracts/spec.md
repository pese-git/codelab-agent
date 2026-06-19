# Spec: agent-message-contracts (Delta)

## MODIFIED Requirements

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

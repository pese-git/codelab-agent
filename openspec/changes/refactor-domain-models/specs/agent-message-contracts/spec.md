# Spec: agent-message-contracts (Delta)

## MODIFIED Requirements

### Требование: Устранение дублирования ToolCall

Система ДОЛЖНА обновить контракты сообщений:
- Использовать domain `ToolCall` из `server/domain/tool_call.py`
- Удалить дублирующийся `ToolCall` из `server/agent/contracts/base.py`
- Все контракты используют единую domain модель

### Требование: AgentResponse с domain ToolCall

`AgentResponse` (DomainEvent для EventBus) ДОЛЖЕН использовать:
- `tool_calls: list[ToolCall]` — domain модель
- Вместо `list[LLMToolCall]` (LLM-specific)

### Требование: AgentResult с domain ToolCall

`AgentResult` (возвращаемое значение Agent.call()) ДОЛЖЕН использовать:
- `tool_calls: list[ToolCall]` — domain модель
- Маппинг из `LLMToolCall` через `LLMResponseMapper`

### Требование: LLMResponseMapper

Система ДОЛЖНА предоставлять `LLMResponseMapper`:
- `to_domain(llm_calls: list[LLMToolCall]) -> list[ToolCall]` — конвертировать LLM в domain

### Требование: Миграция контрактов

Система ДОЛЖНА мигрировать все контракты:
- `AgentRequest` — использовать domain модели
- `AgentResponse` — использовать domain `ToolCall`
- `AgentResult` — использовать domain `ToolCall`
- `ContextBroadcast` — использовать domain модели
- `ChoreographyAnswer` — использовать domain модели

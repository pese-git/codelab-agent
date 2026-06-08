## Why

Текущая архитектура CodeLab — Single-Agent система с монолитным `AgentOrchestrator` и `NaiveAgent`. Для поддержки специализированных агентов, параллельного выполнения и делегирования необходима шина межагентской коммуникации. AgentEventBus — фундамент мультиагентной архитектуры, через который проходит всё общение между агентами (принцип "EventBus-first").

## What Changes

- Введение `AgentEventBus` — in-memory шины с двумя интерфейсами:
  - `AbstractEventBus` (pub/sub) — для observability компонентов
  - `AgentRoutingInterface` (agent routing) — для стратегий выполнения
- Контракты сообщений: `AgentRequest`, `AgentResult`, `AgentResponse`, `ContextBroadcast`, `ChoreographyAnswer`
  - **Примечание:** `AgentResponse` из `server/agent/base.py` НЕ заменяется — используется текущей архитектурой как результат вызова агента
  - Новый `AgentResponse` в `contracts/` — DomainEvent для EventBus (обёртка `AgentResult` + `request_id`)
  - `AgentResult` — возвращаемое значение `Agent.call()` (text, tool_calls, usage: TokenUsage, stop_reason, agent_name)
  - `TokenUsage` — типизированная структура токенов (input, output, total)
  - `ToolCall` — контракт шины для tool calls (id, name, arguments)
- Lifecycle events: `AgentRegistered`, `AgentUnregistered`, `AgentListChanged`
- Point-to-point routing (`send_request`) и broadcast (`broadcast`)
- Подписка/отписка на события с гарантией параллельного вызова обработчиков
- Retry и error handling для dispatch

## Capabilities

### New Capabilities
- `agent-event-bus`: In-memory шина межагентской коммуникации с pub/sub и routing интерфейсами
- `agent-message-contracts`: Контракты запросов, ответов и lifecycle событий для мультиагентности
- `agent-lifecycle-events`: События регистрации/удаления агентов для динамической конфигурации

### Modified Capabilities

## Impact

**Новые файлы:**
- `codelab/src/codelab/server/agent/contracts/` — AgentRequest, AgentResult, AgentResponse, TokenUsage, ToolCall, DomainEvent, lifecycle events
- `codelab/src/codelab/server/agent/event_bus/` — AgentEventBus, AbstractEventBus, AgentRoutingInterface
- `codelab/tests/server/agent/test_event_bus.py` — тесты шины
- `codelab/tests/server/agent/test_contracts.py` — тесты контрактов

**Уже реализовано (переиспользуется):**
- `server/transport/stdio.py` — StdioServerTransport
- `server/transport/websocket.py` — WebSocketTransport
- `server/client_rpc/service.py` — ClientRPCService (Agent → Client)
- `server/protocol/handlers/pipeline/` — Pipeline Pattern
- `server/agent/plan_extractor.py` — PlanExtractor
- `server/tools/mapping.py` — acp_name_to_llm_name(), llm_name_to_acp_name()
- `server/llm/models.py` — LLMMessage, LLMToolCall, CompletionRequest, CompletionResponse
- `server/llm/base.py` — LLMProvider ABC
- `server/tools/base.py` — ToolDefinition, ToolRegistry

**Зависимости:** Никаких новых внешних зависимостей. Стандартная библиотека + asyncio.

**ACP boundary:** НЕ меняется. EventBus — внутренний компонент сервера, клиент не знает о мультиагентности.

```mermaid
sequenceDiagram
    participant Strategy as Strategy
    participant Bus as AgentEventBus
    participant Handler as Agent Handler
    participant Observer as Observer (Metrics/Timeline)

    Strategy->>Bus: register_agent("coder", handler)
    Observer->>Bus: subscribe(AgentRegistered, callback)
    Bus-->>Observer: publish AgentRegistered

    Strategy->>Bus: send_request(AgentRequest, parent_span)
    Bus->>Handler: forward request
    Handler-->>Bus: AgentResult
    Bus-->>Strategy: AgentResponse

    Strategy->>Bus: broadcast(ContextBroadcast)
    Bus->>Handler: forward to all agents
    Handler-->>Bus: ChoreographyAnswer
    Bus-->>Strategy: list[ChoreographyAnswer]
```

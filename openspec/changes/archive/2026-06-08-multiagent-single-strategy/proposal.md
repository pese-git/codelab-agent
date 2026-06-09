## Why

Базовая стратегия выполнения — SingleStrategy — необходима как первый working baseline мультиагентной архитектуры. Она вызывает единственного агента через EventBus, обеспечивает минимальную задержку и служит бенчмарком для сравнения с другими стратегиями. Также требуется замена монолитного `AgentOrchestrator` на композиционный `ExecutionEngine`.

## What Changes

- `SingleStrategy` — вызов агента через `EventBus.send_request()`, uniformity со всеми стратегиями
- `ExecutionEngine` — **замена** `AgentOrchestrator`, композиция компонентов:
  - `HistoryBuilder` — рефакторинг из `AgentOrchestrator._convert_to_llm_messages()`
  - `ToolFilter` — рефакторинг из `AgentOrchestrator._filter_tools_by_capabilities()` + поддержка MCP
  - `MessageSanitizer` — рефакторинг из `AgentOrchestrator._sanitize_orphaned_tool_calls()`
  - `PlanExtractor` — переиспользование существующего `server/agent/plan_extractor.py`
  - `ContextCompactor` — новый компонент (двухфазное сжатие: Prune + LLM Summarize)
- Интеграция с существующим `PromptOrchestrator` / Pipeline
- Управление контекстом: `context_window_limit`, `compaction_reserved_tokens`

## Capabilities

### New Capabilities
- `single-strategy`: Базовая стратегия выполнения через EventBus
- `execution-engine`: Композиционный движок выполнения (замена AgentOrchestrator)
- `context-compaction`: Двухфазное сжатие контекста (Prune + LLM Summarize)
- `history-builder`: Конвертация SessionState history → LLMMessage
- `tool-filter`: Фильтрация инструментов по client capabilities + MCP

### Modified Capabilities
- `codelab`: Замена AgentOrchestrator на ExecutionEngine в PromptOrchestrator pipeline

## Impact

**Новые файлы:**
- `codelab/src/codelab/server/protocol/handlers/strategies/single_strategy.py`
- `codelab/src/codelab/server/agent/execution_engine.py` — ExecutionEngine
- `codelab/src/codelab/server/agent/history_builder.py`
- `codelab/src/codelab/server/agent/tool_filter.py`
- `codelab/src/codelab/server/agent/message_sanitizer.py`
- `codelab/src/codelab/server/agent/context_compactor.py` — ContextCompactor
- `codelab/tests/server/strategies/test_single_strategy.py`
- `codelab/tests/server/agent/test_execution_engine.py`
- `codelab/tests/server/agent/test_context_compactor.py`

**Переиспользуемые файлы (без изменений):**
- `codelab/src/codelab/server/agent/plan_extractor.py` — PlanExtractor
- `codelab/src/codelab/server/tools/mapping.py` — acp_name_to_llm_name()
- `codelab/src/codelab/server/transport/stdio.py` — StdioServerTransport
- `codelab/src/codelab/server/transport/websocket.py` — WebSocketTransport
- `codelab/src/codelab/server/client_rpc/service.py` — ClientRPCService
- `codelab/src/codelab/server/protocol/handlers/pipeline/` — Pipeline Pattern
- `codelab/src/codelab/server/protocol/handlers/directive_resolver.py` — DirectiveResolver
- `codelab/src/codelab/server/protocol/handlers/replay_manager.py` — ReplayManager

**Удаляемые файлы (после миграции):**
- `codelab/src/codelab/server/agent/orchestrator.py` — AgentOrchestrator (заменяется ExecutionEngine)

**Изменяемые файлы:**
- `codelab/src/codelab/server/protocol/handlers/prompt_orchestrator.py` — интеграция ExecutionEngine + SingleStrategy
- `codelab/src/codelab/server/protocol/handlers/pipeline/stages/llm_loop.py` — замена AgentOrchestrator на ExecutionEngine

**Зависимости:** Зависит от `multiagent-event-bus`, `multiagent-llm-adapter`, `multiagent-agent-registry`.

```mermaid
sequenceDiagram
    participant Client as Client (ACP)
    participant Pipeline as PromptOrchestrator
    participant Engine as ExecutionEngine
    participant Strategy as SingleStrategy
    participant EventBus as AgentEventBus
    participant LLM as LLMAdapter

    Client->>Pipeline: session/prompt
    Pipeline->>Engine: build_context(session, prompt, mcp_manager)
    Engine->>Engine: HistoryBuilder + ToolFilter + MessageSanitizer
    Engine->>Strategy: execute(context)
    Strategy->>EventBus: send_request(AgentRequest, parent_span)
    EventBus->>LLM: forward to registered agent
    LLM-->>EventBus: AgentResult
    EventBus-->>Strategy: AgentResponse
    Strategy->>Engine: ensure_context_fits (compaction if needed)
    Engine-->>Pipeline: result
    Pipeline-->>Client: session/update + response
```

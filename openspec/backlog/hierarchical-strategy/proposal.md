## Why

Мультиагентная система требует стратегию HierarchicalStrategy — иерархическое делегирование Primary→Subagent с child sessions, task permissions и навигацией в TUI. Аналогично подходу OpenCode.

Без этой стратегии невозможно делегирование с сохранением полного контекста субагента и навигацией по деталям работы.

## What Changes

### Новые компоненты

- **TaskInvocation** — доменное событие делегирования (конвертируется в AgentRequest)
- **TaskResult** — доменный результат делегирования (строится из AgentResponse)
- **TaskPermissions** — проверка может ли caller вызывать target agent
- **HierarchicalStrategy** — стратегия выполнения с Primary LLM + Task tool + child sessions

### Интеграция

- Валидация через AgentRegistry: требует ≥1 primary + ≥1 subagent
- Task permissions: allow/deny/ask через session/request_permission
- Cascade cancellation: primary → child sessions → sub-agents
- MCP Manager propagation в child sessions

## Capabilities

### New Capabilities
- `task-invocation`: Доменное событие делегирования → AgentRequest
- `task-result`: Доменный результат → строится из AgentResponse
- `task-permissions`: Контроль каких субагентов агент может вызывать
- `hierarchical-strategy`: Primary→Subagent делегирование с child sessions
- `cascade-cancellation`: Каскадная отмена primary → child → sub-agent

### Modified Capabilities
- `strategy-dispatcher`: Валидация HierarchicalStrategy через AgentRegistry
- `agent-registry`: Добавлен mode=primary
- `session-state`: Поля для иерархии сессий

## Impact

**Новые файлы:**
- `src/codelab/server/agent/strategies/models.py` — TaskInvocation, TaskResult
- `src/codelab/server/agent/strategies/task_permissions.py` — TaskPermissions
- `src/codelab/server/agent/strategies/hierarchical.py` — HierarchicalStrategy

**Изменяемые файлы:**
- `src/codelab/server/agent/strategies/descriptor.py` — HIERARCHICAL_STRATEGY_DESCRIPTOR
- `src/codelab/server/protocol/handlers/permissions.py` — task permissions resolution
- `src/codelab/server/agent/strategies/mcp_context.py` — MCP propagation в child sessions

**Зависимости:** Зависит от event-bus, llm-adapter, agent-registry, observability, orchestrated-strategy (TokenSlicer, SubAgentCoordinator).

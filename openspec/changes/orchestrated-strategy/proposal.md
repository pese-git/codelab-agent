## Why

Мультиагентная система требует стратегию OrchestratedStrategy — централизованное управление через агент-оркестратор, который принимает решения о маршрутизации (RouteDecision через Structured Outputs), вызывает субагентов через EventBus, суммаризирует их ответы (TokenSlicer) и создаёт child sessions для навигации.

Без этой стратегии невозможны сложные последовательные задачи с разделением ролей (coder + tester + reviewer).

## What Changes

### Новые компоненты

- **RouteDecision** — Pydantic модель для Structured Outputs (reasoning, target_agent, task_payload)
- **TokenSlicer** — суммаризация ответов субагентов через дешёвую LLM модель, skip threshold, fallback truncate
- **SubAgentCoordinator** — координатор: TokenSlicer + Child Sessions (ContextCompactor убран — покрывается FCM)
- **OrchestratedStrategy** — стратегия выполнения с циклом route→execute→slice→next

### Интеграция

- Валидация через AgentRegistry: требует ≥1 orchestrator + ≥1 subagent
- max_steps предохранитель (default 7)
- Race condition guard: проверка available_agents перед каждым шагом
- Child sessions: создание, связывание parent↔child, storage
- MCP tools доступны субагентам через shared MCPManager

## Capabilities

### New Capabilities
- `route-decision`: Structured Outputs для маршрутизации (Pydantic model)
- `token-slicer`: Суммаризация ответов субагентов, skip threshold, fallback
- `sub-agent-coordinator`: TokenSlicer + Child Sessions (без ContextCompactor — FCM покрывает)
- `orchestrated-strategy`: Цикл route→execute→slice→next с max_steps
- `child-sessions`: Создание и связывание дочерних сессий

### Modified Capabilities
- `strategy-dispatcher`: Валидация OrchestratedStrategy через AgentRegistry
- `agent-registry`: Добавлен mode=orchestrator

## Impact

**Новые файлы:**
- `src/codelab/server/agent/strategies/models.py` — RouteDecision
- `src/codelab/server/agent/strategies/token_slicer.py` — TokenSlicer
- `src/codelab/server/agent/strategies/sub_agent_coordinator.py` — SubAgentCoordinator
- `src/codelab/server/agent/strategies/orchestrated.py` — OrchestratedStrategy

**Изменяемые файлы:**
- `src/codelab/server/agent/strategies/descriptor.py` — ORCHESTRATED_STRATEGY_DESCRIPTOR
- `src/codelab/server/agent/config/models.py` — mode=orchestrator валидация
- `src/codelab/server/di.py` — провайдеры для новых компонентов

**Зависимости:** Зависит от event-bus, llm-adapter, agent-registry, observability, single-strategy, strategy-dispatcher.

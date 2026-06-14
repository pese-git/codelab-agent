## Why

Мультиагентная система требует стратегию ChoreographyStrategy — децентрализованное взаимодействие через broadcast всем агентам параллельно, Conflict Resolution через Priority Queue, и создание child session только для winner-агента.

Без этой стратегии невозможен параллельный анализ и исследование задачи несколькими агентами одновременно.

## What Changes

### Новые компоненты

- **ContextBroadcast** — доменное событие broadcast (context, available_agents, step)
- **ChoreographyAnswer** — ответ агента (action_taken, reasoning, output, status_signal)
- **Conflict Resolution** — Priority Queue из agent config (priority, меньше = важнее)
- **ChoreographyStrategy** — стратегия выполнения с broadcast → parallel → conflict resolution

### Интеграция

- Валидация через AgentRegistry: требует ≥2 subagents
- max_steps предохранитель (default 7)
- Child session только для winner-агента (1 вместо N)
- Проигравшие агенты записываются в EventTimeline для debug mode

## Capabilities

### New Capabilities
- `context-broadcast`: Broadcast всем агентам параллельно
- `choreography-answer`: Ответ агента с action_taken, reasoning, status_signal
- `conflict-resolution`: Priority Queue для выбора winner
- `choreography-strategy`: Broadcast → parallel → conflict resolution → winner
- `winner-child-session`: Child session только для winner-агента

### Modified Capabilities
- `strategy-dispatcher`: Валидация ChoreographyStrategy через AgentRegistry
- `event-bus`: broadcast() → list[ChoreographyAnswer]

## Impact

**Новые файлы:**
- `codelab/src/codelab/server/agent/strategies/models.py` — ContextBroadcast, ChoreographyAnswer
- `codelab/src/codelab/server/agent/strategies/choreography.py` — ChoreographyStrategy

**Изменяемые файлы:**
- `codelab/src/codelab/server/agent/strategies/descriptor.py` — CHOREOGRAPHY_STRATEGY_DESCRIPTOR
- `codelab/src/codelab/server/agent/event_bus/bus.py` — broadcast() implementation

**Зависимости:** Зависит от event-bus, llm-adapter, agent-registry, observability.

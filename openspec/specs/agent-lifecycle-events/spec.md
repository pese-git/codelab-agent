# Spec: agent-lifecycle-events

## ДОБАВЛЕННЫЕ Требования

### Требование: Событие AgentRegistered

Система ДОЛЖНА определять `AgentRegistered` как frozen dataclass с полями:
- `agent_name: str`
- `capabilities: dict`

Это событие ДОЛЖНО публиковаться при регистрации нового агента в EventBus.

### Требование: Событие AgentUnregistered

Система ДОЛЖНА определять `AgentUnregistered` как frozen dataclass с полями:
- `agent_name: str`

Это событие ДОЛЖНО публиковаться при удалении агента из EventBus.

### Требование: Событие AgentListChanged

Система ДОЛЖНА определять `AgentListChanged` как frozen dataclass с полями:
- `added: list[str]`
- `removed: list[str]`

Это событие ДОЛЖНО публиковаться после пакетных операций регистрации/удаления.

### Требование: Публикация событий

Все события жизненного цикла ДОЛЖНЫ публиковаться через метод `AbstractEventBus.publish()`, позволяя наблюдателям (MetricsTracker, EventTimeline, StrategyDispatcher) подписываться и реагировать.

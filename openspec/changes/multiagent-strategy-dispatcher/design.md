## Design

### Архитектура StrategyDispatcher

StrategyDispatcher выбирает стратегию выполнения по приоритету и валидирует доступность через AgentRegistry.

### Priority Chain

```
1. context.meta["routing_mode"]     — slash command override
2. config_values["_routing_mode"]   — persistent config option
3. "single"                         — default fallback
```

### Validation Matrix

| Стратегия | Требуется | При fail → |
|---|---|---|
| Single | Любой агент | — (всегда доступно) |
| Orchestrated | ≥1 orchestrator + ≥1 subagent | fallback_mode |
| Choreography | ≥2 subagents | fallback_mode |
| Hierarchical | ≥1 primary + ≥1 subagent | fallback_mode |

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Slash command override | Быстрое переключение без изменения config |
| Persistent config option | Сохранение режима между turn'ами |
| Fallback с уведомлением | Пользователь знает что произошло |
| Валидация через Registry | Единый источник truth об агентах |

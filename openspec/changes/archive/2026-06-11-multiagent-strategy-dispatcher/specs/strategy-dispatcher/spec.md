# Spec: strategy-dispatcher

## ДОБАВЛЕННЫЕ Требования

### Требование: Выбор StrategyDispatcher

Система ДОЛЖНА предоставлять `StrategyDispatcher`, который выбирает стратегию выполнения по приоритету:
1. `context.meta["active_strategy"]` — override slash командой (высший приоритет)
2. `config_values["_active_strategy"]` — постоянная конфигурация сессии
3. `default_strategy` — fallback по умолчанию из серверной конфигурации

StrategyDispatcher ДОЛЖЕН использовать `StrategyRegistry` для получения списка доступных стратегий.

### Требование: Валидация стратегии через Registry

StrategyDispatcher ДОЛЖЕН валидировать доступность стратегии через `StrategyRegistry.get_available(agent_registry)`:
- `single`: всегда доступно (validator возвращает True)
- `multi_orchestrated`: требует ≥1 агент с mode=orchestrator И ≥1 с mode=subagent
- `multi_choreographed`: требует ≥2 агента с mode=subagent
- `hierarchical`: требует ≥1 агент с mode=primary И ≥1 с mode=subagent

### Требование: Поведение Fallback

Когда выбранная стратегия недоступна, StrategyDispatcher ДОЛЖЕН:
- Переключиться на `fallback_strategy` (по умолчанию: "single")
- Если fallback тоже недоступен — выбрать первую доступную стратегию
- Вернуть кортеж `(strategy_name, fallback_from | None)` где `fallback_from` — имя запрошенной но недоступной стратегии

### Требование: Создание экземпляра стратегии

StrategyDispatcher ДОЛЖЕН создавать экземпляр стратегии через `StrategyRegistry.create_instance(name, deps)`:
- Использовать `StrategyDependencies` для передачи зависимостей
- Возвращать `LLMCallStrategy | None`

### Требование: Fallback Notification

При переключении на другую стратегию система ДОЛЖНА уведомить пользователя через уведомление `session/update`:

```json
{
  "sessionUpdate": "agent_message_chunk",
  "content": {
    "type": "text",
    "text": "[system] Strategy 'multi_orchestrated' unavailable (no orchestrator). Falling back to 'single'."
  }
}
```

### Требование: Логирование Fallback

Система ДОЛЖНА записать warning с:
- Запрошенная стратегия
- Причина недоступности
- Фактический fallback режим

# Spec: strategy-validation

## ДОБАВЛЕННЫЕ Требования

### Требование: Проверка совместимости mode

StrategyRegistry ДОЛЖЕН валидировать совместимость mode + стратегии перед выполнением через `validator` в `StrategyDescriptor`:

```python
def _validate_strategy(mode: str, registry: AgentRegistry) -> bool:
    """Проверить доступность стратегии. Вернуть True если доступна."""
```

### Требование: Правила валидации

Валидация ДОЛЖНА следовать этим правилам:
- Single: всегда проходит (без проверки mode)
- Orchestrated: has_orchestrator И has_subagent
- Choreography: len(subagents) >= 2
- Hierarchical: has_primary И has_subagent
- Unknown mode: возвращается False (недоступна)

# Spec: active-strategy-config

## ДОБАВЛЕННЫЕ Требования

### Требование: Config Option _active_strategy

Система ДОЛЖНА поддерживать опцию конфигурации `_active_strategy` для постоянного выбора стратегии:
- Устанавливается через `session/set_config_option` с configId="_active_strategy"
- Сохраняется в `session.config_values["_active_strategy"]` (существующее поле `dict[str, str]`)
- Сохраняется между turn'ами в пределах сессии
- Имеет приоритет над default, ниже чем slash command

> **Примечание:** `SessionState.config_values` уже поддерживает произвольные ключи. Не требуется изменение модели состояния.

### Требование: Валидация при установке

При установке `_active_strategy` через `session/set_config_option` система ДОЛЖНА:
- Проверить что стратегия доступна через `StrategyRegistry.get_available(agent_registry)`
- Вернуть ошибку если стратегия недоступна

### Требование: Override Slash Command

Система ДОЛЖНА поддерживать override активной стратегии через slash command:
- Установить `context.meta["active_strategy"]` в обработчике slash command
- Имеет высший приоритет в цепочке выбора
- Применяется только к текущему turn (не постоянно)
- Slash command ДОЛЖЕН валидировать доступность через Registry

### Требование: Динамическое формирование configOptions

ACPProtocol ДОЛЖЕН формировать configOptions для `_active_strategy` динамически:
- Использовать `StrategyRegistry.get_available(agent_registry)`
- Включать ТОЛЬКО доступные стратегии
- Использовать `display_name` и `description` из `StrategyDescriptor`
- Обновлять при изменении AgentRegistry (hot reload)

# Spec: strategy-fallback

## ДОБАВЛЕННЫЕ Требования

### Требование: Уведомление о Fallback

При переключении на другую стратегию система ДОЛЖНА уведомить пользователя через уведомление `session/update`:

```json
{
  "sessionUpdate": "agent_message_chunk",
  "content": {
    "type": "text",
    "text": "[system] Strategy 'multi_orchestrated' unavailable (no orchestrator). Falling back to 'single'."
  }
}
```

### Требование: Логирование Fallback

Система ДОЛЖНА записать warning с:
- Запрошенная стратегия
- Причина недоступности
- Фактический fallback режим

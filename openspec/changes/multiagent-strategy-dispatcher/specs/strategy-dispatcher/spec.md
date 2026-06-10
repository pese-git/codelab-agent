# Spec: strategy-dispatcher

## ДОБАВЛЕННЫЕ Требования

### Требование: Выбор StrategyDispatcher

Система ДОЛЖНА предоставлять `StrategyDispatcher`, который выбирает стратегию выполнения по приоритету:
1. `context.meta["active_strategy"]` — override slash командой (высший приоритет)
2. `config_values["_active_strategy"]` — постоянная конфигурация сессии
3. `"single"` — fallback по умолчанию (низший приоритет)

### Требование: Валидация стратегии

StrategyDispatcher ДОЛЖЕН валидировать доступность стратегии через AgentRegistry:
- `single`: всегда доступно (любой зарегистрированный агент)
- `multi_orchestrated`: требует ≥1 агент с mode=orchestrator И ≥1 с mode=subagent
- `multi_choreographed`: требует ≥2 агента с mode=subagent
- `hierarchical`: требует ≥1 агент с mode=primary И ≥1 с mode=subagent

### Требование: Поведение Fallback

Когда выбранная стратегия недоступна, StrategyDispatcher ДОЛЖЕН:
- Переключиться на `global.fallback_mode` (по умолчанию: "single")
- Записать warning с причиной недоступности
- Вернуть фактический режим, использованный для выполнения

# Spec: strategy-validation

## ДОБАВЛЕННЫЕ Требования

### Требование: Проверка совместимости mode

Система ДОЛЖНА валидировать совместимость mode + стратегии перед выполнением:

```python
def _validate_strategy(mode: str, registry: AgentRegistry) -> str:
    """Проверить доступность стратегии. Вернуть фактический режим."""
```

### Требование: Правила валидации

Валидация ДОЛЖНА следовать этим правилам:
- Single: всегда проходит (без проверки mode)
- Orchestrated: has_orchestrator И has_subagent
- Choreography: len(subagents) >= 2
- Hierarchical: has_primary И has_subagent
- Unknown mode: fallback на fallback_mode

# Spec: active-strategy-config

## ДОБАВЛЕННЫЕ Требования

### Требование: Config Option _active_strategy

Система ДОЛЖНА поддерживать опцию конфигурации `_active_strategy` для постоянного выбора стратегии:
- Устанавливается через `session/set_config_option` с configId="_active_strategy"
- Сохраняется в `session.config_values["_active_strategy"]` (существующее поле `dict[str, str]`)
- Сохраняется между turn'ами в пределах сессии
- Имеет приоритет над default, ниже чем slash command

> **Примечание:** `SessionState.config_values` уже поддерживает произвольные ключи. Не требуется изменение модели состояния.

### Требование: Override Slash Command

Система ДОЛЖНА поддерживать override активной стратегии через slash command:
- Установить `context.meta["active_strategy"]` в обработчике slash command
- Имеет высший приоритет в цепочке выбора
- Применяется только к текущему turn (не постоянно)

# Spec: strategy-fallback

## ДОБАВЛЕННЫЕ Требования

### Требование: Уведомление о Fallback

При переключении на другую стратегию система ДОЛЖНА уведомить пользователя через уведомление `session/update`:

```json
{
  "sessionUpdate": "agent_message_chunk",
  "content": {
    "type": "text",
    "text": "[system] OrchestratedStrategy недоступна (нет агента-оркестратора). Переключение на single mode."
  }
}
```

### Требование: Логирование Fallback

Система ДОЛЖНА записать warning с:
- Запрошенная стратегия
- Причина недоступности
- Фактический fallback режим

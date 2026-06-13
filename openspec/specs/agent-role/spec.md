# Spec: AgentRole (переименование AgentMode)

## ИЗМЕНЁННЫЕ Требования

### Требование: Enum AgentRole

Система ДОЛЖНА предоставлять `AgentRole` (переименованный из `AgentMode`) с тремя значениями:

```python
class AgentRole(StrEnum):
    """Роль агента в мультиагентной системе."""
    PRIMARY = "primary"       # Главный агент, отвечает пользователю
    SUBAGENT = "subagent"     # Исполнитель, получает задачи от primary/orchestrator
    ORCHESTRATOR = "orchestrator"  # Маршрутизатор, принимает RouteDecision
```

#### Сценарий: Значения enum
- **КОГДА** проверяется `AgentRole.PRIMARY`
- **ТОГДА** значение равно `"primary"`
- **И** `AgentRole("primary")` возвращает `AgentRole.PRIMARY`

### Требование: Поле role в моделях конфигурации

Все модели конфигурации агентов ДОЛЖНЫ использовать поле `role` вместо `mode`:

- `AgentTOMLConfig.role` (default: `AgentRole.PRIMARY`)
- `AgentsGlobalConfig.role` (default: `AgentRole.PRIMARY`)
- `AgentsGlobalConfig.fallback_role` (default: `AgentRole.PRIMARY`) — переименовано из `fallback_mode`
- `AgentMarkdownConfig.role` (default: `AgentRole.PRIMARY`)
- `ResolvedAgent.role` (default: `AgentRole.PRIMARY`)

#### Сценарий: TOML конфигурация с role
- **КОГДА** TOML содержит `role = "subagent"` в `[agents.definitions.coder]`
- **ТОГДА** `AgentTOMLConfig.role` = `AgentRole.SUBAGENT`

#### Сценарий: TOML конфигурация без role (backward compatibility)
- **КОГДА** TOML содержит `mode = "subagent"` но не содержит `role`
- **ТОГДА** loader читает `mode` как `role` с deprecation warning
- **И** `AgentTOMLConfig.role` = `AgentRole.SUBAGENT`

#### Сценарий: Markdown frontmatter с role
- **КОГДА** Markdown содержит `role: subagent` в frontmatter
- **ТОГДА** `AgentMarkdownConfig.role` = `AgentRole.SUBAGENT`

### Требование: AgentRegistry использует role

`AgentRegistry` ДОЛЖЕН фильтровать агентов по полю `role`:

- `get_primary_agents()` → агенты с `role == AgentRole.PRIMARY`
- `get_subagents()` → агенты с `role == AgentRole.SUBAGENT`
- `get_orchestrator()` → агент с `role == AgentRole.ORCHESTRATOR`

### Требование: Валидация стратегий по role

StrategyDispatcher ДОЛЖЕН валидировать стратегии по `role`:

| Стратегия | Требуемые role |
|---|---|
| Single | любой |
| Orchestrated | ≥1 orchestrator + ≥1 subagent |
| Choreography | ≥2 subagent |
| Hierarchical | ≥1 primary + ≥1 subagent |

### Требование: SessionState migration

Система ДОЛЖНА поддерживать миграцию старых session файлов где `execution_mode` может ссылаться на старое поле `mode` агентов.

#### Сценарий: Загрузка старой сессии
- **КОГДА** загружается session файл с `mode` в конфигурации агентов
- **ТОГДА** `mode` автоматически конвертируется в `role`
- **И** записывается deprecation warning в лог

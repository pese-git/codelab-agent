## Why

Текущая реализация `mode` в CodeLab использует кастомные значения (`code`, `architect`, `ask`, `debug`), которые не соответствуют ACP Protocol spec. Стандартный ACP `mode` должен отвечать за уровень разрешений (Permissions) и степень автономности агента — отдельную плоскость от `_active_strategy` (архитектурная стратегия выполнения).

Без чёткой интеграции `mode` с permission system:
- Child sessions не наследуют mode от parent (риск безопасности: субагент может получить bypass когда parent в plan)
- Нет явной матрицы strategy × mode
- Текущие значения mode не соответствуют ACP spec

## What Changes

### Переименование значений mode

| Старое | Новое | Поведение |
|---|---|---|
| `ask` | `standard` | Permission request для каждого write/execute tool |
| `code` | `bypass` | Auto-execute без подтверждения |
| `architect` | `plan` | Read-only: блокировать write/execute инструменты |
| `debug` | *(удалён)* | Функциональность покрыта `plan` + debug flag |

### Новая интеграция

1. **Mode в permission decision chain**: `mode → session policy → global policy → ask`
2. **Child session mode inheritance**: дочерние сессии наследуют mode от parent
3. **Mode × Strategy matrix**: документированное поведение для каждой комбинации

## Capabilities

### New Capabilities
- `acp-mode-values`: Новые значения mode (plan, standard, bypass) вместо кастомных
- `mode-permission-integration`: Mode в permission decision chain
- `child-mode-inheritance`: Child sessions наследуют mode от parent
- `mode-strategy-matrix`: Документированное поведение strategy × mode

### Modified Capabilities
- `session-config-options`: mode config option с новыми значениями
- `session/set_mode`: ACP метод с валидацией новых modeId
- `tool-execution`: Tool execution учитывает mode (plan=block, standard=ask, bypass=auto)
- `slash-commands`: /mode command с новыми значениями

## Impact

**Изменяемые файлы:**
- `codelab/src/codelab/server/protocol/state.py` — валидатор mode
- `codelab/src/codelab/server/protocol/handlers/config.py` — session_set_mode
- `codelab/src/codelab/server/protocol/handlers/pipeline/stages/directives.py` — tool execution по mode
- `codelab/src/codelab/server/protocol/handlers/slash_commands/builtin/mode.py` — AVAILABLE_MODES
- `codelab/src/codelab/server/protocol/handlers/session.py` — modes state, child inheritance
- `codelab/src/codelab/server/protocol/handlers/permission_manager.py` — mode в decision chain
- `codelab/src/codelab/server/agent/strategies/orchestrated.py` — child mode inheritance
- `codelab/src/codelab/server/agent/strategies/hierarchical.py` — child mode inheritance
- Тесты: обновить все mode references + новые тесты

**Breaking change:** Пользователи с `mode=code`, `mode=architect`, `mode=debug` в config_values получат fallback на `standard`.

# Spec: ACP Protocol Mode Integration

## ИЗМЕНЁННЫЕ Требования

### Требование: Значения mode

Система ДОЛЖНА поддерживать три значения mode для управления уровнем разрешений:

```
plan      — Read-only: агенты строят планы, write/execute инструменты заблокированы
standard  — С подтверждением: каждый write/execute tool требует permission request
bypass    — Автономный: полная свобода действий, auto-execute без подтверждения
```

#### Сценарий: mode=plan блокирует запись
- **КОГДА** mode установлен в "plan"
- **И** агент вызывает инструмент с kind=edit/delete/execute
- **ТОГДА** инструмент блокируется с ошибкой "Cannot execute in 'plan' mode"
- **И** tool_call получает status="failed"

#### Сценарий: mode=standard запрашивает permission
- **КОГДА** mode установлен в "standard"
- **И** агент вызывает write/execute инструмент
- **ТОГДА** отправляется session/request_permission пользователю
- **И** инструмент выполняется только после allow

#### Сценарий: mode=bypass auto-execute
- **КОГДА** mode установлен в "bypass"
- **И** агент вызывает любой инструмент
- **ТОГДА** инструмент выполняется автоматически без permission request

### Требование: session/set_mode

Система ДОЛЖНА обрабатывать ACP метод `session/set_mode` с валидацией modeId:

- modeId ДОЛЖЕН быть одним из: "plan", "standard", "bypass"
- При невалидном modeId → ошибка -32602 (Invalid params)
- При успешной смене → notification `session/mode_changed`

#### Сценарий: Успешная смена mode
- **КОГДА** клиент вызывает session/set_mode с modeId="bypass"
- **ТОГДА** session.config_values["mode"] = "bypass"
- **И** отправляется notification mode_changed с новым modeId

#### Сценарий: Невалидный modeId
- **КОГДА** клиент вызывает session/set_mode с modeId="unknown"
- **ТОГДА** возвращается ошибка -32602 "Invalid params: modeId must be one of: plan, standard, bypass"

### Требование: Mode в permission decision chain

PermissionManager ДОЛЖЕН учитывать mode в цепочке решений:

```
1. mode == "plan" → reject (write/execute заблокированы)
2. mode == "bypass" → allow (auto-execute)
3. mode == "standard" → session policy → global policy → ask user
```

#### Сценарий: plan mode отклоняет write
- **КОГДА** mode="plan" и tool_kind="edit"
- **ТОГДА** permission decision = reject
- **И** tool_call получает status="failed" с reason="Blocked in plan mode"

#### Сценарий: bypass mode пропускает permission
- **КОГДА** mode="bypass" и tool_kind="edit"
- **ТОГДА** permission decision = allow
- **И** инструмент выполняется без permission request

#### Сценарий: standard mode использует policy chain
- **КОГДА** mode="standard" и tool_kind="edit"
- **ТОГДА** проверяется session policy → global policy → ask user
- **И** поведение идентично текущему permission flow

### Требование: Child session mode inheritance

При создании child session ДОЛЖНА наследовать mode от parent session:

- OrchestratedStrategy: каждый sub-agent child session получает mode=parent.mode
- HierarchicalStrategy: каждый sub-agent child session получает mode=parent.mode
- ChoreographyStrategy: winner child session получает mode=parent.mode

#### Сценарий: Наследование mode в child session
- **КОГДА** parent session имеет mode="plan"
- **И** orchestrator создаёт child session для sub-agent
- **ТОГДА** child session.config_values["mode"] = "plan"
- **И** sub-agent НЕ может переключить mode на "bypass"

#### Сценарий: Безопасность наследования
- **КОГДА** parent session имеет mode="standard"
- **И** orchestrator пытается создать child session с mode="bypass"
- **ТОГДА** mode принудительно устанавливается в parent.mode ("standard")
- **И** записывается warning в лог

### Требование: Mode × Strategy Matrix

Система ДОЛЖНА документировать поведение для каждой комбинации:

| mode \ strategy | Single | Orchestrated | Choreography | Hierarchical |
|---|---|---|---|---|
| **plan** | Read-only LLM | Orchestrator планирует, subagents read-only | Все агенты read-only | Primary планирует, subagents read-only |
| **standard** | Permission per tool | Permission per tool call | Permission per tool call | Permission per delegation |
| **bypass** | Auto-execute | Full autonomy | Full autonomy | Full autonomy |

### Требование: Slash command /mode

Команда `/mode` ДОЛЖНА поддерживать новые значения:

- `/mode` — показать текущий mode
- `/mode plan` — установить plan mode
- `/mode standard` — установить standard mode
- `/mode bypass` — установить bypass mode

#### Сценарий: Показать текущий mode
- **КОГДА** пользователь вводит `/mode`
- **ТОГДА** показывается текущий mode и доступные значения

#### Сценарий: Установить новый mode
- **КОГДА** пользователь вводит `/mode bypass`
- **ТОГДА** mode устанавливается в "bypass"
- **И** показывается подтверждение: "Режим изменён: standard → bypass"

### Требование: Session setup — modes state

При session/new система ДОЛЖНА возвращать modes state:

```json
{
  "modes": {
    "availableModes": [
      {"id": "plan", "name": "Plan", "description": "Read-only planning mode"},
      {"id": "standard", "name": "Standard", "description": "Confirm changes before execution"},
      {"id": "bypass", "name": "Bypass", "description": "Full autonomy, no confirmation"}
    ],
    "currentModeId": "standard"
  }
}
```

### Требование: Backward compatibility

Система ДОЛЖНА поддерживать миграцию старых значений mode:

| Старое значение | Новое значение |
|---|---|
| `ask` | `standard` |
| `code` | `bypass` |
| `architect` | `plan` |
| `debug` | `standard` |

#### Сценарий: Миграция старого mode
- **КОГДА** session загружается с mode="code"
- **ТОГДА** mode автоматически конвертируется в "bypass"
- **И** записывается deprecation warning в лог

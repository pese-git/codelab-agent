# Spec: plan-models

## ADDED Requirements

### Требование: Domain PlanEntry

Система ДОЛЖНА предоставлять `PlanEntry` как frozen dataclass:
- `content: str` — описание шага
- `priority: PlanPriority` — приоритет (HIGH, MEDIUM, LOW)
- `status: PlanStatus` — статус (PENDING, IN_PROGRESS, COMPLETED)

### Требование: PlanPriority Domain Enum

Система ДОЛЖНА предоставлять domain enum `PlanPriority`:
- `HIGH` — высокий приоритет
- `MEDIUM` — средний приоритет
- `LOW` — низкий приоритет

### Требование: PlanStatus Domain Enum

Система ДОЛЖНА предоставлять domain enum `PlanStatus`:
- `PENDING` — ожидает выполнения
- `IN_PROGRESS` — выполняется
- `COMPLETED` — завершён

### Требование: Соответствие ACP Spec

`PlanEntry` ДОЛЖЕН соответствовать ACP спецификации (11-Agent Plan.md):
- `content` вместо `description`
- `priority` вместо `step_number`
- `status` с значениями PENDING, IN_PROGRESS, COMPLETED

### Требование: PlanMapper

Система ДОЛЖНА предоставлять `PlanMapper` с методами:
- `to_acp(entries: list[PlanEntry]) -> list[dict]` — конвертировать в ACP format
- `from_acp(blocks: list[dict]) -> list[PlanEntry]` — конвертировать из ACP format

### Требование: Замена PlanStep

Система ДОЛЖНА заменить `PlanStep` на `PlanEntry` в `SessionState`.

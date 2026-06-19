# Spec: plan-models

## ADDED Requirements

### Requirement: Domain PlanEntry

Система SHALL предоставлять `PlanEntry` как frozen dataclass:
- `content: str` — описание шага
- `priority: PlanPriority` — приоритет (HIGH, MEDIUM, LOW)
- `status: PlanStatus` — статус (PENDING, IN_PROGRESS, COMPLETED)

#### Scenario: Создание PlanEntry
- **WHEN** создается PlanEntry
- **THEN** объект содержит поля `content`, `priority`, `status`

#### Scenario: PlanEntry как frozen dataclass
- **WHEN** создан PlanEntry объект
- **THEN** его поля нельзя изменить (immutable)

### Requirement: PlanPriority Domain Enum

Система SHALL предоставлять domain enum `PlanPriority`:
- `HIGH` — высокий приоритет
- `MEDIUM` — средний приоритет
- `LOW` — низкий приоритет

#### Scenario: Использование PlanPriority
- **WHEN** используется PlanPriority
- **THEN** доступны значения HIGH, MEDIUM, LOW

### Requirement: PlanStatus Domain Enum

Система SHALL предоставлять domain enum `PlanStatus`:
- `PENDING` — ожидает выполнения
- `IN_PROGRESS` — выполняется
- `COMPLETED` — завершён

#### Scenario: Использование PlanStatus
- **WHEN** используется PlanStatus
- **THEN** доступны значения PENDING, IN_PROGRESS, COMPLETED

### Requirement: Соответствие ACP Spec

`PlanEntry` SHALL соответствовать ACP спецификации (11-Agent Plan.md):
- `content` вместо `description`
- `priority` вместо `step_number`
- `status` с значениями PENDING, IN_PROGRESS, COMPLETED

#### Scenario: Соответствие ACP спецификации
- **WHEN** используется PlanEntry
- **THEN** он соответствует ACP спецификации для agent plan

### Requirement: PlanMapper

Система SHALL предоставлять `PlanMapper` с методами:
- `to_acp(entries: list[PlanEntry]) -> list[dict]` — конвертировать в ACP format
- `from_acp(blocks: list[dict]) -> list[PlanEntry]` — конвертировать из ACP format

#### Scenario: Конвертация domain в ACP
- **WHEN** вызывается `PlanMapper.to_acp()` с PlanEntry
- **THEN** возвращается список dict в ACP format

#### Scenario: Конвертация ACP в domain
- **WHEN** вызывается `PlanMapper.from_acp()` с ACP blocks
- **THEN** возвращается список PlanEntry объектов

### Requirement: Замена PlanStep

Система SHALL заменить `PlanStep` на `PlanEntry` в `SessionState`.

#### Scenario: Использование PlanEntry вместо PlanStep
- **WHEN** SessionState хранит plan
- **THEN** используется `PlanEntry` вместо `PlanStep`

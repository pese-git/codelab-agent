## Decision 1: Три значения mode вместо четырёх

**Контекст:** Текущие значения `code`, `architect`, `ask`, `debug` не соответствуют ACP spec и создают путаницу.

**Решение:** Три значения: `plan` (read-only), `standard` (confirm), `bypass` (auto). `debug` удаляется — его функциональность покрыта `plan` + debug flag.

**Tradeoffs:**
- ✅ Соответствует ACP spec
- ✅ Чёткая семантика: plan/standard/bypass
- ⚠️ Breaking change для пользователей `mode=debug`

## Decision 2: Mode первым в permission decision chain

**Контекст:** Permission chain: session policy → global policy → ask user. Mode должен быть первым фильтром.

**Решение:** Mode проверяется ДО policy chain:
- `plan` → reject write/execute (независимо от policy)
- `bypass` → allow все (независимо от policy)
- `standard` → policy chain

**Tradeoffs:**
- ✅ Mode = глобальный переключатель автономности
- ✅ Policy chain не может override mode
- ⚠️ Пользователь в bypass mode не получит permission requests даже для CRITICAL инструментов

## Decision 3: Child session mode inheritance

**Контекст:** Child sessions создаются в мультиагентных стратегиях. Без наследования mode субагент может получить bypass когда parent в plan.

**Решение:** Child session наследует mode от parent. Запрещено устанавливать child.mode != parent.mode.

**Tradeoffs:**
- ✅ Безопасность: субагент не может получить больше разрешений чем parent
- ✅ Предсказуемое поведение
- ⚠️ Нельзя временно переключить mode для конкретного sub-agent

## Decision 4: Backward compatibility mapping

**Контекст:** Пользователи имеют существующие session файлы с mode=code/ask/architect/debug.

**Решение:** Автоматическая миграция при загрузке:
- `ask` → `standard`
- `code` → `bypass`
- `architect` → `plan`
- `debug` → `standard`

**Tradeoffs:**
- ✅ Плавная миграция
- ✅ Нет потери функциональности
- ⚠️ Временная сложность поддержки двух форматов

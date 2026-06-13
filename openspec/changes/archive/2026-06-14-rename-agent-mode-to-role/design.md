## Decision 1: Переименование mode → role

**Контекст:** Поле `mode` в конфигурации агента путается с `_active_strategy` (режим выполнения сессии).

**Решение:** Переименовать `mode` → `role` и `AgentMode` → `AgentRole`.

**Tradeoffs:**
- ✅ Устраняет амбигуитет между ролью агента и режимом сессии
- ✅ Семантически точнее: "role" = роль агента, "mode/strategy" = режим выполнения
- ⚠️ Breaking change для TOML конфигов пользователей

## Decision 2: Backward compatibility для TOML

**Контекст:** Пользователи могут иметь существующие `codelab.toml` с полем `mode`.

**Решение:** Loader читает `role`, fallback на `mode` с deprecation warning.

**Tradeoffs:**
- ✅ Плавная миграция для пользователей
- ✅ Предупреждение в логах о необходимости обновления
- ⚠️ Временная сложность поддержки двух полей

## Decision 3: fallback_mode → fallback_role

**Контекст:** `AgentsGlobalConfig.fallback_mode` тоже использует слово "mode".

**Решение:** Переименовать в `fallback_role` для консистентности.

**Tradeoffs:**
- ✅ Полная консистентность naming
- ⚠️ Дополнительное breaking change

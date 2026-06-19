# Spec: session-state (Delta)

## МОДИФИЦИРОВАННЫЕ Требования

### Требование: SessionState как тонкий DTO

Система ДОЛЖНА обновить `SessionState` до `SessionStateDTO`:
- Уменьшить до тонкого DTO для сериализации
- Делегировать бизнес-логику domain агрегатам
- Поддерживать миграцию schema_version: 3 → 4

### Требование: Миграция schema_version

`SessionStateDTO` ДОЛЖЕН поддерживать миграцию:
- `schema_version: 4` — новая версия
- `model_validator` для автоматической миграции из v3
- Обратная совместимость при чтении старых файлов

### Требование: Делегирование бизнес-логики

`SessionStateDTO` НЕ ДОЛЖЕН содержать бизнес-логику:
- Все методы переносятся в domain `Session`
- DTO содержит только данные
- Маппинг через `SessionMapper`

### Требование: Обновление storage

Система ДОЛЖНА обновить storage implementations:
- `InMemoryStorage` — работа с `SessionStateDTO`
- `JsonFileStorage` — сериализация/десериализация DTO
- Миграция существующих файлов при загрузке

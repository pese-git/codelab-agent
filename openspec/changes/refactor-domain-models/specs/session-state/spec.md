# Spec: session-state (Delta)

## МОДИФИЦИРОВАННЫЕ Требования

### Требование: SessionState как ACP Protocol Model

Система ДОЛЖНА обновить `SessionState` как ACP Protocol Model:
- Обновить структуру с использованием value objects
- Делегировать бизнес-логику domain агрегатам
- Поддерживать миграцию schema_version: 3 → 4

### Требование: SessionState Docstring

`SessionState` ДОЛЖЕН иметь docstring с пометкой:
```python
"""ACP Protocol Model — контракт сессии согласно ACP 03-Session Setup.

Wire format для хранения состояния сессии в storage.

НЕ является domain моделью. Для бизнес-логики использовать domain Session.
Конвертация через SessionMapper.
"""
```

### Требование: Миграция schema_version

`SessionState` ДОЛЖЕН поддерживать миграцию:
- `schema_version: 4` — новая версия
- `model_validator` для автоматической миграции из v3
- Обратная совместимость при чтении старых файлов

### Требование: Делегирование бизнес-логики

`SessionState` НЕ ДОЛЖЕН содержать бизнес-логику:
- Все методы переносятся в domain `Session`
- Protocol модель содержит только данные
- Маппинг через `SessionMapper`

### Требование: Обновление storage

Система ДОЛЖНА обновить storage implementations:
- `InMemoryStorage` — работа с обновлённым `SessionState`
- `JsonFileStorage` — сериализация/десериализация с миграцией
- Миграция существующих файлов при загрузке

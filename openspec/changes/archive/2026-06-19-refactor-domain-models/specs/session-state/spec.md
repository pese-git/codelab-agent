# Spec: session-state (Delta)

## ADDED Requirements

### Requirement: SessionState как ACP Protocol Model

Система SHALL обновить `SessionState` как ACP Protocol Model:
- Обновить структуру с использованием value objects
- Делегировать бизнес-логику domain агрегатам
- Поддерживать миграцию schema_version: 3 → 4

#### Scenario: SessionState как ACP Protocol Model
- **WHEN** используется SessionState
- **THEN** он соответствует ACP спецификации для session state

#### Scenario: Делегирование бизнес-логики
- **WHEN** SessionState используется для хранения состояния
- **THEN** бизнес-логика делегирована domain Session агрегату

### Requirement: SessionState Docstring

`SessionState` SHALL иметь docstring с пометкой:
```python
"""ACP Protocol Model — контракт сессии согласно ACP 03-Session Setup.

Wire format для хранения состояния сессии в storage.

НЕ является domain моделью. Для бизнес-логики использовать domain Session.
Конвертация через SessionMapper.
"""
```

#### Scenario: Docstring для SessionState
- **WHEN** определен SessionState
- **THEN** он содержит docstring с пометкой "ACP Protocol Model"

### Requirement: Миграция schema_version

`SessionState` SHALL поддерживать миграцию:
- `schema_version: 4` — новая версия
- `model_validator` для автоматической миграции из v3
- Обратная совместимость при чтении старых файлов

#### Scenario: Миграция с v3 на v4
- **WHEN** загружается SessionState с schema_version 3
- **THEN** автоматически применяется миграция на версию 4

#### Scenario: Обратная совместимость
- **WHEN** читаются старые файлы с schema_version < 4
- **THEN** данные корректно мигрируются на новую версию

### Requirement: Делегирование бизнес-логики

`SessionState` SHALL NOT содержать бизнес-логику:
- Все методы переносятся в domain `Session`
- Protocol модель содержит только данные
- Маппинг через `SessionMapper`

#### Scenario: SessionState без бизнес-логики
- **WHEN** используется SessionState
- **THEN** он содержит только данные без бизнес-методов

#### Scenario: Бизнес-логика в Session
- **WHEN** требуется бизнес-логика для сессии
- **THEN** используется domain Session агрегат

### Requirement: Обновление storage

Система SHALL обновить storage implementations:
- `InMemoryStorage` — работа с обновлённым `SessionState`
- `JsonFileStorage` — сериализация/десериализация с миграцией
- Миграция существующих файлов при загрузке

#### Scenario: InMemoryStorage с обновленным SessionState
- **WHEN** используется InMemoryStorage
- **THEN** он работает с обновленным SessionState

#### Scenario: JsonFileStorage с миграцией
- **WHEN** загружается файл с старой версией SessionState
- **THEN** применяется миграция при десериализации

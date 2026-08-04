# session-state Specification

## Purpose
TBD - created by archiving change refactor-domain-models. Update Purpose after archive.
## Requirements
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


### Requirement: Развязка ядра агента от модели документа сессии

Ядро агента (`server/agent/`) MUST НЕ зависеть от персистентной модели документа сессии. Доступ к
данным сессии из ядра идёт через порт `SessionView` (capability `agent-ports`).

> **Уточнение по факту реализации (2026-08-04).** Delta-спека change `acp-independent-agent-core`
> формулировала это как «ядро не зависит от `protocol.state.SessionState`». К моменту архивации
> изменились два обстоятельства: документ сессии переехал в `storage/document.py` и называется
> `SessionDocument` (фаза D ADR-006), а носителем состояния на прикладных путях стал доменный
> `Session`. Требование поэтому сформулировано по существу — «не зависеть от персистентной модели»,
> — а не по имени класса.

#### Scenario: Ядро не импортирует персистентную модель
- **WHEN** сканируются импорты `server/agent/`
- **THEN** `SessionDocument` в ядре не импортируется; используется порт `SessionView`

#### Scenario: Документ остаётся моделью сериализации
- **WHEN** сессия сохраняется или загружается через storage
- **THEN** используется `SessionDocument` (Pydantic); поведение сериализации этим требованием не меняется

#### Scenario: Мутации идут командами, ядро видит их через живой порт
- **WHEN** прикладной путь меняет состояние сессии
- **THEN** изменение применяется командой к доменному агрегату, а ядро видит результат через живой `SessionView` (read-only)

#### Scenario: Обратная совместимость формата сессии
- **WHEN** загружается ранее сохранённая сессия
- **THEN** формат документа и `schema_version` этим требованием не изменяются — развязано только чтение в ядре

# follow-along Specification

## Purpose
TBD - created by archiving change refactor-domain-models. Update Purpose after archive.
## Requirements
### Requirement: FileOpener Protocol

Система SHALL предоставлять `FileOpener` Protocol в `client/infrastructure/services/follow_along.py`:
```python
class FileOpener(Protocol):
    async def open(self, path: str, line: int | None = None) -> None: ...
```

#### Scenario: Определение FileOpener Protocol
- **WHEN** определяется FileOpener Protocol
- **THEN** он содержит метод `async def open(self, path: str, line: int | None = None) -> None`

### Requirement: StubFileOpener

Система SHALL предоставлять `StubFileOpener` для тестов — реализация `FileOpener`, которая логирует вызовы без реального открытия файлов.

#### Scenario: Использование StubFileOpener в тестах
- **WHEN** создается StubFileOpener
- **THEN** он реализует FileOpener Protocol и логирует вызовы без реального открытия файлов

### Requirement: FollowAlongService

Система SHALL предоставлять `FollowAlongService` в `client/infrastructure/services/follow_along.py`:
- `__init__(file_opener: FileOpener, enabled: bool = True)` — инициализация
- `async on_tool_call_updated(tool_call: dict[str, Any]) -> None` — обработка обновления tool call

#### Scenario: Создание FollowAlongService
- **WHEN** создается FollowAlongService
- **THEN** он принимает `file_opener: FileOpener` и опциональный `enabled: bool = True`

#### Scenario: Обработка обновления tool call
- **WHEN** вызывается `on_tool_call_updated(tool_call)`
- **THEN** сервис обрабатывает обновление tool call

### Requirement: FollowAlongService поведение

`FollowAlongService.on_tool_call_updated()` SHALL:
1. Проверить `enabled` флаг — если False, вернуть немедленно
2. Извлечь `locations` из tool_call
3. Если `locations` пуст — вернуть
4. Взять первую локацию: `locations[0]`
5. Вызвать `file_opener.open(path, line)`

#### Scenario: Сервис отключен
- **WHEN** `enabled=False` и вызывается `on_tool_call_updated()`
- **THEN** метод возвращает немедленно без вызова file_opener

#### Scenario: Пустые locations
- **WHEN** `locations` пуст и вызывается `on_tool_call_updated()`
- **THEN** метод возвращает без вызова file_opener

#### Scenario: Одна локация
- **WHEN** `locations` содержит один элемент и вызывается `on_tool_call_updated()`
- **THEN** вызывается `file_opener.open(path, line)` для первой локации

#### Scenario: Несколько локаций
- **WHEN** `locations` содержит несколько элементов и вызывается `on_tool_call_updated()`
- **THEN** вызывается `file_opener.open()` только для первой локации

### Requirement: FollowAlongService интеграция в ToolCallHandler

Клиентский `ToolCallHandler` SHALL:
1. Принимать опциональный `follow_along: FollowAlongService | None` в конструктор
2. В `_handle_tool_call_updated()` после обновления состояния вызывать `follow_along.on_tool_call_updated()` если сервис доступен

#### Scenario: ToolCallHandler с FollowAlongService
- **WHEN** ToolCallHandler создан с `follow_along` сервисом
- **THEN** при обновлении tool call вызывается `follow_along.on_tool_call_updated()`

#### Scenario: ToolCallHandler без FollowAlongService
- **WHEN** ToolCallHandler создан без `follow_along` сервиса
- **THEN** при обновлении tool call не вызывается follow_along

### Requirement: ToolCallHandler сохраняет locations

`ToolCallHandler._handle_tool_call_created()` SHALL сохранять `locations` из update:
```python
tool_call = {
    "toolCallId": tool_call_id,
    "title": title,
    "status": status,
    "kind": kind,
    "locations": update.get("locations"),
    "rawInput": update.get("rawInput"),
    "rawOutput": update.get("rawOutput"),
}
```

#### Scenario: Сохранение locations при создании tool call
- **WHEN** создается новый tool call
- **THEN** в tool_call сохраняются `locations`, `rawInput`, `rawOutput` из update

### Requirement: ToolCallHandler обновляет locations

`ToolCallHandler._handle_tool_call_updated()` SHALL обновлять `locations` и `rawOutput`:
```python
updates = {}
if status:
    updates["status"] = status
if title:
    updates["title"] = title
if locations := update.get("locations"):
    updates["locations"] = locations
if raw_output := update.get("rawOutput"):
    updates["rawOutput"] = raw_output
```

#### Scenario: Обновление locations и rawOutput
- **WHEN** обновляется tool call
- **THEN** обновляются `locations` и `rawOutput` если они присутствуют в update

### Requirement: Feature flag не нужен

Follow-along SHALL NOT требовать feature flag:
- Это стандартная функция IDE
- Если tool call не имеет `locations` — follow-along не срабатывает
- Нет риска поломки существующего функционала

#### Scenario: Follow-along без feature flag
- **WHEN** используется follow-along
- **THEN** не требуется feature flag для включения/выключения

### Requirement: FollowAlongService unit тесты

Система SHALL предоставлять unit тесты для `FollowAlongService`:
- Тест: `enabled=False` — не вызывает file_opener
- Тест: `locations` пуст — не вызывает file_opener
- Тест: `locations` содержит один элемент — вызывает `open(path, line)`
- Тест: `locations` содержит несколько элементов — вызывает `open()` для первого

#### Scenario: Unit тесты для FollowAlongService
- **WHEN** запускаются unit тесты
- **THEN** тестируются все сценарии поведения FollowAlongService

### Requirement: ToolCallHandler integration тесты

Система SHALL предоставлять integration тесты:
- Тест: tool_call update с locations вызывает follow_along
- Тест: tool_call update без locations не вызывает follow_along
- Тест: tool_call created сохраняет locations, rawInput, rawOutput

#### Scenario: Integration тесты для ToolCallHandler
- **WHEN** запускаются integration тесты
- **THEN** тестируется интеграция ToolCallHandler с FollowAlongService


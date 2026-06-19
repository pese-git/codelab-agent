# Spec: tool-call-models

## ADDED Requirements

### Requirement: Domain ToolCall

Система SHALL предоставлять `ToolCall` как frozen dataclass в domain layer:
- `id: str` — уникальный идентификатор
- `tool_name: str` — имя инструмента
- `arguments: dict[str, Any]` — аргументы вызова
- `status: ToolCallStatus` — статус (domain enum)
- `result: ToolResult | None` — результат выполнения
- `locations: list[FileLocation]` — затронутые файлы
- `raw_output: dict[str, Any]` — исходный результат выполнения

#### Scenario: Создание domain ToolCall
- **WHEN** создается ToolCall
- **THEN** объект содержит все поля: id, tool_name, arguments, status, result, locations, raw_output

#### Scenario: ToolCall как frozen dataclass
- **WHEN** создан ToolCall объект
- **THEN** его поля нельзя изменить (immutable)

### Requirement: ToolCallStatus Domain Enum

Система SHALL предоставлять domain enum `ToolCallStatus`:
- `PENDING` — ожидает выполнения
- `RUNNING` — выполняется
- `COMPLETED` — завершён успешно
- `FAILED` — завершён с ошибкой

#### Scenario: Использование ToolCallStatus
- **WHEN** используется ToolCallStatus
- **THEN** доступны значения PENDING, RUNNING, COMPLETED, FAILED

### Requirement: ToolCallState ACP Protocol Model

Система SHALL обновить `ToolCallState` как ACP Protocol Model:
- `toolCallId: str` — ACP идентификатор
- `title: str` — заголовок для UI
- `kind: ToolKind` — категория инструмента (read, edit, execute, etc.)
- `status: ToolCallStatus` — статус (ACP format)
- `content: list[dict[str, Any]] | None` — контент результата
- `locations: list[ToolCallLocation] | None` — затронутые файлы
- `rawInput: dict[str, Any] | None` — исходные аргументы
- `rawOutput: dict[str, Any] | None` — исходный результат

#### Scenario: ToolCallState как ACP Protocol Model
- **WHEN** используется ToolCallState
- **THEN** он соответствует ACP спецификации для tool calls

### Requirement: ToolCallState Docstring

`ToolCallState` SHALL иметь docstring с пометкой:
```python
"""ACP Protocol Model — контракт tool call согласно ACP 08-Tool Calls.

Wire format для session/update notification с sessionUpdate="tool_call"
и sessionUpdate="tool_call_update".

НЕ является domain моделью. Для бизнес-логики использовать domain ToolCall.
Конвертация через ToolCallMapper.
"""
```

#### Scenario: Docstring для ToolCallState
- **WHEN** определен ToolCallState
- **THEN** он содержит docstring с пометкой "ACP Protocol Model"

### Requirement: ToolCallMapper

Система SHALL предоставлять `ToolCallMapper` с методами:
- `to_protocol(domain: ToolCall) -> ToolCallState` — конвертировать domain в protocol
- `to_domain(protocol: ToolCallState) -> ToolCall` — конвертировать protocol в domain

#### Scenario: Конвертация domain в protocol
- **WHEN** вызывается `ToolCallMapper.to_protocol()` с ToolCall
- **THEN** возвращается ToolCallState

#### Scenario: Конвертация protocol в domain
- **WHEN** вызывается `ToolCallMapper.to_domain()` с ToolCallState
- **THEN** возвращается ToolCall

### Requirement: ToolCallMapper rawInput

`ToolCallMapper.to_protocol()` SHALL маппить:
- `domain.arguments` → `ToolCallState.rawInput`

#### Scenario: Маппинг arguments в rawInput
- **WHEN** конвертируется ToolCall в ToolCallState
- **THEN** `domain.arguments` маппится в `ToolCallState.rawInput`

### Requirement: ToolCallMapper rawOutput

`ToolCallMapper.to_protocol()` SHALL маппить:
- `domain.raw_output` → `ToolCallState.rawOutput`

#### Scenario: Маппинг raw_output в rawOutput
- **WHEN** конвертируется ToolCall в ToolCallState
- **THEN** `domain.raw_output` маппится в `ToolCallState.rawOutput`

### Requirement: ToolCallMapper locations

`ToolCallMapper.to_protocol()` SHALL маппить:
- `domain.locations` (list[FileLocation]) → `ToolCallState.locations` (list[dict])
- Формат: `[{"path": "...", "line": ...}, ...]`

#### Scenario: Маппинг locations
- **WHEN** конвертируется ToolCall в ToolCallState
- **THEN** `domain.locations` маппится в `ToolCallState.locations` в формате dict

### Requirement: ToolCallHandler create_tool_call с locations

`ToolCallHandler.create_tool_call()` SHALL принимать параметр `locations: list[FileLocation] | None` и сохранять его в `ToolCallState`.

#### Scenario: Создание tool call с locations
- **WHEN** вызывается `create_tool_call()` с locations
- **THEN** locations сохраняются в ToolCallState

### Requirement: ToolCallHandler build_tool_call_notification с rawInput

`ToolCallHandler.build_tool_call_notification()` SHALL принимать параметр `raw_input: dict[str, Any] | None` и включать его в notification как `rawInput`.

#### Scenario: Создание notification с rawInput
- **WHEN** вызывается `build_tool_call_notification()` с raw_input
- **THEN** rawInput включается в notification

### Requirement: ToolCallHandler build_tool_update_notification с rawOutput

`ToolCallHandler.build_tool_update_notification()` SHALL принимать параметры:
- `locations: list[FileLocation] | None` — включать как `locations`
- `raw_output: dict[str, Any] | None` — включать как `rawOutput`

#### Scenario: Создание update notification с locations и rawOutput
- **WHEN** вызывается `build_tool_update_notification()` с locations и raw_output
- **THEN** locations и rawOutput включаются в notification

### Requirement: AgentLoop передаёт locations из ToolExecutionResult

`AgentLoop` SHALL после выполнения tool передавать `result.locations` в `build_tool_update_notification()`.

#### Scenario: Передача locations после выполнения tool
- **WHEN** tool выполнен и возвращает ToolExecutionResult
- **THEN** `result.locations` передается в `build_tool_update_notification()`

### Requirement: AgentLoop передаёт rawInput из tool_arguments

`AgentLoop` SHALL при создании tool call передавать `tool_arguments` как `raw_input` в `build_tool_call_notification()`.

#### Scenario: Передача rawInput при создании tool call
- **WHEN** создается tool call
- **THEN** `tool_arguments` передаются как `raw_input` в notification

### Requirement: Удаление мёртвого кода

Система SHALL удалить `ToolCall` из `server/models.py` (не используется).

#### Scenario: Удаление мёртвого кода
- **WHEN** код не используется
- **THEN** он удаляется из `server/models.py`

### Requirement: Миграция ToolCallState

Система SHALL обновить `ToolCallState` с новыми полями `locations`, `rawInput`, `rawOutput`.

#### Scenario: Обновление ToolCallState
- **WHEN** используется ToolCallState
- **THEN** он содержит новые поля: locations, rawInput, rawOutput

# Spec: tool-call-models

## ДОБАВЛЕННЫЕ Требования

### Требование: Domain ToolCall

Система ДОЛЖНА предоставлять `ToolCall` как frozen dataclass в domain layer:
- `id: str` — уникальный идентификатор
- `tool_name: str` — имя инструмента
- `arguments: dict[str, Any]` — аргументы вызова
- `status: ToolCallStatus` — статус (domain enum)
- `result: ToolResult | None` — результат выполнения
- `locations: list[FileLocation]` — затронутые файлы
- `raw_output: dict[str, Any]` — исходный результат выполнения

### Требование: ToolCallStatus Domain Enum

Система ДОЛЖНА предоставлять domain enum `ToolCallStatus`:
- `PENDING` — ожидает выполнения
- `RUNNING` — выполняется
- `COMPLETED` — завершён успешно
- `FAILED` — завершён с ошибкой

### Требование: ToolCallState ACP Protocol Model

Система ДОЛЖНА обновить `ToolCallState` как ACP Protocol Model:
- `toolCallId: str` — ACP идентификатор
- `title: str` — заголовок для UI
- `kind: ToolKind` — категория инструмента (read, edit, execute, etc.)
- `status: ToolCallStatus` — статус (ACP format)
- `content: list[dict[str, Any]] | None` — контент результата
- `locations: list[ToolCallLocation] | None` — затронутые файлы
- `rawInput: dict[str, Any] | None` — исходные аргументы
- `rawOutput: dict[str, Any] | None` — исходный результат

### Требование: ToolCallState Docstring

`ToolCallState` ДОЛЖЕН иметь docstring с пометкой:
```python
"""ACP Protocol Model — контракт tool call согласно ACP 08-Tool Calls.

Wire format для session/update notification с sessionUpdate="tool_call"
и sessionUpdate="tool_call_update".

НЕ является domain моделью. Для бизнес-логики использовать domain ToolCall.
Конвертация через ToolCallMapper.
"""
```

### Требование: ToolCallMapper

Система ДОЛЖНА предоставлять `ToolCallMapper` с методами:
- `to_protocol(domain: ToolCall) -> ToolCallState` — конвертировать domain в protocol
- `to_domain(protocol: ToolCallState) -> ToolCall` — конвертировать protocol в domain

### Требование: ToolCallMapper rawInput

`ToolCallMapper.to_protocol()` ДОЛЖЕН маппить:
- `domain.arguments` → `ToolCallState.rawInput`

### Требование: ToolCallMapper rawOutput

`ToolCallMapper.to_protocol()` ДОЛЖЕН маппить:
- `domain.raw_output` → `ToolCallState.rawOutput`

### Требование: ToolCallMapper locations

`ToolCallMapper.to_protocol()` ДОЛЖЕН маппить:
- `domain.locations` (list[FileLocation]) → `ToolCallState.locations` (list[dict])
- Формат: `[{"path": "...", "line": ...}, ...]`

### Требование: ToolCallHandler create_tool_call с locations

`ToolCallHandler.create_tool_call()` ДОЛЖЕН принимать параметр `locations: list[FileLocation] | None` и сохранять его в `ToolCallState`.

### Требование: ToolCallHandler build_tool_call_notification с rawInput

`ToolCallHandler.build_tool_call_notification()` ДОЛЖЕН принимать параметр `raw_input: dict[str, Any] | None` и включать его в notification как `rawInput`.

### Требование: ToolCallHandler build_tool_update_notification с rawOutput

`ToolCallHandler.build_tool_update_notification()` ДОЛЖЕН принимать параметры:
- `locations: list[FileLocation] | None` — включать как `locations`
- `raw_output: dict[str, Any] | None` — включать как `rawOutput`

### Требование: AgentLoop передаёт locations из ToolExecutionResult

`AgentLoop` ДОЛЖЕН после выполнения tool передавать `result.locations` в `build_tool_update_notification()`.

### Требование: AgentLoop передаёт rawInput из tool_arguments

`AgentLoop` ДОЛЖЕН при создании tool call передавать `tool_arguments` как `raw_input` в `build_tool_call_notification()`.

### Требование: Удаление мёртвого кода

Система ДОЛЖНА удалить `ToolCall` из `server/models.py` (не используется).

### Требование: Миграция ToolCallState

Система ДОЛЖНА обновить `ToolCallState` с новыми полями `locations`, `rawInput`, `rawOutput`.

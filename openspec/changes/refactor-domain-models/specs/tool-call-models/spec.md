# Spec: tool-call-models

## ДОБАВЛЕННЫЕ Требования

### Требование: Domain ToolCall

Система ДОЛЖНА предоставлять `ToolCall` как frozen dataclass в domain layer:
- `id: str` — уникальный идентификатор
- `tool_name: str` — имя инструмента
- `arguments: dict[str, Any]` — аргументы вызова
- `status: ToolCallStatus` — статус (domain enum)
- `result: ToolResult | None` — результат выполнения

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

### Требование: Удаление мёртвого кода

Система ДОЛЖНА удалить `ToolCall` из `server/models.py` (не используется).

### Требование: Миграция ToolCallState

Система ДОЛЖНА обновить `ToolCallState` с новыми полями `locations`, `rawInput`, `rawOutput`.

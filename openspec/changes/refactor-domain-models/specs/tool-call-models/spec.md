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

### Требование: ToolCallDTO для ACP

Система ДОЛЖНА предоставлять `ToolCallDTO` как Pydantic модель в protocol layer:
- `toolCallId: str` — ACP идентификатор
- `title: str` — заголовок для UI
- `kind: ToolKind` — категория инструмента (read, edit, execute, etc.)
- `status: ToolCallStatus` — статус (ACP format)
- `content: list[dict[str, Any]] | None` — контент результата
- `locations: list[ToolCallLocationDTO] | None` — затронутые файлы
- `rawInput: dict[str, Any] | None` — исходные аргументы
- `rawOutput: dict[str, Any] | None` — исходный результат

### Требование: ToolCallMapper

Система ДОЛЖНА предоставлять `ToolCallMapper` с методами:
- `to_dto(domain: ToolCall) -> ToolCallDTO` — конвертировать domain в DTO
- `to_domain(dto: ToolCallDTO) -> ToolCall` — конвертировать DTO в domain

### Требование: Удаление мёртвого кода

Система ДОЛЖНА удалить `ToolCall` из `server/models.py` (не используется).

### Требование: Миграция ToolCallState

Система ДОЛЖНА заменить `ToolCallState` на `ToolCallDTO` в `SessionState`.

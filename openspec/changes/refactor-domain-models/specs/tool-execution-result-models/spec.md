# Spec: tool-execution-result-models

## ДОБАВЛЕННЫЕ Требования

### Требование: Domain FileLocation

Система ДОЛЖНА предоставлять `FileLocation` как frozen dataclass:
- `path: str` — путь к файлу
- `line: int | None` — номер строки

### Требование: Domain ToolResult

Система ДОЛЖНА предоставлять `ToolResult` как frozen dataclass:
- `success: bool` — успешность выполнения
- `output: str | None` — текстовый вывод
- `error: str | None` — сообщение об ошибке
- `metadata: dict[str, Any]` — метаданные
- `locations: list[FileLocation]` — затронутые файлы

### Требование: ToolExecutionResult без ACP content

Система ДОЛЖНА обновить `ToolExecutionResult`:
- Убрать `content: list[dict[str, Any]]` (ACP format)
- Использовать `locations: list[FileLocation]` (domain model)

### Требование: ToolResultMapper

Система ДОЛЖНА предоставлять `ToolResultMapper` с методами:
- `to_acp_content(result: ToolExecutionResult) -> list[dict]` — конвертировать в ACP content
- `from_tool_result(result: ToolExecutionResult) -> ToolResult` — конвертировать в domain ToolResult

### Требование: Миграция ToolExecutionResult

Система ДОЛЖНА мигрировать все executors для использования `FileLocation` вместо `content`.

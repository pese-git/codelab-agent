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
- `raw_output: dict[str, Any]` — исходный результат выполнения

### Требование: ToolExecutionResult без ACP content

Система ДОЛЖНА обновить `ToolExecutionResult`:
- Убрать `content: list[dict[str, Any]]` (ACP format)
- Использовать `locations: list[FileLocation]` (domain model)
- Добавить `raw_output: dict[str, Any]` (ACP raw output)

### Требование: ToolExecutionResult raw_output

`ToolExecutionResult` ДОЛЖЕН содержать `raw_output: dict[str, Any]` — исходный результат выполнения инструмента для ACP `rawOutput`.

### Требование: raw_output для fs/read_text_file

`FileSystemToolExecutor.execute_read()` ДОЛЖЕН возвращать `raw_output`:
```python
raw_output={
    "content": content,           # Сырое содержимое файла
    "bytes_read": len(content),   # Количество прочитанных байт
}
```

### Требование: raw_output для fs/write_text_file

`FileSystemToolExecutor.execute_write()` ДОЛЖЕН возвращать `raw_output`:
```python
raw_output={
    "bytes_written": len(content),  # Количество записанных байт
    "diff": diff_text,              # Diff если доступен
}
```

### Требование: raw_output для terminal/create

`TerminalToolExecutor.execute_create()` ДОЛЖЕН возвращать `raw_output`:
```python
raw_output={
    "terminal_id": terminal_id,  # ID созданного терминала
}
```

### Требование: raw_output для terminal/wait_for_exit

`TerminalToolExecutor.execute_wait_for_exit()` ДОЛЖЕН возвращать `raw_output`:
```python
raw_output={
    "exit_code": exit_code,  # Код выхода (может быть null)
    "signal": signal,        # Сигнал (может быть null)
    "output": output,        # Вывод терминала
}
```

### Требование: raw_output для MCP tools

`MCPToolExecutor.execute()` ДОЛЖЕН возвращать `raw_output`:
```python
raw_output={
    "result": result,  # Сырой результат от MCP сервера
}
```

### Требование: locations для fs/read_text_file

`FileSystemToolExecutor.execute_read()` ДОЛЖЕН возвращать `locations`:
```python
locations=[FileLocation(path=path, line=line)]
```

### Требование: locations для fs/write_text_file

`FileSystemToolExecutor.execute_write()` ДОЛЖЕН возвращать `locations`:
```python
locations=[FileLocation(path=path)]
```

### Требование: locations для terminal tools

`TerminalToolExecutor` НЕ ДОЛЖЕН возвращать `locations` (терминалы не имеют file locations).

### Требование: locations для MCP tools

`MCPToolExecutor` НЕ ДОЛЖЕН возвращать `locations` (MCP tools работают с внешними ресурсами, не с файлами IDE).

### Требование: ToolResultMapper

Система ДОЛЖНА предоставлять `ToolResultMapper` с методами:
- `to_acp_content(result: ToolExecutionResult) -> list[dict]` — конвертировать в ACP content
- `from_tool_result(result: ToolExecutionResult) -> ToolResult` — конвертировать в domain ToolResult

### Требование: Миграция ToolExecutionResult

Система ДОЛЖНА мигрировать все executors для использования `FileLocation` вместо `content`.

### Требование: Миграция executors с raw_output

Система ДОЛЖНА мигрировать все executors для возврата `raw_output` согласно требованиям выше.

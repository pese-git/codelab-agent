# Spec: tool-execution-result-models

## ADDED Requirements

### Requirement: Domain FileLocation

Система SHALL предоставлять `FileLocation` как frozen dataclass:
- `path: str` — путь к файлу
- `line: int | None` — номер строки

#### Scenario: Создание FileLocation
- **WHEN** создается FileLocation
- **THEN** объект содержит поля `path` и `line`

#### Scenario: FileLocation как frozen dataclass
- **WHEN** создан FileLocation объект
- **THEN** его поля нельзя изменить (immutable)

### Requirement: Domain ToolResult

Система SHALL предоставлять `ToolResult` как frozen dataclass:
- `success: bool` — успешность выполнения
- `output: str | None` — текстовый вывод
- `error: str | None` — сообщение об ошибке
- `metadata: dict[str, Any]` — метаданные
- `locations: list[FileLocation]` — затронутые файлы
- `raw_output: dict[str, Any]` — исходный результат выполнения

#### Scenario: Создание ToolResult
- **WHEN** создается ToolResult
- **THEN** объект содержит все поля: success, output, error, metadata, locations, raw_output

### Requirement: ToolExecutionResult без ACP content

Система SHALL обновить `ToolExecutionResult`:
- Убрать `content: list[dict[str, Any]]` (ACP format)
- Использовать `locations: list[FileLocation]` (domain model)
- Добавить `raw_output: dict[str, Any]` (ACP raw output)

#### Scenario: ToolExecutionResult без ACP content
- **WHEN** используется ToolExecutionResult
- **THEN** он не содержит поле `content`, только `locations` и `raw_output`

### Requirement: ToolExecutionResult raw_output

`ToolExecutionResult` SHALL содержать `raw_output: dict[str, Any]` — исходный результат выполнения инструмента для ACP `rawOutput`.

#### Scenario: Наличие raw_output
- **WHEN** создается ToolExecutionResult
- **THEN** он содержит поле `raw_output` для ACP rawOutput

### Requirement: raw_output для fs/read_text_file

`FileSystemToolExecutor.execute_read()` SHALL возвращать `raw_output`:
```python
raw_output={
    "content": content,           # Сырое содержимое файла
    "bytes_read": len(content),   # Количество прочитанных байт
}
```

#### Scenario: raw_output для чтения файла
- **WHEN** выполняется fs/read_text_file
- **THEN** raw_output содержит `content` и `bytes_read`

### Requirement: raw_output для fs/write_text_file

`FileSystemToolExecutor.execute_write()` SHALL возвращать `raw_output`:
```python
raw_output={
    "bytes_written": len(content),  # Количество записанных байт
    "diff": diff_text,              # Diff если доступен
}
```

#### Scenario: raw_output для записи файла
- **WHEN** выполняется fs/write_text_file
- **THEN** raw_output содержит `bytes_written` и `diff` (если доступен)

### Requirement: raw_output для terminal/create

`TerminalToolExecutor.execute_create()` SHALL возвращать `raw_output`:
```python
raw_output={
    "terminal_id": terminal_id,  # ID созданного терминала
}
```

#### Scenario: raw_output для создания терминала
- **WHEN** выполняется terminal/create
- **THEN** raw_output содержит `terminal_id`

### Requirement: raw_output для terminal/wait_for_exit

`TerminalToolExecutor.execute_wait_for_exit()` SHALL возвращать `raw_output`:
```python
raw_output={
    "exit_code": exit_code,  # Код выхода (может быть null)
    "signal": signal,        # Сигнал (может быть null)
    "output": output,        # Вывод терминала
}
```

#### Scenario: raw_output для ожидания завершения терминала
- **WHEN** выполняется terminal/wait_for_exit
- **THEN** raw_output содержит `exit_code`, `signal`, `output`

### Requirement: raw_output для MCP tools

`MCPToolExecutor.execute()` SHALL возвращать `raw_output`:
```python
raw_output={
    "result": result,  # Сырой результат от MCP сервера
}
```

#### Scenario: raw_output для MCP tools
- **WHEN** выполняется MCP tool
- **THEN** raw_output содержит `result` от MCP сервера

### Requirement: locations для fs/read_text_file

`FileSystemToolExecutor.execute_read()` SHALL возвращать `locations`:
```python
locations=[FileLocation(path=path, line=line)]
```

#### Scenario: locations для чтения файла
- **WHEN** выполняется fs/read_text_file
- **THEN** locations содержит FileLocation с path и line

### Requirement: locations для fs/write_text_file

`FileSystemToolExecutor.execute_write()` SHALL возвращать `locations`:
```python
locations=[FileLocation(path=path)]
```

#### Scenario: locations для записи файла
- **WHEN** выполняется fs/write_text_file
- **THEN** locations содержит FileLocation с path

### Requirement: locations для terminal tools

`TerminalToolExecutor` SHALL NOT возвращать `locations` (терминалы не имеют file locations).

#### Scenario: Отсутствие locations для terminal tools
- **WHEN** выполняется terminal tool
- **THEN** locations пустой список

### Requirement: locations для MCP tools

`MCPToolExecutor` SHALL NOT возвращать `locations` (MCP tools работают с внешними ресурсами, не с файлами IDE).

#### Scenario: Отсутствие locations для MCP tools
- **WHEN** выполняется MCP tool
- **THEN** locations пустой список

### Requirement: ToolResultMapper

Система SHALL предоставлять `ToolResultMapper` с методами:
- `to_acp_content(result: ToolExecutionResult) -> list[dict]` — конвертировать в ACP content
- `from_tool_result(result: ToolExecutionResult) -> ToolResult` — конвертировать в domain ToolResult

#### Scenario: Конвертация в ACP content
- **WHEN** вызывается `to_acp_content()` с ToolExecutionResult
- **THEN** возвращается список dict в ACP content format

#### Scenario: Конвертация в domain ToolResult
- **WHEN** вызывается `from_tool_result()` с ToolExecutionResult
- **THEN** возвращается domain ToolResult объект

### Requirement: Миграция ToolExecutionResult

Система SHALL мигрировать все executors для использования `FileLocation` вместо `content`.

#### Scenario: Миграция executors
- **WHEN** executors возвращают результаты
- **THEN** они используют `FileLocation` вместо `content`

### Requirement: Миграция executors с raw_output

Система SHALL мигрировать все executors для возврата `raw_output` согласно требованиям выше.

#### Scenario: Миграция executors с raw_output
- **WHEN** executors возвращают результаты
- **THEN** они возвращают `raw_output` согласно спецификации для каждого типа инструмента

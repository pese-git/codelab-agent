# Spec: follow-along

## ADDED Requirements

### Требование: FileOpener Protocol

Система ДОЛЖНА предоставлять `FileOpener` Protocol в `client/infrastructure/services/follow_along.py`:
```python
class FileOpener(Protocol):
    async def open(self, path: str, line: int | None = None) -> None: ...
```

### Требование: StubFileOpener

Система ДОЛЖНА предоставлять `StubFileOpener` для тестов — реализация `FileOpener`, которая логирует вызовы без реального открытия файлов.

### Требование: FollowAlongService

Система ДОЛЖНА предоставлять `FollowAlongService` в `client/infrastructure/services/follow_along.py`:
- `__init__(file_opener: FileOpener, enabled: bool = True)` — инициализация
- `async on_tool_call_updated(tool_call: dict[str, Any]) -> None` — обработка обновления tool call

### Требование: FollowAlongService поведение

`FollowAlongService.on_tool_call_updated()` ДОЛЖЕН:
1. Проверить `enabled` флаг — если False, вернуть немедленно
2. Извлечь `locations` из tool_call
3. Если `locations` пуст — вернуть
4. Взять первую локацию: `locations[0]`
5. Вызвать `file_opener.open(path, line)`

### Требование: FollowAlongService интеграция в ToolCallHandler

Клиентский `ToolCallHandler` ДОЛЖЕН:
1. Принимать опциональный `follow_along: FollowAlongService | None` в конструктор
2. В `_handle_tool_call_updated()` после обновления состояния вызывать `follow_along.on_tool_call_updated()` если сервис доступен

### Требование: ToolCallHandler сохраняет locations

`ToolCallHandler._handle_tool_call_created()` ДОЛЖЕН сохранять `locations` из update:
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

### Требование: ToolCallHandler обновляет locations

`ToolCallHandler._handle_tool_call_updated()` ДОЛЖЕН обновлять `locations` и `rawOutput`:
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

### Требование: Feature flag не нужен

Follow-along НЕ ДОЛЖЕН требовать feature flag:
- Это стандартная функция IDE
- Если tool call не имеет `locations` — follow-along не срабатывает
- Нет риска поломки существующего функционала

### Требование: FollowAlongService unit тесты

Система ДОЛЖНА предоставлять unit тесты для `FollowAlongService`:
- Тест: `enabled=False` — не вызывает file_opener
- Тест: `locations` пуст — не вызывает file_opener
- Тест: `locations` содержит один элемент — вызывает `open(path, line)`
- Тест: `locations` содержит несколько элементов — вызывает `open()` для первого

### Требование: ToolCallHandler integration тесты

Система ДОЛЖНА предоставлять integration тесты:
- Тест: tool_call update с locations вызывает follow_along
- Тест: tool_call update без locations не вызывает follow_along
- Тест: tool_call created сохраняет locations, rawInput, rawOutput

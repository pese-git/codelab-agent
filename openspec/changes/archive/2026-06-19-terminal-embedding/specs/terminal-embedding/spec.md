# Spec: terminal-embedding

## ДОБАВЛЕННЫЕ Требования

### Требование: ContentValidator поддерживает terminal и content типы

Система ДОЛЖНА поддерживать `terminal` и `content` типы в `ContentValidator`:
- `SUPPORTED_TYPES` ДОЛЖЕН содержать `"terminal"` и `"content"`
- `REQUIRED_FIELDS` ДОЛЖЕН содержать:
  - `{"type", "terminalId"}` для terminal типа
  - `{"type", "content"}` для content типа (обёртка для ContentBlock)

### Требование: ToolExecutionResult имеет поле content

`ToolExecutionResult` ДОЛЖЕН иметь опциональное поле `content`:
```python
@dataclass
class ToolExecutionResult:
    # ... существующие поля ...
    content: list[dict[str, Any]] | None = None  # ToolCallContent items
```

Поле ДОЛЖНО хранить готовые ToolCallContent items для передачи клиенту.

### Требование: ToolResultMapper проверяет result.content

`ToolResultMapper.to_acp_content()` ДОЛЖЕН:
- Проверять `result.content` — если задан, возвращать его as-is
- Иначе — fallback на текущую логику (text из output)

```python
@staticmethod
def to_acp_content(result: ToolExecutionResult) -> list[dict[str, Any]]:
    if result.content is not None:
        return result.content
    # fallback...
```

### Требование: TerminalToolExecutor возвращает terminal content

`TerminalToolExecutor.execute_create()` ДОЛЖЕН возвращать `ToolExecutionResult` с `content`:
```python
content = [
    {"type": "terminal", "terminalId": terminal_id},
    {"type": "content", "content": {"type": "text", "text": "..."}},
]
```

### Требование: AgentLoop передаёт extracted content

`AgentLoop` ДОЛЖЕН передавать `extracted_content.content_items` в `build_tool_update_notification()`:
- Если `extracted_content.content_items` не пустой — использовать его
- Иначе — fallback на text content из `result.output`

### Требование: Клиентский ToolCallHandler сохраняет content

Клиентский `ToolCallHandler` ДОЛЖЕН сохранять `content` из tool call updates:
- `_handle_tool_call_created()` — сохранять `update.get("content")`
- `_handle_tool_call_updated()` — обновлять `content` если присутствует

### Требование: Обратная совместимость со slash-командами

Slash-команды (`/term-run`) ДОЛЖНЫ продолжать работать как раньше:
- Генерация terminal content в `prompt.py` не изменяется
- Terminal embedding для LLM tool calls — дополнение, не замена

### Требование: Unit тесты для ContentValidator

Система ДОЛЖНА предоставлять unit тесты:
- Тест: `terminal` тип проходит валидацию
- Тест: `terminal` без `terminalId` не проходит валидацию
- Тест: `content` тип проходит валидацию
- Тест: `content` без `content` поля не проходит валидацию

### Требование: Unit тесты для ToolResultMapper

Система ДОЛЖНА предоставлять unit тесты:
- Тест: `to_acp_content()` возвращает `result.content` если задан
- Тест: `to_acp_content()` fallback на text если content не задан

### Требование: Unit тесты для TerminalToolExecutor

Система ДОЛЖНА предоставлять unit тесты:
- Тест: `execute_create()` возвращает terminal content
- Тест: terminal content содержит `terminalId`

### Требование: Unit тесты для AgentLoop

Система ДОЛЖНА предоставлять unit тесты:
- Тест: передаёт `extracted_content.content_items` в notification
- Тест: fallback на text если content пустой

### Требование: Unit тесты для клиентского ToolCallHandler

Система ДОЛЖНА предоставлять unit тесты:
- Тест: `_handle_tool_call_created()` сохраняет content
- Тест: `_handle_tool_call_updated()` обновляет content

### Требование: Integration тест

Система ДОЛЖНА предоставлять integration тест:
- Тест: LLM вызывает terminal tool → клиент получает terminal content в notification

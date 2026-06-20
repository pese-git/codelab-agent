# Design: Terminal Embedding в Tool Calls

## Контекст

ACP спецификация определяет механизм встраивания live terminal output в tool calls через content type `terminal`. Это позволяет клиентам отображать реальный вывод терминала в контексте выполнения инструмента, обеспечивая лучшую видимость процесса выполнения.

**Текущая реализация:**
- Slash-команды (`/term-run`) уже используют terminal embedding
- LLM tool calls не используют — executor возвращает только text
- Клиентская модель готова, но handler не сохраняет content

## Цели / Не цели

**Цели:**
- Включить terminal embedding для LLM tool calls
- Обеспечить передачу terminal content через весь pipeline
- Сохранить обратную совместимость со slash-командами

**Не цели:**
- Реализация live terminal output на клиенте (это UI-фича)
- Изменение slash-команд (они уже работают)
- Поддержка других content types (image, audio) — отдельная задача

## Решения

### Решение 1: ContentValidator — добавить terminal и content типы

**Проблема:** `ContentValidator.SUPPORTED_TYPES` не содержит `terminal` и `content`.

**Решение:**
```python
# server/protocol/content/validator.py
SUPPORTED_TYPES = {
    "text", "diff", "image", "audio", "embedded", "resource_link",
    "terminal",  # NEW — для embedding terminal в tool calls
    "content",   # NEW — обёртка для стандартных ContentBlock в ToolCallContent
}

REQUIRED_FIELDS = {
    # ... существующие ...
    "terminal": {"type", "terminalId"},  # NEW
    "content": {"type", "content"},      # NEW — обёртка для ContentBlock
}
```

**Обоснование:**
- Соответствует ACP спецификации (08-Tool Calls.md, 17-Schema.md ToolCallContent)
- `ToolCallContent` — это union из трёх вариантов: `content`, `diff`, `terminal`
- Executor возвращает `{"type": "content", "content": {...}}` — нужна валидация
- Минимальное изменение — добавить типы и обязательные поля
- Не влияет на существующую валидацию

**Примечание:** Pre-existing баг — `"diff": {"type", "path", "diff"}` не соответствует ACP Schema (должно быть `{"type", "path", "oldText", "newText"}`). Не исправляется в рамках этой задачи.

### Решение 1.5: ToolExecutionResult и ToolResultMapper — поддержка ToolCallContent

**Проблема:** `ToolExecutionResult` не имеет поля для хранения готовых ToolCallContent items. `ToolResultMapper.to_acp_content()` возвращает ContentBlocks (`{type: "text", text: ...}`), а не ToolCallContent items (`{type: "content", content: {...}}`).

**Решение:**

1. Добавить опциональное поле `content` в `ToolExecutionResult`:
```python
# server/tools/base.py
@dataclass
class ToolExecutionResult:
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    locations: list[FileLocation] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)
    content: list[dict[str, Any]] | None = None  # NEW — ToolCallContent items
```

2. Обновить `ToolResultMapper.to_acp_content()` для проверки поля `content`:
```python
# server/mapping/tool_result_mapper.py
@staticmethod
def to_acp_content(result: ToolExecutionResult) -> list[dict[str, Any]]:
    # Если executor задал готовый ToolCallContent — использовать его
    if result.content is not None:
        return result.content
    
    # Fallback: конвертировать output в text ContentBlock
    blocks: list[dict[str, Any]] = []
    if result.output:
        blocks.append({"type": "text", "text": result.output})
    return blocks
```

**Обоснование:**
- Разделяет ответственность: executor формирует ToolCallContent, mapper только конвертирует
- Обратная совместимость: если `content` не задан — работает как раньше
- Позволяет executor'ам возвращать сложные content items (terminal, diff, content)
- Соответствует ACP ToolCallContent union type

### Решение 2: TerminalToolExecutor — возвращать terminal content

**Проблема:** `execute_create()` возвращает только text content.

**Решение:**
```python
# server/tools/executors/terminal_executor.py
async def execute_create(self, session, command, args, env, cwd, output_byte_limit):
    # ... существующий код ...
    
    # Сгенерировать ToolCallContent items для отправки клиенту и LLM
    # Формат соответствует ACP ToolCallContent union (17-Schema.md)
    content_items = [
        {
            "type": "terminal",
            "terminalId": terminal_id,
        },
        {
            "type": "content",
            "content": {
                "type": "text",
                "text": f"Terminal {terminal_id} created for command: {command}",
            },
        },
    ]
    
    return ToolExecutionResult(
        success=True,
        output=f"Терминал создан с ID: {terminal_id}",
        metadata={"terminal_id": terminal_id, "command": command},
        raw_output={"terminal_id": terminal_id},
        content=content_items,  # NEW — ToolCallContent items
    )
```

**Обоснование:**
- Соответствует ACP спецификации (10-Terminal.md: Embedding in Tool Calls, 17-Schema.md ToolCallContent)
- Terminal content идёт первым — клиент может сразу начать отображение
- Text content (обёрнутый в `{type: "content", content: {...}}`) остаётся для LLM как fallback
- Поле `content` в `ToolExecutionResult` передаётся через `ToolResultMapper.to_acp_content()` без изменений

### Решение 3: AgentLoop — передавать extracted content

**Проблема:** `AgentLoop` игнорирует `extracted_content.content_items` и передаёт только text.

**Решение:**
```python
# server/protocol/handlers/pipeline/stages/agent_loop.py
# Было (строки 671-675):
notification_content = None
if result.success and result.output:
    notification_content = [
        {"type": "content", "content": {"type": "text", "text": result.output}}
    ]

# Стало:
# extracted_content.content_items уже содержит ToolCallContent items
# (благодаря обновлённому ToolResultMapper.to_acp_content())
notification_content = (
    extracted_content.content_items
    if extracted_content.content_items
    else (
        [{"type": "content", "content": {"type": "text", "text": result.output}}]
        if result.success and result.output
        else None
    )
)
```

**Обоснование:**
- Приоритет: extracted content > text output
- `extracted_content.content_items` уже в формате ToolCallContent (благодаря Решению 1.5)
- Fallback на text если extracted content пустой (обратная совместимость)
- Не ломает существующие executors которые возвращают только text

### Решение 4: Клиентский ToolCallHandler — сохранять content

**Проблема:** Клиентский `ToolCallHandler` не сохраняет `content` из updates.

**Решение:**
```python
# client/presentation/chat/handlers/tool_call_handler.py
def _handle_tool_call_created(self, update, context):
    tool_call = {
        "toolCallId": tool_call_id,
        "title": title,
        "status": status,
        "kind": kind,
        "content": update.get("content"),  # NEW
    }
    # ...

def _handle_tool_call_updated(self, update, context):
    updates = {}
    if status:
        updates["status"] = status
    if title:
        updates["title"] = title
    if content := update.get("content"):  # NEW
        updates["content"] = content
    # ...
```

**Обоснование:**
- Минимальное изменение — добавить одно поле
- Сохраняет content для дальнейшего использования UI
- Не ломает существующую логику

## Зависимости между решениями

```
Решение 1 (ContentValidator) — независимо
Решение 1.5 (ToolExecutionResult + ToolResultMapper) — независимо
Решение 2 (TerminalToolExecutor) — зависит от Решения 1.5
Решение 3 (AgentLoop) — зависит от Решений 1 и 2
Решение 4 (Client ToolCallHandler) — зависит от Решения 3
```

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Поломать slash-команды | Низкая | Высокое | Unit тесты для `/term-run` |
| Клиент не обрабатывает terminal content | Низкая | Среднее | Integration тесты |
| LLM не понимает terminal content | Низкая | Среднее | Text content остаётся как fallback |
| Неверный формат ToolCallContent | Низкая | Среднее | Валидация в ContentValidator, unit тесты |

## Известные проблемы (не исправляются в рамках этой задачи)

- `ContentValidator.REQUIRED_FIELDS["diff"]` содержит `{"type", "path", "diff"}`, но ACP Schema определяет `{type, path, oldText, newText}`. Это pre-existing баг, не связанный с terminal embedding.

## План внедрения

См. `tasks.md` для детального плана.

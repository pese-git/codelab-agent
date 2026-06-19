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

### Решение 1: ContentValidator — добавить terminal тип

**Проблема:** `ContentValidator.SUPPORTED_TYPES` не содержит `terminal`.

**Решение:**
```python
# server/protocol/content/validator.py
SUPPORTED_TYPES = {
    "text", "diff", "image", "audio", "embedded", "resource_link",
    "terminal",  # NEW
}

REQUIRED_FIELDS = {
    # ... существующие ...
    "terminal": {"type", "terminalId"},  # NEW
}
```

**Обоснование:**
- Соответствует ACP спецификации (08-Tool Calls.md)
- Минимальное изменение — добавить тип и обязательные поля
- Не влияет на существующую валидацию

### Решение 2: TerminalToolExecutor — возвращать terminal content

**Проблема:** `execute_create()` возвращает только text content.

**Решение:**
```python
# server/tools/executors/terminal_executor.py
async def execute_create(self, session, command, args, env, cwd, output_byte_limit):
    # ... существующий код ...
    
    # Сгенерировать content для отправки клиенту и LLM согласно ACP Content Types
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
        content=content_items,
    )
```

**Обоснование:**
- Соответствует ACP спецификации (10-Terminal.md: Embedding in Tool Calls)
- Terminal content идёт первым — клиент может сразу начать отображение
- Text content остаётся для LLM (fallback для моделей без terminal support)

### Решение 3: AgentLoop — передавать extracted content

**Проблема:** `AgentLoop` игнорирует `extracted_content.content_items` и передаёт только text.

**Решение:**
```python
# server/protocol/handlers/pipeline/stages/agent_loop.py
# Было:
notification_content = None
if result.success and result.output:
    notification_content = [
        {"type": "content", "content": {"type": "text", "text": result.output}}
    ]

# Стало:
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
- Fallback на text если extracted content пустой
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
Решение 2 (TerminalToolExecutor) — зависит от Решения 1
Решение 3 (AgentLoop) — зависит от Решения 2
Решение 4 (Client ToolCallHandler) — зависит от Решения 3
```

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Поломать slash-команды | Низкая | Высокое | Unit тесты для `/term-run` |
| Клиент не обрабатывает terminal content | Низкая | Среднее | Integration тесты |
| LLM не понимает terminal content | Низкая | Среднее | Text content остаётся как fallback |

## План внедрения

См. `tasks.md` для детального плана.

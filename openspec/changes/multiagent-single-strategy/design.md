## Design

### Архитектура SingleStrategy

SingleStrategy — базовая стратегия выполнения, вызывает единственного агента через EventBus. Принцип uniformity — тот же паттерн вызова, что и все остальные стратегии.

### Композиция ExecutionEngine

```python
class ExecutionEngine:
    _history_builder: HistoryBuilder      # session.history → LLMMessage
    _tool_filter: ToolFilter              # filter by capabilities
    _sanitizer: MessageSanitizer          # fix orphaned tool calls
    _plan_extractor: PlanExtractor        # extract plan from response
    _compactor: ContextCompactor          # prune + summarize
```

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Через EventBus | Uniformity, observability, testing |
| Композиция вместо монолита | Тестируемость, расширяемость |
| Compaction fallback | Двухфазный: Prune → LLM Summarize |
| Без Token-Slicing | Нет субагентов — не нужно сжимать |

### Compaction Flow

```
1. Перед LLM call: check context tokens
2. Если > trigger (limit - reserved):
   a. Prune: удалить старые tool outputs (FIFO, без LLM)
   b. Если недостаточно → LLM Summarize: сжать середину conversation
3. Сохранить первые 2 сообщения (system + initial prompt)
4. Сохранить последние 3 сообщения (recent context)
```

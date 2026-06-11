## Design

### Архитектура LLMAdapter

LLMAdapter заменяет NaiveAgent как реализация Agent Protocol. Ключевое отличие — сохранение `usage` (токены) и интеграция с observability (Tracer, MetricsTracker, EventTimeline).

### Композиция

```python
class LLMAdapter:
    _llm_provider: LLMProvider          # мульти-провайдер
    _tool_registry: ToolRegistry        # инструменты
    _tracer: Tracer                     # tracing
    _event_bus: AgentEventBus           # регистрация как handler
    _active_tasks: dict[str, asyncio.Task]  # cancellation
```

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Agent Protocol | Единый контракт для всех стратегий |
| Registration в EventBus | Point-to-point вызов через send_request |
| Tracer span per call | Вложенность: strategy → bus → llm_call |
| Usage preservation | Было потеряно в NaiveAgent — критично для observability |
| Cancellation via Task | Сохранение существующего паттерна |

### Flow вызова

```
1. EventBus → LLMAdapter.call(messages, tools, config, parent_span)
2. Tracer.start_span("llm_call", parent=parent_span)
3. LLMProvider.create_completion(messages, tools)
4. Если tool_calls → execute tools → continue loop
5. Build AgentResult(text, tool_calls, usage, stop_reason)
6. Tracer.end_span(usage, latency)
7. Return AgentResult
```

### Cancellation

```python
async def call(...):
    task = asyncio.create_task(self._execute(messages, tools))
    self._active_tasks[id(task)] = task
    try:
        return await task
    except asyncio.CancelledError:
        return AgentResult(text="", tool_calls=[], usage=TokenUsage(), stop_reason="cancelled", agent_name=self._name)
    finally:
        self._active_tasks.pop(id(task), None)
```

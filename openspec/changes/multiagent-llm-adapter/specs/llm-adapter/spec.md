# Spec: llm-adapter

## ДОБАВЛЕННЫЕ Требования

### Требование: Реализация Agent Protocol

Система ДОЛЖНА предоставлять `LLMAdapter`, реализующий протокол `Agent`:

```python
async def call(
    messages: list[Message],
    tools: list[ToolDefinition] | None = None,
    config: AgentConfig | None = None,
    parent_span: SpanContext | None = None,
) -> AgentResult:
```

### Требование: Цикл LLM вызовов

LLMAdapter ДОЛЖЕН:
- Вызывать LLM провайдер с messages и tools
- Выполнять tool calls если присутствуют (максимум 5 итераций)
- Возвращать AgentResult с text, tool_calls, usage, stop_reason
- Поддерживать отмену через asyncio.Task

### Требование: Регистрация в EventBus

LLMAdapter ДОЛЖЕН регистрировать себя как `RequestHandler` в AgentEventBus:

```python
async def _handle_request(request: AgentRequest, parent_span: SpanContext | None) -> AgentResponse:
    result = await self.call(request.messages, request.tools, parent_span=parent_span)
    return AgentResponse(
        request_id=request.correlation_id,
        text=result.text,
        tool_calls=result.tool_calls,
        usage=result.usage,
        stop_reason=result.stop_reason,
        agent_name=result.agent_name,
    )
```

### Требование: Поддержка отмены

LLMAdapter ДОЛЖЕН поддерживать отмену через `asyncio.Task`:
- Отслеживать активные задачи в dict `_active_tasks`
- Возвращать `AgentResult(stop_reason="cancelled")` при отмене
- Очищать ссылку на задачу при завершении

# Spec: agent-result-usage

## ДОБАВЛЕННЫЕ Требования

### Требование: Сохранение TokenUsage

`AgentResult` ДОЛЖЕН включать поле `usage: TokenUsage` с:
- `input_tokens: int`
- `output_tokens: int`
- `total_tokens: int`

Эта информация ДОЛЖНА сохраняться из ответа LLM провайдера и не теряться при обработке.

# Spec: llm-tracing

## ДОБАВЛЕННЫЕ Требования

### Требование: Tracer Span для каждого LLM вызова

Каждый LLM вызов ДОЛЖЕН создавать span трассировки с:
- Имя: "llm_call"
- Родитель: parent_span из AgentRequest
- Атрибуты: model, provider, input_tokens, output_tokens, latency_ms

### Требование: Распространение контекста Span

LLMAdapter ДОЛЖЕН распространять контекст span через цепочку вызовов:
- parent_span → span LLM вызова → spans выполнения инструментов

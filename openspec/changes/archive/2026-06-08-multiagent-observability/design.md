## Design

### Архитектура Observability

Observability состоит из 3 компонентов, подписанных на EventBus:

1. **Tracer** — span hierarchy с context propagation
2. **EventTimeline** — хронология событий для debug mode
3. **MetricsTracker** — автолог метрик

### Span Hierarchy

```
strategy_execution (root)
└── bus_request
    └── llm_call
        └── tool_execution (если есть)
```

### Интеграция с существующим кодом

- `structlog` уже используется для логирования — Tracer дополняет, не заменяет
- EventTimeline подписывается на `AbstractEventBus` (новый интерфейс)
- MetricsTracker — полностью новый компонент
- SpanContext передаётся через `parent_span` параметр в `send_request()`
- TokenSlicer создаёт span `token_slicing` с атрибутами: original_tokens, sliced_tokens, compression_ratio, slicer_latency_ms

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Pluggable exporters | Post-MVP: OpenTelemetry, Langfuse |
| Подписка на EventBus | Автоматический сбор без изменения стратегий |
| Span context propagation | Tracing через весь call chain |
| Debug mode flag | Полные логи только когда нужно |

### Metrics

| Метрика | Источник | Когда |
|---|---|---|
| bus_dispatch_latency_ms | EventBus.publish | Каждый dispatch |
| llm_call_latency_ms | LLMAdapter.call() | Каждый LLM call |
| input_tokens / output_tokens | AgentResult.usage | Каждый response |
| compression_ratio | ContextCompactor | После compaction |
| slicer_original_tokens | TokenSlicer.slice() | После slicing |
| slicer_sliced_tokens | TokenSlicer.slice() | После slicing |
| slicer_latency_ms | TokenSlicer.slice() | После slicing |
| strategy_execution_time | Strategy.execute() | За turn |

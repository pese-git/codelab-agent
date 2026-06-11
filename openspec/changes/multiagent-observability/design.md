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
| llm_call_latency_ms | LLMAdapter | Каждый LLM call |
| input_tokens / output_tokens | AgentResponse.usage | Каждый response |
| compression_ratio | TokenSlicer | После slicing |
| strategy_execution_time | Strategy | За turn |

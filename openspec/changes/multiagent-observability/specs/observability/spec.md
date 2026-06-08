# Spec: agent-tracing

## ДОБАВЛЕННЫЕ Требования

### Требование: Интерфейс Tracer

Система ДОЛЖНА предоставлять `Tracer` с методами:
- `start_span(name: str, parent: SpanContext | None = None) -> SpanContext`
- `end_span(span: SpanContext, attributes: dict | None = None) -> None`
- `get_current_span() -> SpanContext | None`

### Требование: Иерархия Span

Tracer ДОЛЖЕН поддерживать вложенные span'ы:
- strategy_execution → bus_request → llm_call → tool_execution
- Каждый span наследует родительский контекст для корреляции трейса

### Требование: Атрибуты Span

Каждый span ДОЛЖЕН поддерживать произвольные атрибуты key-value:
- llm_call: model, provider, input_tokens, output_tokens, latency_ms
- bus_request: target_agent, dispatch_latency_ms
- strategy_execution: strategy_name, total_time_ms
- token_slicing: original_tokens, sliced_tokens, compression_ratio, slicer_latency_ms, was_skipped

### Требование: Распространение контекста

Tracer ДОЛЖЕН распространять контекст span через:
- AgentRequest → параметр parent_span
- EventBus.send_request(request, parent_span)
- LLMAdapter.call(..., parent_span)

# Spec: event-timeline

## ДОБАВЛЕННЫЕ Требования

### Требование: Запись EventTimeline

Система ДОЛЖНА предоставлять `EventTimeline`, который записывает события с:
- `timestamp: float` — ISO timestamp
- `event_type: str` — имя типа
- `session_id: str` — ассоциированная сессия
- `details: dict` — payload события

### Требование: Подписка EventTimeline

EventTimeline ДОЛЖЕН подписаться на `AbstractEventBus` для:
- AgentRegistered, AgentUnregistered, AgentListChanged
- AgentResponse (от стратегий через EventBus)
- События жизненного цикла стратегий

### Требование: Доступ в Debug Mode

Когда debug mode включён, EventTimeline ДОЛЖЕН предоставлять полные payload'ы событий для инспекции через TUI или API.

# Spec: agent-metrics

## ДОБАВЛЕННЫЕ Требования

### Требование: Автолог MetricsTracker

Система ДОЛЖНА предоставлять `MetricsTracker`, который автоматически записывает:
- `bus_dispatch_latency_ms` — время dispatch EventBus
- `llm_call_latency_ms` — время вызова LLM провайдера
- `input_tokens`, `output_tokens`, `total_tokens` — из AgentResult.usage
- `compression_ratio` — из результата ContextCompactor
- `slicer_original_tokens`, `slicer_sliced_tokens`, `slicer_latency_ms` — из TokenSlicer
- `strategy_execution_time` — общее время за turn

### Требование: Подписка на метрики

MetricsTracker ДОЛЖЕН подписаться на `AbstractEventBus` для автоматического сбора метрик без модификации стратегий.

### Требование: Хранение метрик

Метрики ДОЛЖНЫ храниться по сессиям и быть доступны для:
- Мониторинга текущей сессии
- Пост-turn анализа
- Инспекции в debug mode

# Spec: debug-mode

## ДОБАВЛЕННЫЕ Требования

### Требование: Флаг Debug Mode

Система ДОЛЖНА поддерживать флаг `debug: bool` в конфигурации TOML `[agents]`.

### Требование: Поведение Debug Mode

Когда debug mode включён:
- Полные payload логи для всех сообщений EventBus
- Dump запросов/ответов LLM
- EventTimeline доступен с полными деталями
- Span'ы Tracer включают все атрибуты
- TokenSlicing diff (до/после) экспортируется

### Требование: Debug Mode выключен

Когда debug mode выключен (по умолчанию):
- Только summary логи (без полных payload'ов)
- EventTimeline записывает минимальные детали
- Span'ы Tracer включают только essential атрибуты

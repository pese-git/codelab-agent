## Tasks

### 1. Tracer

- [x] 1.1 Создать пакет `codelab/src/codelab/server/observability/` с `__init__.py`
- [x] 1.2 Создать dataclass `SpanContext`: span_id, name, parent_id, attributes, start_time, end_time
- [x] 1.3 Создать класс `Tracer` с методами: start_span, end_span, get_current_span
- [x] 1.4 Реализовать вложенную иерархию span (родитель → дочерний)
- [x] 1.5 Реализовать распространение контекста span через цепочку вызовов
- [x] 1.6 Написать тесты: жизненный цикл start/end span
- [x] 1.7 Написать тесты: вложенная иерархия span
- [x] 1.8 Написать тесты: атрибуты span

### 2. EventTimeline

- [x] 2.1 Создать класс `EventTimeline`
- [x] 2.2 Реализовать `record_event(event_type, session_id, details)` — запись события
- [x] 2.3 Реализовать `get_events(session_id) → list[TimelineEvent]` — получение событий
- [x] 2.4 Реализовать подписку на AbstractEventBus для автоматической записи
- [x] 2.5 Подписаться на: AgentRegistered, AgentUnregistered, AgentListChanged, AgentResponse
- [x] 2.6 Написать тесты: запись + получение событий
- [x] 2.7 Написать тесты: автозапись из событий EventBus

### 3. MetricsTracker

- [x] 3.1 Создать класс `MetricsTracker`
- [x] 3.2 Реализовать `record_bus_dispatch(latency_ms, target_agent)`
- [x] 3.3 Реализовать `record_llm_call(latency_ms, model, input_tokens, output_tokens)`
- [x] 3.4 Реализовать `record_agent_response(agent_name, stop_reason, usage)`
- [x] 3.5 Реализовать `record_compression(original_tokens, sliced_tokens, ratio)`
- [x] 3.6 Реализовать `record_slicer(original_tokens, sliced_tokens, latency_ms, was_skipped)`
- [x] 3.7 Реализовать `record_strategy_execution(strategy, total_time_ms)`
- [x] 3.8 Реализовать `get_metrics(session_id) → SessionMetrics`
- [x] 3.9 Реализовать подписку на AbstractEventBus для автосбора
- [x] 3.10 Написать тесты: запись + получение метрик
- [x] 3.11 Написать тесты: автозапись из событий EventBus

### 4. Debug Mode

- [x] 4.1 Реализовать флаг debug mode в Tracer (полные атрибуты)
- [x] 4.2 Реализовать флаг debug mode в EventTimeline (полные payload'ы)
- [x] 4.3 Реализовать флаг debug mode в MetricsTracker (дополнительные метрики)
- [x] 4.4 Написать тесты: debug mode включён → полные детали
- [x] 4.5 Написать тесты: debug mode выключен → минимальные детали

### 5. Интеграция

- [x] 5.1 Обновить `codelab/src/codelab/server/observability/__init__.py` с экспортами
- [x] 5.2 Написать integration тесты: Tracer + EventBus + MetricsTracker вместе

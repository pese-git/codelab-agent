## Tasks

### 1. Tracer

- [ ] 1.1 Создать пакет `codelab/src/codelab/server/observability/` с `__init__.py`
- [ ] 1.2 Создать dataclass `SpanContext`: span_id, name, parent_id, attributes, start_time, end_time
- [ ] 1.3 Создать класс `Tracer` с методами: start_span, end_span, get_current_span
- [ ] 1.4 Реализовать вложенную иерархию span (родитель → дочерний)
- [ ] 1.5 Реализовать распространение контекста span через цепочку вызовов
- [ ] 1.6 Написать тесты: жизненный цикл start/end span
- [ ] 1.7 Написать тесты: вложенная иерархия span
- [ ] 1.8 Написать тесты: атрибуты span

### 2. EventTimeline

- [ ] 2.1 Создать класс `EventTimeline`
- [ ] 2.2 Реализовать `record_event(event_type, session_id, details)` — запись события
- [ ] 2.3 Реализовать `get_events(session_id) → list[TimelineEvent]` — получение событий
- [ ] 2.4 Реализовать подписку на AbstractEventBus для автоматической записи
- [ ] 2.5 Подписаться на: AgentRegistered, AgentUnregistered, AgentListChanged, AgentResponse
- [ ] 2.6 Написать тесты: запись + получение событий
- [ ] 2.7 Написать тесты: автозапись из событий EventBus

### 3. MetricsTracker

- [ ] 3.1 Создать класс `MetricsTracker`
- [ ] 3.2 Реализовать `record_bus_dispatch(latency_ms, target_agent)`
- [ ] 3.3 Реализовать `record_llm_call(latency_ms, model, input_tokens, output_tokens)`
- [ ] 3.4 Реализовать `record_agent_response(agent_name, stop_reason, usage)`
- [ ] 3.5 Реализовать `record_compression(original_tokens, sliced_tokens, ratio)`
- [ ] 3.6 Реализовать `record_strategy_execution(strategy, total_time_ms)`
- [ ] 3.7 Реализовать `get_metrics(session_id) → SessionMetrics`
- [ ] 3.8 Реализовать подписку на AbstractEventBus для автосбора
- [ ] 3.9 Написать тесты: запись + получение метрик
- [ ] 3.10 Написать тесты: автозапись из событий EventBus

### 4. Debug Mode

- [ ] 4.1 Реализовать флаг debug mode в Tracer (полные атрибуты)
- [ ] 4.2 Реализовать флаг debug mode в EventTimeline (полные payload'ы)
- [ ] 4.3 Реализовать флаг debug mode в MetricsTracker (дополнительные метрики)
- [ ] 4.4 Написать тесты: debug mode включён → полные детали
- [ ] 4.5 Написать тесты: debug mode выключен → минимальные детали

### 5. Интеграция

- [ ] 5.1 Обновить `codelab/src/codelab/server/observability/__init__.py` с экспортами
- [ ] 5.2 Написать integration тесты: Tracer + EventBus + MetricsTracker вместе

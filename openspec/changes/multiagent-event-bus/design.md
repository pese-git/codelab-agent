## Design

### Архитектура AgentEventBus

AgentEventBus реализует два интерфейса по принципу Interface Segregation:

1. **AbstractEventBus** — pub/sub для observability (MetricsTracker, EventTimeline)
2. **AgentRoutingInterface** — agent routing для стратегий выполнения

Оба интерфейса реализованы в одном классе `AgentEventBus`, что упрощает DI и тестирование.

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Interface Segregation | Observability компоненты не могут случайно вызвать `send_request` |
| Async publish с asyncio.gather | Параллельный вызов подписчиков, ошибка одного не влияет на остальных |
| Retry для dispatch | 3 попытки с exponential backoff при transient errors |
| Dict[str, RequestHandler] | O(1) lookup по agent_name |
| Subscription с cancel() | Явное управление жизненным циклом подписки |

### Структура данных

```python
class AgentEventBus(AbstractEventBus, AgentRoutingInterface):
    _subscribers: dict[type, list[tuple[Handler, bool]]]  # event_type → [(handler, is_active)]
    _agents: dict[str, RequestHandler]                     # agent_name → handler
    _retry_config: RetryConfig                             # max_attempts, backoff
```

### Flow point-to-point

```
1. Strategy → send_request(AgentRequest, parent_span)
2. Bus.lookup(agent_name) → RequestHandler
3. Bus.dispatch_with_retry(handler, request, parent_span)
4. Handler → AgentResult
5. Bus.publish(AgentDispatched) → observability
6. Return AgentBusResponse
```

### Flow broadcast

```
1. Strategy → broadcast(ContextBroadcast)
2. Для каждого registered agent: dispatch(handler, broadcast)
3. asyncio.gather(all_responses, return_exceptions=True)
4. Filter errors, build list[ChoreographyAnswer]
5. Return answers
```

### Error handling

- `AgentNotFoundError` — target_agent не зарегистрирован (наследуется от AgentBusError)
- `AgentDispatchError` — handler упал после retry (наследуется от AgentBusError)
- Ошибки в pub/sub обработчиках логируются, не прерывают dispatch

### Тестирование

- Unit тесты: subscribe/unsubscribe, publish, send_request, broadcast
- Integration тесты: полный цикл register → send_request → response
- Error тесты: agent not found, handler error, retry behavior
- Concurrency тесты: parallel publish, parallel send_request

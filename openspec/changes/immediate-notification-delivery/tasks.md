# Tasks: Immediate Notification Delivery

## Фаза 1: AgentLoop — добавление callback (низкий риск)

### 1.1 Добавить notification_callback параметр
- [x] 1.1.1 Добавить параметр `notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None` в `AgentLoop.__init__()` (`server/protocol/handlers/pipeline/stages/agent_loop.py`)
- [x] 1.1.2 Сохранить callback в `self._notification_callback`
- [x] 1.1.3 Обновить docstring с описанием параметра
- [x] 1.1.4 Добавить import `from typing import Awaitable, Callable` (если отсутствует)

### 1.2 Реализовать _send_notification_immediately()
- [x] 1.2.1 Добавить метод `_send_notification_immediately()` после `__init__()`
- [x] 1.2.2 Реализовать проверку `if self._notification_callback is not None`
- [x] 1.2.3 Реализовать try/except с логированием warning при ошибке
- [x] 1.2.4 Добавить docstring с описанием graceful error handling

### 1.3 Unit тесты для callback
- [x] 1.3.1 Написать тест: callback не вызывается если None (backward compatibility)
- [x] 1.3.2 Написать тест: callback вызывается для agent response notification
- [x] 1.3.3 Написать тест: callback вызывается для tool call notification
- [x] 1.3.4 Написать тест: callback вызывается для tool update notification с content
- [x] 1.3.5 Написать тест: ошибка в callback не прерывает AgentLoop
- [x] 1.3.6 Написать тест: warning логируется при ошибке callback
- [x] 1.3.7 Написать тест: notification по-прежнему в списке при ошибке callback

## Фаза 2: Immediate sending во всех точках (средний риск)

### 2.1 Agent response notifications
- [x] 2.1.1 Обновить `run()` метод — строка ~254
- [x] 2.1.2 Изменить: `notification = ...` → `agent_response_notification = ...`
- [x] 2.1.3 Добавить: `await self._send_notification_immediately(agent_response_notification)`

### 2.2 Plan notifications
- [x] 2.2.1 Обновить `run()` метод — строка ~268
- [x] 2.2.2 Изменить: `notifications.append(...)` → `plan_notification = ...; notifications.append(plan_notification)`
- [x] 2.2.3 Добавить: `await self._send_notification_immediately(plan_notification)`
- [x] 2.2.4 Обновить `_process_tool_calls()` — строка ~761
- [x] 2.2.5 Аналогично изменить для plan notification из update_plan tool

### 2.3 Tool call notifications
- [x] 2.3.1 Обновить `_process_tool_calls()` — строка ~541
- [x] 2.3.2 Изменить: `notifications.append(...)` → `tool_call_notification = ...; notifications.append(tool_call_notification)`
- [x] 2.3.3 Добавить: `await self._send_notification_immediately(tool_call_notification)`

### 2.4 Permission request notifications
- [x] 2.4.1 Обновить `_process_tool_calls()` — строка ~589
- [x] 2.4.2 Добавить: `await self._send_notification_immediately(permission_msg)`

### 2.5 Tool execution status notifications (КРИТИЧНО для terminal embedding)
- [x] 2.5.1 Обновить `_process_tool_calls()` — "in_progress" status, строка ~641
- [x] 2.5.2 Изменить: `notifications.append(...)` → `in_progress_notification = ...; notifications.append(in_progress_notification)`
- [x] 2.5.3 Добавить: `await self._send_notification_immediately(in_progress_notification)`
- [x] 2.5.4 Обновить `_process_tool_calls()` — "completed/failed" status, строка ~716
- [x] 2.5.5 Изменить: `notifications.append(...)` → `tool_update_notification = ...; notifications.append(tool_update_notification)`
- [x] 2.5.6 Добавить: `await self._send_notification_immediately(tool_update_notification)` — КРИТИЧНО для terminal embedding!

### 2.6 Tool rejection notifications
- [x] 2.6.1 Обновить `_process_tool_calls()` — строка ~612
- [x] 2.6.2 Изменить: `notifications.append(...)` → `rejection_notification = ...; notifications.append(rejection_notification)`
- [x] 2.6.3 Добавить: `await self._send_notification_immediately(rejection_notification)`

### 2.7 Error notifications
- [x] 2.7.1 Обновить `run()` метод — строка ~219
- [x] 2.7.2 Изменить: `notifications.append(...)` → `error_notification = ...; notifications.append(error_notification)`
- [x] 2.7.3 Добавить: `await self._send_notification_immediately(error_notification)`

### 2.8 Unit тесты для immediate sending
- [x] 2.8.1 Написать тест: agent response notification отправляется немедленно
- [x] 2.8.2 Написать тест: tool call notification отправляется немедленно
- [x] 2.8.3 Написать тест: tool update с terminal content отправляется немедленно
- [x] 2.8.4 Написать тест: permission request notification отправляется немедленно
- [x] 2.8.5 Написать тест: error notification отправляется немедленно

## Фаза 3: Проброс callback через stack (средний риск)

### 3.1 LLMLoopStage
- [x] 3.1.1 Добавить параметр `notification_callback` в `execute_pending_tool()` (`server/protocol/handlers/pipeline/stages/llm_loop.py`)
- [x] 3.1.2 Передать callback в `AgentLoop` при создании (строка ~276)
- [x] 3.1.3 Добавить параметр `notification_callback` в `process()` метод
- [x] 3.1.4 Извлечь callback из `context.meta.get("notification_callback")`
- [x] 3.1.5 Передать callback в `AgentLoop` при создании в `process()`

### 3.2 PromptOrchestrator
- [x] 3.2.1 Добавить параметр `notification_callback` в `execute_pending_tool()` (`server/protocol/handlers/prompt_orchestrator.py`)
- [x] 3.2.2 Передать callback в `self._llm_loop_stage.execute_pending_tool()`
- [x] 3.2.3 Добавить параметр `notification_callback` в `handle_prompt()`
- [x] 3.2.4 Добавить callback в `context.meta["notification_callback"]`

### 3.3 ProtocolCore
- [x] 3.3.1 Обновить `execute_pending_tool()` — передать `self._send_message` как callback (`server/protocol/core.py`)
- [x] 3.3.2 Найти handler для `session/prompt` — передать `self._send_message` как callback
- [x] 3.3.3 Проверить что `_send_message` корректно работает с transport callback

### 3.4 Unit тесты для проброса
- [x] 3.4.1 Написать тест: LLMLoopStage пробрасывает callback в AgentLoop
- [x] 3.4.2 Написать тест: PromptOrchestrator пробрасывает callback в LLMLoopStage
- [x] 3.4.3 Написать тест: ProtocolCore передаёт self._send_message как callback

## Фаза 4: Integration и Performance тесты (средний риск)

### 4.1 Integration тест terminal embedding
- [x] 4.1.1 Создать файл `tests/server/test_terminal_embedding_immediate_delivery.py`
- [x] 4.1.2 Написать тест: terminal notification доставляется < 100ms
- [x] 4.1.3 Написать тест: notification содержит terminalId
- [x] 4.1.4 Написать тест: notification содержит terminal content
- [x] 4.1.5 Написать тест: клиент может начать отображение live output

### 4.2 Performance benchmark
- [x] 4.2.1 Создать файл `tests/server/test_notification_performance.py`
- [x] 4.2.2 Написать benchmark: измерить latency для 100 notifications
- [x] 4.2.3 Проверить average latency < 50ms
- [x] 4.2.4 Проверить P95 latency < 100ms

### 4.3 Backward compatibility тесты
- [x] 4.3.1 Запустить все существующие тесты — должны пройти без изменений
- [x] 4.3.2 Проверить что без callback notifications накапливаются как раньше
- [x] 4.3.3 Проверить что batch mode работает если callback не задан

## Фаза 5: Документация (низкий риск)

### 5.1 Inline документация
- [x] 5.1.1 Добавить комментарий перед `_send_notification_immediately()` с объяснением ACP требований
- [x] 5.1.2 Обновить docstrings в `AgentLoop.__init__()` с описанием callback
- [x] 5.1.3 Обновить docstrings в `LLMLoopStage.execute_pending_tool()` с описанием callback
- [x] 5.1.4 Обновить docstrings в `PromptOrchestrator.execute_pending_tool()` с описанием callback

### 5.2 README обновление
- [ ] 5.2.1 Добавить секцию "Real-time Notifications" в README.md
- [ ] 5.2.2 Описать архитектуру immediate delivery
- [ ] 5.2.3 Добавить диаграмму sequence для terminal embedding flow
- [ ] 5.2.4 Упомянуть backward compatibility

## Фаза 6: Проверка перед merge (низкий риск)

### 6.1 Чеклист изменений
- [x] 6.1.1 Проверить что все 8 точек создания notifications вызывают immediate send
- [x] 6.1.2 Проверить что callback опционален во всех местах
- [x] 6.1.3 Проверить что error handling корректен
- [x] 6.1.4 Проверить что нет дублирования кода

### 6.2 Команды проверки
- [x] 6.2.1 Запустить `uv run ruff check src/ tests/` — lint должен пройти
- [x] 6.2.2 Запустить `uv run ty check` — typecheck должен пройти
- [x] 6.2.3 Запустить `uv run python -m pytest tests/server/protocol/handlers/pipeline/stages/test_agent_loop.py -v`
- [x] 6.2.4 Запустить `uv run python -m pytest tests/server/test_terminal_embedding_immediate_delivery.py -v`
- [x] 6.2.5 Запустить `uv run python -m pytest tests/server/test_notification_performance.py -v`
- [x] 6.2.6 Запустить `uv run python -m pytest` — все тесты должны пройти
- [x] 6.2.7 Запустить `make check` — полная проверка

### 6.3 Измерение улучшений
- [x] 6.3.1 Измерить latency ДО изменений (baseline: ~15 секунд)
- [x] 6.3.2 Измерить latency ПОСЛЕ изменений (average: 0.03ms, P95: 0.05ms, P99: 0.17ms)
- [x] 6.3.3 Зафиксировать улучшение (~500,000x faster: 15s → 0.03ms)

## Дополнительные исправления (не в spec)

### WebSocket fix
- [x] WebSocket transport: заменить `handle_client_response` на `handle_and_process` для permission response
- [x] Tool calls больше не зависают в pending статусе при использовании WebSocket transport

### Устранение дублирования
- [x] Убрать batch отправку notifications в `_execute_tool_in_background()`
- [x] Notifications отправляются только через callback, не дублируются

### Логирование
- [x] Добавить детальное логирование для диагностики WebSocket transport
- [x] Добавить логирование для отслеживания callback lifecycle в AgentLoop
- [x] Добавить логирование для диагностики в LLMLoopStage

## Оценка объёма

| Фаза | Новых файлов | Изменённых файлов | Тестов | Риск |
|------|--------------|-------------------|--------|------|
| Фаза 1 | 0 | 1 | 7 | Низкий |
| Фаза 2 | 0 | 1 | 5 | Средний |
| Фаза 3 | 0 | 3 | 3 | Средний |
| Фаза 4 | 2 | 0 | 8 | Средний |
| Фаза 5 | 0 | 1 | 0 | Низкий |
| Фаза 6 | 0 | 0 | 0 | Низкий |
| **Итого** | **2** | **6** | **23** | - |

## Зависимости между фазами

```
Фаза 1 → Фаза 2
Фаза 1 → Фаза 3
Фаза 2 → Фаза 4
Фаза 3 → Фаза 4
Фаза 4 → Фаза 6
Фаза 5 может выполняться параллельно
```

## Рекомендации по выполнению

1. **Фаза 1** — начать с добавления callback в AgentLoop (низкий риск)
2. **Фаза 2** — добавить immediate sending во всех точках (тщательно тестировать)
3. **Фаза 3** — пробросить callback через stack (следить за типами)
4. **Фаза 4** — integration и performance тесты (критично для приёмки)
5. **Фаза 5** — документация (можно делать параллельно)
6. **Фаза 6** — финальная проверка перед merge

## Критерии приёмки

- [ ] Notification с terminal content доставляется клиенту в течение 100ms после создания
- [ ] Terminal embedding работает в UI: пользователь видит live output
- [ ] Существующие тесты проходят без изменений
- [ ] Новые тесты покрывают immediate delivery
- [ ] `make check` проходит (lint + typecheck + tests)
- [ ] Документация обновлена
- [ ] Backward compatibility сохранена

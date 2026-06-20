# Proposal: Immediate Notification Delivery

## Контекст

В рамках реализации terminal embedding обнаружена архитектурная проблема:
notifications не доставляются клиенту в момент создания, а накапливаются
и отправляются пакетом после завершения LLM loop.

### Текущий flow (permission flow)

```
14:52:02.641  LLM вызывает terminal/create
14:52:04.753  Запрос permission → background scheduling
14:52:04.754  Permission получен, tool выполняется
14:52:04.819  terminal/create выполнен
14:52:04.819  Notification built with content ['terminal', 'content']
14:52:07.275  LLM вызывает terminal/wait_for_exit
14:52:07.278  wait_for_exit выполнен
...
14:52:20.337  Отправлено 6 notifications клиенту (пакетом)
```

**Задержка между созданием notification и отправкой: ~13 секунд.**

### Нарушение ACP спецификации

**05-Prompt Turn.md (строка 169):**
> "If the model requested tool calls, these are also reported **immediately**"

**08-Tool Calls.md (строка 11):**
> "Agents report tool calls through `session/update` notifications, allowing
> Clients to display **real-time progress** and results to users"

**10-Terminal.md (строка 115, 140):**
> "Terminals can be embedded directly in tool calls to provide **real-time
> output** to users"
>
> "When a terminal is embedded in a tool call, the Client displays **live
> output as it's generated**"

### Влияние на пользователя

1. **Terminal embedding не работает как задумано** — пользователь не видит
   live terminal output, т.к. notification с `terminalId` приходит с задержкой
2. **UX деградация** — нет real-time feedback при выполнении tool calls
3. **Нарушение семантики ACP** — спецификация требует немедленной доставки

## Что изменяется

- **Сервер:** `AgentLoop` получает опциональный `notification_callback` для немедленной отправки
- **Сервер:** `LLMLoopStage` пробрасывает callback при создании `AgentLoop`
- **Сервер:** `PromptOrchestrator` пробрасывает callback через pipeline
- **Сервер:** `ProtocolCore` передаёт `self._send_message` как callback
- **Тесты:** Unit и integration тесты для immediate delivery

## Capabilities

### New Capabilities

- `immediate-notification-delivery`: Поддержка немедленной отправки notifications
  через callback pattern. Включает: добавление callback в AgentLoop, проброс через
  pipeline, immediate sending во всех точках создания notifications.

### Modified Capabilities

(нет модификаций существующих capabilities)

## Impact

**Сервер:**
- `server/protocol/handlers/pipeline/stages/agent_loop.py` — добавить `notification_callback`
  параметр и `_send_notification_immediately()` метод
- `server/protocol/handlers/pipeline/stages/llm_loop.py` — пробросить callback в `AgentLoop`
- `server/protocol/handlers/prompt_orchestrator.py` — пробросить callback через pipeline
- `server/protocol/core.py` — передать `self._send_message` как callback

**Тесты:**
- Unit тесты для `AgentLoop` (callback вызывается для каждого notification)
- Unit тесты для `AgentLoop` (ошибка в callback не прерывает loop)
- Unit тесты для `AgentLoop` (backward compatibility без callback)
- Integration тест: terminal embedding notification доставляется < 100ms
- Performance benchmark: измерение latency

**Документация:**
- Обновить docstrings в изменённых файлах
- Добавить комментарий о immediate delivery pattern

**Зависимости:** Нет новых зависимостей.

**Обратная совместимость:** Полная. `notification_callback` опционален — существующий
код работает без изменений.

## Обоснование выбора Callback Pattern

### Альтернативы

1. **Event Bus** — избыточен для point-to-point communication
2. **Async Generator** — ломает существующий API
3. **Threading** — нарушает async architecture

### Почему Callback Pattern

1. **Уже используется в проекте** — `protocol._send_callback = transport.send`
2. **Минимальные изменения** — только добавление callback параметра
3. **Обратная совместимость** — callback опционален
4. **Соответствует ACP** — "immediately", "real-time", "live output"
5. **Соблюдает границы слоёв** — AgentLoop не знает о transport деталях
6. **Не создаёт фоновых задач** — нет утечек ресурсов

### Два транспорта (stdio/websocket) — НЕ аргумент за Event Bus

- Один protocol instance = один transport (REQUEST scope)
- Каждый transport передаёт свой callback
- Callback pattern идеален для этого сценария

## Критерии приёмки

- [ ] Notification с terminal content доставляется клиенту в течение 100ms
  после создания
- [ ] Terminal embedding работает в UI: пользователь видит live output
- [ ] Существующие тесты проходят без изменений
- [ ] Новые тесты покрывают immediate delivery
- [ ] `make check` проходит (lint + typecheck + tests)

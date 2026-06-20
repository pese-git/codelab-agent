# Problem Statement: Immediate Notification Delivery

## Контекст

В рамках реализации terminal embedding обнаружена архитектурная проблема:
notifications не доставляются клиенту в момент создания, а накапливаются
и отправляются пакетом после завершения LLM loop.

## Как сейчас работает

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

### Цепочка вызовов

```
ProtocolCore._execute_tool_in_background()
  └─ ProtocolCore.execute_pending_tool()
      └─ PromptOrchestrator.execute_pending_tool()
          └─ LLMLoopStage.execute_pending_tool()
              └─ AgentLoop.resume_after_permission()
                  └─ AgentLoop.run()
                      └─ AgentLoop._process_tool_calls()
                          └─ notifications.append(...)  ← накапливаются
```

### Ключевые места кода

**AgentLoop.run()** (`agent_loop.py:190`):
```python
notifications: list[ACPMessage] = []
# ... цикл итераций ...
notifications.append(notification)  # накапливается
return AgentLoopResult(notifications=notifications, ...)
```

**ProtocolCore._execute_tool_in_background()** (`core.py:631-644`):
```python
llm_result: LLMLoopResult = await self.execute_pending_tool(...)
# Отправка ПОСЛЕ завершения всего LLM loop
for notification in llm_result.notifications:
    await self._send_message(notification)
```

## Суть проблемы

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

### Архитектурные ограничения проекта

Из `AGENTS.md`:
- "Предпочитать расширение существующих компонентов созданию новых" (строка 68)
- "Новая абстракция — исключение, а не правило" (строка 72)
- "Не создавать фоновые задачи без контроля жизненного цикла" (строка 88)
- "Соблюдать границы protocol, storage, agent, tools, llm" (строка 157)

## Как должно работать

### Требуемый flow

```
14:52:02.641  LLM вызывает terminal/create
14:52:04.753  Запрос permission → background scheduling
14:52:04.754  Permission получен, tool выполняется
14:52:04.819  terminal/create выполнен
14:52:04.819  Notification built → СРАЗУ отправлен клиенту  ← ИЗМЕНЕНИЕ
14:52:04.820  Клиент получает terminalId, начинает отображать live output
14:52:07.275  LLM вызывает terminal/wait_for_exit
14:52:07.278  wait_for_exit выполнен
14:52:07.280  Notification built → СРАЗУ отправлен клиенту  ← ИЗМЕНЕНИЕ
```

### Требования к решению

1. **Немедленная доставка** — notification отправляется в момент создания
2. **Минимальность изменений** — не ломать существующую архитектуру
3. **Соответствие ACP** — "immediately", "real-time", "live output"
4. **Соблюдение границ слоёв** — AgentLoop не знает о transport
5. **Контроль lifecycle** — нет утечек ресурсов
6. **Обратная совместимость** — не менять публичные контракты

### Критерии приёмки

- [ ] Notification с terminal content доставляется клиенту в течение 100ms
  после создания
- [ ] Terminal embedding работает в UI: пользователь видит live output
- [ ] Существующие тесты проходят без изменений
- [ ] Новые тесты покрывают immediate delivery
- [ ] `make check` проходит (lint + typecheck + tests)

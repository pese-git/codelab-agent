# Design: Immediate Notification Delivery

## Контекст

ACP спецификация требует немедленной доставки notifications для tool calls,
особенно критично для terminal embedding (live output). Текущая архитектура
накапливает notifications в `AgentLoop` и отправляет пакетом после завершения
LLM loop, что нарушает требования ACP.

**Текущая архитектура:**
```
AgentLoop._process_tool_calls()
  ↓ создаёт notification
  ↓ добавляет в список notifications
  ↓ возвращает список
PromptOrchestrator.execute_pending_tool()
  ↓ оборачивает в LLMLoopResult
ProtocolCore.execute_pending_tool()
  ↓ получает LLMLoopResult
ProtocolCore._execute_tool_in_background()
  ↓ отправляет ВСЕ notifications ПАКЕТОМ ← ПРОБЛЕМА
```

## Цели / Не цели

**Цели:**
- Немедленная доставка notifications в момент создания
- Соответствие ACP спецификации ("immediately", "real-time", "live output")
- Минимальность изменений — не ломать существующую архитектуру
- Полная обратная совместимость
- Соблюдение границ слоёв (Clean Architecture)

**Не цели:**
- Изменение ACP, A2A или MCP спецификаций
- Создание нового Event Bus (избыточно)
- Использование async generators (ломает API)
- Изменение публичных контрактов SessionState, ToolCallState

## Решения

### Решение 1: Добавить notification_callback в AgentLoop

**Проблема:** AgentLoop не имеет доступа к transport для немедленной отправки.

**Решение:**
```python
# server/protocol/handlers/pipeline/stages/agent_loop.py
def __init__(
    self,
    strategy: LLMCallStrategy,
    tool_registry: ToolRegistry,
    # ... existing params ...
    notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,  # NEW
) -> None:
    self._notification_callback = notification_callback
```

**Обоснование:**
- Соответствует существующему паттерну (`protocol._send_callback = transport.send`)
- Минимальное изменение — один параметр
- Обратная совместимость — callback опционален
- Не нарушает layering — AgentLoop не знает о transport деталях

### Решение 2: Вспомогательный метод для безопасной отправки

**Проблема:** Callback может упасть с ошибкой, нужно обработать gracefully.

**Решение:**
```python
async def _send_notification_immediately(self, notification: ACPMessage) -> None:
    """Отправить notification немедленно через callback если он задан.
    
    Обработка ошибок: если callback падает, логируем warning но не прерываем выполнение.
    Notification всё равно будет отправлен в batch mode через накопленный список.
    """
    if self._notification_callback is not None:
        try:
            await self._notification_callback(notification)
        except Exception as e:
            logger.warning(
                "notification_callback_failed",
                notification_method=notification.method,
                error=str(e),
                exc_info=True,
            )
            # Продолжаем выполнение — notification всё равно в списке
```

**Обоснование:**
- Graceful error handling — не прерывает loop при ошибке callback
- Логирование для debugging
- Fallback на batch mode при ошибке
- Принцип "fail gracefully"

### Решение 3: Вызывать immediate send во всех точках создания notifications

**Проблема:** Notifications создаются в 8+ местах, нужно добавить immediate send везде.

**Решение:**
```python
# Пример в _process_tool_calls() для tool call notification:
tool_call_notification = self._tool_call_handler.build_tool_call_notification(
    session_id=session_id,
    tool_call_id=tool_call_id,
    title=acp_tool_name,
    kind=tool_kind,
)
notifications.append(tool_call_notification)
await self._send_notification_immediately(tool_call_notification)  # NEW

# Пример для tool update с content (КРИТИЧНО для terminal embedding):
tool_update_notification = self._tool_call_handler.build_tool_update_notification(
    session_id=session_id,
    tool_call_id=tool_call_id,
    status=status,
    content=notification_content,  # Может содержать terminal embedding!
)
notifications.append(tool_update_notification)
await self._send_notification_immediately(tool_update_notification)  # NEW
```

**Точки интеграции:**
1. Agent response notifications (строка ~254)
2. Plan notifications (строки ~268, ~761)
3. Tool call notifications (строка ~541)
4. Permission request notifications (строка ~589)
5. Tool "in_progress" status (строка ~641)
6. Tool "completed/failed" status с content (строка ~716) — КРИТИЧНО
7. Tool rejection notifications (строка ~612)
8. Error notifications (строка ~219)

**Обоснование:**
- Покрытие всех типов notifications
- Сохранение порядка отправки
- Notifications по-прежнему накапливаются (backward compatibility)

### Решение 4: Пробросить callback через цепочку вызовов

**Проблема:** Callback нужно передать от ProtocolCore до AgentLoop через 3-4 слоя.

**Решение:**

#### 4.1 LLMLoopStage

```python
# server/protocol/handlers/pipeline/stages/llm_loop.py
async def execute_pending_tool(
    self,
    session: SessionState,
    session_id: str,
    tool_call_id: str,
    mcp_manager: Any | None = None,
    notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,  # NEW
) -> LLMLoopResult:
    # ...
    self._agent_loop = AgentLoop(
        # ... existing params ...
        notification_callback=notification_callback,  # NEW
    )
```

#### 4.2 PromptOrchestrator

```python
# server/protocol/handlers/prompt_orchestrator.py
async def execute_pending_tool(
    self,
    session: SessionState,
    session_id: str,
    tool_call_id: str,
    mcp_manager: Any | None = None,
    notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,  # NEW
) -> LLMLoopResult:
    return await self._llm_loop_stage.execute_pending_tool(
        # ... existing params ...
        notification_callback=notification_callback,  # NEW
    )
```

#### 4.3 ProtocolCore

```python
# server/protocol/core.py
async def execute_pending_tool(
    self,
    session_id: str,
    tool_call_id: str,
) -> LLMLoopResult:
    # ...
    llm_result = await orchestrator.execute_pending_tool(
        session=session,
        session_id=session_id,
        tool_call_id=tool_call_id,
        mcp_manager=mcp_manager,
        notification_callback=self._send_message,  # NEW — КЛЮЧЕВОЕ ИЗМЕНЕНИЕ!
    )
```

**Обоснование:**
- Следует существующему паттерну проброса параметров
- Минимальные изменения в каждом слое
- ProtocolCore использует уже существующий `self._send_message`

### Решение 5: Дедупликация notifications (опционально)

**Проблема:** Notification может быть отправлен дважды — через callback и через batch.

**Решение A (Рекомендуется):** Оставить как есть
- Notifications idempotent — дублирование не вредит
- Клиент может игнорировать дубликаты по `toolCallId` + `status`
- Проще в реализации

**Решение B (Альтернатива):** Добавить tracking
```python
# В AgentLoop:
self._sent_notification_ids: set[str] = set()

async def _send_notification_immediately(self, notification: ACPMessage) -> None:
    if self._notification_callback is not None:
        # Извлечь ID из notification params
        notif_id = self._extract_notification_id(notification)
        if notif_id and notif_id in self._sent_notification_ids:
            return  # Уже отправлен
        await self._notification_callback(notification)
        if notif_id:
            self._sent_notification_ids.add(notif_id)
```

**Обоснование:**
- Решение A проще и достаточно для большинства случаев
- Решение B добавляет overhead, но гарантирует отсутствие дубликатов
- Можно начать с A, перейти на B если станет проблемой

## Зависимости между решениями

```
Решение 1 (notification_callback в AgentLoop) — независимо
Решение 2 (_send_notification_immediately) — зависит от Решения 1
Решение 3 (Вызовы immediate send) — зависит от Решения 2
Решение 4 (Проброс callback) — зависит от Решения 1
Решение 5 (Дедупликация) — опционально, зависит от Решения 3
```

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Ошибка в callback прервёт loop | Низкая | Высокое | Graceful error handling в `_send_notification_immediately()` |
| Дублирование notifications | Средняя | Низкое | Idempotent notifications, опциональная дедупликация |
| Race condition между immediate и batch | Низкая | Среднее | Immediate send происходит ПЕРЕД batch, порядок сохраняется |
| Нарушение backward compatibility | Низкая | Высокое | Callback опционален, существующий код работает без изменений |
| Callback вызывается из неправильного context | Низкая | Среднее | Callback в том же async context, проблем не будет |

## Альтернативные решения (отклонённые)

### Отклонённое решение A: Event Bus

**Почему отклонено:**
- Избыточно для point-to-point communication
- Создание нового Event Bus добавляет сложность
- Переиспользование AgentEventBus смешивает concerns
- Callback pattern уже используется в проекте для аналогичных задач

### Отклонённое решение B: Async Generator

**Почему отклонено:**
- Ломает существующий API (`AgentLoop.run()` → `AsyncGenerator`)
- Требует изменений во всех вызывающих местах
- Сложная миграция

### Отклонённое решение C: Threading/Multiprocessing

**Почему отклонено:**
- Избыточная сложность
- Нарушает async architecture
- Проблемы с lifecycle management

## План внедрения

См. `tasks.md` для детального плана.

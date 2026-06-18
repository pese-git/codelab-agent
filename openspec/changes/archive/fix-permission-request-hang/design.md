# Design: Fix Permission Request Hang

## Context

### Архитектура обработки Permission Requests

```
┌─────────────────────────────────────────────────────────────┐
│                    ACPTransportService                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  request_with_callbacks()                                   │
│    ├─ Создаёт response_task (ожидание ответа на request)   │
│    ├─ Создаёт permission_task (ожидание permission request) │
│    └─ Вызывает _wait_for_response_with_events()            │
│                                                              │
│  _wait_for_response_with_events()                           │
│    └─ Цикл while True:                                      │
│         ├─ Создаёт notification_task (timeout 0.1s)         │
│         ├─ asyncio.wait([response, notification, perm])     │
│         ├─ Если notification_task в pending → отменить      │
│         ├─ Если permission_task в done → обработать         │
│         │    └─ Создать НОВЫЙ permission_task ← ПРОБЛЕМА    │
│         ├─ Если notification_task в done → обработать       │
│         └─ Если response_task в done → return               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Поток обработки Permission Request

```
1. BackgroundReceiveLoop получает session/request_permission
2. MessageRouter маршрутизирует в permission_queue
3. RoutingQueues.put_permission_request() кладёт в очередь
4. permission_task (asyncio.Task) получает сообщение из очереди
5. _handle_permission_task() вызывается
6. _handle_permission_request_with_handler() обрабатывает async
7. PermissionHandler показывает UI modal
8. Пользователь выбирает опцию
9. Response отправляется на сервер
10. Цикл продолжается
```

## Root Cause Analysis

### Анализ логов

**Первый permission request (успешный)**:
```
06:45:43.709 - permission_request_queued (request_id=68a5485d)
06:45:43.709 - permission_task_completed_in_wait_loop
06:45:43.709 - handle_permission_task_called
06:45:43.709 - tool_lifecycle_permission_request_received
06:45:43.709 - handling_permission_request_with_handler
06:45:43.709 - permission_callback_provided_showing_ui_modal
06:45:43.709 - show_permission_request_start
...
06:45:45.226 - permission_choice_received_from_ui
06:45:45.235 - permission_request_completed
06:45:45.236 - permission_response_sent_successfully
```

**Второй permission request (завис)**:
```
06:46:27.436 - permission_request_queued (request_id=28b31d40)
06:46:27.500 - tool_call_created (call_002)
... (нет permission_task_completed_in_wait_loop)
... (нет show_permission_request_start)
06:51:27.437 - receive_timeout (300.0s)
06:51:27.438 - receive_loop_error
```

### Корневая причина

**Проблема 1: Race condition при пересоздании permission_task**

```python
# Строки 658-669 в acp_transport_service.py
if permission_task is not None and permission_task in done:
    self._handle_permission_task(permission_task, ...)
    # ПРОБЛЕМА: Новый task создаётся здесь, но не добавляется
    # в tasks_to_wait до следующей итерации цикла
    permission_task = asyncio.create_task(
        self._queues.permission_queue.get()
    )
```

Если второй permission request приходит в очередь **до** того как новый permission_task начнёт ожидать, сообщение может быть потеряно (хотя очередь asyncio.Queue гарантирует доставку, task может не успеть подписаться).

**Проблема 2: Отмена notification_task**

```python
# Строки 653-656
if notification_task in pending:
    notification_task.cancel()  # Отменяется на каждой итерации!
    with contextlib.suppress(asyncio.CancelledError, TimeoutError):
        await notification_task
```

Это создаёт дополнительную нагрузку и может влиять на обработку других событий.

**Проблема 3: Нет логирования создания нового permission_task**

Невозможно отследить когда создаётся новый permission_task и начинает ли он ожидать сообщения.

## Solution

### Вариант 1: Убрать пересоздание permission_task (Рекомендуемый)

**Идея**: Создавать permission_task один раз перед циклом и не пересоздавать его.

```python
async def _wait_for_response_with_events(
    self,
    response_task: asyncio.Task[dict[str, Any]],
    permission_task: asyncio.Task[dict[str, Any]] | None,
    ...
) -> dict[str, Any]:
    while True:
        # Создаём notification_task с timeout
        notification_task = asyncio.create_task(
            asyncio.wait_for(
                self._queues.notification_queue.get(),
                timeout=0.1,
            )
        )

        tasks_to_wait = [response_task, notification_task]
        if permission_task is not None:
            tasks_to_wait.append(permission_task)

        done, pending = await asyncio.wait(
            tasks_to_wait,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Отменяем notification_task если он в pending
        if notification_task in pending:
            notification_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await notification_task

        # Обрабатываем permission_task
        if permission_task is not None and permission_task in done:
            self._logger.info("permission_task_completed")
            self._handle_permission_task(permission_task, ...)
            
            # НЕ пересоздаём permission_task здесь
            # Вместо этого устанавливаем в None и создаём заново
            # только если нужно продолжать слушать permissions
            permission_task = None  # Сбрасываем
            
            # Создаём новый task для следующего permission request
            # Это делается СРАЗУ после обработки, не в конце цикла
            permission_task = asyncio.create_task(
                self._queues.permission_queue.get()
            )
            self._logger.info("new_permission_task_created")

        # Обрабатываем notification_task
        if notification_task in done:
            await self._handle_notification_task(...)

        # Проверяем response_task
        if response_task in done:
            return await self._process_response(...)
```

**Преимущества**:
- Проще для понимания
- Меньше race conditions
- Лучшее логирование

**Недостатки**:
- Всё ещё есть небольшая задержка между созданием нового task и получением сообщения

### Вариант 2: Использовать отдельный permission listener (Альтернативный)

**Идея**: Запустить отдельную фоновую задачу для обработки permission requests, не связанную с циклом ожидания response.

```python
async def request_with_callbacks(...):
    # Создаём response_task
    response_task = asyncio.create_task(response_queue.get())
    
    # Запускаем отдельный permission listener
    permission_listener = asyncio.create_task(
        self._permission_listener_loop(method, request_id, ...)
    )
    
    try:
        # Ждём только response и notifications
        return await self._wait_for_response_and_notifications(
            response_task, ...
        )
    finally:
        permission_listener.cancel()

async def _permission_listener_loop(...):
    """Отдельный цикл для обработки permission requests."""
    while True:
        permission_data = await self._queues.permission_queue.get()
        self._logger.info("permission_received_in_listener")
        await self._handle_permission_request_with_handler(permission_data)
```

**Преимущества**:
- Полное разделение ответственности
- Нет race conditions
- Permission requests обрабатываются немедленно

**Недостатки**:
- Более сложная архитектура
- Нужно управлять lifecycle listener'а
- Может конфликтовать с существующей логикой

### Рекомендуемое решение

**Вариант 1** с улучшениями:

1. Добавить логирование создания нового permission_task
2. Убедиться что новый task создаётся **сразу** после обработки предыдущего
3. Добавить тесты для множественных permission requests

## Implementation Plan

### Шаг 1: Изменить `_wait_for_response_with_events`

**Файл**: `src/codelab/client/infrastructure/services/acp_transport_service.py`

**Изменения**:
1. Добавить логирование после создания нового permission_task
2. Убедиться что permission_task пересоздаётся **сразу** после обработки
3. Добавить комментарий объясняющий логику

### Шаг 2: Добавить тесты

**Файл**: `tests/client/test_acp_transport_service.py`

**Новые тесты**:
1. `test_multiple_permission_requests_in_sequence`
   - Отправить prompt с permission
   - Одобрить permission
   - Отправить второй prompt с permission
   - Проверить что второй permission обрабатывается

2. `test_permission_request_during_notification_processing`
   - Permission request приходит во время обработки notification
   - Проверить что permission не теряется

### Шаг 3: Проверить существующие тесты

Запустить все тесты связанные с permission:
```bash
pytest tests/client/test_permission_handler_direct_lifecycle.py -v
pytest tests/client/test_acp_transport_service.py -v
```

## Testing Strategy

### Unit Tests

1. **Тест множественных permission requests**
   - Mock permission_queue
   - Положить два сообщения в очередь
   - Проверить что оба обрабатываются

2. **Тест race condition**
   - Permission request приходит сразу после обработки предыдущего
   - Проверить что новый task создаётся и получает сообщение

### Integration Tests

1. **E2E тест с реальным сервером**
   - Запустить сервер и клиент
   - Отправить последовательные prompts с permission
   - Проверить что все permissions отображаются

### Manual Testing

1. Воспроизвести баг из proposal
2. Применить исправление
3. Проверить что баг исправлен
4. Проверить что другие сценарии работают

## Migration Plan

### Backward Compatibility

- Полная обратная совместимость
- Изменяется только внутренняя логика
- Публичный API не меняется

### Rollback Plan

Если исправление вызывает проблемы:
1. Откатить коммит
2. Использовать предыдущую версию

### Monitoring

После deployment:
1. Мониторить логи на наличие `permission_request_queued` без последующего `permission_task_completed`
2. Отслеживать timeout ошибки
3. Собирать feedback от пользователей

## Risks and Mitigations

### Риск 1: Изменение логики может сломать другие сценарии

**Митигация**:
- Тщательное тестирование всех permission flow
- Проверить все существующие тесты
- Manual testing различных сценариев

### Риск 2: Performance impact

**Митигация**:
- Изменение минимально (добавление логирования)
- Нет дополнительных async операций
- Performance test перед и после

### Риск 3: Race condition всё ещё возможен

**Митигация**:
- Добавить больше логирования
- Рассмотреть Вариант 2 если проблема не решится
- Добавить stress test с множеством permission requests

## Success Metrics

1. **Functional**: Второй permission request отображается сразу
2. **Performance**: Нет задержек в обработке permission
3. **Reliability**: Нет timeout ошибок при последовательных permissions
4. **Test Coverage**: Новые тесты покрывают сценарий

## References

- Логи: `~/.codelab/logs/codelab-34685.log`
- Код: `src/codelab/client/infrastructure/services/acp_transport_service.py:613-692`
- Документация: `doc/Agent Client Protocol/permission-flow.md` (если есть)

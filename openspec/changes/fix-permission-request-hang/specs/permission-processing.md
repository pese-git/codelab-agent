# Spec: Permission Request Processing

## Overview

Спецификация обработки permission requests в клиенте ACP. Описывает корректное поведение при обработке множественных permission requests в рамках одной сессии.

## Requirements

### REQ-1: Обработка permission request

**Уровень**: MUST

**Описание**: Клиент ДОЛЖЕН обрабатывать каждый permission request от сервера и отображать его пользователю.

**Критерии приёмки**:
- При получении `session/request_permission` от сервера, клиент ДОЛЖЕН:
  1. Получить сообщение из `permission_queue`
  2. Вызвать `_handle_permission_task`
  3. Показать UI modal пользователю
  4. Дождаться выбора пользователя
  5. Отправить response на сервер

**Тесты**:
- `test_permission_request_displayed`
- `test_permission_response_sent`

### REQ-2: Обработка множественных permission requests

**Уровень**: MUST

**Описание**: Клиент ДОЛЖЕН корректно обрабатывать множественные permission requests в последовательности.

**Критерии приёмки**:
- После обработки первого permission request, клиент ДОЛЖЕН:
  1. Сразу создать новый `permission_task` для ожидания следующего request
  2. Новый task ДОЛЖЕН быть готов получить следующее сообщение из `permission_queue`
  3. Второй permission request ДОЛЖЕН быть обработан без задержек

**Тесты**:
- `test_multiple_permission_requests_in_sequence`
- `test_permission_task_recreated_immediately`

### REQ-3: Отсутствие race conditions

**Уровень**: MUST

**Описание**: Клиент ДОЛЖЕН гарантировать отсутствие race conditions при обработке permission requests.

**Критерии приёмки**:
- Между завершением обработки одного permission request и созданием нового task НЕ ДОЛЖНО быть задержек
- Новый task ДОЛЖЕН быть создан **до** того как следующий permission request придёт в очередь
- Если permission request приходит в очередь до создания нового task, он ДОЛЖЕН быть обработан когда task создан

**Тесты**:
- `test_no_race_condition_between_permission_requests`
- `test_permission_request_arrives_before_task_creation`

### REQ-4: Логирование lifecycle

**Уровень**: SHOULD

**Описание**: Клиент ДОЛЖЕН логировать lifecycle permission task для отладки.

**Критерии приёмки**:
- При создании permission_task ДОЛЖЕН быть лог: `permission_task_created`
- При получении permission request ДОЛЖЕН быть лог: `permission_task_completed`
- При создании нового task после обработки ДОЛЖЕН быть лог: `new_permission_task_created`

**Тесты**:
- `test_permission_lifecycle_logging`

### REQ-5: Timeout handling

**Уровень**: MUST

**Описание**: Клиент ДОЛЖЕН корректно обрабатывать timeout при ожидании permission request.

**Критерии приёмки**:
- Если permission request не приходит в течение timeout, клиент ДОЛЖЕН:
  1. Не завершать сессию с ошибкой
  2. Продолжать обработку других событий (notifications, response)
  3. Быть готовым получить permission request после timeout

**Тесты**:
- `test_permission_timeout_does_not_break_session`

## Implementation Notes

### Текущая реализация (проблемная)

```python
# В _wait_for_response_with_events
if permission_task is not None and permission_task in done:
    self._handle_permission_task(permission_task, ...)
    # ПРОБЛЕМА: Новый task создаётся здесь, но может не успеть
    # подписаться на очередь до прихода следующего сообщения
    permission_task = asyncio.create_task(
        self._queues.permission_queue.get()
    )
```

### Исправленная реализация

```python
# В _wait_for_response_with_events
if permission_task is not None and permission_task in done:
    self._logger.info("permission_task_completed")
    self._handle_permission_task(permission_task, ...)
    
    # Сразу создаём новый task
    permission_task = asyncio.create_task(
        self._queues.permission_queue.get()
    )
    self._logger.info("new_permission_task_created")
```

## Test Scenarios

### Scenario 1: Последовательные permission requests

**Given**: Клиент подключён к серверу  
**When**: 
1. Отправлен prompt "прочти README.md"
2. Сервер запрашивает permission на fs/read_text_file
3. Пользователь одобряет permission
4. Агент читает файл
5. Отправлен prompt "выполни команду ls"
6. Сервер запрашивает permission на terminal/create  
**Then**: Второй permission request отображается сразу  
**And**: Пользователь может одобрить второй permission  
**And**: Команда выполняется

### Scenario 2: Permission request во время обработки notification

**Given**: Клиент обрабатывает notification (session/update)  
**When**: Приходит permission request  
**Then**: Permission request ставится в очередь  
**And**: После завершения обработки notification, permission request обрабатывается  
**And**: Permission request не теряется

### Scenario 3: Multiple permissions в одном prompt

**Given**: Клиент подключён к серверу  
**When**: Отправлен prompt который требует множественных permissions  
**Then**: Все permissions отображаются последовательно  
**And**: Каждый permission обрабатывается корректно  
**And**: Нет зависаний

### Scenario 4: Permission timeout

**Given**: Клиент ожидает permission request  
**When**: Permission request не приходит в течение 5 минут  
**Then**: Сессия НЕ завершается с ошибкой  
**And**: Клиент продолжает обработку других событий  
**And**: Клиент готов получить permission request после timeout

## Metrics

### Успешные метрики

- Время между созданием нового permission_task и получением следующего permission request < 100ms
- Количество потерянных permission requests = 0
- Количество timeout ошибок при обработке permission = 0

### Мониторинг

- Лог `permission_request_queued` без последующего `permission_task_completed` = 0
- Лог `receive_timeout` при обработке permission = 0

## References

- [ACP Protocol Specification - Permission](https://github.com/anthropics/agent-protocol/blob/main/spec/permission.md)
- [Issue: Permission request hang](link-to-issue)
- [Design Document](./design.md)

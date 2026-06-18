# Fix: Permission Request Hang

## Why

Второй permission request не отображается после одобрения первого, что приводит к зависанию сессии на 5 минут до timeout.

### Проблема

При последовательных запросах с permission:
1. Первый permission request отображается и обрабатывается корректно
2. После одобрения первого запроса, второй permission request ставится в очередь (`permission_request_queued`)
3. Второй запрос НЕ обрабатывается - нет логов `permission_task_completed_in_wait_loop` и `show_permission_request_start`
4. Сессия зависает на 5 минут до timeout
5. После timeout сессия завершается с ошибкой

### Воспроизведение

```
1. Запустить клиент
2. Отправить: "прочти README.md"
3. Агент запрашивает permission на fs/read_text_file
4. Одобрить permission
5. Агент читает файл и показывает содержимое
6. Отправить: "выполни команду ls -ahl ."
7. Агент запрашивает permission на terminal/create
8. Permission request НЕ отображается
9. Ожидание 5 минут до timeout
10. Сессия завершается с ошибкой
```

### Влияние на пользователей

- **Критичность**: Высокая - блокирует использование клиента
- **Частота**: Всегда воспроизводится при последовательных permission requests
- **Workaround**: Перезапуск клиента (неудобно)

## What Changes

### Изменения в коде

**Файл**: `src/codelab/client/infrastructure/services/acp_transport_service.py`

**Метод**: `_wait_for_response_with_events`

**Проблемные строки**:
- Строки 667-669: Пересоздание permission_task внутри цикла
- Строки 653-656: Отмена notification_task на каждой итерации

### Что нужно изменить

1. Убрать пересоздание permission_task внутри цикла
2. Изменить логику notification_task чтобы не отменять его на каждой итерации
3. Добавить логирование для отладки race conditions

## Capabilities

### Modified Capabilities

Нет новых capabilities. Исправление существующего поведения обработки permission requests.

## Impact

### Affected Code

- `src/codelab/client/infrastructure/services/acp_transport_service.py`
  - Метод `_wait_for_response_with_events`
  - Метод `_handle_permission_task`

### Affected Tests

- `tests/client/test_acp_transport_service.py`
- `tests/client/test_permission_handler_direct_lifecycle.py`
- Необходимо добавить новые тесты для множественных permission requests

### Backward Compatibility

Полная обратная совместимость. Изменяется только внутренняя логика обработки событий.

## Success Criteria

1. Второй permission request отображается сразу после одобрения первого
2. Нет зависаний сессии при последовательных permission requests
3. Все существующие тесты проходят
4. Новые тесты покрывают сценарий множественных permission requests

## Related Issues

- Обнаружено в логах: `~/.codelab/logs/codelab-34685.log`
- Строки 158-164: Второй permission request поставлен в очередь но не обработан
- Строка 164: Timeout после 5 минут ожидания

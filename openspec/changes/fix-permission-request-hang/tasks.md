# Tasks: Fix Permission Request Hang

## 1. Подготовка

- [ ] 1.1 Изучить текущий код `_wait_for_response_with_events` в `acp_transport_service.py`
- [ ] 1.2 Воспроизвести баг вручную (промпты из proposal)
- [ ] 1.3 Записать baseline логи для сравнения

## 2. Изменение кода

- [ ] 2.1 Изменить `_wait_for_response_with_events` в `acp_transport_service.py`:
  - [ ] 2.1.1 Добавить логирование после создания нового permission_task
  - [ ] 2.1.2 Убедиться что permission_task пересоздаётся сразу после обработки
  - [ ] 2.1.3 Добавить комментарии объясняющие логику
- [ ] 2.2 Добавить вспомогательный метод `_create_permission_task` для централизованного создания
- [ ] 2.3 Добавить логирование в `_handle_permission_task` для отслеживания lifecycle

## 3. Тестирование

### Unit Tests

- [ ] 3.1 Добавить тест `test_multiple_permission_requests_in_sequence` в `test_acp_transport_service.py`:
  - [ ] 3.1.1 Mock permission_queue
  - [ ] 3.1.2 Положить два сообщения в очередь
  - [ ] 3.1.3 Проверить что оба обрабатываются
  - [ ] 3.1.4 Проверить логирование создания нового permission_task

- [ ] 3.2 Добавить тест `test_permission_request_during_notification_processing`:
  - [ ] 3.2.1 Permission request приходит во время обработки notification
  - [ ] 3.2.2 Проверить что permission не теряется

- [ ] 3.3 Добавить тест `test_permission_task_recreated_immediately`:
  - [ ] 3.3.1 Проверить что новый permission_task создаётся сразу после обработки
  - [ ] 3.3.2 Проверить что нет задержек

### Integration Tests

- [ ] 3.4 Добавить интеграционный тест `test_e2e_multiple_permissions`:
  - [ ] 3.4.1 Запустить сервер и клиент
  - [ ] 3.4.2 Отправить последовательные prompts с permission
  - [ ] 3.4.3 Проверить что все permissions отображаются

### Regression Tests

- [ ] 3.5 Запустить все существующие тесты permission:
  ```bash
  pytest tests/client/test_permission_handler_direct_lifecycle.py -v
  pytest tests/client/test_acp_transport_service.py -v
  pytest tests/client/test_session_coordinator_permissions.py -v
  ```

- [ ] 3.6 Запустить все тесты клиента:
  ```bash
  pytest tests/client/ -v
  ```

- [ ] 3.7 Запустить все тесты проекта:
  ```bash
  make check
  ```

## 4. Manual Testing

- [ ] 4.1 Воспроизвести баг из proposal (до исправления)
- [ ] 4.2 Применить исправление
- [ ] 4.3 Проверить что баг исправлен:
  - [ ] 4.3.1 Отправить "прочти README.md"
  - [ ] 4.3.2 Одобрить permission
  - [ ] 4.3.3 Отправить "выполни команду ls -ahl ."
  - [ ] 4.3.4 Проверить что второй permission отображается
  - [ ] 4.3.5 Одобрить второй permission
  - [ ] 4.3.6 Проверить что команда выполняется

- [ ] 4.4 Проверить другие сценарии:
  - [ ] 4.4.1 Multiple permissions в одном prompt
  - [ ] 4.4.2 Permission timeout
  - [ ] 4.4.3 Permission + tool call
  - [ ] 4.4.4 Permission при reconnect

## 5. Документация

- [ ] 5.1 Обновить docstring в `_wait_for_response_with_events`
- [ ] 5.2 Добавить комментарий в код объясняющий почему permission_task пересоздаётся
- [ ] 5.3 Обновить CHANGELOG.md (если есть)

## 6. Code Review

- [ ] 6.1 Self-review изменений
- [ ] 6.2 Проверить что все тесты проходят
- [ ] 6.3 Проверить что нет новых warnings
- [ ] 6.4 Проверить что логирование информативное

## 7. Commit

- [ ] 7.1 Создать commit с описанием:
  ```
  fix(client): исправить зависание при последовательных permission requests

  Проблема:
  - Второй permission request не отображался после одобрения первого
  - Сессия зависала на 5 минут до timeout

  Причина:
  - Permission task пересоздавался в конце цикла обработки
  - Race condition между созданием нового task и получением сообщения

  Решение:
  - Permission task пересоздаётся сразу после обработки предыдущего
  - Добавлено логирование для отладки
  - Добавлены тесты для множественных permission requests

  Fixes: #<issue_number>
  ```

- [ ] 7.2 Push в branch
- [ ] 7.3 Создать PR

## 8. Verification

- [ ] 8.1 Проверить что CI проходит
- [ ] 8.2 Проверить что code review одобрен
- [ ] 8.3 Merge PR
- [ ] 8.4 Проверить что в main всё работает

## 9. Post-deployment

- [ ] 9.1 Мониторить логи на наличие `permission_request_queued` без последующего `permission_task_completed`
- [ ] 9.2 Отслеживать timeout ошибки
- [ ] 9.3 Собирать feedback от пользователей
- [ ] 9.4 Обновить openspec статус задачи

## Definition of Done

- [ ] Все тесты проходят (unit, integration, manual)
- [ ] Баг из proposal исправлен
- [ ] Код review пройден
- [ ] Документация обновлена
- [ ] PR merged в main
- [ ] Нет regressions

## Estimate

- Подготовка: 1 час
- Изменение кода: 2 часа
- Тестирование: 3 часа
- Manual testing: 1 час
- Документация: 0.5 часа
- Code review: 0.5 часа
- **Total: 8 часов**

## Priority

**Высокий** - блокирует использование клиента при последовательных permission requests.

## Assignee

TBD

## Labels

- `bug`
- `client`
- `permission`
- `high-priority`

# Tasks: Terminal Embedding в Tool Calls

## Фаза 1: Серверная часть (низкий риск)

### 1.1 Обновление ContentValidator
- [ ] 1.1.1 Добавить `"terminal"` в `SUPPORTED_TYPES` в `server/protocol/content/validator.py`
- [ ] 1.1.2 Добавить `"terminal": {"type", "terminalId"}` в `REQUIRED_FIELDS`
- [ ] 1.1.3 Написать unit тест: terminal тип проходит валидацию
- [ ] 1.1.4 Написать unit тест: terminal без terminalId не проходит валидацию

### 1.2 Обновление TerminalToolExecutor
- [ ] 1.2.1 Обновить `execute_create()` в `server/tools/executors/terminal_executor.py`
- [ ] 1.2.2 Добавить `{"type": "terminal", "terminalId": terminal_id}` в content_items
- [ ] 1.2.3 Оставить text content как fallback для LLM
- [ ] 1.2.4 Написать unit тест: execute_create возвращает terminal content
- [ ] 1.2.5 Написать unit тест: terminal content содержит terminalId

### 1.3 Обновление AgentLoop
- [ ] 1.3.1 Обновить `server/protocol/handlers/pipeline/stages/agent_loop.py`
- [ ] 1.3.2 Изменить логику формирования `notification_content`
- [ ] 1.3.3 Приоритет: `extracted_content.content_items` > text fallback
- [ ] 1.3.4 Написать unit тест: передаёт extracted content в notification
- [ ] 1.3.5 Написать unit тест: fallback на text если content пустой

## Фаза 2: Клиентская часть (низкий риск)

### 2.1 Обновление ToolCallHandler
- [ ] 2.1.1 Обновить `_handle_tool_call_created()` в `client/presentation/chat/handlers/tool_call_handler.py`
- [ ] 2.1.2 Добавить сохранение `content` из `update.get("content")`
- [ ] 2.1.3 Обновить `_handle_tool_call_updated()`
- [ ] 2.1.4 Добавить обновление `content` если присутствует
- [ ] 2.1.5 Написать unit тест: сохранение content при создании
- [ ] 2.1.6 Написать unit тест: обновление content при обновлении

## Фаза 3: Интеграционные тесты (низкий риск)

### 3.1 E2E тесты
- [ ] 3.1.1 Написать integration тест: LLM вызывает terminal tool → клиент получает terminal content
- [ ] 3.1.2 Проверить что slash-команды (`/term-run`) продолжают работать
- [ ] 3.1.3 Запустить `make check` (lint + typecheck + tests)

### 3.2 Документация
- [ ] 3.2.1 Обновить docstrings в изменённых файлах
- [ ] 3.2.2 Добавить примеры использования terminal embedding

## Оценка объёма

| Фаза | Новых файлов | Изменённых файлов | Тестов | Риск |
|------|--------------|-------------------|--------|------|
| Фаза 1 | 0 | 3 | 10 | Низкий |
| Фаза 2 | 0 | 1 | 5 | Низкий |
| Фаза 3 | 0 | 0 | 5 | Низкий |
| **Итого** | **0** | **4** | **20** | - |

## Зависимости между фазами

```
Фаза 1.1 → Фаза 1.2 → Фаза 1.3
Фаза 1 → Фаза 2
Фаза 2 → Фаза 3
```

## Рекомендации по выполнению

1. **Фаза 1** должна быть выполнена полностью перед Фазой 2
2. **Фаза 2** может быть выполнена параллельно с Фазой 1.3
3. **Фаза 3** выполняется после завершения Фаз 1 и 2
4. Каждая задача должна завершаться прогоном соответствующих тестов

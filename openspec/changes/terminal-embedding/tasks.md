# Tasks: Terminal Embedding в Tool Calls

## Фаза 1: Серверная часть (низкий риск)

### 1.1 Обновление ContentValidator
- [x] 1.1.1 Добавить `"terminal"` в `SUPPORTED_TYPES` в `server/protocol/content/validator.py`
- [x] 1.1.2 Добавить `"content"` в `SUPPORTED_TYPES` (обёртка для ContentBlock)
- [x] 1.1.3 Добавить `"terminal": {"type", "terminalId"}` в `REQUIRED_FIELDS`
- [x] 1.1.4 Добавить `"content": {"type", "content"}` в `REQUIRED_FIELDS`
- [x] 1.1.5 Написать unit тест: terminal тип проходит валидацию
- [x] 1.1.6 Написать unit тест: terminal без terminalId не проходит валидацию
- [x] 1.1.7 Написать unit тест: content тип проходит валидацию

### 1.2 Обновление ToolExecutionResult и ToolResultMapper
- [x] 1.2.1 Добавить поле `content: list[dict[str, Any]] | None = None` в `ToolExecutionResult` (`server/tools/base.py`)
- [x] 1.2.2 Обновить `ToolResultMapper.to_acp_content()` — проверять `result.content` перед fallback (`server/mapping/tool_result_mapper.py`)
- [x] 1.2.3 Написать unit тест: `to_acp_content()` возвращает `result.content` если задан
- [x] 1.2.4 Написать unit тест: `to_acp_content()` fallback на text если content не задан

### 1.3 Обновление TerminalToolExecutor
- [x] 1.3.1 Обновить `execute_create()` в `server/tools/executors/terminal_executor.py`
- [x] 1.3.2 Добавить `{"type": "terminal", "terminalId": terminal_id}` в content_items
- [x] 1.3.3 Обернуть text content в `{"type": "content", "content": {...}}`
- [x] 1.3.4 Передать `content=content_items` в `ToolExecutionResult`
- [x] 1.3.5 Написать unit тест: execute_create возвращает terminal content
- [x] 1.3.6 Написать unit тест: terminal content содержит terminalId

### 1.4 Обновление AgentLoop
- [x] 1.4.1 Обновить `server/protocol/handlers/pipeline/stages/agent_loop.py`
- [x] 1.4.2 Изменить логику формирования `notification_content` (строки 671-675)
- [x] 1.4.3 Приоритет: `extracted_content.content_items` > text fallback
- [x] 1.4.4 Написать unit тест: передаёт extracted content в notification
- [x] 1.4.5 Написать unit тест: fallback на text если content пустой

## Фаза 2: Клиентская часть (низкий риск)

### 2.1 Обновление ToolCallHandler
- [x] 2.1.1 Обновить `_handle_tool_call_created()` в `client/presentation/chat/handlers/tool_call_handler.py`
- [x] 2.1.2 Добавить сохранение `content` из `update.get("content")`
- [x] 2.1.3 Обновить `_handle_tool_call_updated()`
- [x] 2.1.4 Добавить обновление `content` если присутствует
- [x] 2.1.5 Написать unit тест: сохранение content при создании
- [x] 2.1.6 Написать unit тест: обновление content при обновлении

## Фаза 3: Интеграционные тесты (низкий риск)

### 3.1 E2E тесты
- [x] 3.1.1 Написать integration тест: LLM вызывает terminal tool → клиент получает terminal content
- [x] 3.1.2 Проверить что slash-команды (`/term-run`) продолжают работать
- [x] 3.1.3 Запустить `make check` (lint + typecheck + tests)

### 3.2 Документация
- [x] 3.2.1 Обновить docstrings в изменённых файлах
- [x] 3.2.2 Добавить примеры использования terminal embedding

## Оценка объёма

| Фаза | Новых файлов | Изменённых файлов | Тестов | Риск |
|------|--------------|-------------------|--------|------|
| Фаза 1 | 0 | 5 | 15 | Низкий |
| Фаза 2 | 0 | 1 | 4 | Низкий |
| Фаза 3 | 0 | 0 | 5 | Низкий |
| **Итого** | **0** | **6** | **24** | - |

## Зависимости между фазами

```
Фаза 1.1 → Фаза 1.4
Фаза 1.2 → Фаза 1.3 → Фаза 1.4
Фаза 1 → Фаза 2
Фаза 2 → Фаза 3
```

## Рекомендации по выполнению

1. **Фаза 1.1 и 1.2** могут быть выполнены параллельно
2. **Фаза 1.3** зависит от 1.2 (нужно поле `content` в `ToolExecutionResult`)
3. **Фаза 1.4** зависит от 1.1 и 1.3
4. **Фаза 2** может быть выполнена параллельно с Фазой 1.4
5. **Фаза 3** выполняется после завершения Фаз 1 и 2
6. Каждая задача должна завершаться прогоном соответствующих тестов

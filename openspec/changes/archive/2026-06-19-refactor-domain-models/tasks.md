# Tasks: Рефакторизация доменных моделей

## Фаза 1: Независимые изменения (низкий риск)

### 1.1 Удаление мёртвого кода
- [x] 1.1.1 Удалить `ToolCall` из `server/models.py` (не используется)
- [x] 1.1.2 Удалить `ToolCallParameter` из `server/models.py` (не используется)
- [x] 1.1.3 Обновить импорты в зависимых файлах
- [x] 1.1.4 Запустить тесты для проверки отсутствия поломок

### 1.2 Создание domain value objects
- [x] 1.2.1 Создать `server/domain/__init__.py`
- [x] 1.2.2 Создать `server/domain/value_objects.py` с `SessionId`, `FileLocation`
- [x] 1.2.3 Создать domain enums: `ToolCallStatus`, `MessageRole`, `PlanPriority`, `PlanStatus`
- [x] 1.2.4 Написать unit тесты для value objects и enums

### 1.3 Создание domain FileLocation
- [x] 1.3.1 Создать `FileLocation` frozen dataclass в `server/domain/value_objects.py`
- [x] 1.3.2 Добавить валидацию path (должен быть абсолютным)
- [x] 1.3.3 Написать unit тесты для `FileLocation`

### 1.4 Создание domain ClientCapabilities
- [x] 1.4.1 Создать `ClientCapabilities` frozen dataclass в `client/domain/entities.py`
- [x] 1.4.2 Добавить properties: `supports_fs`, `supports_multimodal`
- [x] 1.4.3 Добавить методы: `can_read_files()`, `can_write_files()`
- [x] 1.4.4 Написать unit тесты для `ClientCapabilities`
- [x] 1.4.5 Мигрировать `Session.capabilities` на типизированную модель

## Фаза 2: Разделение ToolCall (средний риск)

### 2.1 Создание domain ToolCall
- [x] 2.1.1 Создать `server/domain/tool_call.py` с `ToolCall` frozen dataclass
- [x] 2.1.2 Создать `ToolResult` frozen dataclass с полями `locations`, `raw_output`
- [x] 2.1.3 Добавить property `is_terminal`
- [x] 2.1.4 Написать unit тесты для `ToolCall` и `ToolResult`

### 2.2 Обновление ToolCallState (ACP Protocol Model)
- [x] 2.2.1 Добавить docstring с пометкой "ACP Protocol Model" в `ToolCallState`
- [x] 2.2.2 Добавить поля `locations`, `rawInput`, `rawOutput`
- [x] 2.2.3 Написать unit тесты для новых полей

### 2.3 Создание ToolCallMapper
- [x] 2.3.1 Создать `server/mapping/__init__.py`
- [x] 2.3.2 Создать `server/mapping/tool_call_mapper.py`
- [x] 2.3.3 Реализовать `to_protocol()` — маппить `arguments` → `rawInput`, `raw_output` → `rawOutput`, `locations` → `locations`
- [x] 2.3.4 Реализовать `to_domain()` — обратный маппинг
- [x] 2.3.5 Написать unit тесты для маппера

### 2.4 Миграция ToolCallHandler
- [x] 2.4.1 Обновить `create_tool_call()` — принимать `locations: list[FileLocation] | None`
- [x] 2.4.2 Обновить `build_tool_call_notification()` — принимать `raw_input: dict | None`, включать как `rawInput`
- [x] 2.4.3 Обновить `build_tool_update_notification()` — принимать `locations`, `raw_output`, включать в notification
- [x] 2.4.4 Написать unit тесты для обновлённых методов

### 2.5 Миграция AgentLoop
- [x] 2.5.1 Обновить создание tool call — передавать `tool_arguments` как `raw_input` в notification
- [x] 2.5.2 Обновить после выполнения tool — передавать `result.locations` в `build_tool_update_notification()`
- [x] 2.5.3 Обновить `ReplayManager` для работы с маппером
- [x] 2.5.4 Написать интеграционные тесты

## Фаза 3: Разделение HistoryMessage (средний риск)

### 3.1 Создание domain ConversationMessage
- [x] 3.1.1 Создать `server/domain/conversation.py`
- [x] 3.1.2 Создать `ConversationMessage` frozen dataclass
- [x] 3.1.3 Создать `MessageContent` frozen dataclass
- [x] 3.1.4 Создать `Resource` и `Image` frozen dataclasses
- [x] 3.1.5 Написать unit тесты

### 3.2 Обновление HistoryMessage (ACP Protocol Model)
- [x] 3.2.1 Добавить docstring с пометкой "ACP Protocol Model" в `HistoryMessage`
- [x] 3.2.2 Обновить структуру полей
- [x] 3.2.3 Написать unit тесты

### 3.3 Создание HistoryMapper
- [x] 3.3.1 Создать `server/mapping/history_mapper.py`
- [x] 3.3.2 Реализовать `to_protocol()` метод
- [x] 3.3.3 Реализовать `to_domain()` метод
- [x] 3.3.4 Обработать все варианты content (text, resource, image)
- [x] 3.3.5 Написать unit тесты

### 3.4 Миграция HistoryMessage
- [x] 3.4.1 Обновить `HistoryBuilder` для работы с маппером
- [x] 3.4.2 Обновить `StateManager` для работы с маппером
- [x] 3.4.3 Написать интеграционные тесты

## Фаза 4: Разделение AgentContext и AgentResponse (средний риск)

### 4.1 Создание domain UserPrompt
- [x] 4.1.1 Создать `server/domain/prompt.py`
- [x] 4.1.2 Создать `UserPrompt` frozen dataclass
- [x] 4.1.3 Добавить property `has_multimodal`
- [x] 4.1.4 Добавить метод `get_text_preview()`
- [x] 4.1.5 Написать unit тесты

### 4.2 Создание PromptMapper
- [x] 4.2.1 Создать `server/mapping/prompt_mapper.py`
- [x] 4.2.2 Реализовать `from_acp_blocks()` метод
- [x] 4.2.3 Реализовать `to_acp_blocks()` метод
- [x] 4.2.4 Обработать все типы content (text, resource, image)
- [x] 4.2.5 Написать unit тесты

### 4.3 Миграция AgentContext
- [x] 4.3.1 Обновить `AgentContext.prompt` на `UserPrompt`
- [x] 4.3.2 Обновить `ExecutionEngine.build_context()` для маппинга
- [x] 4.3.3 Обновить `HistoryBuilder` для работы с `UserPrompt`
- [x] 4.3.4 Обновить все использования `AgentContext.prompt`
- [x] 4.3.5 Написать интеграционные тесты

### 4.4 Создание LLMResponseMapper
- [x] 4.4.1 Создать `server/mapping/llm_response_mapper.py`
- [x] 4.4.2 Реализовать `to_domain()` метод для `LLMToolCall` → `ToolCall`
- [x] 4.4.3 Написать unit тесты

### 4.5 Миграция AgentResponse
- [x] 4.5.1 Обновить `AgentResponse.tool_calls` на domain `ToolCall`
- [x] 4.5.2 Обновить `AgentResult.tool_calls` на domain `ToolCall`
- [x] 4.5.3 Обновить `LLMAdapter` для маппинга `LLMToolCall` → `ToolCall`
- [x] 4.5.4 Обновить все контракты в `server/agent/contracts/base.py`
- [x] 4.5.5 Написать интеграционные тесты

## Фаза 5: Создание PlanEntry (низкий риск)

### 5.1 Создание domain PlanEntry
- [x] 5.1.1 Создать `server/domain/plan.py`
- [x] 5.1.2 Создать `PlanEntry` frozen dataclass
- [x] 5.1.3 Соответствие ACP spec: `content`, `priority`, `status`
- [x] 5.1.4 Написать unit тесты

### 5.2 Создание PlanMapper
- [x] 5.2.1 Создать `server/mapping/plan_mapper.py`
- [x] 5.2.2 Реализовать `to_acp()` метод
- [x] 5.2.3 Реализовать `from_acp()` метод
- [x] 5.2.4 Написать unit тесты

### 5.3 Миграция PlanStep
- [x] 5.3.1 Обновить `PlanStep` с docstring "ACP Protocol Model"
- [x] 5.3.2 Обновить `PlanBuilder` для работы с `PlanEntry`
- [x] 5.3.3 Обновить `PlanExtractor` для работы с `PlanEntry`
- [x] 5.3.4 Написать интеграционные тесты

## Фаза 6: Разделение ToolExecutionResult (низкий риск)

### 6.1 Обновление ToolExecutionResult
- [x] 6.1.1 Убрать `content: list[dict[str, Any]]` из `ToolExecutionResult`
- [x] 6.1.2 Добавить `locations: list[FileLocation]`
- [x] 6.1.3 Добавить `raw_output: dict[str, Any]`
- [x] 6.1.4 Обновить docstring
- [x] 6.1.5 Написать unit тесты

### 6.2 Создание ToolResultMapper
- [x] 6.2.1 Создать `server/mapping/tool_result_mapper.py`
- [x] 6.2.2 Реализовать `to_acp_content()` метод
- [x] 6.2.3 Реализовать `from_tool_result()` метод
- [x] 6.2.4 Написать unit тесты

### 6.3 Миграция FileSystemToolExecutor
- [x] 6.3.1 `execute_read()` — возвращать `locations=[FileLocation(path, line)]`
- [x] 6.3.2 `execute_read()` — возвращать `raw_output={"content": content, "bytes_read": len(content)}`
- [x] 6.3.3 `execute_write()` — возвращать `locations=[FileLocation(path)]`
- [x] 6.3.4 `execute_write()` — возвращать `raw_output={"bytes_written": len(content), "diff": diff_text}`
- [x] 6.3.5 Написать unit тесты

### 6.4 Миграция TerminalToolExecutor
- [x] 6.4.1 `execute_create()` — возвращать `locations=[]`
- [x] 6.4.2 `execute_create()` — возвращать `raw_output={"terminal_id": terminal_id}`
- [x] 6.4.3 `execute_wait_for_exit()` — возвращать `raw_output={"exit_code": ..., "signal": ..., "output": ...}`
- [x] 6.4.4 Написать unit тесты

### 6.5 Миграция MCPToolExecutor
- [x] 6.5.1 `execute()` — возвращать `locations=[]` (MCP tools не имеют file locations)
- [x] 6.5.2 `execute()` — возвращать `raw_output={"result": result}` (сырой результат от MCP)
- [x] 6.5.3 Написать unit тесты

### 6.6 Миграция ContentExtractor
- [x] 6.6.1 Обновить `ContentExtractor` для использования `ToolResultMapper`
- [x] 6.6.2 Написать интеграционные тесты

## Фаза 7: Разделение SessionState (высокий риск)

### 7.1 Создание domain агрегатов
- [x] 7.1.1 Создать `server/domain/session.py` с `Session` aggregate root
- [x] 7.1.2 Создать `SessionConfig` value object
- [x] 7.1.3 Создать `ConversationHistory` value object
- [x] 7.1.4 Создать `ToolCallRegistry` value object
- [x] 7.1.5 Создать `PermissionState` value object
- [x] 7.1.6 Создать `AgentPlan` value object
- [x] 7.1.7 Создать `MultiAgentState` value object
- [x] 7.1.8 Написать unit тесты для каждого агрегата

### 7.2 Обновление SessionState (ACP Protocol Model)
- [x] 7.2.1 Добавить docstring с пометкой "ACP Protocol Model" в `SessionState`
- [x] 7.2.2 Обновить структуру с использованием value objects
- [x] 7.2.3 Добавить `schema_version: 4`
- [x] 7.2.4 Написать unit тесты

### 7.3 Создание SessionMapper
- [x] 7.3.1 Создать `server/mapping/session_mapper.py`
- [x] 7.3.2 Реализовать `to_protocol()` метод
- [x] 7.3.3 Реализовать `to_domain()` метод
- [x] 7.3.4 Обработать все value objects
- [x] 7.3.5 Написать unit тесты

### 7.4 Миграция SessionState
- [x] 7.4.1 Добавить миграцию schema_version: 3 → 4
- [x] 7.4.2 Обновить `InMemoryStorage` для работы с новым `SessionState`
- [x] 7.4.3 Обновить `JsonFileStorage` для работы с новым `SessionState`
- [x] 7.4.4 Обновить все handlers для работы с domain `Session`
- [x] 7.4.5 Обновить `ACPProtocol` для работы с domain `Session`
- [x] 7.4.6 Обновить `PromptOrchestrator` для работы с domain `Session`
- [x] 7.4.7 Написать интеграционные тесты

### 7.5 Миграция бизнес-логики
- [x] 7.5.1 Перенести `add_message()` в `Session`
- [x] 7.5.2 Перенести `create_tool_call()` в `Session`
- [x] 7.5.3 Перенести `update_tool_call()` в `Session`
- [x] 7.5.4 Перенести `set_permission_policy()` в `Session`
- [x] 7.5.5 Обновить все вызовы для использования domain методов
- [x] 7.5.6 Написать интеграционные тесты

## Фаза 8: Интеграционные тесты и документация

### 8.1 Интеграционные тесты
- [x] 8.1.1 Написать E2E тесты для полного цикла prompt turn
- [x] 8.1.2 Написать тесты для миграции storage format
- [x] 8.1.3 Написать тесты для всех мапперов
- [x] 8.1.4 Написать тесты для domain агрегатов

### 8.2 Документация
- [x] 8.2.1 Обновить ARCHITECTURE.md с новой структурой
- [x] 8.2.2 Обновить docstrings во всех новых файлах
- [x] 8.2.3 Добавить примеры использования мапперов
- [x] 8.2.4 Обновить codelab.md с новой архитектурой

### 8.3 Финальная проверка
- [x] 8.3.1 Запустить `make check` (lint + typecheck + tests)
- [x] 8.3.2 Проверить обратную совместимость storage
- [x] 8.3.3 Проверить производительность (нет деградации)
- [x] 8.3.4 Проверить покрытие тестами (>80%)

## Фаза 9: Клиентская часть + Follow-along (низкий риск)

### 9.1 Обновление ToolCallHandler (клиент)
- [x] 9.1.1 `_handle_tool_call_created()` — сохранять `locations`, `rawInput`, `rawOutput`
- [x] 9.1.2 `_handle_tool_call_updated()` — обновлять `locations`, `rawOutput`
- [x] 9.1.3 Написать unit тесты

### 9.2 Создание FileOpener Protocol
- [x] 9.2.1 Создать `client/infrastructure/services/follow_along.py`
- [x] 9.2.2 Определить `FileOpener` Protocol с методом `open(path, line)`
- [x] 9.2.3 Реализовать `StubFileOpener` для тестов
- [x] 9.2.4 Написать unit тесты

### 9.3 Создание FollowAlongService
- [x] 9.3.1 Реализовать `FollowAlongService` с методом `on_tool_call_updated()`
- [x] 9.3.2 Логика: проверить `enabled`, извлечь `locations[0]`, вызвать `file_opener.open()`
- [x] 9.3.3 Написать unit тесты: enabled=False, locations пуст, locations с одним элементом, locations с несколькими элементами

### 9.4 Интеграция FollowAlongService в ToolCallHandler
- [x] 9.4.1 Добавить опциональный параметр `follow_along: FollowAlongService | None` в конструктор
- [x] 9.4.2 В `_handle_tool_call_updated()` вызывать `follow_along.on_tool_call_updated()` если сервис доступен
- [x] 9.4.3 Написать integration тесты

### 9.5 Финальная проверка follow-along
- [x] 9.5.1 Запустить `make check` (lint + typecheck + tests)
- [x] 9.5.2 Проверить что follow-along не ломает существующий функционал
- [x] 9.5.3 Проверить что feature flag не нужен

## Оценка объёма

| Фаза | Новых файлов | Изменённых файлов | Тестов | Риск |
|------|--------------|-------------------|--------|------|
| Фаза 1 | 3 | 5 | 15 | Низкий |
| Фаза 2 | 2 | 8 | 20 | Средний |
| Фаза 3 | 2 | 6 | 15 | Средний |
| Фаза 4 | 3 | 10 | 20 | Средний |
| Фаза 5 | 2 | 5 | 10 | Низкий |
| Фаза 6 | 2 | 8 | 20 | Низкий |
| Фаза 7 | 8 | 25 | 40 | Высокий |
| Фаза 8 | 0 | 5 | 30 | Низкий |
| Фаза 9 | 2 | 3 | 15 | Низкий |
| **Итого** | **24** | **75** | **185** | - |

## Зависимости между фазами

```
Фаза 1 → Фаза 2 → Фаза 3 → Фаза 7
Фаза 1 → Фаза 4
Фаза 1 → Фаза 5
Фаза 1 → Фаза 6
Фаза 2, 3, 5, 6 → Фаза 7
Фаза 7 → Фаза 8
Фаза 2 → Фаза 9 (follow-along зависит от ToolCall с locations)
```

## Рекомендации по выполнению

1. **Фазы 1-6** можно выполнять параллельно (независимые изменения)
2. **Фаза 7** требует завершения фаз 2, 3, 5, 6
3. **Фаза 8** выполняется после завершения всех предыдущих фаз
4. **Фаза 9** может выполняться после Фазы 2 (независима от Фаз 3-7)
5. Каждая фаза должна завершаться полным прогоном тестов
6. Рекомендуется создавать отдельный PR для каждой фазы

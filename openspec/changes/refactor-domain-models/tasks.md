# Tasks: Рефакторизация доменных моделей

## Фаза 1: Независимые изменения (низкий риск)

### 1.1 Удаление мёртвого кода
- [ ] 1.1.1 Удалить `ToolCall` из `server/models.py` (не используется)
- [ ] 1.1.2 Удалить `ToolCallParameter` из `server/models.py` (не используется)
- [ ] 1.1.3 Обновить импорты в зависимых файлах
- [ ] 1.1.4 Запустить тесты для проверки отсутствия поломок

### 1.2 Создание domain value objects
- [ ] 1.2.1 Создать `server/domain/__init__.py`
- [ ] 1.2.2 Создать `server/domain/value_objects.py` с `SessionId`, `FileLocation`
- [ ] 1.2.3 Создать domain enums: `ToolCallStatus`, `MessageRole`, `PlanPriority`, `PlanStatus`
- [ ] 1.2.4 Написать unit тесты для value objects и enums

### 1.3 Создание domain FileLocation
- [ ] 1.3.1 Создать `FileLocation` frozen dataclass в `server/domain/value_objects.py`
- [ ] 1.3.2 Добавить валидацию path (должен быть абсолютным)
- [ ] 1.3.3 Написать unit тесты для `FileLocation`

### 1.4 Создание domain ClientCapabilities
- [ ] 1.4.1 Создать `ClientCapabilities` frozen dataclass в `client/domain/entities.py`
- [ ] 1.4.2 Добавить properties: `supports_fs`, `supports_multimodal`
- [ ] 1.4.3 Добавить методы: `can_read_files()`, `can_write_files()`
- [ ] 1.4.4 Написать unit тесты для `ClientCapabilities`
- [ ] 1.4.5 Мигрировать `Session.capabilities` на типизированную модель

## Фаза 2: Разделение ToolCall (средний риск)

### 2.1 Создание domain ToolCall
- [ ] 2.1.1 Создать `server/domain/tool_call.py` с `ToolCall` frozen dataclass
- [ ] 2.1.2 Создать `ToolResult` frozen dataclass
- [ ] 2.1.3 Добавить property `is_terminal`
- [ ] 2.1.4 Написать unit тесты для `ToolCall` и `ToolResult`

### 2.2 Создание ToolCallDTO
- [ ] 2.2.1 Создать `server/protocol/dto/tool_call_dto.py`
- [ ] 2.2.2 Создать `ToolCallDTO` Pydantic модель
- [ ] 2.2.3 Создать `ToolCallLocationDTO` Pydantic модель
- [ ] 2.2.4 Написать unit тесты для DTO

### 2.3 Создание ToolCallMapper
- [ ] 2.3.1 Создать `server/mapping/__init__.py`
- [ ] 2.3.2 Создать `server/mapping/tool_call_mapper.py`
- [ ] 2.3.3 Реализовать `to_dto()` метод
- [ ] 2.3.4 Реализовать `to_domain()` метод
- [ ] 2.3.5 Написать unit тесты для маппера

### 2.4 Миграция ToolCallState
- [ ] 2.4.1 Заменить `ToolCallState` на `ToolCallDTO` в `SessionState`
- [ ] 2.4.2 Обновить `ToolCallHandler` для работы с DTO
- [ ] 2.4.3 Обновить `AgentLoop` для работы с DTO
- [ ] 2.4.4 Обновить `ReplayManager` для работы с DTO
- [ ] 2.4.5 Обновить storage для работы с DTO
- [ ] 2.4.6 Написать интеграционные тесты

## Фаза 3: Разделение HistoryMessage (средний риск)

### 3.1 Создание domain ConversationMessage
- [ ] 3.1.1 Создать `server/domain/conversation.py`
- [ ] 3.1.2 Создать `ConversationMessage` frozen dataclass
- [ ] 3.1.3 Создать `MessageContent` frozen dataclass
- [ ] 3.1.4 Создать `Resource` и `Image` frozen dataclasses
- [ ] 3.1.5 Написать unit тесты

### 3.2 Создание HistoryMessageDTO
- [ ] 3.2.1 Создать `server/protocol/dto/history_dto.py`
- [ ] 3.2.2 Создать `HistoryMessageDTO` Pydantic модель
- [ ] 3.2.3 Создать `ContentBlockDTO` Pydantic модель
- [ ] 3.2.4 Написать unit тесты

### 3.3 Создание HistoryMapper
- [ ] 3.3.1 Создать `server/mapping/history_mapper.py`
- [ ] 3.3.2 Реализовать `to_dto()` метод
- [ ] 3.3.3 Реализовать `to_domain()` метод
- [ ] 3.3.4 Обработать все варианты content (text, resource, image)
- [ ] 3.3.5 Написать unit тесты

### 3.4 Миграция HistoryMessage
- [ ] 3.4.1 Заменить `HistoryMessage` на `HistoryMessageDTO` в `SessionState`
- [ ] 3.4.2 Обновить `HistoryBuilder` для работы с DTO
- [ ] 3.4.3 Обновить `StateManager` для работы с DTO
- [ ] 3.4.4 Обновить storage для работы с DTO
- [ ] 3.4.5 Написать интеграционные тесты

## Фаза 4: Разделение AgentContext и AgentResponse (средний риск)

### 4.1 Создание domain UserPrompt
- [ ] 4.1.1 Создать `server/domain/prompt.py`
- [ ] 4.1.2 Создать `UserPrompt` frozen dataclass
- [ ] 4.1.3 Добавить property `has_multimodal`
- [ ] 4.1.4 Добавить метод `get_text_preview()`
- [ ] 4.1.5 Написать unit тесты

### 4.2 Создание PromptMapper
- [ ] 4.2.1 Создать `server/mapping/prompt_mapper.py`
- [ ] 4.2.2 Реализовать `from_acp_blocks()` метод
- [ ] 4.2.3 Реализовать `to_acp_blocks()` метод
- [ ] 4.2.4 Обработать все типы content (text, resource, image)
- [ ] 4.2.5 Написать unit тесты

### 4.3 Миграция AgentContext
- [ ] 4.3.1 Обновить `AgentContext.prompt` на `UserPrompt`
- [ ] 4.3.2 Обновить `ExecutionEngine.build_context()` для маппинга
- [ ] 4.3.3 Обновить `HistoryBuilder` для работы с `UserPrompt`
- [ ] 4.3.4 Обновить все использования `AgentContext.prompt`
- [ ] 4.3.5 Написать интеграционные тесты

### 4.4 Создание LLMResponseMapper
- [ ] 4.4.1 Создать `server/mapping/llm_response_mapper.py`
- [ ] 4.4.2 Реализовать `to_domain()` метод для `LLMToolCall` → `ToolCall`
- [ ] 4.4.3 Написать unit тесты

### 4.5 Миграция AgentResponse
- [ ] 4.5.1 Обновить `AgentResponse.tool_calls` на domain `ToolCall`
- [ ] 4.5.2 Обновить `AgentResult.tool_calls` на domain `ToolCall`
- [ ] 4.5.3 Обновить `LLMAdapter` для маппинга `LLMToolCall` → `ToolCall`
- [ ] 4.5.4 Обновить все контракты в `server/agent/contracts/base.py`
- [ ] 4.5.5 Написать интеграционные тесты

## Фаза 5: Создание PlanEntry (низкий риск)

### 5.1 Создание domain PlanEntry
- [ ] 5.1.1 Создать `server/domain/plan.py`
- [ ] 5.1.2 Создать `PlanEntry` frozen dataclass
- [ ] 5.1.3 Соответствие ACP spec: `content`, `priority`, `status`
- [ ] 5.1.4 Написать unit тесты

### 5.2 Создание PlanMapper
- [ ] 5.2.1 Создать `server/mapping/plan_mapper.py`
- [ ] 5.2.2 Реализовать `to_acp()` метод
- [ ] 5.2.3 Реализовать `from_acp()` метод
- [ ] 5.2.4 Написать unit тесты

### 5.3 Миграция PlanStep
- [ ] 5.3.1 Заменить `PlanStep` на `PlanEntry` в `SessionState`
- [ ] 5.3.2 Обновить `PlanBuilder` для работы с `PlanEntry`
- [ ] 5.3.3 Обновить `PlanExtractor` для работы с `PlanEntry`
- [ ] 5.3.4 Написать интеграционные тесты

## Фаза 6: Разделение ToolExecutionResult (низкий риск)

### 6.1 Обновление ToolExecutionResult
- [ ] 6.1.1 Убрать `content: list[dict[str, Any]]` из `ToolExecutionResult`
- [ ] 6.1.2 Добавить `locations: list[FileLocation]`
- [ ] 6.1.3 Обновить docstring
- [ ] 6.1.4 Написать unit тесты

### 6.2 Создание ToolResultMapper
- [ ] 6.2.1 Создать `server/mapping/tool_result_mapper.py`
- [ ] 6.2.2 Реализовать `to_acp_content()` метод
- [ ] 6.2.3 Реализовать `from_tool_result()` метод
- [ ] 6.2.4 Написать unit тесты

### 6.3 Миграция executors
- [ ] 6.3.1 Обновить `FileSystemToolExecutor` для использования `FileLocation`
- [ ] 6.3.2 Обновить `TerminalToolExecutor` для использования `FileLocation`
- [ ] 6.3.3 Обновить `MCPToolExecutor` для использования `FileLocation`
- [ ] 6.3.4 Обновить `ContentExtractor` для использования маппера
- [ ] 6.3.5 Написать интеграционные тесты

## Фаза 7: Разделение SessionState (высокий риск)

### 7.1 Создание domain агрегатов
- [ ] 7.1.1 Создать `server/domain/session.py` с `Session` aggregate root
- [ ] 7.1.2 Создать `SessionConfig` value object
- [ ] 7.1.3 Создать `ConversationHistory` value object
- [ ] 7.1.4 Создать `ToolCallRegistry` value object
- [ ] 7.1.5 Создать `PermissionState` value object
- [ ] 7.1.6 Создать `AgentPlan` value object
- [ ] 7.1.7 Создать `MultiAgentState` value object
- [ ] 7.1.8 Написать unit тесты для каждого агрегата

### 7.2 Создание SessionStateDTO
- [ ] 7.2.1 Создать `server/protocol/dto/session_dto.py`
- [ ] 7.2.2 Создать `SessionStateDTO` Pydantic модель
- [ ] 7.2.3 Создать DTO для каждого value object
- [ ] 7.2.4 Добавить `schema_version: 4`
- [ ] 7.2.5 Написать unit тесты

### 7.3 Создание SessionMapper
- [ ] 7.3.1 Создать `server/mapping/session_mapper.py`
- [ ] 7.3.2 Реализовать `to_dto()` метод
- [ ] 7.3.3 Реализовать `to_domain()` метод
- [ ] 7.3.4 Обработать все value objects
- [ ] 7.3.5 Написать unit тесты

### 7.4 Миграция SessionState
- [ ] 7.4.1 Заменить `SessionState` на `SessionStateDTO` в storage
- [ ] 7.4.2 Добавить миграцию schema_version: 3 → 4
- [ ] 7.4.3 Обновить `InMemoryStorage` для работы с DTO
- [ ] 7.4.4 Обновить `JsonFileStorage` для работы с DTO
- [ ] 7.4.5 Обновить все handlers для работы с domain `Session`
- [ ] 7.4.6 Обновить `ACPProtocol` для работы с domain `Session`
- [ ] 7.4.7 Обновить `PromptOrchestrator` для работы с domain `Session`
- [ ] 7.4.8 Написать интеграционные тесты

### 7.5 Миграция бизнес-логики
- [ ] 7.5.1 Перенести `add_message()` в `Session`
- [ ] 7.5.2 Перенести `create_tool_call()` в `Session`
- [ ] 7.5.3 Перенести `update_tool_call()` в `Session`
- [ ] 7.5.4 Перенести `set_permission_policy()` в `Session`
- [ ] 7.5.5 Обновить все вызовы для использования domain методов
- [ ] 7.5.6 Написать интеграционные тесты

## Фаза 8: Интеграционные тесты и документация

### 8.1 Интеграционные тесты
- [ ] 8.1.1 Написать E2E тесты для полного цикла prompt turn
- [ ] 8.1.2 Написать тесты для миграции storage format
- [ ] 8.1.3 Написать тесты для всех мапперов
- [ ] 8.1.4 Написать тесты для domain агрегатов

### 8.2 Документация
- [ ] 8.2.1 Обновить ARCHITECTURE.md с новой структурой
- [ ] 8.2.2 Обновить docstrings во всех новых файлах
- [ ] 8.2.3 Добавить примеры использования мапперов
- [ ] 8.2.4 Обновить codelab.md с новой архитектурой

### 8.3 Финальная проверка
- [ ] 8.3.1 Запустить `make check` (lint + typecheck + tests)
- [ ] 8.3.2 Проверить обратную совместимость storage
- [ ] 8.3.3 Проверить производительность (нет деградации)
- [ ] 8.3.4 Проверить покрытие тестами (>80%)

## Оценка объёма

| Фаза | Новых файлов | Изменённых файлов | Тестов | Риск |
|------|--------------|-------------------|--------|------|
| Фаза 1 | 3 | 5 | 15 | Низкий |
| Фаза 2 | 4 | 8 | 20 | Средний |
| Фаза 3 | 4 | 8 | 20 | Средний |
| Фаза 4 | 3 | 10 | 20 | Средний |
| Фаза 5 | 3 | 5 | 10 | Низкий |
| Фаза 6 | 2 | 6 | 15 | Низкий |
| Фаза 7 | 10 | 25 | 40 | Высокий |
| Фаза 8 | 0 | 5 | 30 | Низкий |
| **Итого** | **29** | **72** | **170** | - |

## Зависимости между фазами

```
Фаза 1 → Фаза 2 → Фаза 3 → Фаза 7
Фаза 1 → Фаза 4
Фаза 1 → Фаза 5
Фаза 1 → Фаза 6
Фаза 2, 3, 5, 6 → Фаза 7
Фаза 7 → Фаза 8
```

## Рекомендации по выполнению

1. **Фазы 1-6** можно выполнять параллельно (независимые изменения)
2. **Фаза 7** требует завершения фаз 2, 3, 5, 6
3. **Фаза 8** выполняется после завершения всех предыдущих фаз
4. Каждая фаза должна завершаться полным прогоном тестов
5. Рекомендуется создавать отдельный PR для каждой фазы

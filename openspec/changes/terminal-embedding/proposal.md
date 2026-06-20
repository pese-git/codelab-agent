# Proposal: Terminal Embedding в Tool Calls

## Контекст

ACP спецификация (08-Tool Calls.md, 10-Terminal.md) определяет возможность встраивания live terminal output в tool calls через content type `terminal`. Это позволяет клиентам отображать реальный вывод терминала в контексте выполнения инструмента.

**Текущее состояние:**
- Клиентская модель `ToolCallTerminalContent` уже готова (`client/messages.py:676-688`)
- Slash-команды (`/term-run`) уже генерируют terminal content (`prompt.py:1097, 1280`)
- Но LLM tool calls НЕ работают — `TerminalToolExecutor` возвращает только text output

**Проблемы:**
1. `ContentValidator` не поддерживает типы `terminal` и `content` в `SUPPORTED_TYPES`
2. `ToolExecutionResult` не имеет поля для хранения готовых ToolCallContent items
3. `ToolResultMapper.to_acp_content()` возвращает ContentBlocks, а не ToolCallContent items
4. `TerminalToolExecutor.execute_create()` не возвращает `{"type": "terminal", "terminalId": ...}` в content
5. `AgentLoop` игнорирует `extracted_content.content_items` и передаёт только text
6. Клиентский `ToolCallHandler` не сохраняет `content` из tool call updates

## Что изменяется

- **Сервер:** `ContentValidator` добавляет `terminal` и `content` в поддерживаемые типы
- **Сервер:** `ToolExecutionResult` получает поле `content` для ToolCallContent items
- **Сервер:** `ToolResultMapper.to_acp_content()` проверяет `result.content` перед fallback
- **Сервер:** `TerminalToolExecutor` возвращает terminal content в `ToolExecutionResult.content`
- **Сервер:** `AgentLoop` передаёт `extracted_content.content_items` вместо только text
- **Клиент:** `ToolCallHandler` сохраняет `content` из tool call updates
- **Тесты:** Unit и integration тесты для всех изменений

## Capabilities

### New Capabilities

- `terminal-embedding`: Поддержка `type: "terminal"` в tool call content для LLM tool calls. Включает: валидацию, генерацию terminal content в executor, передачу content через AgentLoop, сохранение на клиенте.

### Modified Capabilities

(нет модификаций существующих capabilities)

## Impact

**Сервер:**
- `server/protocol/content/validator.py` — добавить `terminal` и `content` в `SUPPORTED_TYPES` и `REQUIRED_FIELDS`
- `server/tools/base.py` — добавить поле `content` в `ToolExecutionResult`
- `server/mapping/tool_result_mapper.py` — обновить `to_acp_content()` для проверки `result.content`
- `server/tools/executors/terminal_executor.py` — возвращать terminal content в `execute_create()`
- `server/protocol/handlers/pipeline/stages/agent_loop.py` — передавать `extracted_content.content_items` в notification

**Клиент:**
- `client/presentation/chat/handlers/tool_call_handler.py` — сохранять `content` из updates

**Тесты:**
- Unit тесты для `ContentValidator` (terminal и content типы)
- Unit тесты для `ToolResultMapper` (проверка result.content)
- Unit тесты для `TerminalToolExecutor` (terminal content)
- Unit тесты для `AgentLoop` (передача content)
- Unit тесты для клиентского `ToolCallHandler` (сохранение content)
- Integration тест: LLM вызывает terminal tool → клиент получает terminal content

**Документация:**
- Обновить docstrings в изменённых файлах

**Зависимости:** Нет новых зависимостей.

**Обратная совместимость:** Полная. Slash-команды (`/term-run`) продолжают работать как раньше.

**Известные проблемы (не исправляются в рамках этой задачи):**
- `ContentValidator.REQUIRED_FIELDS["diff"]` содержит `{"type", "path", "diff"}`, но ACP Schema определяет `{type, path, oldText, newText}`. Это pre-existing баг, не связанный с terminal embedding.

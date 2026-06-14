# Убрать MCP info из system prompt

## Контекст

MCP инструменты уже передаются LLM через `tools` параметр (function calling format) наравне с нативными инструментами. Секция MCP info в system prompt — дублирование, не несущее уникальной ценности. Tool names содержат префикс сервера, descriptions объясняют функциональность.

## Изменения

### 1. `src/codelab/server/agent/system_prompt_builder.py`
- Удалить метод `_format_mcp_info()`
- Удалить блок формирования MCP info в `build()`
- Удалить параметр `mcp_manager` из `build()`
- Обновить docstring (убрать упоминание MCP)
- Обновить логирование (убрать `has_mcp_info`)

### 2. `src/codelab/server/agent/orchestrator.py` (legacy, deprecated)
- Удалить метод `_format_mcp_info()`
- Удалить блок MCP info из `_build_system_message()`
- Удалить параметр `mcp_manager` из `_build_system_message()`

### 3. `src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py`
- Обновить комментарий: убрать "MCP info"
- Обновить docstring `__init__`: убрать "(config + MCP info)"
- Убрать `mcp_manager` из вызова `_system_prompt_builder.build()`

### 4. `src/codelab/server/protocol/handlers/pipeline/stages/llm_loop.py`
- Обновить docstring: убрать "(config + MCP info)"

### 5. `tests/server/agent/test_system_prompt_builder.py`
- Удалить `TestSystemPromptBuilderMCP` (5 тестов)
- Удалить `TestSystemPromptBuilderFormatMCPInfo` (2 теста)
- Удалить helper `_create_mock_mcp()`
- Обновить оставшиеся тесты

### 6. `tests/server/agent/test_orchestrator_mcp.py`
- Удалить `test_build_system_message_includes_mcp_info`

## Не затрагивает

- MCP инструменты продолжают передаваться через `tools` parameter
- `MCPManager.get_all_tools()` продолжает использоваться для фильтрации tools
- MCP executor продолжает работать

## Верификация

```bash
cd codelab && uv run ruff check . && uv run ty check && uv run python -m pytest
```

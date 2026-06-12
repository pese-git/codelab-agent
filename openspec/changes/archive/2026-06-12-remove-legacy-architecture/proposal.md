# Remove Legacy Architecture (AgentOrchestrator + NaiveAgent)

## Why

Текущая кодовая база содержит дублирующую legacy архитектуру (`AgentOrchestrator` + `NaiveAgent` + `LegacyCallStrategy`), которая полностью заменена новой архитектурой (`ExecutionEngine` + `LLMAdapter` + `StrategyDispatcher` + `SingleStrategy`).

Legacy код создаёт:
- **Двойные пути выполнения** — `LLMLoopStage` поддерживает fallback на `LegacyCallStrategy` когда нет `StrategyDispatcher`
- **Связанность** — `core.py`, `prompt_orchestrator.py`, `di.py` зависят от `AgentOrchestrator`
- **Поддержку** — 12 тестовых файлов, docstrings ссылаются на удалённый код
- **Путаницу** — новые разработчики не понимают какой путь использовать

`SingleStrategy` покрывает 100% функциональности legacy пути:

| Функция | Legacy | New |
|---------|--------|-----|
| System prompt | `_build_system_message()` | `SystemPromptBuilder` |
| History building | `_convert_to_llm_messages()` | `HistoryBuilder` |
| Tool filtering | `_filter_tools_by_capabilities()` | `ToolFilter` |
| Message sanitization | `_sanitize_orphaned_tool_calls()` | `MessageSanitizer` |
| Context compaction | ❌ | `ContextCompactor` |
| LLM call | `NaiveAgent.start_turn()` | `LLMAdapter` |
| Cancellation | `NaiveAgent._active_tasks` | `LLMAdapter._active_tasks` |
| Model resolution | `AgentOrchestrator.model_resolver` | `ModelResolver` (standalone) |

## What Changes

### Архитектурные изменения

1. **ModelResolver** — вынести из `AgentOrchestrator` в отдельный компонент DI
2. **cancel_prompt** — вынести из `AgentOrchestrator` в `LLMAdapter`
3. **PromptOrchestrator** — убрать `agent_orchestrator` параметр
4. **LLMLoopStage** — убрать fallback на `LegacyCallStrategy`
5. **DI контейнер** — убрать `AgentProvider`, добавить `ModelResolver`
6. **Удалить файлы** — `orchestrator.py`, `naive.py`, `legacy_adapter.py`
7. **Обновить тесты** — 12 файлов, ~50 тестов

### Capabilities

#### Removed Capabilities
- `agent-orchestrator`: Удалён `AgentOrchestrator` — заменён `ExecutionEngine`
- `naive-agent`: Удалён `NaiveAgent` — заменён `LLMAdapter`
- `legacy-call-strategy`: Удалён `LegacyCallStrategy` — адаптер для удалённого кода

#### Modified Capabilities
- `llm-loop-stage`: Убран fallback на legacy path, только `StrategyDispatcher`
- `prompt-orchestrator`: Убран `agent_orchestrator` параметр
- `acp-protocol`: Убран `agent_orchestrator` параметр, добавлен `model_resolver`
- `di-container`: Убран `AgentProvider`, добавлен `ModelResolver`

## Impact

**Удаляемые файлы:**
- `codelab/src/codelab/server/agent/orchestrator.py`
- `codelab/src/codelab/server/agent/naive.py`
- `codelab/src/codelab/server/agent/strategies/legacy_adapter.py`

**Изменяемые файлы:**
- `codelab/src/codelab/server/protocol/core.py`
- `codelab/src/codelab/server/protocol/handlers/prompt_orchestrator.py`
- `codelab/src/codelab/server/protocol/handlers/pipeline/stages/llm_loop.py`
- `codelab/src/codelab/server/di.py`
- `codelab/src/codelab/server/agent/__init__.py`
- `codelab/src/codelab/server/agent/strategies/__init__.py`
- `codelab/src/codelab/server/agent/strategies/base.py`
- `codelab/src/codelab/server/agent/base.py`
- `codelab/src/codelab/server/agent/llm_adapter.py`

**Удаляемые тесты:**
- `tests/server/test_agent_orchestrator.py`
- `tests/server/test_naive_agent.py`
- `tests/server/agent/strategies/test_legacy_adapter.py`
- `tests/server/agent/test_orchestrator_mcp.py`

**Обновляемые тесты:**
- `tests/server/test_protocol.py`
- `tests/server/test_protocol_with_agent.py`
- `tests/server/test_prompt_orchestrator.py`
- `tests/server/test_agent_loop_integration.py`
- `tests/server/test_tool_execution_integration.py`
- `tests/server/test_extensibility.py`
- `tests/server/test_client_rpc_service_integration.py`
- `tests/server/llm/test_integration_multi_provider.py`
- `tests/server/factories.py`

## Breaking Changes

- `ACPProtocol.__init__` — убран `agent_orchestrator` параметр
- `PromptOrchestrator.handle_prompt()` — убран `agent_orchestrator` параметр
- `LLMLoopStage.execute_pending_tool()` — убран `agent_orchestrator` параметр
- DI — убран `AgentProvider`, `AgentOrchestrator` больше не создаётся

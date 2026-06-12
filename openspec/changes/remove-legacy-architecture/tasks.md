# Tasks: Remove Legacy Architecture

## Phase 1: Вынести ModelResolver из AgentOrchestrator

- [ ] 1.1 Добавить `ModelResolver` провайдер в `di.py` (в `RegistryProvider` или отдельный)
- [ ] 1.2 Обновить `core.py:294-314` — `_get_default_model()` использовать `self._model_resolver`
- [ ] 1.3 Обновить `core.py:1291-1294` — `_handle_set_config_option()` использовать `self._model_resolver`
- [ ] 1.4 Добавить `model_resolver: ModelResolver | None` параметр в `ACPProtocol.__init__`
- [ ] 1.5 Обновить `di.py:RequestProvider` — передать `model_resolver` в `ACPProtocol`
- [ ] 1.6 Написать тесты: `test_get_default_model_uses_model_resolver`

---

## Phase 2: Вынести cancel_prompt в LLMAdapter

- [ ] 2.1 Добавить `cancel_prompt(session_id: str)` метод в `LLMAdapter`
- [ ] 2.2 Добавить `cancel_prompt(session_id)` в `LLMAgent` Protocol (`agent/base.py`)
- [ ] 2.3 Добавить `llm_adapter: LLMAdapter | None` параметр в `ACPProtocol.__init__`
- [ ] 2.4 Обновить `core.py:1246-1247` — `_handle_session_cancel()` использовать `llm_adapter.cancel_prompt()`
- [ ] 2.5 Обновить `di.py:RequestProvider` — передать `llm_adapter` в `ACPProtocol`
- [ ] 2.6 Написать тесты: `test_cancel_prompt_calls_llm_adapter`

---

## Phase 3: Убрать agent_orchestrator из PromptOrchestrator

- [ ] 3.1 Убрать `agent_orchestrator` параметр из `PromptOrchestrator.handle_prompt()`
- [ ] 3.2 Убрать `context.meta["agent_orchestrator"] = agent_orchestrator`
- [ ] 3.3 Убрать `agent_orchestrator` из `PromptOrchestrator.execute_pending_tool()`
- [ ] 3.4 Обновить `core.py:1696-1700` — убрать `agent_orchestrator` из вызова `execute_pending_tool()`
- [ ] 3.5 Обновить `core.py:1188` — убрать `agent_orchestrator` из `_get_prompt_orchestrator()`
- [ ] 3.6 Обновить TYPE_CHECKING imports в `prompt_orchestrator.py`
- [ ] 3.7 Написать тесты: `test_handle_prompt_without_agent_orchestrator`

---

## Phase 4: Убрать fallback на LegacyCallStrategy из LLMLoopStage

- [ ] 4.1 Удалить `from codelab.server.agent.strategies.legacy_adapter import LegacyCallStrategy`
- [ ] 4.2 Удалить TYPE_CHECKING import `AgentOrchestrator`
- [ ] 4.3 `_get_or_create_agent_loop()` — заменить fallback на `raise ValueError("StrategyDispatcher not configured")`
- [ ] 4.4 `process()` — убрать проверку `agent_orchestrator` для demo mode, заменить на отдельный флаг
- [ ] 4.5 `execute_pending_tool()` — убрать `agent_orchestrator` параметр
- [ ] 4.6 Убрать `LegacyCallStrategy` из docstrings
- [ ] 4.7 Написать тесты: `test_llm_loop_raises_without_strategy_dispatcher`

---

## Phase 5: Обновить DI контейнер

- [ ] 5.1 Удалить `from .agent.orchestrator import AgentOrchestrator`
- [ ] 5.2 Удалить `AgentProvider` класс
- [ ] 5.3 Убрать `AgentProvider()` из `make_container()`
- [ ] 5.4 `RequestProvider.get_acp_protocol()` — убрать `agent_orchestrator` параметр
- [ ] 5.5 Добавить `ModelResolver` в провайдеры
- [ ] 5.6 Добавить `LLMAdapter` в провайдеры (получить из `ExecutionEngine` или `AgentFactory`)
- [ ] 5.7 Написать тесты: `test_di_creates_acp_protocol_without_agent_orchestrator`

---

## Phase 6: Удалить legacy файлы

- [ ] 6.1 Удалить `codelab/src/codelab/server/agent/orchestrator.py`
- [ ] 6.2 Удалить `codelab/src/codelab/server/agent/naive.py`
- [ ] 6.3 Удалить `codelab/src/codelab/server/agent/strategies/legacy_adapter.py`
- [ ] 6.4 Обновить `agent/__init__.py` — убрать экспорты `NaiveAgent`, `AgentOrchestrator`
- [ ] 6.5 Обновить `agent/strategies/__init__.py` — убрать экспорт `LegacyCallStrategy`
- [ ] 6.6 Обновить `agent/strategies/base.py` docstring — убрать упоминание `LegacyCallStrategy`
- [ ] 6.7 Обновить `agent/base.py` docstring — убрать упоминание `AgentOrchestrator`

---

## Phase 7: Удалить legacy тесты

- [ ] 7.1 Удалить `tests/server/test_agent_orchestrator.py`
- [ ] 7.2 Удалить `tests/server/test_naive_agent.py`
- [ ] 7.3 Удалить `tests/server/agent/strategies/test_legacy_adapter.py`
- [ ] 7.4 Удалить `tests/server/agent/test_orchestrator_mcp.py`

---

## Phase 8: Обновить интеграционные тесты

- [ ] 8.1 Обновить `tests/server/test_protocol.py` — убрать `agent_orchestrator` из fixtures
- [ ] 8.2 Обновить `tests/server/test_protocol_with_agent.py` — перейти на `StrategyDispatcher`
- [ ] 8.3 Обновить `tests/server/test_prompt_orchestrator.py` — убрать `agent_orchestrator` параметр
- [ ] 8.4 Обновить `tests/server/test_agent_loop_integration.py` — убрать legacy path тесты
- [ ] 8.5 Обновить `tests/server/test_tool_execution_integration.py` — обновить fixtures
- [ ] 8.6 Обновить `tests/server/test_extensibility.py` — обновить fixtures
- [ ] 8.7 Обновить `tests/server/test_client_rpc_service_integration.py` — обновить fixtures
- [ ] 8.8 Обновить `tests/server/llm/test_integration_multi_provider.py` — обновить `model_resolver` usage
- [ ] 8.9 Обновить `tests/server/factories.py` — обновить factory функции

---

## Phase 9: Обновить docstrings и комментарии

- [ ] 9.1 `agent/tool_filter.py:3` — убрать "Рефакторинг из AgentOrchestrator"
- [ ] 9.2 `agent/execution_engine.py:3` — убрать "Заменяет AgentOrchestrator"
- [ ] 9.3 `agent/history_builder.py:3` — убрать "Рефакторинг из AgentOrchestrator"
- [ ] 9.4 `agent/message_sanitizer.py:3` — убрать "Рефакторинг из AgentOrchestrator"
- [ ] 9.5 `agent/system_prompt_builder.py:3` — убрать "Рефакторинг из AgentOrchestrator"
- [ ] 9.6 `agent/llm_adapter.py:3` — убрать "Заменяет NaiveAgent"

---

## Phase 10: Верификация

- [ ] 10.1 `cd codelab && uv run ruff check .` — нет lint ошибок
- [ ] 10.2 `cd codelab && uv run ty check` — нет type ошибок
- [ ] 10.3 `cd codelab && uv run python -m pytest` — все тесты проходят
- [ ] 10.4 `make check` — полная проверка проходит

---

## Приоритеты

| Фаза | Приоритет | Зависимости |
|------|-----------|-------------|
| 1. ModelResolver | High | — |
| 2. cancel_prompt | High | — |
| 3. PromptOrchestrator | High | 1, 2 |
| 4. LLMLoopStage | High | 3 |
| 5. DI контейнер | High | 1, 2, 3, 4 |
| 6. Удаление файлов | High | 5 |
| 7. Удаление тестов | High | 6 |
| 8. Обновление тестов | High | 6, 7 |
| 9. Docstrings | Medium | 6 |
| 10. Верификация | High | 8, 9 |

---

## Метрики успеха

- [ ] Все legacy файлы удалены
- [ ] Все legacy тесты удалены или обновлены
- [ ] `make check` проходит без ошибок
- [ ] Все тесты проходят (нет регрессии)
- [ ] `AgentOrchestrator`, `NaiveAgent`, `LegacyCallStrategy` не импортируются нигде
- [ ] `LLMLoopStage` не имеет fallback на legacy path
- [ ] `PromptOrchestrator` не принимает `agent_orchestrator`
- [ ] `ACPProtocol` не принимает `agent_orchestrator`

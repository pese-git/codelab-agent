# Tasks: AgentLoop Refactoring

## 1. Создать `StopReason` enum

- [ ] 1.1 Создать `codelab/src/codelab/server/protocol/stop_reasons.py`
- [ ] 1.2 Реализовать enum с значениями: `END_TURN`, `MAX_TOKENS`, `MAX_TURN_REQUESTS`, `REFUSAL`, `CANCELLED`
- [ ] 1.3 Написать тесты: `tests/server/protocol/test_stop_reasons.py`

---

## 2. Создать `LLMCallStrategy` Protocol

- [ ] 2.1 Создать `codelab/src/codelab/server/agent/strategies/base.py`
- [ ] 2.2 Определить Protocol с методами `execute()` и `continue_execution()`
- [ ] 2.3 Добавить type hints и docstrings

---

## 3. Создать `LegacyCallStrategy` адаптер

- [ ] 3.1 Создать `codelab/src/codelab/server/agent/strategies/legacy_adapter.py`
- [ ] 3.2 Реализовать адаптер AgentOrchestrator под LLMCallStrategy
- [ ] 3.3 Написать тесты: `tests/server/agent/strategies/test_legacy_adapter.py`

---

## 4. Адаптировать `StrategyDispatcher` под Protocol

- [ ] 4.1 Обновить сигнатуры `execute()` и `continue_execution()` в `dispatcher.py`
- [ ] 4.2 Убедиться что StrategyDispatcher соответствует LLMCallStrategy Protocol
- [ ] 4.3 Обновить тесты: `tests/server/agent/strategies/test_dispatcher.py`

---

## 5. Создать `AgentLoop`

- [ ] 5.1 Создать `codelab/src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py`
- [ ] 5.2 Реализовать `AgentLoopResult` dataclass
- [ ] 5.3 Реализовать `AgentLoop.run()` — цикл итераций
- [ ] 5.4 Реализовать `AgentLoop.resume_after_permission()` — permission resume
- [ ] 5.5 Перенести `_process_tool_calls()` из LLMLoopStage
- [ ] 5.6 Перенести `_execute_pending_tool()` из LLMLoopStage
- [ ] 5.7 Добавить проверку cancellation через `_is_cancel_requested()`
- [ ] 5.8 Использовать `StopReason.MAX_TURN_REQUESTS` вместо `"max_iterations"`
- [ ] 5.9 Написать тесты: `tests/server/protocol/handlers/pipeline/stages/test_agent_loop.py`
  - [ ] test_run_no_tool_calls
  - [ ] test_run_with_tool_calls
  - [ ] test_run_max_turn_requests
  - [ ] test_run_cancellation
  - [ ] test_resume_after_permission

---

## 6. Рефакторить `LLMLoopStage`

- [ ] 6.1 Обновить `llm_loop.py` — тонкий адаптер к AgentLoop
- [ ] 6.2 Реализовать `_get_or_create_agent_loop()` — ленивое создание AgentLoop
- [ ] 6.3 Обновить `process()` — делегировать AgentLoop.run()
- [ ] 6.4 Обновить `execute_pending_tool()` — делегировать AgentLoop.resume_after_permission()
- [ ] 6.5 Удалить `_run_llm_loop()` — заменён AgentLoop.run()
- [ ] 6.6 Удалить `_process_via_event_bus()` — заменён AgentLoop.run()
- [ ] 6.7 Удалить `_process_tool_calls_for_llm_loop()` — перенесён в AgentLoop
- [ ] 6.8 Удалить `run_loop()` — заменён AgentLoop.run()
- [ ] 6.9 Обновить тесты: `tests/server/protocol/handlers/pipeline/stages/test_llm_loop.py`

---

## 7. Обновить DI провайдеры

- [ ] 7.1 Обновить `PipelineProvider.get_llm_loop_stage()` в `di.py`
- [ ] 7.2 Передать новые зависимости в LLMLoopStage

---

## 8. Обновить существующие stop_reason usage

- [ ] 8.1 Заменить `"max_iterations"` на `StopReason.MAX_TURN_REQUESTS` в llm_loop.py
- [ ] 8.2 Обновить `prompt.py` — использовать StopReason enum
- [ ] 8.3 Обновить `core.py` — использовать StopReason enum

---

## 9. Интеграционные тесты

- [ ] 9.1 Создать `tests/server/test_agent_loop_integration.py`
- [ ] 9.2 Тест: полный цикл через EventBus с tool_calls
- [ ] 9.3 Тест: полный цикл через AgentOrchestrator с tool_calls
- [ ] 9.4 Тест: permission flow → resume → continue
- [ ] 9.5 Тест: cancellation во время tool execution

---

## 10. Документация

- [ ] 10.1 Обновить `codelab/README.md` — описать новую архитектуру
- [ ] 10.2 Добавить diagram в design.md — sequence diagram для AgentLoop
- [ ] 10.3 Обновить AGENTS.md — описать AgentLoop и LLMCallStrategy

---

## 11. Миграция и обратная совместимость

- [ ] 11.1 Проверить что legacy путь работает через LegacyCallStrategy
- [ ] 11.2 Проверить что EventBus путь работает через StrategyDispatcher
- [ ] 11.3 Убедиться что все существующие тесты проходят

---

## Приоритеты

| Задача | Приоритет | Зависимости |
|--------|-----------|-------------|
| 1. StopReason enum | High | — |
| 2. LLMCallStrategy Protocol | High | — |
| 3. LegacyCallStrategy | High | 2 |
| 4. StrategyDispatcher адаптация | High | 2 |
| 5. AgentLoop | High | 1, 2 |
| 6. LLMLoopStage рефакторинг | High | 5 |
| 7. DI провайдеры | High | 6 |
| 8. Stop_reason usage | Medium | 1 |
| 9. Интеграционные тесты | High | 6, 7 |
| 10. Документация | Medium | 6 |
| 11. Миграция | High | 6, 7, 9 |

---

## Метрики успеха

- [ ] Все существующие тесты проходят
- [ ] Новые тесты для AgentLoop проходят
- [ ] `LLMLoopStage` < 100 строк
- [ ] `AgentLoop` имеет полную coverage
- [ ] Stop reasons соответствуют ACP спецификации
- [ ] Legacy путь работает без изменений
- [ ] EventBus путь имеет цикл итераций
- [ ] Permission flow работает корректно

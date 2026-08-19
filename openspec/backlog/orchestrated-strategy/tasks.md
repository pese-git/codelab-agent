## 1. RouteDecision модель
- [ ] 1.1 Создать `server/agent/strategies/models.py` с RouteDecision (Pydantic)
- [ ] 1.2 Создать prompt template ROUTE_DECISION_PROMPT
- [ ] 1.3 Unit-тесты RouteDecision валидации

## 2. TokenSlicer
- [ ] 2.1 Создать `server/agent/strategies/token_slicer.py` — TokenSlicer класс
- [ ] 2.2 Реализовать SUMMARIZE_PROMPT template
- [ ] 2.3 Реализовать skip threshold логику
- [ ] 2.4 Реализовать fallback truncate (60% head + 40% tail)
- [ ] 2.5 Интеграция с Tracer (span token_slicing с метриками)
- [ ] 2.6 Unit-тесты TokenSlicer (summarize, skip, fallback)

## 3. SubAgentCoordinator
- [ ] 3.1 Создать `server/agent/strategies/sub_agent_coordinator.py` — SubAgentCoordinator
- [ ] 3.2 Реализовать process_subagent_response() — child session + TokenSlicer + FCM.add_to_scope()
- [ ] 3.3 Реализовать _create_child_session() — создание и связывание parent↔child в SessionStorage
- [ ] 3.4 Unit-тесты SubAgentCoordinator
- **Примечание:** `ensure_context_fits()` НЕ реализуется — FCM.optimize_and_build_payload() покрывает через DefaultContextCompactor

## 4. OrchestratedStrategy
- [ ] 4.1 Создать `server/agent/strategies/orchestrated.py` — OrchestratedStrategy
- [ ] 4.2 Реализовать цикл route→execute→slice→next
- [ ] 4.3 Интеграция с RouteDecision (Structured Outputs)
- [ ] 4.4 Интеграция с SubAgentCoordinator (вместо HybridContextManager)
- [ ] 4.5 Интеграция с FCM: create_scope, add_to_scope, share_item, optimize_and_build_payload
- [ ] 4.6 Реализовать max_steps предохранитель
- [ ] 4.7 Реализовать race condition guard (проверка available_agents)
- [ ] 4.8 Реализовать cancellation flow
- [ ] 4.9 Unit-тесты OrchestratedStrategy

## 5. Интеграция с StrategyDispatcher
- [ ] 5.1 Добавить ORCHESTRATED_STRATEGY_DESCRIPTOR в descriptor.py
- [ ] 5.2 Валидация: orchestrator + subagent через AgentRegistry
- [ ] 5.3 Fallback notification при недоступности
- [ ] 5.4 Интеграция в DI контейнер

## 6. Child Sessions
- [ ] 6.1 SessionState: parent_session_id, child_session_ids, is_child_session
- [ ] 6.2 Storage: сохранение child sessions в отдельной директории
- [ ] 6.3 Migration v1→v3 для существующих session файлов

## 7. MCP Integration
- [ ] 7.1 MCP tools в AgentRequest.tools
- [ ] 7.2 MCPManager propagation в child sessions

## 8. Plan Support
- [ ] 8.1 Orchestrator update_plan → parent session plan
- [ ] 8.2 Sub-agent update_plan → child session plan
- [ ] 8.3 Merged plan в TUI

## 9. Тесты
- [ ] 9.1 Unit-тесты RouteDecision
- [ ] 9.2 Unit-тесты TokenSlicer
- [ ] 9.3 Unit-тесты SubAgentCoordinator
- [ ] 9.4 Unit-тесты OrchestratedStrategy
- [ ] 9.5 Integration тесты полного цикла (с FCM)
- [ ] 9.6 Тесты cancellation
- [ ] 9.7 Тесты child sessions

## 10. Верификация
- [ ] 10.1 uv run ruff check .
- [ ] 10.2 uv run ty check
- [ ] 10.3 uv run python -m pytest
- [ ] 10.4 make check

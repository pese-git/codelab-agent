## 1. TaskInvocation и TaskResult модели
- [ ] 1.1 Добавить TaskInvocation, TaskResult в `server/agent/strategies/models.py`
- [ ] 1.2 Реализовать _invocation_to_request() конвертацию
- [ ] 1.3 Unit-тесты моделей

## 2. Task Permissions
- [ ] 2.1 Создать `server/agent/strategies/task_permissions.py` — TaskPermissions resolver
- [ ] 2.2 Реализовать проверку: allow/deny/ask
- [ ] 2.3 Интеграция с session/request_permission
- [ ] 2.4 Unit-тесты task permissions

## 3. HierarchicalStrategy
- [ ] 3.1 Создать `server/agent/strategies/hierarchical.py` — HierarchicalStrategy
- [ ] 3.2 Реализовать цикл: primary LLM → decision → delegate/answer
- [ ] 3.3 Интеграция с TaskInvocation → AgentRequest
- [ ] 3.4 Интеграция с TaskResult ← AgentResponse
- [ ] 3.5 Интеграция с SubAgentCoordinator (child sessions + TokenSlicer, вместо HybridContextManager)
- [ ] 3.6 Интеграция с FCM: create_scope, hydrate_from_history, share_item, optimize_and_build_payload
- [ ] 3.7 Интеграция с TaskPermissions
- [ ] 3.8 Реализовать cascade cancellation
- [ ] 3.9 Unit-тесты HierarchicalStrategy

## 4. Интеграция с StrategyDispatcher
- [ ] 4.1 Добавить HIERARCHICAL_STRATEGY_DESCRIPTOR в descriptor.py
- [ ] 4.2 Валидация: primary + subagent через AgentRegistry
- [ ] 4.3 Fallback notification при недоступности
- [ ] 4.4 Интеграция в DI контейнер

## 5. MCP Propagation
- [ ] 5.1 Создать `server/agent/strategies/mcp_context.py` — MCP propagation
- [ ] 5.2 MCPManager в child sessions
- [ ] 5.3 Тесты MCP в hierarchical

## 6. Plan Support
- [ ] 6.1 Primary update_plan → parent session
- [ ] 6.2 Sub-agent update_plan → child session
- [ ] 6.3 Merged plan в TUI

## 7. Тесты
- [ ] 7.1 Unit-тесты TaskInvocation/TaskResult
- [ ] 7.2 Unit-тесты TaskPermissions
- [ ] 7.3 Unit-тесты HierarchicalStrategy
- [ ] 7.4 Integration тесты полного цикла
- [ ] 7.5 Тесты cascade cancellation
- [ ] 7.6 Тесты MCP propagation

## 8. Верификация
- [ ] 8.1 uv run ruff check .
- [ ] 8.2 uv run ty check
- [ ] 8.3 uv run python -m pytest
- [ ] 8.4 make check

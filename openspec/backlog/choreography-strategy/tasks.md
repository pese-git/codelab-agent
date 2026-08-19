## 1. ContextBroadcast и ChoreographyAnswer модели
- [ ] 1.1 Добавить ContextBroadcast, ChoreographyAnswer в `server/agent/strategies/models.py`
- [ ] 1.2 Unit-тесты моделей

## 2. Conflict Resolution
- [ ] 2.1 Создать `server/agent/strategies/conflict_resolution.py` — Priority Queue
- [ ] 2.2 Реализовать выбор winner по priority
- [ ] 2.3 Обработка равных priority
- [ ] 2.4 Unit-тесты Conflict Resolution

## 3. ChoreographyStrategy
- [ ] 3.1 Создать `server/agent/strategies/choreography.py` — ChoreographyStrategy
- [ ] 3.2 Реализовать broadcast → parallel → conflict resolution → winner
- [ ] 3.3 Интеграция с EventBus.broadcast()
- [ ] 3.4 Интеграция с SubAgentCoordinator (child session для winner, вместо HybridContextManager)
- [ ] 3.5 Интеграция с FCM: create_scope("_broadcast_context"), optimize_and_build_payload, share_from winner
- [ ] 3.6 Реализовать max_steps предохранитель
- [ ] 3.7 Реализовать coordination_overhead_tokens подсчёт
- [ ] 3.8 Реализовать cancellation flow (asyncio.gather + return_exceptions)
- [ ] 3.9 Unit-тесты ChoreographyStrategy

## 4. Интеграция с StrategyDispatcher
- [ ] 4.1 Добавить CHOREOGRAPHY_STRATEGY_DESCRIPTOR в descriptor.py
- [ ] 4.2 Валидация: ≥2 subagents через AgentRegistry
- [ ] 4.3 Fallback notification при недоступности
- [ ] 4.4 Интеграция в DI контейнер

## 5. Тесты
- [ ] 5.1 Unit-тесты ContextBroadcast/ChoreographyAnswer
- [ ] 5.2 Unit-тесты Conflict Resolution
- [ ] 5.3 Unit-тесты ChoreographyStrategy
- [ ] 5.4 Integration тесты полного цикла
- [ ] 5.5 Тесты cancellation (partial results ignored)
- [ ] 5.6 Тесты winner child session

## 6. Верификация
- [ ] 6.1 uv run ruff check .
- [ ] 6.2 uv run ty check
- [ ] 6.3 uv run python -m pytest
- [ ] 6.4 make check

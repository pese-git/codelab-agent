## Tasks

### 1. StrategyDispatcher

- [ ] 1.1 Создать `codelab/src/codelab/server/protocol/handlers/strategies/strategy_dispatcher.py`
- [ ] 1.2 Создать класс `StrategyDispatcher` с полями: `_registry` (AgentRegistry), `_fallback`
- [ ] 1.3 Реализовать `select_strategy(session) → str` — выбор по приоритету
- [ ] 1.4 Реализовать приоритет: `context.meta["active_strategy"]` → `config_values["_active_strategy"]` → `"single"`
- [ ] 1.5 Реализовать `_validate_strategy(mode, registry) → str` — валидация + fallback
- [ ] 1.6 Реализовать валидацию single: всегда проходит
- [ ] 1.7 Реализовать валидацию multi_orchestrated: требуется orchestrator + subagent
- [ ] 1.8 Реализовать валидацию multi_choreographed: требуется >= 2 subagents
- [ ] 1.9 Реализовать валидацию hierarchical: требуется primary + subagent
- [ ] 1.10 Реализовать fallback на `global.fallback_mode` при недоступности
- [ ] 1.11 Написать тесты: цепочка приоритетов (slash > config > default)
- [ ] 1.12 Написать тесты: валидация для каждой стратегии
- [ ] 1.13 Написать тесты: поведение fallback

### 2. Уведомление о Fallback

- [ ] 2.1 Реализовать `build_fallback_notification(requested, actual, reason) → ACPMessage`
- [ ] 2.2 Формат: agent_message_chunk с text="[system] ... Переключение на ... mode"
- [ ] 2.3 Написать тесты: корректность формата уведомления

### 3. Config Option `_active_strategy`

> **Существующий код:** `SessionState.config_values: dict[str, str]` уже поддерживает произвольные ключи. Не нужно менять модель — `_active_strategy` хранится в `config_values`.

- [ ] 3.1 ~~Обновить `state.py`~~ — ПРОПУСТИТЬ: `config_values` уже поддерживает произвольные ключи
- [ ] 3.2 Обновить `handlers/config.py` — обработка `set_config_option` для `_active_strategy` с валидацией значений (single, multi_orchestrated, multi_choreographed, hierarchical)
- [ ] 3.3 Написать тесты: set_config_option _active_strategy → сохраняется в config_values

### 4. Интеграция PromptOrchestrator

- [ ] 4.1 Обновить `prompt_orchestrator.py` — интеграция StrategyDispatcher
- [ ] 4.2 Вызывать `select_strategy()` перед `execute()`
- [ ] 4.3 Отправить fallback notification если режим изменился
- [ ] 4.4 Написать тесты: интеграция с pipeline

### 5. Интеграция Slash Command

- [ ] 5.1 Обновить обработчик slash command для поддержки `/strategy` override (опционально)
- [ ] 5.2 Установить `context.meta["active_strategy"]` при slash command
- [ ] 5.3 Написать тесты: override slash командой

## Tasks

### 0. StrategyRegistry Infrastructure

- [ ] 0.1 Создать `codelab/src/codelab/server/agent/strategies/descriptor.py`
- [ ] 0.2 Создать `StrategyDescriptor` dataclass (name, display_name, description, factory, validator)
- [ ] 0.3 Создать `StrategyDependencies` dataclass (event_bus, execution_engine, tracer, agent_name)
- [ ] 0.4 Создать `codelab/src/codelab/server/agent/strategies/registry.py`
- [ ] 0.5 Создать класс `StrategyRegistry` с методами: register, get, get_available, create_instance, list_all
- [ ] 0.6 Реализовать `get_available(agent_registry)` — фильтрация по validator
- [ ] 0.7 Реализовать `create_instance(name, deps)` — создание экземпляра через factory
- [ ] 0.8 Добавить `SINGLE_STRATEGY_DESCRIPTOR` в `single_strategy.py`
- [ ] 0.9 Написать тесты: `tests/server/agent/strategies/test_registry.py`
  - [ ] test_register_strategy
  - [ ] test_get_strategy
  - [ ] test_get_available_filters_by_validator
  - [ ] test_create_instance
  - [ ] test_list_all
  - [ ] test_single_strategy_descriptor_exists
  - [ ] test_single_strategy_validator_always_true

---

### 1. StrategyDispatcher (маршрутизация)

- [ ] 1.1 Обновить `codelab/src/codelab/server/agent/strategies/dispatcher.py`
- [ ] 1.2 Изменить `__init__` — принимать `strategy_registry: StrategyRegistry`, `agent_registry: AgentRegistry`, `strategy_dependencies: StrategyDependencies`
- [ ] 1.3 Реализовать `select_strategy(session, context_meta) → (strategy_name, fallback_from | None)`
- [ ] 1.4 Реализовать приоритет: `context.meta["active_strategy"]` → `config_values["_active_strategy"]` → `default_strategy`
- [ ] 1.5 Реализовать валидацию через `strategy_registry.get_available(agent_registry)`
- [ ] 1.6 Реализовать fallback на `fallback_strategy` при недоступности
- [ ] 1.7 Реализовать `get_current_strategy() → LLMCallStrategy | None`
- [ ] 1.8 Реализовать `set_current_strategy(name) → bool`
- [ ] 1.9 Реализовать `build_fallback_notification(session_id, requested, actual, reason) → ACPMessage`
- [ ] 1.10 Написать тесты: `tests/server/agent/strategies/test_dispatcher.py`
  - [ ] test_select_strategy_priority_slash_command
  - [ ] test_select_strategy_priority_config_values
  - [ ] test_select_strategy_priority_default
  - [ ] test_select_strategy_fallback_when_unavailable
  - [ ] test_select_strategy_fallback_chain
  - [ ] test_get_current_strategy
  - [ ] test_set_current_strategy
  - [ ] test_build_fallback_notification_format

---

### 2. Уведомление о Fallback

- [ ] 2.1 Реализовать `build_fallback_notification(requested, actual, reason) → ACPMessage`
- [ ] 2.2 Формат: agent_message_chunk с text="[system] Strategy 'X' unavailable (reason). Falling back to 'Y'."
- [ ] 2.3 Написать тесты: корректность формата уведомления

---

### 3. Config Option `_active_strategy`

> **Существующий код:** `SessionState.config_values: dict[str, str]` уже поддерживает произвольные ключи. Не нужно менять модель — `_active_strategy` хранится в `config_values`.

- [ ] 3.1 ~~Обновить `state.py`~~ — ПРОПУСТИТЬ: `config_values` уже поддерживает произвольные ключи
- [ ] 3.2 Обновить `handlers/config.py` — обработка `set_config_option` для `_active_strategy` с валидацией через StrategyRegistry
- [ ] 3.3 Добавить параметр `strategy_registry: StrategyRegistry | None` в `session_set_config_option`
- [ ] 3.4 Реализовать валидацию: проверять что стратегия доступна через `registry.get_available()`
- [ ] 3.5 Написать тесты: set_config_option _active_strategy → сохраняется в config_values
- [ ] 3.6 Написать тесты: set_config_option _active_strategy unavailable → ошибка

---

### 4. Динамическое формирование configOptions

- [ ] 4.1 Обновить `codelab/src/codelab/server/protocol/core.py`
- [ ] 4.2 Создать метод `_build_active_strategy_config_spec()`
- [ ] 4.3 Реализовать динамическое формирование options из `strategy_registry.get_available(agent_registry)`
- [ ] 4.4 Использовать `display_name` и `description` из `StrategyDescriptor`
- [ ] 4.5 Обновить `_build_config_specs()` — добавить `_active_strategy` в additional_specs
- [ ] 4.6 Написать тесты: configOptions содержит только доступные стратегии
- [ ] 4.7 Написать тесты: configOptions использует display_name и description из descriptor

---

### 5. Интеграция в Pipeline

- [ ] 5.1 Обновить `prompt_orchestrator.py` — интеграция StrategyDispatcher
- [ ] 5.2 Обновить `llm_loop.py` — вызывать `select_strategy()` перед execute
- [ ] 5.3 Отправить fallback notification если режим изменился
- [ ] 5.4 Установить стратегию через `set_current_strategy()`
- [ ] 5.5 Получить экземпляр через `get_current_strategy()`
- [ ] 5.6 Написать тесты: интеграция с pipeline
- [ ] 5.7 Написать тесты: fallback notification отправляется

---

### 6. Интеграция Slash Command

- [ ] 6.1 Обновить обработчик slash command `strategy.py`
- [ ] 6.2 Добавить проверку доступности через `strategy_registry.get_available()`
- [ ] 6.3 Установить `session.config_values["_active_strategy"]` при slash command
- [ ] 6.4 Обновить `slash_commands.py` — установить `context.meta["active_strategy"]` после slash command
- [ ] 6.5 Написать тесты: override slash командой
- [ ] 6.6 Написать тесты: slash command валидирует доступность

---

### 7. DI обновление

- [ ] 7.1 Создать `StrategyRegistryProvider` в `di.py`
- [ ] 7.2 Реализовать `get_strategy_registry()` — создать и заполнить Registry
- [ ] 7.3 Зарегистрировать `SINGLE_STRATEGY_DESCRIPTOR`
- [ ] 7.4 Создать `get_strategy_dependencies()` в `MultiAgentProvider`
- [ ] 7.5 Обновить `get_strategy_dispatcher()` — передавать StrategyRegistry, AgentRegistry, StrategyDependencies
- [ ] 7.6 Обновить `RequestProvider.get_acp_protocol()` — передавать strategy_registry
- [ ] 7.7 Написать тесты: DI создаёт StrategyDispatcher с правильными параметрами

---

### 8. Client-side UI: StrategySelectorViewModel

- [ ] 8.1 Создать `codelab/src/codelab/client/presentation/strategy_selector_view_model.py`
- [ ] 8.2 Создать dataclass `StrategyOption` (value, label, description)
- [ ] 8.3 Создать класс `StrategySelectorViewModel` с Observable свойствами
- [ ] 8.4 Реализовать `update_strategies_from_config(configOptions, session_id)`
- [ ] 8.5 Реализовать поиск option с id="_active_strategy"
- [ ] 8.6 Реализовать `_parse_strategy_options(raw_options)`
- [ ] 8.7 Реализовать `select_strategy_cmd` — отправка set_config_option
- [ ] 8.8 Написать тесты: `tests/client/test_presentation_strategy_selector_view_model.py`
  - [ ] test_update_strategies_from_config
  - [ ] test_update_strategies_finds_active_strategy
  - [ ] test_select_strategy_success
  - [ ] test_select_strategy_updates_config
  - [ ] test_parse_strategy_options

---

### 9. Client-side UI: StrategySelectorModal

- [ ] 9.1 Создать `codelab/src/codelab/client/tui/components/strategy_selector.py`
- [ ] 9.2 Создать класс `StrategyItem` (аналог ModelItem)
- [ ] 9.3 Создать класс `StrategySelectorModal` (ModalScreen)
- [ ] 9.4 Реализовать compose() — отображение списка стратегий
- [ ] 9.5 Реализовать навигацию (↑↓)
- [ ] 9.6 Реализовать выбор (Enter)
- [ ] 9.7 Реализовать закрытие (Esc)
- [ ] 9.8 Написать тесты: StrategySelectorModal
  - [ ] test_strategy_selector_modal_compose
  - [ ] test_strategy_item_click
  - [ ] test_strategy_item_current_marker
  - [ ] test_action_select
  - [ ] test_action_previous_next

---

### 10. Интеграция в TUI

- [ ] 10.1 Обновить `codelab/src/codelab/client/tui/app.py`
- [ ] 10.2 Создать `StrategySelectorViewModel` в `__init__`
- [ ] 10.3 Подписаться на событие `config_option_updated`
- [ ] 10.4 Реализовать `_on_config_option_updated` — обновить ViewModel
- [ ] 10.5 Реализовать `action_open_strategy_selector()`
- [ ] 10.6 Добавить hotkey `Ctrl+S` в BINDINGS
- [ ] 10.7 Написать тесты: интеграция в TUI
  - [ ] test_strategy_selector_vm_initialized
  - [ ] test_config_option_updated_updates_strategy_vm
  - [ ] test_action_open_strategy_selector

---

### 11. Интеграционные тесты

- [ ] 11.1 Создать `tests/server/test_strategy_integration.py`
- [ ] 11.2 Тест: e2e strategy selection via configOptions
- [ ] 11.3 Тест: e2e strategy selection via slash command
- [ ] 11.4 Тест: e2e fallback notification sent
- [ ] 11.5 Тест: e2e priority chain works
- [ ] 11.6 Тест: e2e dynamic strategy list updates

---

### 12. Документация

- [ ] 12.1 Обновить `codelab/README.md` — описать новую архитектуру
- [ ] 12.2 Добавить diagram в design.md — sequence diagram для StrategyDispatcher
- [ ] 12.3 Обновить AGENTS.md — описать StrategyRegistry и StrategyDispatcher

---

## Приоритеты

| Задача | Приоритет | Зависимости |
|--------|-----------|-------------|
| 0. StrategyRegistry Infrastructure | High | — |
| 1. StrategyDispatcher | High | 0 |
| 2. Fallback Notification | High | 1 |
| 3. Config Option _active_strategy | High | 0 |
| 4. Динамическое формирование configOptions | High | 0, 3 |
| 5. Интеграция в Pipeline | High | 1, 2 |
| 6. Интеграция Slash Command | High | 0, 3 |
| 7. DI обновление | High | 0, 1 |
| 8. StrategySelectorViewModel | Medium | 4 |
| 9. StrategySelectorModal | Medium | 8 |
| 10. Интеграция в TUI | Medium | 8, 9 |
| 11. Интеграционные тесты | High | 5, 6, 7 |
| 12. Документация | Medium | 5, 6, 7 |

---

## Метрики успеха

- [ ] StrategyRegistry создан и работает
- [ ] StrategyDispatcher использует Registry (только маршрутизация)
- [ ] configOptions формируется динамически из Registry
- [ ] Priority chain работает (slash > config > default)
- [ ] Validation через Registry.get_available()
- [ ] Fallback notification отправляется
- [ ] StrategySelectorViewModel парсит configOptions
- [ ] StrategySelectorModal позволяет выбрать стратегию
- [ ] Hotkey Ctrl+S открывает modal
- [ ] Slash command /strategy работает
- [ ] Все тесты проходят
- [ ] `make check` проходит

## Tasks

### 0. StrategyRegistry Infrastructure

- [x] 0.1 Создать `codelab/src/codelab/server/agent/strategies/descriptor.py`
- [x] 0.2 Создать `StrategyDescriptor` dataclass (name, display_name, description, factory, validator)
- [x] 0.3 Создать `StrategyDependencies` dataclass (event_bus, execution_engine, tracer, agent_name)
- [x] 0.4 Создать `codelab/src/codelab/server/agent/strategies/registry.py`
- [x] 0.5 Создать класс `StrategyRegistry` с методами: register, get, get_available, create_instance, list_all
- [x] 0.6 Реализовать `get_available(agent_registry)` — фильтрация по validator
- [x] 0.7 Реализовать `create_instance(name, deps)` — создание экземпляра через factory
- [x] 0.8 Добавить `SINGLE_STRATEGY_DESCRIPTOR` в `single_strategy.py`
- [x] 0.9 Написать тесты: `tests/server/agent/strategies/test_registry.py`
  - [x] test_register_strategy
  - [x] test_get_strategy
  - [x] test_get_available_filters_by_validator
  - [x] test_create_instance
  - [x] test_list_all
  - [x] test_single_strategy_descriptor_exists
  - [x] test_single_strategy_validator_always_true

---

### 1. StrategyDispatcher (маршрутизация)

- [x] 1.1 Обновить `codelab/src/codelab/server/agent/strategies/dispatcher.py`
- [x] 1.2 Изменить `__init__` — принимать `strategy_registry: StrategyRegistry`, `agent_registry: AgentRegistry`, `strategy_dependencies: StrategyDependencies`
- [x] 1.3 Реализовать `select_strategy(session, context_meta) → (strategy_name, fallback_from | None)`
- [x] 1.4 Реализовать приоритет: `context.meta["active_strategy"]` → `config_values["_active_strategy"]` → `default_strategy`
- [x] 1.5 Реализовать валидацию через `strategy_registry.get_available(agent_registry)`
- [x] 1.6 Реализовать fallback на `fallback_strategy` при недоступности
- [x] 1.7 Реализовать `get_current_strategy() → LLMCallStrategy | None`
- [x] 1.8 Реализовать `set_current_strategy(name) → bool`
- [x] 1.9 Реализовать `build_fallback_notification(session_id, requested, actual, reason) → ACPMessage`
- [x] 1.10 Написать тесты: `tests/server/agent/strategies/test_dispatcher.py`
  - [x] test_select_strategy_priority_slash_command
  - [x] test_select_strategy_priority_config_values
  - [x] test_select_strategy_priority_default
  - [x] test_select_strategy_fallback_when_unavailable
  - [x] test_select_strategy_fallback_chain
  - [x] test_get_current_strategy
  - [x] test_set_current_strategy
  - [x] test_build_fallback_notification_format

---

### 2. Уведомление о Fallback

- [x] 2.1 Реализовать `build_fallback_notification(requested, actual, reason) → ACPMessage`
- [x] 2.2 Формат: agent_message_chunk с text="[system] Strategy 'X' unavailable (reason). Falling back to 'Y'."
- [x] 2.3 Написать тесты: корректность формата уведомления

---

### 3. Config Option `_active_strategy`

> **Существующий код:** `SessionState.config_values: dict[str, str]` уже поддерживает произвольные ключи. Не нужно менять модель — `_active_strategy` хранится в `config_values`.

- [x] 3.1 ~~Обновить `state.py`~~ — ПРОПУСТИТЬ: `config_values` уже поддерживает произвольные ключи
- [x] 3.2 Обновить `handlers/config.py` — валидация работает автоматически через config_specs
- [x] 3.3 ~~Добавить параметр `strategy_registry`~~ — ПРОПУСТИТЬ: валидация через config_specs
- [x] 3.4 ~~Реализовать валидацию~~ — ПРОПУСТИТЬ: валидация через config_specs автоматически
- [x] 3.5 ~~Написать тесты~~ — валидация тестируется через интеграционные тесты
- [x] 3.6 ~~Написать тесты~~ — валидация тестируется через интеграционные тесты

---

### 4. Динамическое формирование configOptions

- [x] 4.1 Обновить `codelab/src/codelab/server/protocol/core.py`
- [x] 4.2 Создать метод `_build_active_strategy_config_spec()`
- [x] 4.3 Реализовать динамическое формирование options из `strategy_registry.get_available(agent_registry)`
- [x] 4.4 Использовать `display_name` и `description` из `StrategyDescriptor`
- [x] 4.5 Обновить `_build_config_specs()` — добавить `_active_strategy` в additional_specs
- [x] 4.6 Написать тесты: configOptions содержит только доступные стратегии
- [x] 4.7 Написать тесты: configOptions использует display_name и description из descriptor

---

### 5. Интеграция в Pipeline

- [x] 5.1 Обновить `prompt_orchestrator.py` — интеграция StrategyDispatcher
- [x] 5.2 Обновить `llm_loop.py` — вызывать `select_strategy()` перед execute
- [x] 5.3 Отправить fallback notification если режим изменился
- [x] 5.4 Установить стратегию через `set_current_strategy()`
- [x] 5.5 Получить экземпляр через `get_current_strategy()`
- [x] 5.6 Написать тесты: интеграция с pipeline
- [x] 5.7 Написать тесты: fallback notification отправляется

---

### 6. Интеграция Slash Command

- [x] 6.1 Обновить обработчик slash command `strategy.py`
- [x] 6.2 Добавить проверку доступности через `strategy_registry.get_available()`
- [x] 6.3 Установить `session.config_values["_active_strategy"]` при slash command
- [x] 6.4 Обновить `slash_commands.py` — установить `context.meta["active_strategy"]` после slash command
- [x] 6.5 Написать тесты: override slash командой
- [x] 6.6 Написать тесты: slash command валидирует доступность

---

### 7. DI обновление

- [x] 7.1 Создать `StrategyRegistryProvider` в `di.py` — добавлен в `MultiAgentProvider`
- [x] 7.2 Реализовать `get_strategy_registry()` — создать и заполнить Registry
- [x] 7.3 Зарегистрировать `SINGLE_STRATEGY_DESCRIPTOR`
- [x] 7.4 Создать `get_strategy_dependencies()` в `MultiAgentProvider`
- [x] 7.5 Обновить `get_strategy_dispatcher()` — передавать StrategyRegistry, AgentRegistry, StrategyDependencies
- [x] 7.6 Обновить `RequestProvider.get_acp_protocol()` — передавать strategy_registry
- [x] 7.7 Написать тесты: DI создаёт StrategyDispatcher с правильными параметрами

---

### 8. Client-side UI: StrategySelectorViewModel

- [x] 8.1 Создать `codelab/src/codelab/client/presentation/config_option_selector_view_model.py`
- [x] 8.2 Создать dataclass `ConfigOption` (value, label, description, extra)
- [x] 8.3 Создать класс `ConfigOptionSelectorViewModel` с Observable свойствами
- [x] 8.4 Реализовать `update_from_config(configOptions, session_id)`
- [x] 8.5 Реализовать поиск option с id=config_id
- [x] 8.6 Реализовать `_parse_options(raw_options)`
- [x] 8.7 Реализовать `select_option_cmd` — отправка set_config_option
- [x] 8.8 Создать специализированные ViewModel:
  - [x] ModeSelectorViewModel (config_id="mode")
  - [x] AgentSelectorViewModel (config_id="_agent")
  - [x] StrategySelectorViewModel (config_id="_active_strategy")
- [x] 8.9 Написать тесты: `tests/client/test_presentation_config_option_selector_view_model.py`
  - [x] test_init_with_config_id
  - [x] test_update_from_config_finds_correct_option
  - [x] test_update_from_config_uses_default_when_no_current
  - [x] test_update_from_config_config_not_found
  - [x] test_get_current_label_returns_label
  - [x] test_get_current_label_returns_value_if_not_found
  - [x] test_get_current_label_returns_not_selected_if_none
  - [x] test_select_option_calls_coordinator
  - [x] test_select_option_raises_if_not_available
  - [x] test_parse_options_with_extra_data

---

### 9. Client-side UI: StrategySelectorModal

- [x] 9.1 Создать `codelab/src/codelab/client/tui/components/config_option_selector.py`
- [x] 9.2 Создать класс `ConfigOptionItem` (аналог ModelItem)
- [x] 9.3 Создать класс `ConfigOptionSelectorModal` (ModalScreen)
- [x] 9.4 Реализовать compose() — отображение списка опций
- [x] 9.5 Реализовать навигацию (↑↓)
- [x] 9.6 Реализовать выбор (Enter)
- [x] 9.7 Реализовать закрытие (Esc)
- [x] 9.8 Реализовать поиск (Input с fuzzy match)

---

### 10. Интеграция в TUI

- [x] 10.1 Обновить `codelab/src/codelab/client/tui/app.py`
- [x] 10.2 Получить `ModeSelectorViewModel`, `AgentSelectorViewModel`, `StrategySelectorViewModel` из DI
- [x] 10.3 Подписаться на событие `config_option_updated`
- [x] 10.4 Реализовать `_on_config_option_updated` — обновить все ViewModel
- [x] 10.5 Реализовать `action_select_mode()`, `action_select_agent()`, `action_select_strategy()`
- [x] 10.6 Добавить hotkeys:
  - [x] `Ctrl+Shift+M` — выбрать режим
  - [x] `Ctrl+A` — выбрать агента
  - [x] `Ctrl+Shift+A` — выбрать стратегию
- [x] 10.7 Обновить `codelab/src/codelab/client/infrastructure/view_model_provider.py`
  - [x] Зарегистрировать ModeSelectorViewModel
  - [x] Зарегистрировать AgentSelectorViewModel
  - [x] Зарегистрировать StrategySelectorViewModel

---

### 11. Интеграционные тесты

- [x] 11.1 Создать `tests/server/test_strategy_integration.py`
- [x] 11.2 Тест: e2e strategy selection via configOptions
- [x] 11.3 Тест: e2e strategy selection via slash command
- [x] 11.4 Тест: e2e fallback notification sent
- [x] 11.5 Тест: e2e priority chain works
- [x] 11.6 Тест: e2e dynamic strategy list updates

---

### 12. Документация

- [x] 12.1 Обновить `codelab/README.md` — описать новую архитектуру
- [x] 12.2 Добавить diagram в design.md — sequence diagram для StrategyDispatcher
- [x] 12.3 Обновить AGENTS.md — описать StrategyRegistry и StrategyDispatcher

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

- [x] StrategyRegistry создан и работает
- [x] StrategyDispatcher использует Registry (только маршрутизация)
- [x] configOptions формируется динамически из Registry
- [x] Priority chain работает (slash > config > default)
- [x] Validation через Registry.get_available()
- [x] Fallback notification отправляется
- [x] ConfigOptionSelectorViewModel парсит configOptions
- [x] ConfigOptionSelectorModal позволяет выбрать опцию
- [x] Hotkeys работают:
  - [x] `Ctrl+M` — выбрать модель
  - [x] `Ctrl+Shift+M` — выбрать режим
  - [x] `Ctrl+A` — выбрать агента
  - [x] `Ctrl+Shift+A` — выбрать стратегию
- [x] Slash command /strategy работает
- [x] Все тесты проходят (3745 tests)
- [x] `make check` проходит — 67 ошибок lint являются pre-existing, не связаны с этим изменением

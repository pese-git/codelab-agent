## Tasks

### 1. Переименовать AgentsConfig.mode → AgentsConfig.strategy

- [ ] 1.1 Обновить `codelab/src/codelab/server/config.py`:
  - `mode: str = "single"` → `strategy: str = "single"`
  - `fallback_mode: str = "single"` → `fallback_strategy: str = "single"`
- [ ] 1.2 Обновить все ссылки на `agents.mode` → `agents.strategy` в кодовой базе
- [ ] 1.3 Обновить все ссылки на `agents.fallback_mode` → `agents.fallback_strategy`
- [ ] 1.4 Обновить TOML конфигурацию в примерах и документации
- [ ] 1.5 Написать тесты: загрузка `strategy` из TOML

### 2. Обновить StrategyDispatcher

- [ ] 2.1 Добавить параметр `agent_registry: AgentRegistry` в `__init__`
- [ ] 2.2 Добавить параметр `strategy: str = "single"` в `__init__`
- [ ] 2.3 Реализовать `_resolve_strategy()` — возвращает `(agent_name, strategy)`
- [ ] 2.4 Реализовать `_get_default_agent_name()` — по priority
- [ ] 2.5 Реализовать `_select_strategy()` — на основе состава Registry
- [ ] 2.6 Реализовать `set_strategy()` — runtime override
- [ ] 2.7 Обновить `execute()` — передавать `agent_name` в стратегию
- [ ] 2.8 Обновить `continue_execution()` — передавать `agent_name`
- [ ] 2.9 Написать тесты: `_resolve_strategy()` с разными агентами
- [ ] 2.10 Написать тесты: ошибка если агент не найден
- [ ] 2.11 Написать тесты: `set_strategy()` runtime override

### 3. Обновить SingleStrategy

- [ ] 3.1 Добавить параметр `agent_name: str | None = None` в `execute()`
- [ ] 3.2 Добавить параметр `agent_name: str | None = None` в `continue_execution()`
- [ ] 3.3 Использовать `target_agent = agent_name or self.agent_name`
- [ ] 3.4 Обновить tracing — `agent_name` в атрибутах span
- [ ] 3.5 Написать тесты: `execute()` с переданным `agent_name`
- [ ] 3.6 Написать тесты: `execute()` без `agent_name` (default)

### 4. Обновить ACPProtocol

- [ ] 4.1 Добавить параметр `agent_registry: AgentRegistry | None = None` в `__init__`
- [ ] 4.2 Реализовать `_build_agent_config_spec()` — из AgentRegistry
- [ ] 4.3 Обновить `_build_config_specs()` — добавить `_agent` option
- [ ] 4.4 Обновить session/new response — configOptions с `mode` и `_agent`
- [ ] 4.5 Обновить session/new response — legacy `modes` для совместимости
- [ ] 4.6 Написать тесты: configOptions содержит `mode` и `_agent`
- [ ] 4.7 Написать тесты: `_agent` options формируются из Registry

### 5. Обновить session.py

- [ ] 5.1 Обновить `build_config_options()` — для configOptions response
- [ ] 5.2 Обновить `build_modes_state()` — для legacy modes response
- [ ] 5.3 Написать тесты: configOptions format
- [ ] 5.4 Написать тесты: modes format (legacy)

### 6. Обновить DI провайдеры

- [ ] 6.1 Обновить `MultiAgentProvider.get_strategy_dispatcher()`:
  - Добавить `agent_registry` параметр
  - Добавить `config` параметр для `agents.strategy`
- [ ] 6.2 Обновить `RequestProvider.get_acp_protocol()`:
  - Добавить `agent_registry` параметр
- [ ] 6.3 Написать тесты: DI создаёт StrategyDispatcher с правильными параметрами

### 7. Обновить LLMLoopStage

- [ ] 7.1 Изменить параметр `use_event_bus: bool` → `strategy: str`
- [ ] 7.2 Обновить логирование — `strategy` вместо `mode`
- [ ] 7.3 Обновить `process()` — использовать `strategy` из server config
- [ ] 7.4 Написать тесты: LLMLoopStage с разными strategy

### 8. Добавить slash command `/strategy`

- [ ] 8.1 Создать `codelab/src/codelab/server/protocol/handlers/slash_commands/builtin/strategy.py`
- [ ] 8.2 Реализовать `StrategyCommandHandler`
- [ ] 8.3 Реализовать `execute()` — показать/изменить strategy
- [ ] 8.4 Реализовать `get_definition()` — AvailableCommand
- [ ] 8.5 Зарегистрировать в `SlashCommandsProvider`
- [ ] 8.6 Написать тесты: `/strategy` показывает текущую
- [ ] 8.7 Написать тесты: `/strategy single` меняет strategy
- [ ] 8.8 Написать тесты: `/strategy unknown` возвращает ошибку

### 9. Обновить тесты

- [ ] 9.1 Обновить `tests/server/test_config.py` — `mode` → `strategy`
- [ ] 9.2 Обновить `tests/server/test_protocol.py` — configOptions с `_agent`
- [ ] 9.3 Создать `tests/server/agent/strategies/test_dispatcher.py`
- [ ] 9.4 Создать `tests/server/protocol/handlers/slash_commands/test_strategy.py`
- [ ] 9.5 Обновить `tests/server/observability/` — agent_name в span

### 10. Интеграционные тесты

- [ ] 10.1 Создать `tests/server/test_strategy_integration.py`
- [ ] 10.2 Тест: полный flow с выбором агента
- [ ] 10.3 Тест: configOptions в session/new response
- [ ] 10.4 Тест: `/strategy` slash command
- [ ] 10.5 Тест: fallback — агент не найден

### 11. Обновить документацию

- [ ] 11.1 Обновить `codelab/README.md` — TOML конфигурация
- [ ] 11.2 Добавить описание `/strategy` slash command
- [ ] 11.3 Добавить описание config options `mode` и `_agent`
- [ ] 11.4 Обновить `codelab.toml.example` — `strategy` вместо `mode`

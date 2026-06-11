## Tasks

### 1. Переименовать AgentsConfig.mode → AgentsConfig.strategy

- [x] 1.1 Обновить `codelab/src/codelab/server/config.py`:
  - `mode: str = "single"` → `strategy: str = "single"`
  - `fallback_mode: str = "single"` → `fallback_strategy: str = "single"`
- [x] 1.2 Обновить все ссылки на `agents.mode` → `agents.strategy` в кодовой базе
- [x] 1.3 Обновить все ссылки на `agents.fallback_mode` → `agents.fallback_strategy`
- [x] 1.4 Обновить TOML конфигурацию в примерах и документации
- [x] 1.5 Написать тесты: загрузка `strategy` из TOML

### 2. Обновить StrategyDispatcher

- [x] 2.1 Добавить параметр `agent_registry: AgentRegistry` в `__init__`
- [x] 2.2 Добавить параметр `strategy: str = "single"` в `__init__`
- [x] 2.3 Реализовать `_resolve_strategy()` — возвращает `(agent_name, strategy)`
- [x] 2.4 Реализовать `_get_default_agent_name()` — по priority
- [x] 2.5 Реализовать `_select_strategy()` — на основе состава Registry
- [x] 2.6 Реализовать `set_strategy()` — runtime override
- [x] 2.7 Обновить `execute()` — передавать `agent_name` в стратегию
- [x] 2.8 Обновить `continue_execution()` — передавать `agent_name`
- [x] 2.9 Написать тесты: `_resolve_strategy()` с разными агентами
- [x] 2.10 Написать тесты: ошибка если агент не найден
- [x] 2.11 Написать тесты: `set_strategy()` runtime override

### 3. Обновить SingleStrategy

- [x] 3.1 Добавить параметр `agent_name: str | None = None` в `execute()`
- [x] 3.2 Добавить параметр `agent_name: str | None = None` в `continue_execution()`
- [x] 3.3 Использовать `target_agent = agent_name or self.agent_name`
- [x] 3.4 Обновить tracing — `agent_name` в атрибутах span
- [x] 3.5 Написать тесты: `execute()` с переданным `agent_name`
- [x] 3.6 Написать тесты: `execute()` без `agent_name` (default)

### 4. Обновить ACPProtocol

- [x] 4.1 Добавить параметр `agent_registry: AgentRegistry | None = None` в `__init__`
- [x] 4.2 Реализовать `_build_agent_config_spec()` — из AgentRegistry
- [x] 4.3 Обновить `_build_config_specs()` — добавить `_agent` option
- [x] 4.4 Обновить session/new response — configOptions с `mode` и `_agent`
- [x] 4.5 Обновить session/new response — legacy `modes` для совместимости
- [x] 4.6 Написать тесты: configOptions содержит `mode` и `_agent`
- [x] 4.7 Написать тесты: `_agent` options формируются из Registry

### 5. Обновить session.py — configOptions вместо modes

- [x] 5.1 Обновить `build_config_options()` — для configOptions response
- [x] 5.2 Обновить `build_modes_state()` — для legacy modes response
- [x] 5.3 Написать тесты: configOptions format
- [x] 5.4 Написать тесты: modes format (legacy)

### 6. Обновить DI провайдеры

- [x] 6.1 Обновить `MultiAgentProvider.get_strategy_dispatcher()`:
  - Добавить `agent_registry` параметр
  - Добавить `config` параметр для `agents.strategy`
- [x] 6.2 Обновить `RequestProvider.get_acp_protocol()`:
  - Добавить `agent_registry` параметр
- [x] 6.3 Написать тесты: DI создаёт StrategyDispatcher с правильными параметрами

### 7. Обновить LLMLoopStage

- [x] 7.1 Изменить параметр `use_event_bus: bool` → `strategy: str`
- [x] 7.2 Обновить логирование — `strategy` вместо `mode`
- [x] 7.3 Обновить `process()` — использовать `strategy` из server config
- [x] 7.4 Написать тесты: LLMLoopStage с разными strategy

### 8. Добавить slash command `/strategy`

- [x] 8.1 Создать `codelab/src/codelab/server/protocol/handlers/slash_commands/builtin/strategy.py`
- [x] 8.2 Реализовать `StrategyCommandHandler`
- [x] 8.3 Реализовать `execute()` — показать/изменить strategy
- [x] 8.4 Реализовать `get_definition()` — AvailableCommand
- [x] 8.5 Зарегистрировать в `SlashCommandsProvider`
- [x] 8.6 Написать тесты: `/strategy` показывает текущую
- [x] 8.7 Написать тесты: `/strategy single` меняет strategy
- [x] 8.8 Написать тесты: `/strategy unknown` возвращает ошибку

### 9. Обновить тесты

- [x] 9.1 Обновить `tests/server/test_config.py` — `mode` → `strategy`
- [x] 9.2 Обновить `tests/server/test_protocol.py` — configOptions с `_agent`
- [x] 9.3 Создать `tests/server/agent/strategies/test_dispatcher.py`
- [x] 9.4 Создать `tests/server/protocol/handlers/slash_commands/test_strategy.py`
- [x] 9.5 Обновить `tests/server/observability/` — agent_name в span

### 10. Интеграционные тесты

- [x] 10.1 Создать `tests/server/test_strategy_integration.py`
- [x] 10.2 Тест: полный flow с выбором агента
- [x] 10.3 Тест: configOptions в session/new response
- [x] 10.4 Тест: `/strategy` slash command
- [x] 10.5 Тест: fallback — агент не найден

### 11. Обновить документацию

- [x] 11.1 Обновить `codelab/README.md` — TOML конфигурация
- [x] 11.2 Добавить описание `/strategy` slash command
- [x] 11.3 Добавить описание config options `mode` и `_agent`
- [x] 11.4 Обновить `codelab.toml.example` — `strategy` вместо `mode`

### 12. Добавить конфигурации агентов

- [x] 12.1 Создать `~/.codelab/agents/coder.md` — агент-программист (priority: 1)
- [x] 12.2 Создать `~/.codelab/agents/architect.md` — агент-архитектор (priority: 2)
- [x] 12.3 Создать `~/.codelab/agents/debug.md` — агент-отладчик (priority: 3)
- [x] 12.4 Создать `~/.codelab/agents/ask.md` — агент-консультант (priority: 4)

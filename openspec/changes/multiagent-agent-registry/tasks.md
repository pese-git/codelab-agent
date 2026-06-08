## Tasks

### 1. Pydantic модели

- [ ] 1.1 Создать пакет `codelab/src/codelab/server/agent/config/` с `__init__.py`
- [ ] 1.2 Создать enum `AgentMode`: primary, subagent, orchestrator
- [ ] 1.3 Создать Pydantic модель `AgentPermission`: edit, bash, webfetch, task
- [ ] 1.4 Создать Pydantic модель `AgentTOMLConfig` с model_config(extra="allow")
- [ ] 1.5 Создать Pydantic модель `AgentsGlobalConfig` с полями: mode, fallback_mode, default_model, max_steps, context_window_limit, compaction_reserved_tokens, debug, definitions
- [ ] 1.6 Создать Pydantic модель `AgentMarkdownConfig` с model_config(extra="allow")
- [ ] 1.7 Создать Pydantic модель `ResolvedAgent`
- [ ] 1.8 Написать тесты для всех моделей (валидация, значения по умолчанию, extra поля)

### 2. AgentConfigLoader

- [ ] 2.1 Создать класс `AgentConfigLoader`
- [ ] 2.2 Реализовать `_parse_markdown(path: Path) → AgentMarkdownConfig` — парсинг frontmatter + body
- [ ] 2.3 Реализовать `_toml_to_markdown(name, cfg) → AgentMarkdownConfig` — конвертация TOML
- [ ] 2.4 Реализовать `load_all(global_toml, project_toml) → dict[str, AgentMarkdownConfig]`
- [ ] 2.5 Реализовать загрузку в порядке: global TOML → global MD → project TOML → project MD
- [ ] 2.6 Написать тесты: парсинг Markdown с frontmatter
- [ ] 2.7 Написать тесты: конвертация TOML в Markdown
- [ ] 2.8 Написать тесты: логика override (project MD > project TOML > global MD > global TOML)

### 3. AgentConfigResolver

- [ ] 3.1 Создать класс `AgentConfigResolver`
- [ ] 3.2 Реализовать `_resolve(name, md_config) → ResolvedAgent` с приоритетом разрешения
- [ ] 3.3 Реализовать `resolve_all() → dict[str, ResolvedAgent]` — пропуск отключённых агентов
- [ ] 3.4 Реализовать разрешение model: agent → global.default_model
- [ ] 3.5 Реализовать разрешение temperature: agent → модель по умолчанию → 0.0
- [ ] 3.6 Реализовать разрешение steps: agent → global.max_steps → None
- [ ] 3.7 Реализовать разрешение prompt: agent.prompt → тело Markdown
- [ ] 3.8 Извлечь vendor-specific params из extra="allow" → additional_params
- [ ] 3.9 Написать тесты: разрешение с defaults
- [ ] 3.10 Написать тесты: отключённые агенты исключены

### 4. AgentRegistry

- [ ] 4.1 Создать `codelab/src/codelab/server/agent/registry.py`
- [ ] 4.2 Создать класс `AgentRegistry` с полями: _loader, _resolver, _event_bus, _agents, _watchdog
- [ ] 4.3 Реализовать `initialize()` — загрузка, регистрация в EventBus, запуск watchdog
- [ ] 4.4 Реализовать `reload()` — hot reload с diff (added/removed)
- [ ] 4.5 Реализовать `get(agent_name) → ResolvedAgent | None`
- [ ] 4.6 Реализовать `get_all() → dict[str, ResolvedAgent]`
- [ ] 4.7 Реализовать `get_primary_agents()`, `get_subagents()`, `get_orchestrator()`
- [ ] 4.8 Реализовать `_register_agent(name)` — регистрация handler в EventBus
- [ ] 4.9 Реализовать публикацию событий жизненного цикла при reload
- [ ] 4.10 Написать тесты: initialize → агенты загружены
- [ ] 4.11 Написать тесты: reload → события added/removed опубликованы
- [ ] 4.12 Написать тесты: get_primary_agents, get_subagents, get_orchestrator

### 5. Интеграция AppConfig

- [ ] 5.1 Расширить `AppConfig` полем `agents_global: AgentsGlobalConfig`
- [ ] 5.2 Реализовать `_merge_agents_config()` — извлечение [agents] из TOML
- [ ] 5.3 Написать тесты: AppConfig загружает agents_global из TOML

### 6. codelab.toml.example

- [ ] 6.1 Обновить `codelab/codelab.toml.example` с секцией [agents] и примерами определений

## Tasks

### 1. Pydantic модели

- [x] 1.1 Создать пакет `codelab/src/codelab/server/agent/config/` с `__init__.py`
- [x] 1.2 Создать enum `AgentMode`: primary, subagent, orchestrator
- [x] 1.3 Создать Pydantic модель `AgentPermission`: edit, bash, webfetch, task
- [x] 1.4 Создать Pydantic модель `AgentTOMLConfig` с model_config(extra="allow")
- [x] 1.5 Создать Pydantic модель `AgentsGlobalConfig` с полями: mode, fallback_mode, default_model, max_steps, slicer_model, max_sliced_tokens, slicer_skip_threshold, context_window_limit, compaction_reserved_tokens, debug, definitions
  - `slicer_model`, `max_sliced_tokens`, `slicer_skip_threshold` — для TokenSlicer в OrchestratedStrategy и HierarchicalStrategy
- [x] 1.6 Создать Pydantic модель `AgentMarkdownConfig` с model_config(extra="allow")
- [x] 1.7 Создать Pydantic модель `ResolvedAgent`
- [x] 1.8 Создать Pydantic модель `SessionMetrics`: total_time_sec, total_llm_calls, input_tokens, output_tokens, estimated_cost_usd, task_success, agent_breakdown
- [x] 1.9 Написать тесты для всех моделей (валидация, значения по умолчанию, extra поля)

### 2. AgentConfigLoader

- [x] 2.1 Создать класс `AgentConfigLoader`
- [x] 2.2 Реализовать `_parse_markdown(path: Path) → AgentMarkdownConfig` — парсинг frontmatter + body
- [x] 2.3 Реализовать `_toml_to_markdown(name, cfg) → AgentMarkdownConfig` — конвертация TOML
- [x] 2.4 Реализовать `load_all(global_toml, project_toml) → dict[str, AgentMarkdownConfig]`
- [x] 2.5 Реализовать загрузку в порядке: global TOML → global MD → project TOML → project MD
- [x] 2.6 Написать тесты: парсинг Markdown с frontmatter
- [x] 2.7 Написать тесты: конвертация TOML в Markdown
- [x] 2.8 Написать тесты: логика override (project MD > project TOML > global MD > global TOML)

### 3. AgentConfigResolver

- [x] 3.1 Создать класс `AgentConfigResolver`
- [x] 3.2 Реализовать `_resolve(name, md_config) → ResolvedAgent` с приоритетом разрешения
- [x] 3.3 Реализовать `resolve_all() → dict[str, ResolvedAgent]` — пропуск отключённых агентов
- [x] 3.4 Реализовать разрешение model: agent → global.default_model
- [x] 3.5 Реализовать разрешение temperature: agent → модель по умолчанию → 0.0
- [x] 3.6 Реализовать разрешение steps: agent → global.max_steps → None
- [x] 3.7 Реализовать разрешение prompt: agent.prompt → тело Markdown
- [x] 3.8 Извлечь vendor-specific params из extra="allow" → additional_params
- [x] 3.9 Написать тесты: разрешение с defaults
- [x] 3.10 Написать тесты: отключённые агенты исключены

### 4. AgentRegistry

- [x] 4.1 Создать `codelab/src/codelab/server/agent/registry.py`
- [x] 4.2 Создать класс `AgentRegistry` с полями: _loader, _resolver, _event_bus, _agents, _watchdog
- [x] 4.3 Реализовать `initialize()` — загрузка, регистрация в EventBus, запуск watchdog
- [x] 4.4 Реализовать `reload()` — hot reload с diff (added/removed)
- [x] 4.5 Реализовать `get(agent_name) → ResolvedAgent | None`
- [x] 4.6 Реализовать `get_all() → dict[str, ResolvedAgent]`
- [x] 4.7 Реализовать `get_primary_agents()`, `get_subagents()`, `get_orchestrator()`
- [x] 4.8 Реализовать `_register_agent(name)` — регистрация handler в EventBus
- [x] 4.9 Реализовать публикацию событий жизненного цикла при reload
- [x] 4.10 Написать тесты: initialize → агенты загружены
- [x] 4.11 Написать тесты: reload → события added/removed опубликованы
- [x] 4.12 Написать тесты: get_primary_agents, get_subagents, get_orchestrator

### 5. Интеграция AppConfig

- [x] 5.1 Расширить `AppConfig` полем `agents_global: AgentsGlobalConfig`
- [x] 5.2 Реализовать `_merge_agents_config()` — извлечение [agents] из TOML
- [x] 5.3 Написать тесты: AppConfig загружает agents_global из TOML

### 6. SessionState migration v1 → v3

- [x] 6.1 Добавить новые поля в `SessionState`: execution_mode, active_agents, session_metrics, correlation_id, parent_session_id, child_session_ids, is_child_session, task_result, sliced_summary
- [x] 6.2 Все новые поля должны иметь defaults для совместимости с существующими session файлами
- [x] 6.3 Обновить `model_validator` для миграции schema_version < 3
- [x] 6.4 Написать тесты: загрузка старого session файла → новые поля с defaults
- [x] 6.5 Написать тесты: schema_version обновляется до 3

### 7. codelab.toml.example

- [x] 7.1 Обновить `codelab/codelab.toml.example` с секцией [agents] и примерами определений

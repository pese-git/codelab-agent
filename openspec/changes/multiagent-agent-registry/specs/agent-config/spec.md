# Spec: agent-config-toml

## ДОБАВЛЕННЫЕ Требования

### Требование: Глобальная конфигурация TOML

Система ДОЛЖНА парсить секцию `[agents]` из codelab.toml с полями:
- `mode: str` — режим выполнения по умолчанию (по умолчанию: "single")
- `fallback_mode: str` — fallback при недоступности стратегии (по умолчанию: "single")
- `default_model: str` — модель LLM по умолчанию (по умолчанию: "openai/gpt-4o")
- `max_steps: int` — макс. шагов мультиагентного выполнения (по умолчанию: 7)
- `slicer_model: str` — модель для Token-Slicing (по умолчанию: "openai/gpt-4o-mini")
- `max_sliced_tokens: int` — лимит токенов для summary (по умолчанию: 120)
- `slicer_skip_threshold: int` — пропуск slicing если output < N токенов (по умолчанию: 300)
- `context_window_limit: int` — лимит окна контекста (по умолчанию: 128000)
- `compaction_reserved_tokens: int` — буфер для compaction (по умолчанию: 10000)
- `debug: bool` — режим отладки (по умолчанию: false)

### Требование: Определения агентов в TOML

Система ДОЛЖНА парсить секции `[agents.definitions.<name>]` с полями:
- `description: str` — обязательно
- `mode: str` — "primary", "subagent", "orchestrator" (по умолчанию: "subagent")
- `priority: int` — приоритет разрешения конфликтов (по умолчанию: 99)
- `model: str | None` — модель LLM (fallback: default_model)
- `temperature: float | None` — 0.0-1.0 (fallback: модель по умолчанию → 0.0)
- `tools: dict[str, bool] | None` — доступные инструменты
- `permission: dict | None` — правила разрешений
- `prompt: str | None` — inline текст или "{file:...}"

# Spec: agent-config-markdown

## ДОБАВЛЕННЫЕ Требования

### Требование: Формат Markdown агента

Система ДОЛЖНА парсить Markdown файлы с YAML frontmatter:
- Frontmatter (между `---`) → AgentMarkdownConfig
- Тело после frontmatter → system_prompt
- Имя файла без `.md` → agent_name

### Требование: Параметры Frontmatter

Система ДОЛЖНА поддерживать параметры frontmatter:
- `description` (обязательно): string
- `mode`: "primary", "subagent", "orchestrator" (по умолчанию: "subagent")
- `priority`: int (по умолчанию: 99)
- `model`: string (fallback: global.default_model)
- `temperature`: float (fallback: модель по умолчанию → 0.0)
- `top_p`: float
- `steps`: int (fallback: global.max_steps)
- `disable`: bool (по умолчанию: false)
- `hidden`: bool (по умолчанию: false)
- `color`: string (HEX или цвет темы)
- `tools`: dict
- `permission`: dict
- `prompt`: string ("{file:./prompts/...}" или None → тело как prompt)

### Требование: Вендор-специфичные параметры

Система ДОЛЖНА пропускать вендор-специфичные параметры (например, `reasoningEffort`, `textVerbosity`) через `model_config(extra="allow")`.

# Spec: agent-registry

## ДОБАВЛЕННЫЕ Требования

### Требование: Интерфейс AgentRegistry

Система ДОЛЖНА предоставлять `AgentRegistry` с методами:
- `async initialize() -> None` — загрузить агентов, зарегистрировать в EventBus, запустить watchdog
- `async reload() -> None` — hot reload агентов из файлов
- `get(agent_name: str) -> ResolvedAgent | None` — получить конфигурацию агента
- `get_all() -> dict[str, ResolvedAgent]` — получить всех активных агентов
- `get_primary_agents() -> dict[str, ResolvedAgent]` — агенты с mode=primary
- `get_subagents() -> dict[str, ResolvedAgent]` — агенты с mode=subagent
- `get_orchestrator() -> ResolvedAgent | None` — агент с mode=orchestrator

### Требование: Hot Reload

AgentRegistry ДОЛЖЕН:
- Наблюдать за `.codelab/agents/*.md`, `~/.codelab/agents/*.md`, `codelab.toml`, `~/.codelab/codelab.toml`
- При изменении: перезагрузить всех агентов, сравнить с предыдущим состоянием
- Удалить удалённых агентов, зарегистрировать новых
- Публиковать события жизненного цикла (AgentRegistered, AgentUnregistered, AgentListChanged)

### Требование: Отключённые агенты

Агенты с `disable: true` НЕ ДОЛЖНЫ загружаться в реестр.

# Spec: agent-config-resolver

## ДОБАВЛЕННЫЕ Требования

### Требование: Модель ResolvedAgent

Система ДОЛЖНА определять `ResolvedAgent` с разрешёнными полями:
- `name: str`
- `description: str`
- `mode: AgentMode`
- `priority: int` (по умолчанию: 99)
- `model: str` (разрешено: agent → default)
- `system_prompt: str`
- `prompt_source: str` — "inline" | "file:./prompts/..."
- `temperature: float` (разрешено: agent → модель по умолчанию → 0.0)
- `top_p: float | None`
- `steps: int | None` (разрешено: agent → global.max_steps → None)
- `disable: bool`
- `hidden: bool`
- `color: str | None`
- `tools: dict[str, bool] | None`
- `permission: AgentPermission`
- `additional_params: dict[str, Any]` — вендор-специфичные
- `source: str` — путь к файлу для отладки

### Требование: Приоритет разрешения

AgentConfigResolver ДОЛЖЕН разрешать значения по умолчанию в следующем порядке:
- model: agent.model → global.default_model
- temperature: agent.temperature → модель по умолчанию → 0.0
- steps: agent.steps → global.max_steps → None
- permission: agent.permission → значения по умолчанию
- prompt: agent.prompt → тело Markdown файла

# Spec: agent-config-loader

## ДОБАВЛЕННЫЕ Требования

### Требование: Порядок загрузки

AgentConfigLoader ДОЛЖЕН загружать агентов в следующем порядке (от низшего к высшему приоритету):
1. Глобальный TOML (~/.codelab/codelab.toml definitions)
2. Глобальный Markdown (~/.codelab/agents/*.md)
3. Проектный TOML (codelab.toml definitions)
4. Проектный Markdown (.codelab/agents/*.md)

### Требование: Поведение Override

Когда агент с одинаковым именем определён в нескольких источниках, источник с высшим приоритетом ДОЛЖЕН полностью заменять (не объединять) определение с низшим приоритетом.

### Требование: Конвертация TOML в Markdown

AgentConfigLoader ДОЛЖЕН конвертировать TOML конфиги в AgentMarkdownConfig для единообразной обработки.

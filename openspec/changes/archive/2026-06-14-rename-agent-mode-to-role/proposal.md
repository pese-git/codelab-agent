## Why

Поле `mode` в конфигурации агента (`AgentMode`) создаёт путаницу с `_active_strategy` — режимом выполнения сессии. Оба используют слово "mode" но означают разные вещи:

- `mode` агента = **роль** (primary/subagent/orchestrator)
- `_active_strategy` = **режим выполнения** (single/multi_orchestrated/multi_choreographed/hierarchical)

Переименование `mode` → `role` и `AgentMode` → `AgentRole` устраняет эту амбигуитет.

## What Changes

### Переименование

- `AgentMode` enum → `AgentRole`
- Поле `mode` → `role` во всех моделях (AgentTOMLConfig, AgentsGlobalConfig, AgentMarkdownConfig, ResolvedAgent)
- Поле `fallback_mode` → `fallback_role` в AgentsGlobalConfig
- Все ссылки в коде, тестах, документации, TOML конфигах

### Backward compatibility

- TOML loader читает `role`, fallback на `mode` с deprecation warning
- SessionState migration для старых session файлов

## Capabilities

### New Capabilities
- `agent-role`: Переименование AgentMode → AgentRole, mode → role

### Modified Capabilities
- `agent-config-toml`: TOML поле `role` вместо `mode`
- `agent-config-markdown`: Markdown frontmatter поле `role` вместо `mode`
- `agent-registry`: методы get_primary_agents, get_subagents, get_orchestrator используют `.role`

## Impact

**Изменяемые файлы (source):**
- `codelab/src/codelab/server/agent/config/models.py` — AgentMode → AgentRole, mode → role
- `codelab/src/codelab/server/agent/config/__init__.py` — экспорт
- `codelab/src/codelab/server/agent/config/loader.py` — импорты, обращения
- `codelab/src/codelab/server/agent/config/resolver.py` — обращения
- `codelab/src/codelab/server/agent/registry.py` — обращения
- `codelab/src/codelab/server/agent/__init__.py` — экспорт

**Изменяемые файлы (tests):**
- `codelab/tests/server/agent/test_config_models.py`
- `codelab/tests/server/agent/test_config_loader.py`
- `codelab/tests/server/agent/test_agent_factory.py`
- `codelab/tests/server/agent/test_agent_registry.py`
- `codelab/tests/server/agent/test_contracts.py`

**Изменяемые файлы (docs):**
- `openspec/specs/agent-registry/spec.md`
- `doc/architecture/MULTIAGENT_TECHNICAL_SPECIFICATION.md`
- `codelab/codelab.toml.example`

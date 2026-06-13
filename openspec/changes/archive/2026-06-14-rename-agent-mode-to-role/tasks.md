## 1. Source: models.py
- [x] 1.1 Переименовать `AgentMode` → `AgentRole` в models.py
- [x] 1.2 Переименовать поле `mode` → `role` в AgentTOMLConfig
- [x] 1.3 Переименовать поле `mode` → `role` в AgentsGlobalConfig
- [x] 1.4 Переименовать поле `fallback_mode` → `fallback_role` в AgentsGlobalConfig
- [x] 1.5 Переименовать поле `mode` → `role` в AgentMarkdownConfig
- [x] 1.6 Переименовать поле `mode` → `role` в ResolvedAgent
- [x] 1.7 Обновить docstrings

## 2. Source: config/__init__.py
- [x] 2.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 2.2 Обновить экспорт `"AgentMode"` → `"AgentRole"`

## 3. Source: config/loader.py
- [x] 3.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 3.2 Обновить `AgentMode(mode_str)` → `AgentRole(role_str)`
- [x] 3.3 Добавить backward compatibility: читать `mode` если `role` отсутствует
- [x] 3.4 Добавить deprecation warning при чтении `mode`
- [x] 3.5 Обновить `.mode` → `.role` в _toml_to_markdown()

## 4. Source: config/resolver.py
- [x] 4.1 Обновить `md_config.mode` → `md_config.role`

## 5. Source: registry.py
- [x] 5.1 Обновить `agent.mode` → `agent.role` в get_primary_agents()
- [x] 5.2 Обновить `agent.mode` → `agent.role` в get_subagents()
- [x] 5.3 Обновить `agent.mode` → `agent.role` в get_orchestrator()
- [x] 5.4 Обновить импорт `AgentMode` → `AgentRole`

## 6. Source: agent/__init__.py
- [x] 6.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 6.2 Обновить экспорт `"AgentMode"` → `"AgentRole"`

## 7. Tests: test_config_models.py
- [x] 7.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 7.2 Переименовать `TestAgentMode` → `TestAgentRole`
- [x] 7.3 Обновить все `AgentMode.*` → `AgentRole.*`
- [x] 7.4 Обновить все `.mode` → `.role` в тестах

## 8. Tests: test_config_loader.py
- [x] 8.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 8.2 Обновить `.mode` → `.role` в assertions
- [x] 8.3 Добавить тест backward compatibility (mode → role)

## 9. Tests: test_agent_factory.py
- [x] 9.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 9.2 Обновить `mode=AgentMode.*` → `role=AgentRole.*`

## 10. Tests: test_agent_registry.py
- [x] 10.1 Обновить импорт `AgentMode` → `AgentRole`
- [x] 10.2 Обновить `mode=AgentMode.*` → `role=AgentRole.*`

## 11. Tests: test_contracts.py
- [x] 11.1 Проверить и обновить `ev.mode` → `ev.role` если относится к AgentRole
  - Примечание: `AgentRegistered.mode` — это execution mode (single/multi_orchestrated), не AgentRole. Переименование не требуется.

## 12. Documentation
- [x] 12.1 Обновить openspec/specs/agent-registry/spec.md — уже использует `role` и `fallback_role`
- [x] 12.2 Обновить MULTIAGENT_TECHNICAL_SPECIFICATION.md — уже использует `role`
- [x] 12.3 Обновить codelab.toml.example — уже использует `role` в примерах

## 13. Верификация
- [x] 13.1 uv run ruff check . — All checks passed!
- [x] 13.2 uv run ty check — pre-existing errors, не связанные с rename
- [x] 13.3 uv run python -m pytest — 281 passed in tests/server/agent/
- [x] 13.4 make check

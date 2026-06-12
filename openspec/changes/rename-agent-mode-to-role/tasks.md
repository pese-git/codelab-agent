## 1. Source: models.py
- [ ] 1.1 Переименовать `AgentMode` → `AgentRole` в models.py
- [ ] 1.2 Переименовать поле `mode` → `role` в AgentTOMLConfig
- [ ] 1.3 Переименовать поле `mode` → `role` в AgentsGlobalConfig
- [ ] 1.4 Переименовать поле `fallback_mode` → `fallback_role` в AgentsGlobalConfig
- [ ] 1.5 Переименовать поле `mode` → `role` в AgentMarkdownConfig
- [ ] 1.6 Переименовать поле `mode` → `role` в ResolvedAgent
- [ ] 1.7 Обновить docstrings

## 2. Source: config/__init__.py
- [ ] 2.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 2.2 Обновить экспорт `"AgentMode"` → `"AgentRole"`

## 3. Source: config/loader.py
- [ ] 3.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 3.2 Обновить `AgentMode(mode_str)` → `AgentRole(role_str)`
- [ ] 3.3 Добавить backward compatibility: читать `mode` если `role` отсутствует
- [ ] 3.4 Добавить deprecation warning при чтении `mode`
- [ ] 3.5 Обновить `.mode` → `.role` в _toml_to_markdown()

## 4. Source: config/resolver.py
- [ ] 4.1 Обновить `md_config.mode` → `md_config.role`

## 5. Source: registry.py
- [ ] 5.1 Обновить `agent.mode` → `agent.role` в get_primary_agents()
- [ ] 5.2 Обновить `agent.mode` → `agent.role` в get_subagents()
- [ ] 5.3 Обновить `agent.mode` → `agent.role` в get_orchestrator()
- [ ] 5.4 Обновить импорт `AgentMode` → `AgentRole`

## 6. Source: agent/__init__.py
- [ ] 6.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 6.2 Обновить экспорт `"AgentMode"` → `"AgentRole"`

## 7. Tests: test_config_models.py
- [ ] 7.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 7.2 Переименовать `TestAgentMode` → `TestAgentRole`
- [ ] 7.3 Обновить все `AgentMode.*` → `AgentRole.*`
- [ ] 7.4 Обновить все `.mode` → `.role` в тестах

## 8. Tests: test_config_loader.py
- [ ] 8.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 8.2 Обновить `.mode` → `.role` в assertions
- [ ] 8.3 Добавить тест backward compatibility (mode → role)

## 9. Tests: test_agent_factory.py
- [ ] 9.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 9.2 Обновить `mode=AgentMode.*` → `role=AgentRole.*`

## 10. Tests: test_agent_registry.py
- [ ] 10.1 Обновить импорт `AgentMode` → `AgentRole`
- [ ] 10.2 Обновить `mode=AgentMode.*` → `role=AgentRole.*`

## 11. Tests: test_contracts.py
- [ ] 11.1 Проверить и обновить `ev.mode` → `ev.role` если относится к AgentRole

## 12. Documentation
- [ ] 12.1 Обновить openspec/specs/agent-registry/spec.md
- [ ] 12.2 Обновить MULTIAGENT_TECHNICAL_SPECIFICATION.md
- [ ] 12.3 Обновить codelab.toml.example (mode → role, fallback_mode → fallback_role)

## 13. Верификация
- [ ] 13.1 uv run ruff check .
- [ ] 13.2 uv run ty check
- [ ] 13.3 uv run python -m pytest
- [ ] 13.4 make check

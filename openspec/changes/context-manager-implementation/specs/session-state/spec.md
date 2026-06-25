# Delta-спецификация session-state

## ADDED Requirements

### Requirement: SessionState current_agent_scope
Система MUST добавить поле `current_agent_scope: str = "single"` в `SessionState` для идентификации области агента.

#### Scenario: Область агента по умолчанию
- **WHEN** `SessionState` создаётся без явной области
- **THEN** `current_agent_scope` по умолчанию равен `"single"`

#### Scenario: Область агента для мультиагентных стратегий
- **WHEN** `OrchestratedStrategy` создаёт дочернюю сессию
- **THEN** дочерний `SessionState` имеет `current_agent_scope`, установленный в идентификатор области дочернего элемента

#### Scenario: Область агента передаётся в ContextManager
- **WHEN** вызывается `ExecutionEngine.build_context()`
- **THEN** параметр `agent_scope` получается из `session.current_agent_scope`

### Requirement: Миграция SessionState для Context Manager
Система MUST поддерживать миграцию `SessionState` для включения поля `current_agent_scope`.

#### Scenario: Обратная совместимость
- **WHEN** загружается старый `SessionState` без `current_agent_scope`
- **THEN** система устанавливает значение по умолчанию `"single"` при десериализации

#### Scenario: Обновление версии схемы
- **WHEN** схема `SessionState` обновляется
- **THEN** schema_version инкрементируется, миграция обрабатывает новое поле

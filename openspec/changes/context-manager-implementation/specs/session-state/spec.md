# session-state Delta Specification

## ADDED Requirements

### Requirement: SessionState current_agent_scope
The system MUST add field `current_agent_scope: str = "single"` to `SessionState` for agent scope identification.

#### Scenario: Default agent scope
- **WHEN** `SessionState` is created without explicit scope
- **THEN** `current_agent_scope` defaults to `"single"`

#### Scenario: Agent scope for multiagent strategies
- **WHEN** `OrchestratedStrategy` creates child session
- **THEN** child `SessionState` has `current_agent_scope` set to child's scope identifier

#### Scenario: Agent scope passed to ContextManager
- **WHEN** `ExecutionEngine.build_context()` is called
- **THEN** parameter `agent_scope` is derived from `session.current_agent_scope`

### Requirement: SessionState Migration for Context Manager
The system MUST support migration of `SessionState` to include `current_agent_scope` field.

#### Scenario: Backward compatibility
- **WHEN** old `SessionState` without `current_agent_scope` is loaded
- **THEN** the system sets default value `"single"` during deserialization

#### Scenario: Schema version update
- **WHEN** `SessionState` schema is updated
- **THEN** schema_version is incremented, migration handles new field

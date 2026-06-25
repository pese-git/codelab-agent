# single-strategy Delta Specification

## MODIFIED Requirements

### Requirement: SingleStrategy Flow

SingleStrategy MUST:
1. Call `ExecutionEngine.build_context(session, prompt, agent_scope="single", system_prompt=...)`
2. Receive `PayloadEnvelope` from `ContextManager.build_context()`
3. Call `ContextManager.ensure_context_fits(envelope, *, max_context_tokens, reserved_tokens)`
4. Convert `envelope.to_messages()` to `AgentRequest.messages`
5. Call `event_bus.send_request(request, parent_span)`
6. Return `AgentResponse` to caller

#### Scenario: SingleStrategy with ContextManager
- **WHEN** `SingleStrategy.execute()` is called
- **THEN** strategy uses `ContextManager.build_context()` and `ensure_context_fits()` instead of direct legacy `ContextCompactor` call

#### Scenario: PayloadEnvelope conversion
- **WHEN** `PayloadEnvelope` is received from `build_context()`
- **THEN** strategy calls `envelope.to_messages()` to get flat list of messages for `AgentRequest`

### Requirement: ExecutionEngine.build_context with ContextManager

`ExecutionEngine.build_context(session, prompt, *, agent_scope, system_prompt, options)` MUST:
1. Call `ContextManager.build_context(session, prompt, agent_scope=agent_scope, system_prompt=system_prompt, options=options)`
2. Receive `PayloadEnvelope`
3. Call `ContextManager.ensure_context_fits(envelope, *, max_context_tokens, reserved_tokens)`
4. Form `AgentContext` with `conversation_history = envelope.to_messages()`

#### Scenario: ExecutionEngine delegates to ContextManager
- **WHEN** `ExecutionEngine.build_context()` is called
- **THEN** execution is delegated to `ContextManager`, legacy `ContextCompactor` is used only when `agents.context.enabled=false`

#### Scenario: AgentContext from PayloadEnvelope
- **WHEN** `PayloadEnvelope` is received
- **THEN** `AgentContext.conversation_history` is formed via `envelope.to_messages()`

### Requirement: ContextManager Implementation Selection

`ExecutionEngine` MUST select implementation by flag `agents.context.enabled`:
- `enabled=true` → use new `ContextManager`
- `enabled=false` (default) → use legacy `ContextCompactor`

#### Scenario: Legacy mode
- **WHEN** `agents.context.enabled=false`
- **THEN** `ExecutionEngine` uses legacy `ContextCompactor`, behavior is bit-for-bit as before Phase 0

#### Scenario: New mode
- **WHEN** `agents.context.enabled=true`
- **THEN** `ExecutionEngine` uses new `ContextManager` with full functionality

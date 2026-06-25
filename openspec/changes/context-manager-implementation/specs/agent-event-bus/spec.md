# agent-event-bus Delta Specification

## MODIFIED Requirements

### Requirement: Request Sending Guarantees

The `send_request()` method MUST:
- Raise `AgentNotFoundError` if target_agent is not registered
- Retry sending up to 3 times with exponential backoff
- Raise `AgentDispatchError` if all retry attempts are exhausted
- Propagate parent_span context for tracing
- Return `AgentResponse` (DomainEvent) wrapped from `AgentResult`
- Accept `messages` from `PayloadEnvelope.to_messages()` at the boundary with `ContextManager`

#### Scenario: AgentRequest from PayloadEnvelope
- **WHEN** strategy forms `AgentRequest`
- **THEN** `request.messages` is formed via `envelope.to_messages()` at the boundary with `EventBus`

#### Scenario: PayloadEnvelope does not leak
- **WHEN** `ContextManager` returns `PayloadEnvelope`
- **THEN** `PayloadEnvelope` is not passed to `EventBus` directly, only via `to_messages()` at the boundary

### Requirement: Integration with ContextManager

`AgentEventBus` MUST work with `ContextManager` through `ExecutionEngine`:
- Strategies call `ExecutionEngine.build_context()` → receive `PayloadEnvelope`
- Strategies convert `envelope.to_messages()` → `AgentRequest.messages`
- `EventBus.send_request()` accepts `AgentRequest` with flat list of messages

#### Scenario: Transparent integration
- **WHEN** strategy uses `ContextManager`
- **THEN** `EventBus` does not know about `PayloadEnvelope`, works with flat list of messages

#### Scenario: Backward compatibility
- **WHEN** legacy `ContextCompactor` is used
- **THEN** `EventBus` works as before, without changes

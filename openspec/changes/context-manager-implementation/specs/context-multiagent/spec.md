# Context Multiagent Capability Specification

## ADDED Requirements

### Requirement: ChildSessionManager Isolates Subagents
The system MUST isolate subagents in child sessions by default.

#### Scenario: Child session creation
- **WHEN** `create_child(parent, subagent_scope)` is called
- **THEN** the system creates new `SessionState` for child with isolated context, returns child session

#### Scenario: Child session has separate scope
- **WHEN** child session is created
- **THEN** child has its own `agent_scope`, separate from parent

#### Scenario: Child session has separate epoch
- **WHEN** child session runs
- **THEN** child has its own `ContextEpoch`, separate from parent

### Requirement: process_subagent_response Summarizes for Parent
The system MUST summarize subagent response for parent agent.

#### Scenario: Successful summarization
- **WHEN** `process_subagent_response(parent_scope, subagent_scope, response)` is called
- **THEN** the system returns `SubagentResult` with `summary` (summarized result), `token_count`, `source_scope`

#### Scenario: Summary added to parent context
- **WHEN** subagent completes
- **THEN** `SubagentResult.summary` is added to parent scope as `ContextType.AGENT_REPORT` with `priority=7`

#### Scenario: Degradation on summarization failure
- **WHEN** LLM summarization fails
- **THEN** the system returns truncated raw result via `bound_content()`, logs warning `subagent_summary_degraded`

### Requirement: Subagent Failure Does Not Crash Parent
The system MUST handle subagent failures gracefully without crashing parent.

#### Scenario: Subagent exception
- **WHEN** subagent raises exception in child session
- **THEN** `process_subagent_response()` returns `SubagentResult` with error summary, parent continues, logs error `subagent_failed`

#### Scenario: Subagent timeout
- **WHEN** child session times out
- **THEN** `collect_summary()` cancels child task, returns `SubagentResult` with timeout marker, parent does not block, logs warning `subagent_timeout`

#### Scenario: Child session creation failure
- **WHEN** `create_child()` fails
- **THEN** the system returns `SubagentResult` with error to parent, does not crash parent strategy, logs error `child_session_create_failed`

### Requirement: Federation Is Candidate for Rejection
The system MUST treat federated `share_item()` as candidate for rejection (ADR-002 §8).

#### Scenario: Federation disabled by default
- **WHEN** `agents.context.multiagent.federation=false` (default)
- **THEN** the system uses isolation only, no federated sharing

#### Scenario: Federation enabled only with justification
- **WHEN** federation is enabled via feature flag
- **THEN** the system allows `share_item()` between scopes, requires scenario justification not covered by isolation

#### Scenario: Federation conflicts with epoch stability
- **WHEN** shared item changes baseline of another agent
- **THEN** the system breaks epoch for affected agent, logs warning about federation conflict

### Requirement: Orchestrated Strategy Uses ContextManager
The system MUST integrate `OrchestratedStrategy` with `ContextManager` methods.

#### Scenario: Orchestrator builds context
- **WHEN** `OrchestratedStrategy.execute()` is called
- **THEN** the system calls `build_context(agent_scope="orchestrator")` for routing decision

#### Scenario: Subagent builds context
- **WHEN** orchestrator delegates to subagent
- **THEN** the system calls `build_context(agent_scope="<subagent>")` for subagent

#### Scenario: Subagent response processed
- **WHEN** subagent returns response
- **THEN** the system calls `process_subagent_response(parent="orchestrator", subagent=..., response)`, adds summary to orchestrator scope

#### Scenario: ensure_context_fits between rounds
- **WHEN** orchestrator prepares next delegation round
- **THEN** the system calls `ensure_context_fits()` for orchestrator scope

### Requirement: Choreography Strategy Uses ContextManager
The system MUST integrate `ChoreographyStrategy` with `ContextManager` methods.

#### Scenario: Each participant builds context
- **WHEN** `ChoreographyStrategy.execute()` broadcasts to participants
- **THEN** the system calls `build_context(agent_scope="<participant>")` for each participant

#### Scenario: Only winner response processed
- **WHEN** responses are collected
- **THEN** the system calls `process_subagent_response()` only for winner, discards other responses

#### Scenario: No ensure_context_fits for choreography
- **WHEN** choreography completes
- **THEN** the system does not call `ensure_context_fits()` (unlike orchestrated/hierarchical)

### Requirement: Hierarchical Strategy Uses ContextManager
The system MUST integrate `HierarchicalStrategy` with `ContextManager` methods.

#### Scenario: Root builds context
- **WHEN** `HierarchicalStrategy.execute()` starts
- **THEN** the system calls `build_context(agent_scope="root")`

#### Scenario: Child sessions created for delegation
- **WHEN** root delegates to child
- **THEN** the system calls `ChildSessionManager.create_child(parent, subagent_scope)`, child has own scope and epoch

#### Scenario: Bottom-up response processing
- **WHEN** child completes
- **THEN** the system calls `ChildSessionManager.collect_summary(child)`, then `process_subagent_response()`, summary goes to parent

#### Scenario: ensure_context_fits at each level
- **WHEN** hierarchy has multiple levels
- **THEN** the system calls `ensure_context_fits()` at each level to prevent context growth

### Requirement: Strategy Integration Is Transparent
The system MUST make lifecycle model (hydration vs epoch) transparent to strategies.

#### Scenario: Strategy does not know about lifecycle
- **WHEN** strategy calls `build_context()`
- **THEN** strategy receives `PayloadEnvelope`, does not know if hydration or epoch is used

#### Scenario: Lifecycle switch does not require strategy changes
- **WHEN** flag `agents.context.lifecycle.incremental` changes
- **THEN** strategies continue to work without modifications

### Requirement: Multiagent Metrics Are Emitted
The system MUST emit metrics for multiagent operations.

#### Scenario: Subagent response count
- **WHEN** `process_subagent_response()` is called
- **THEN** the system increments counter `context_subagent_responses_total` with label `parent_scope`

#### Scenario: Subagent failure metric
- **WHEN** subagent fails
- **THEN** the system increments metric `context.subagent.failures` with `subagent_scope` and `error_type`

#### Scenario: Subagent timeout metric
- **WHEN** subagent times out
- **THEN** the system increments metric `context.subagent.timeouts` with `subagent_scope` and `timeout_sec`

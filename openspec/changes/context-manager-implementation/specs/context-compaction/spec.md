# Context Compaction Capability Specification

## ADDED Requirements

### Requirement: ContextCompactor Runs Three Phases
The system MUST run compaction in three phases: Prune → Skeletonize → Summarize.

#### Scenario: Three-phase compaction
- **WHEN** `compact_if_needed()` is called and `token_count > max_context_tokens - reserved_tokens`
- **THEN** the system runs Prune (FIFO removal), then Skeletonize (AST compression), then Summarize (LLM summarization)

#### Scenario: Phase order is fixed
- **WHEN** compaction is triggered
- **THEN** Prune runs first, Skeletonize second, Summarize third

#### Scenario: Compaction signature compatible with legacy
- **WHEN** `compact_if_needed(messages, max_context_tokens, reserved_tokens)` is called
- **THEN** signature matches legacy `ContextCompactor.compact_if_needed()` for seamless migration

### Requirement: Prune Phase Removes Old Tool Outputs
The system MUST remove old tool output messages using FIFO, preserving the first 2 and last N messages.

#### Scenario: Prune preserves first and last messages
- **WHEN** Prune is triggered on a history of 200 messages
- **THEN** the system preserves the first 2 messages and last N messages, removes middle tool outputs

#### Scenario: Prune removes tool_call + tool_result pairs
- **WHEN** Prune removes a tool result
- **THEN** the system removes the corresponding tool_call to maintain protocol validity

#### Scenario: Prune does not create orphaned messages
- **WHEN** Prune completes
- **THEN** every `tool_result` has a corresponding `tool_call`, no orphaned messages

### Requirement: Skeletonize Phase Compresses Code
The system MUST compress code files using `CodeSkeletonizer` during compaction.

#### Scenario: Skeletonize compresses read-only files
- **WHEN** Skeletonize phase runs
- **THEN** the system applies `skeletonize()` to large code files that are not being edited by the agent

#### Scenario: Skeletonize skips unsupported languages
- **WHEN** file is not Python or unsupported language
- **THEN** the system skips skeletonization for that file, uses original content

#### Scenario: Skeletonize achieves token savings
- **WHEN** skeleton is produced
- **THEN** skeleton is 80-85% smaller than original (for Python files)

### Requirement: Summarize Phase Uses LLM
The system MUST summarize conversation using LLM when Prune + Skeletonize are insufficient.

#### Scenario: Summarize triggered when needed
- **WHEN** Prune + Skeletonize do not reduce below limit
- **THEN** the system calls `ConversationSummarizer.summarize(messages, target_tokens)`

#### Scenario: Summarize preserves key decisions
- **WHEN** summarization completes
- **THEN** summary contains key decisions, task state, important context

#### Scenario: Summarize when LLM unavailable
- **WHEN** LLM provider is unavailable
- **THEN** the system skips Summarize phase, continues with Prune + Skeletonize only, logs warning `summarization_failed_degrade_to_prune`

### Requirement: Compaction Respects Priority
The system MUST NOT evict items with `priority >= 10` during compaction.

#### Scenario: System rules not evicted
- **WHEN** compaction needs to reduce tokens
- **THEN** the system does not evict `system_rules` (priority=10)

#### Scenario: User prompt not evicted
- **WHEN** compaction needs to reduce tokens
- **THEN** the system does not evict `user_prompt` (priority=8) unless critical overflow

#### Scenario: Eviction order by priority
- **WHEN** items are evicted
- **THEN** the system evicts lowest priority first: `file_skeleton=3` → `terminal_output=4` → `file_content=5` → ... → `system_rules=10`

### Requirement: Hard Truncation After Three Phases
The system MUST perform hard truncation if payload still exceeds budget after three phases.

#### Scenario: Hard truncation by priority
- **WHEN** `token_count > max_context_tokens - reserved_tokens` after Prune + Skeletonize + Summarize
- **THEN** the system performs hard truncation via `TokenBudgetManager.bound_content()` by priority, evicts from lowest priority up

#### Scenario: Critical items exceed budget
- **WHEN** `system_rules` (priority >= 10) themselves exceed budget
- **THEN** the system truncates critical items as last resort, logs error `critical_items_exceed_budget`, does not raise exception in hot path

#### Scenario: Provider overflow with approximate counter
- **WHEN** `ApproximateTokenCounter` underestimates and provider rejects
- **THEN** the system retries `ensure_context_fits()` with stricter limit, logs warning `budget_underestimated_retry`

### Requirement: Orphaned Tool Messages Are Sanitized
The system MUST sanitize orphaned tool messages before forming `PayloadEnvelope`.

#### Scenario: Orphaned tool_result removed
- **WHEN** `tool_result` has no corresponding `tool_call` in payload
- **THEN** the system removes orphaned `tool_result` or converts to neutral text message, logs `orphaned_tool_result_dropped`

#### Scenario: Orphaned tool_call completed
- **WHEN** `tool_call` has no corresponding `tool_result`
- **THEN** the system adds placeholder result or removes `tool_call` to maintain protocol validity

#### Scenario: Prune removes pairs
- **WHEN** Prune removes tool messages
- **THEN** the system removes `tool_call` + `tool_result` together, does not create orphans

### Requirement: Compaction Metrics Are Emitted
The system MUST emit metrics for compaction ratio, duration, and degradation.

#### Scenario: Compaction ratio metric
- **WHEN** compaction completes
- **THEN** the system emits histogram `context_compaction_ratio` with label `phase`

#### Scenario: Compaction count metric
- **WHEN** compaction is triggered
- **THEN** the system increments counter `context_compaction_total`

#### Scenario: Degradation metric
- **WHEN** Summarize phase is skipped
- **THEN** the system increments counter `context_compaction_degraded_total` with label `reason`

### Requirement: ensure_context_fits Guarantees Budget
The system MUST guarantee that payload fits within `max_context_tokens - reserved_tokens`.

#### Scenario: ensure_context_fits reduces tokens
- **WHEN** `ensure_context_fits(envelope, max_context_tokens, reserved_tokens)` is called
- **THEN** returned envelope has `token_count <= max_context_tokens - reserved_tokens`

#### Scenario: ensure_context_fits preserves critical items
- **WHEN** compaction is needed
- **THEN** items with `priority >= 10` are preserved unless critical overflow

#### Scenario: ensure_context_fits does not raise in hot path
- **WHEN** compaction fails or budget cannot be met
- **THEN** the system degrades gracefully (hard truncation, logging), does not raise exception

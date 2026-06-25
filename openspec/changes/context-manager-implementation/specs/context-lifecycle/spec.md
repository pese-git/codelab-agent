# Context Lifecycle Capability Specification

## ADDED Requirements

### Requirement: PayloadEnvelope Separates Baseline and Tail
The system MUST support `PayloadEnvelope` with explicit separation of immutable `baseline` and `tail` deltas.

#### Scenario: PayloadEnvelope structure
- **WHEN** `build_context()` is called
- **THEN** the system returns `PayloadEnvelope` with `baseline: list[LLMMessage]`, `tail: list[LLMMessage]`, `baseline_fingerprint: str`, `token_count: int`

#### Scenario: to_messages flattens baseline and tail
- **WHEN** `envelope.to_messages()` is called
- **THEN** the system returns `[*baseline, *tail]` as flat `list[LLMMessage]`

#### Scenario: Baseline fingerprint stability
- **WHEN** baseline content does not change between calls
- **THEN** `baseline_fingerprint` remains identical (deterministic hash)

### Requirement: ContextEpoch Manages Incremental Updates
The system MUST support `ContextEpoch` with immutable baseline and incremental `mid_conversation_messages`.

#### Scenario: Epoch creation
- **WHEN** new epoch starts
- **THEN** the system creates `ContextEpoch` with `epoch_id`, `baseline`, `baseline_fingerprint`, empty `mid_conversation_messages`

#### Scenario: get_full_context returns baseline + mid_conversation
- **WHEN** `epoch.get_full_context()` is called
- **THEN** the system returns `[*baseline, *mid_conversation_messages]`

#### Scenario: Mid-conversation messages accumulation
- **WHEN** tool results are added during conversation
- **THEN** the system adds them to `mid_conversation_messages`, baseline remains unchanged

### Requirement: ContextSnapshot Detects Changes via Fingerprint
The system MUST detect source changes using Codec fingerprints, not timestamps.

#### Scenario: Snapshot creation
- **WHEN** `ContextReconciler.snapshot(registry)` is called
- **THEN** the system collects fingerprints from all sources, returns `ContextSnapshot` with `fingerprints: dict[str, str]`

#### Scenario: Diff detects changed sources
- **WHEN** `snapshot.diff(other)` is called
- **THEN** the system compares fingerprints, returns list of `source_id` with changed fingerprints

#### Scenario: Fingerprint is Codec-based
- **WHEN** source content changes
- **THEN** fingerprint changes (does not depend on timestamp)

### Requirement: ContextReconciler Safely Applies Changes
The system MUST apply changes on safe boundaries with states `UNCHANGED`, `UPDATED`, or `DEFERRED`.

#### Scenario: Reconcile without changes
- **WHEN** `reconcile(epoch, registry)` is called and no source has changed
- **THEN** the system returns `ReconcileResult(state=UNCHANGED, epoch_broken=False)`

#### Scenario: Reconcile with source change on safe boundary
- **WHEN** source has changed and reconcile is called on safe boundary
- **THEN** the system returns `ReconcileResult(state=UPDATED, updated_sources=[...], epoch_broken=True)`, baseline is rebuilt

#### Scenario: Reconcile with change detected mid-turn
- **WHEN** change is detected but not on safe boundary
- **THEN** the system returns `ReconcileResult(state=DEFERRED)`, change is applied on next boundary

#### Scenario: Reconcile with uncertain change
- **WHEN** fingerprint is unreadable or ambiguous
- **THEN** the system conservatively returns `ReconcileResult(state=UPDATED, epoch_broken=True)`, rebuilds baseline

### Requirement: ConversationSummarizer Preserves Key Decisions
The system MUST summarize conversation history, preserving key decisions and task state.

#### Scenario: Successful summarization
- **WHEN** `summarize(messages, target_tokens)` is called
- **THEN** the system returns summarized `LLMMessage` with preserved key decisions and state

#### Scenario: Degradation when LLM unavailable
- **WHEN** LLM provider is unavailable
- **THEN** the system skips Summarize phase, continues with Prune + Skeletonize only, logs warning `summarization_failed_degrade_to_prune`

#### Scenario: Empty or invalid summarization result
- **WHEN** summarizer returns empty or invalid result
- **THEN** the system treats this as failure, degrades to Prune + Skeletonize

### Requirement: Baseline Fingerprint Uses Canonical Form
The system MUST compute `baseline_fingerprint` from canonicalized baseline content.

#### Scenario: Baseline canonicalization during hashing
- **WHEN** baseline is assembled from sources
- **THEN** the system canonicalizes content (stable order, normalized whitespace), computes hash over full baseline

#### Scenario: Identical baseline produces identical fingerprint
- **WHEN** same content arrives in different order
- **THEN** after canonicalization fingerprint is identical

#### Scenario: Different baseline produces different fingerprint
- **WHEN** baseline content differs
- **THEN** fingerprint differs (no collisions on test corpus)

### Requirement: Incremental Model Saves Tokens on Stable Baseline
The system MUST send only tail when baseline is unchanged (Phase 4+).

#### Scenario: Stable baseline in incremental mode
- **WHEN** `incremental=true` and baseline has not changed
- **THEN** the system sends only `tail` (30 tokens), reuses cached baseline (52000 tokens), achieves >60% token savings

#### Scenario: Baseline change breaks epoch
- **WHEN** source changes and `epoch_broken=True`
- **THEN** the system rebuilds baseline, sends new baseline + tail, prompt cache misses but correctness is preserved

### Requirement: Epoch Breaks Are Limited
The system MUST limit epoch breaks to no more than one per turn.

#### Scenario: Multiple changes in one turn
- **WHEN** multiple sources change in one turn
- **THEN** the system applies all changes in one `epoch_broken=True`, not multiple breaks

#### Scenario: Debounce with DEFERRED state
- **WHEN** `DEFERRED` changes accumulate
- **THEN** the system applies them together on next boundary, one epoch break

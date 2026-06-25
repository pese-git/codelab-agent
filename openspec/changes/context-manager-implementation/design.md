# Context Manager Implementation — Design Document

## Context

### Current State

CodeLab currently uses a legacy `ContextCompactor` with two-phase compaction (Prune + LLM Summarize). This approach has several limitations:

1. **No intelligent file collection** — agents rely on manual context attachment or simple heuristics
2. **Full context re-sending every turn** — linear cost growth on long sessions (quadratic total)
3. **No file content cache** — repeated ACP RPCs for the same files
4. **No AST-based skeletonization** — loss of code structure during compression
5. **No incremental model** — no savings on stable prefix (prompt cache miss every turn)

### Constraints

- **ACP Protocol compliance** — all tool calls go through `ToolRegistry`, no direct file I/O
- **Backward compatibility** — legacy `ContextCompactor` must work when `agents.context.enabled=false`
- **Graceful degradation** — hot path must never crash; every failure has a fallback
- **Deterministic output** — `CodeSkeletonizer` and `FileContentCache` must produce byte-identical output for cache stability
- **Python 3.12+** — strict type hints, asyncio, Pydantic 2.11+

### Stakeholders

- **End users** — developers using CodeLab agent for coding tasks
- **SRE** — monitoring rollout via metrics and canary deployment
- **Developers** — implementing and maintaining the system

## Goals / Non-Goals

**Goals:**

1. **Intelligent context collection** — automatically gather relevant files for the task (Layer A)
2. **Incremental context model** — send only deltas when baseline is unchanged (Layer B)
3. **Efficient storage** — file content cache, AST skeletonization, accurate token counting (Layer C)
4. **Three-phase compaction** — Prune → Skeletonize → Summarize with graceful degradation
5. **Multiagent isolation** — child sessions for subagents with summarized results (Layer D)
6. **Observability** — 20+ metrics, tracing spans, structured logs for canary rollout
7. **Phased rollout** — 7 phases (0-6) over ~13 weeks with feature flags

**Non-Goals:**

1. **Federated context sharing** — candidate for rejection (ADR-002 §8); isolation is default
2. **Cross-session persistent memory** — out of scope for this change (see COMPETITIVE_BACKLOG.md)
3. **Learning loop / auto-skill creation** — future work (see COMPETITIVE_BACKLOG.md)
4. **Tree-sitter parsing** — Phase 5 optional; regex-based dependency graph is MVP
5. **Provider-specific optimizations** — focus on protocol-level prompt cache, not provider internals

## Decisions

### Decision 1: Consolidate CM and FCM into 4-Layer Architecture

**Choice:** Merge two previously independent designs (CM "what to read" + FCM "how to store efficiently") into a unified 4-layer architecture (A-D).

**Rationale:**
- CM and FCM answered complementary questions and were not competitors
- CM = intelligence layer (task analysis, gathering, lifecycle)
- FCM = efficiency layer (caching, skeletonization, token counting)
- Consolidation avoids duplication and provides a single source of truth

**Alternatives considered:**
- Keep CM and FCM separate → rejected: would lead to duplicated effort and inconsistent APIs
- Choose one "winner" → rejected: both have valuable capabilities

### Decision 2: PayloadEnvelope with baseline/tail Separation

**Choice:** Introduce `PayloadEnvelope` as the canonical payload format with explicit `baseline` (immutable prefix) and `tail` (deltas).

**Rationale:**
- Foundation for incremental model (Phase 4) — stable baseline enables prompt cache hits
- Must be established in Phase 0, otherwise late incremental support = core rewrite
- Single point of conversion: `to_messages()` at the `EventBus` boundary

**Alternatives considered:**
- Flat `list[LLMMessage]` throughout → rejected: no way to distinguish stable prefix from deltas
- Implicit baseline detection → rejected: fragile, hard to test, provider-specific

### Decision 3: Incremental Model via ContextEpoch

**Choice:** Use `ContextEpoch` with immutable baseline + `mid_conversation_messages` for incremental updates.

**Rationale:**
- Long sessions are the primary use case; hydration-every-turn cost grows quadratically
- Epoch model sends baseline once, then only deltas → stable prefix → prompt cache hit
- Hybrid bridge: Phase 1 (hydration) uses the same API as Phase 4 (epochs), just rebuilds baseline every turn

**Alternatives considered:**
- Hydration-only model → rejected: too expensive for long sessions
- Provider-specific caching → rejected: not portable, provider-dependent

### Decision 4: Codec Fingerprint for Change Detection

**Choice:** Use Codec-based fingerprints (not timestamps) for detecting source changes.

**Rationale:**
- Timestamps are unreliable (clock skew, file system differences)
- Codec fingerprints compare actual content → accurate change detection
- Required for `ContextSnapshot.diff()` and `baseline_fingerprint` stability

**Alternatives considered:**
- Timestamp-based detection → rejected: fragile, platform-dependent
- Hash of file path + size → rejected: does not detect content changes

### Decision 5: Three-Phase Compaction with Graceful Degradation

**Choice:** Implement 3-phase compaction: Prune (FIFO) → Skeletonize (AST) → Summarize (LLM).

**Rationale:**
- Prune is cheap (no LLM) and effective for old tool outputs
- Skeletonize achieves 80-85% token savings on code while preserving structure
- Summarize is expensive (LLM call) but preserves key decisions; skipped if LLM unavailable
- Graceful degradation: if Summarize fails, continue with Prune + Skeletonize

**Alternatives considered:**
- Two-phase (Prune + Summarize) → rejected: loses code structure
- LLM-only compression → rejected: too expensive, no structure preservation

### Decision 6: Deterministic CodeSkeletonizer

**Choice:** Require `CodeSkeletonizer.skeletonize()` to produce byte-identical output for the same input.

**Rationale:**
- Non-deterministic output breaks `baseline_fingerprint` stability → prompt cache miss
- Stable AST traversal order, sorted imports, normalized whitespace are required
- Determinism is a requirement, not a convenience

**Alternatives considered:**
- Non-deterministic skeletonization → rejected: breaks cache stability
- Provider-side normalization → rejected: not portable, provider-dependent

### Decision 7: Unified Invalidation Signal (Phase 2 ↔ Phase 4 Integration)

**Choice:** `FileCacheDecorator.invalidate()` MUST publish a change signal to a unified source of truth.

**Rationale:**
- Prevents silent baseline desync (cache says V2, epoch says V1)
- `ContextSnapshot` compares Codec fingerprints independently of cache signal → double protection
- Lost signal is recoverable via snapshot comparison, not a silent bug

**Alternatives considered:**
- Cache and epoch update independently → rejected: risk of silent desync
- Timestamp-based invalidation → rejected: unreliable

### Decision 8: Isolation by Default for Multiagent

**Choice:** Subagents work in child sessions with isolated context; parent receives only summarized result.

**Rationale:**
- Clean boundaries, predictable budget
- Federated `share_item()` conflicts with isolation and epoch stability
- Both benefits of federation (file cache reuse, derived context transfer) are already covered by `FileContentCache` and `process_subagent_response()`

**Alternatives considered:**
- Federated sharing by default → rejected: conflicts with isolation, breaks epoch stability
- Hybrid approach → rejected: added complexity without clear benefit

### Decision 9: Feature Flags for Canary Rollout

**Choice:** Use `[agents.context.*]` TOML config with master switch `enabled` and per-layer sub-flags.

**Rationale:**
- Master switch allows instant rollback to legacy
- Per-layer flags enable gradual rollout (gather → storage → lifecycle → multiagent)
- Environment variables override TOML for deployment flexibility

**Alternatives considered:**
- Single feature flag → rejected: no granular control
- Code-level toggles → rejected: not configurable per deployment

### Decision 10: File Structure and DI

**Choice:** Organize code under `src/codelab/server/agent/context/` with one file per component; use constructor-based DI.

**Rationale:**
- Clear separation of concerns (one component per file)
- Constructor DI makes dependencies explicit, testable
- External dependencies (ToolRegistry, LLMProvider) passed via constructor, not method parameters

**Alternatives considered:**
- Monolithic `context_manager.py` → rejected: hard to test, maintain
- Service locator pattern → rejected: hidden dependencies, hard to test

## Risks / Trade-offs

### Risk 1: Phase 2 ↔ Phase 4 Integration Complexity

**Risk:** Unified invalidation signal is critical for correctness; if lost, baseline desyncs silently.

**Mitigation:**
- `ContextSnapshot.diff()` compares Codec fingerprints independently of cache signal
- Lost signal counter (`context.invalidation.lost`) detects desync
- Conservative fallback: `epoch_broken=True` on uncertainty (expensive but correct)

### Risk 2: CodeSkeletonizer Determinism

**Risk:** Non-deterministic output breaks prompt cache stability.

**Mitigation:**
- Golden tests: 100 runs on same input → byte-identical output
- Stable AST traversal order, sorted imports, normalized whitespace
- Regression test: same file two turns → identical fingerprint

### Risk 3: Graceful Degradation Complexity

**Risk:** Hot path must never crash; every failure has a fallback.

**Mitigation:**
- Detailed error handling spec (ERROR_HANDLING.md)
- 14 edge cases with acceptance criteria (EDGE_CASES.md)
- Tests for every fallback path

### Risk 4: Performance Overhead

**Risk:** New layers add latency to `build_context()`.

**Mitigation:**
- SLO: `build_context()` p95 < 200ms (without LLM calls)
- Benchmark scenarios for short/medium/long sessions
- Canary rollout with latency monitoring

### Risk 5: Migration Complexity

**Risk:** Migrating from legacy `ContextCompactor` to new `ContextManager` may break existing behavior.

**Mitigation:**
- Feature flag `agents.context.enabled=false` (default) → legacy behavior preserved
- Legacy bridge: `ContextCompactor.compact_if_needed()` signature preserved
- Canary rollout: 5% → 25% → 50% → 100% with metrics

### Trade-off 1: Complexity vs. Flexibility

**Trade-off:** 4-layer architecture is more complex than monolithic design, but provides clear separation of concerns and independent evolution.

**Acceptance:** Complexity is justified by the need for incremental model, multiagent support, and observability.

### Trade-off 2: Determinism vs. Simplicity

**Trade-off:** Deterministic `CodeSkeletonizer` requires more effort (sorted imports, stable AST order), but enables prompt cache hits.

**Acceptance:** Determinism is a requirement for cache stability; non-deterministic output is unacceptable.

### Trade-off 3: Isolation vs. Sharing

**Trade-off:** Isolation by default is simpler and safer, but federated sharing could save tokens in some scenarios.

**Acceptance:** Isolation covers 95% of use cases; federation is candidate for rejection unless specific scenario justifies it.

## Migration Plan

### Phase 0: Foundation (1 week)

1. Create `src/codelab/server/agent/context/` package
2. Implement data models (`PayloadEnvelope`, `ContextItem`, etc.)
3. Define ABC interfaces (`ContextManager`, `TaskAnalyzer`, etc.)
4. Add feature flags `[agents.context.*]` with `enabled=false` default
5. Wrap legacy `ContextCompactor` in `ContextCompactor(ABC)` implementation
6. Archive `doc/internals/architecture/fcm/` → `doc/internals/archive/fcm/`

**Rollback:** Feature flag `enabled=false` → legacy behavior preserved.

### Phase 1: MVP Gather (3 weeks)

1. Implement `TaskAnalyzer` (LLM-based classification)
2. Implement `ContextGatherer` (ACP `ToolRegistry` pipeline)
3. Implement `DependencyGraph` (regex-based)
4. Implement `TokenBudgetManager`
5. Integrate with `ExecutionEngine.build_context()`

**Rollback:** Feature flag `gather.enabled=false` → no automatic gathering.

### Phase 2: Storage Layer (2 weeks)

1. Implement `TokenCounter` (tiktoken + fallback)
2. Implement `FileContentCache` + `SessionFileCacheRegistry`
3. Implement `FileCacheDecorator`
4. Implement `CodeSkeletonizer` (AST-based)

**Rollback:** Feature flag `storage.enabled=false` → no caching/skeletonization.

### Phase 3: Sources + Compaction (1 week)

1. Implement `ContextRegistry` + `ContextSource` + `SkillContextSource`
2. Implement 3-phase `ContextCompactor` (Prune → Skeletonize → Summarize)
3. Implement `ConversationSummarizer`

**Rollback:** Feature flag `storage.skeletonize=false` → no skeletonization.

### Phase 4: Incremental Lifecycle (2 weeks)

1. Implement `ContextEpoch` + `ContextSnapshot` + `ContextReconciler`
2. Unified invalidation signal (Phase 2 ↔ Phase 4 integration)
3. Enable `lifecycle.incremental=true` for prompt cache hits

**Rollback:** Feature flag `lifecycle.incremental=false` → hydration mode.

### Phase 5: Full DependencyGraph (2 weeks)

1. Implement recursive dependency resolution
2. Optional: tree-sitter instead of regex

**Rollback:** Feature flag `gather.recursive_dependencies=false` → non-recursive.

### Phase 6: Multiagent (2 weeks)

1. Implement `ChildSessionManager`
2. Implement `process_subagent_response()`
3. Integrate with Orchestrated/Choreography/Hierarchical strategies

**Rollback:** Feature flag `multiagent.federation=false` → isolation only.

## Open Questions

### Question 1: Tree-sitter vs. Regex for DependencyGraph

**Question:** Should Phase 5 use tree-sitter for more accurate dependency parsing?

**Status:** Optional; regex is MVP. Tree-sitter adds complexity but improves accuracy for complex imports.

**Decision needed:** Before Phase 5 implementation.

### Question 2: Federation Use Cases

**Question:** Are there specific scenarios where federated `share_item()` provides value not covered by isolation?

**Status:** Candidate for rejection. Need concrete use case to justify complexity.

**Decision needed:** Before Phase 6 implementation.

### Question 3: Provider-Specific Prompt Cache

**Question:** Should we implement provider-specific optimizations (e.g., Anthropic prompt caching, OpenAI prefix caching)?

**Status:** Out of scope. Focus on protocol-level prompt cache via stable `baseline_fingerprint`.

**Decision needed:** Future work, if provider-specific optimizations provide significant value.

### Question 4: Persistent Memory Integration

**Question:** Should Context Manager integrate with persistent memory (MEMORY.md/USER.md) from COMPETITIVE_BACKLOG?

**Status:** Out of scope for this change. Future work (Phase 7+).

**Decision needed:** After Phase 6 completion.

## References

- [ADR-002: Context Manager Consolidation](../doc/internals/architecture/adr/ADR-002-context-manager-consolidation.md)
- [CONSOLIDATED_ARCHITECTURE.md](../doc/internals/context-manager/CONSOLIDATED_ARCHITECTURE.md)
- [INTERFACES.md](../doc/internals/context-manager/INTERFACES.md)
- [DATA_MODELS.md](../doc/internals/context-manager/DATA_MODELS.md)
- [ERROR_HANDLING.md](../doc/internals/context-manager/ERROR_HANDLING.md)
- [EDGE_CASES.md](../doc/internals/context-manager/EDGE_CASES.md)
- [OBSERVABILITY.md](../doc/internals/context-manager/OBSERVABILITY.md)
- [PERFORMANCE_SLO.md](../doc/internals/context-manager/PERFORMANCE_SLO.md)
- [TESTING_STRATEGY.md](../doc/internals/context-manager/TESTING_STRATEGY.md)
- [COMPETITIVE_BACKLOG.md](../doc/internals/context-manager/COMPETITIVE_BACKLOG.md)

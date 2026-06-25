# Context Manager Implementation — Tasks

## Phase 0: Foundation (1 week)

- [ ] 0.1 Create package structure `src/codelab/server/agent/context/` with `__init__.py`
- [ ] 0.2 Implement data models in `models.py`: `PayloadEnvelope`, `TaskProfile`, `BudgetAllocation`, `BuildOptions`, `ContextConfig`, `ContextItem`, `ContextEpoch`, `ContextSnapshot`, `ReconcileResult`, `SubagentResult`, enums (`TaskType`, `ContextType`, `ChangeState`)
- [ ] 0.3 Write unit tests for `PayloadEnvelope.to_messages()` and `ContextSnapshot.diff()`
- [ ] 0.4 Define ABC interfaces in `interfaces.py`: `ContextManager`, `TaskAnalyzer`, `ContextGatherer`, `DependencyGraph`, `TokenBudgetManager`, `ContextSource`, `ContextRegistry`, `ConversationSummarizer`, `ContextReconciler`, `TokenCounter`, `CodeSkeletonizer`, `FileContentCache`, `ContextCompactor`, `ChildSessionManager`
- [ ] 0.5 Verify all ABCs have `@abstractmethod` decorators; mypy/pyright passes
- [ ] 0.6 Introduce `PayloadEnvelope` in `ExecutionEngine.build_context()` return type with `to_messages()` adapter at `LLMAdapter` boundary
- [ ] 0.7 Implement feature flags loader: TOML `[agents.context.*]` → `ContextConfig` with env overrides `CODELAB_CONTEXT_*`
- [ ] 0.8 Deprecate `agents.context.enable_fcm` → alias to `agents.context.enabled` with warning
- [ ] 0.9 Wrap legacy `context_compactor.py` in `ContextCompactor(ABC)` implementation without changing logic
- [ ] 0.10 Update `ExecutionEngine` to select implementation by `agents.context.enabled` flag
- [ ] 0.11 Verify `enabled=false` (default) preserves legacy behavior; all existing `test_context_compactor.py` tests pass
- [ ] 0.12 Archive `doc/internals/architecture/fcm/` → `doc/internals/archive/fcm/` with redirect header to ADR-002
- [ ] 0.13 Update cross-references in `doc/internals/` to point to new canon `doc/internals/context-manager/`
- [ ] 0.14 Write integration test: `PayloadEnvelope` flows through `ExecutionEngine` → `LLMAdapter` boundary

## Phase 1: MVP Gather (3 weeks)

- [ ] 1.1 Implement `TaskAnalyzer.analyze()` with LLM-based classification (BUG_FIX/FEATURE/REFACTOR/ARCHITECTURE)
- [ ] 1.2 Implement default `TaskProfile` fallback when LLM classification fails
- [ ] 1.3 Write unit tests for `TaskAnalyzer` with mocked LLM provider
- [ ] 1.4 Implement `ContextGatherer.gather()` pipeline: `project_tree()` → `search()` → `read_file()` → dependency graph → selection
- [ ] 1.5 Ensure `ContextGatherer` performs all I/O through ACP `ToolRegistry`, no direct file access
- [ ] 1.6 Implement binary file detection (by extension and UTF-8 decode error)
- [ ] 1.7 Implement empty/whitespace file filtering
- [ ] 1.8 Write unit tests for `ContextGatherer` with mocked `ToolRegistry`
- [ ] 1.9 Implement `DependencyGraph` with regex-based import parsing (Phase 1)
- [ ] 1.10 Implement `get_dependencies(recursive=False)` and `get_dependents()` methods
- [ ] 1.11 Implement cyclic import protection with visited set
- [ ] 1.12 Write unit tests for `DependencyGraph` including cyclic imports
- [ ] 1.13 Implement `TokenBudgetManager.allocate()` with configurable shares (system/history/tool_output/response_buffer)
- [ ] 1.14 Implement `TokenBudgetManager.bound_content()` preserving start and end
- [ ] 1.15 Write unit tests for `TokenBudgetManager`
- [ ] 1.16 Implement `ContextRegistry` with `register()`, `render_baseline()`, `render_updates()`, `detect_changes()`
- [ ] 1.17 Implement `ContextSource` ABC with `source_id`, `render()`, `fingerprint()` (Codec-based)
- [ ] 1.18 Write unit tests for `ContextRegistry` and `ContextSource`
- [ ] 1.19 Integrate Layer A with `ExecutionEngine.build_context()`: `TaskAnalyzer` → `ContextGatherer` → `DependencyGraph` → `TokenBudgetManager`
- [ ] 1.20 Write integration test: `build_context()` collects relevant files for a sample task
- [ ] 1.21 Write e2e test: `SingleStrategy` → `ExecutionEngine` → `ContextManager` → file collection ≥80% accuracy
- [ ] 1.22 Add metrics: `context_gathered_files`, `context_build_duration_ms`, `context_baseline_tokens`, `context_tail_tokens`
- [ ] 1.23 Add tracing span: `context.build` with attributes (`agent_scope`, `task_type`, `gathered_files`, `baseline_tokens`, `tail_tokens`)
- [ ] 1.24 Add tracing span: `context.gather` with attributes (`task_type`, `search_terms`, `candidate_files`, `selected_files`)
- [ ] 1.25 Verify feature flag `gather.enabled=false` disables automatic gathering

## Phase 2: Storage Layer (2 weeks)

- [ ] 2.1 Implement `TokenCounter` ABC with `count()` and `count_messages()` methods
- [ ] 2.2 Implement `TiktokenCounter` using tiktoken library
- [ ] 2.3 Implement `ApproximateTokenCounter` fallback (`len(text) // 4`)
- [ ] 2.4 Implement factory: try tiktoken import, fallback to approximate with warning log
- [ ] 2.5 Write unit tests for `TokenCounter` accuracy and fallback
- [ ] 2.6 Implement `FileContentCache` ABC with `get()`, `set()`, `invalidate()` methods
- [ ] 2.7 Implement `InMemoryFileCache` with LRU eviction at `cache_max_files`
- [ ] 2.8 Ensure `invalidate()` publishes change signal to unified source of truth
- [ ] 2.9 Write unit tests for `FileContentCache` including LRU eviction and invalidation signal
- [ ] 2.10 Implement `SessionFileCacheRegistry` for per-session cache lifecycle
- [ ] 2.11 Ensure registry releases cache memory on session close
- [ ] 2.12 Write unit tests for `SessionFileCacheRegistry` lifecycle
- [ ] 2.13 Implement `FileCacheDecorator` wrapping `ToolExecutor`
- [ ] 2.14 Intercept successful `fs/read` → call `FileContentCache.set(path, content)`
- [ ] 2.15 Intercept successful `fs/write` → call `FileContentCache.invalidate(path)` + publish signal
- [ ] 2.16 Ensure decorator errors are logged but not propagated (tool execution succeeds)
- [ ] 2.17 Write unit tests for `FileCacheDecorator` with mocked `ToolExecutor`
- [ ] 2.18 Implement `CodeSkeletonizer` ABC with `can_handle()` and `skeletonize()` methods
- [ ] 2.19 Implement `PythonASTSkeletonizer` using Python `ast` module
- [ ] 2.20 Ensure skeletonization is deterministic: stable AST order, sorted imports, normalized whitespace
- [ ] 2.21 Implement fallback: return original code on `SyntaxError` or unsupported language
- [ ] 2.22 Implement check: if skeleton token count >= original, use original
- [ ] 2.23 Write golden tests: 100 runs on same input → byte-identical output
- [ ] 2.24 Write unit tests for `CodeSkeletonizer` including determinism and fallback
- [ ] 2.25 Implement `ContextItem` dataclass with `id`, `type`, `content`, `priority`, `owner_scope`, `token_count`, `last_accessed`
- [ ] 2.26 Add metrics: `context_file_cache_hits`, `context_file_cache_misses`, `context_file_cache_evictions`, `context_file_cache_size_bytes`, `context_token_count_duration_ms`, `context_skeleton_savings_ratio`
- [ ] 2.27 Verify feature flag `storage.enabled=false` disables caching and skeletonization

## Phase 3: Sources + Compaction (1 week)

- [ ] 3.1 Implement `SkillContextSource` for skill catalog in system prompt
- [ ] 3.2 Register `SkillContextSource` with `ContextRegistry`
- [ ] 3.3 Write unit tests for `SkillContextSource` rendering and change detection
- [ ] 3.4 Implement 3-phase `ContextCompactor`: `compact_if_needed()` with Prune → Skeletonize → Summarize
- [ ] 3.5 Implement Prune phase: FIFO removal of old tool outputs, preserve first 2 and last N messages
- [ ] 3.6 Ensure Prune removes `tool_call` + `tool_result` pairs together (no orphans)
- [ ] 3.7 Implement Skeletonize phase: apply `CodeSkeletonizer` to large read-only files
- [ ] 3.8 Implement Summarize phase: call `ConversationSummarizer.summarize()` if Prune + Skeletonize insufficient
- [ ] 3.9 Implement graceful degradation: if LLM unavailable, skip Summarize, continue with Prune + Skeletonize
- [ ] 3.10 Ensure `compact_if_needed()` signature matches legacy for seamless migration
- [ ] 3.11 Write unit tests for `ContextCompactor` including all three phases and degradation
- [ ] 3.12 Implement `ConversationSummarizer.summarize()` with LLM provider
- [ ] 3.13 Implement fallback: return truncated raw result if summarization fails
- [ ] 3.14 Write unit tests for `ConversationSummarizer` with mocked LLM provider
- [ ] 3.15 Implement `ensure_context_fits()` method in `ContextManager`
- [ ] 3.16 Implement hard truncation via `TokenBudgetManager.bound_content()` if payload still exceeds budget after 3 phases
- [ ] 3.17 Ensure items with `priority >= 10` are not evicted unless critical overflow
- [ ] 3.18 Implement orphaned message sanitization: remove `tool_result` without `tool_call`, add placeholder for `tool_call` without `tool_result`
- [ ] 3.19 Write unit tests for `ensure_context_fits()` including hard truncation and sanitization
- [ ] 3.20 Add metrics: `context_compaction_ratio`, `context_compaction_total`, `context_compaction_degraded_total`
- [ ] 3.21 Add tracing span: `context.compact` with attributes (`phase`, `ratio`, `tokens_before`, `tokens_after`, `degraded`)

## Phase 4: Incremental Lifecycle (2 weeks)

- [ ] 4.1 Implement `ContextEpoch` dataclass with `epoch_id`, `baseline`, `baseline_fingerprint`, `mid_conversation_messages`
- [ ] 4.2 Implement `ContextEpoch.get_full_context()` returning `[*baseline, *mid_conversation_messages]`
- [ ] 4.3 Implement `ContextSnapshot` dataclass with `fingerprints: dict[str, str]`
- [ ] 4.4 Implement `ContextSnapshot.diff()` comparing fingerprints, returning changed `source_id` list
- [ ] 4.5 Implement `ContextReconciler.snapshot()` collecting fingerprints from all sources
- [ ] 4.6 Implement `ContextReconciler.reconcile()` returning `ReconcileResult` with `state`, `updated_sources`, `new_tail_messages`, `epoch_broken`
- [ ] 4.7 Implement `UNCHANGED` state: no sources changed, baseline stable
- [ ] 4.8 Implement `UPDATED` state: sources changed on safe boundary, baseline rebuilt (`epoch_broken=True`)
- [ ] 4.9 Implement `DEFERRED` state: change detected mid-turn, applied on next boundary
- [ ] 4.10 Implement conservative fallback: uncertain change → `epoch_broken=True`
- [ ] 4.11 Write unit tests for `ContextReconciler` including all states and conservative fallback
- [ ] 4.12 Integrate unified invalidation signal: `FileCacheDecorator.invalidate()` publishes to unified source
- [ ] 4.13 Ensure `ContextSnapshot.diff()` detects changes independently of cache signal (double protection)
- [ ] 4.14 Write integration test: `fs/write` → `invalidate()` → `reconcile()` detects change
- [ ] 4.15 Write integration test: lost invalidation signal detected by snapshot comparison
- [ ] 4.16 Implement `baseline_fingerprint` computation over canonicalized baseline content
- [ ] 4.17 Ensure identical baseline produces identical fingerprint (deterministic hash)
- [ ] 4.18 Implement incremental mode: send only `tail` when baseline unchanged (prompt cache hit)
- [ ] 4.19 Write integration test: stable baseline → `epoch_broken=False` → tail-only send
- [ ] 4.20 Write integration test: baseline change → `epoch_broken=True` → full baseline send
- [ ] 4.21 Ensure epoch breaks are bounded: at most one per turn
- [ ] 4.22 Implement `DEFERRED` debounce: accumulate changes, apply together on next boundary
- [ ] 4.23 Add metrics: `context_epoch_breaks_total`, `context_reconcile_total`, `context_prompt_cache_hit_rate`
- [ ] 4.24 Add tracing span: `context.reconcile` with attributes (`state`, `epoch_broken`, `changed_sources`)
- [ ] 4.25 Verify feature flag `lifecycle.incremental=false` uses hydration mode (baseline rebuilt every turn)
- [ ] 4.26 Verify feature flag `lifecycle.incremental=true` uses epoch mode (baseline stable, tail-only send)

## Phase 5: Full DependencyGraph (2 weeks)

- [ ] 5.1 Implement recursive dependency resolution in `DependencyGraph.get_dependencies(recursive=True)`
- [ ] 5.2 Ensure recursive resolution uses visited set to prevent infinite loops
- [ ] 5.3 Ensure result order is deterministic (by first visit order)
- [ ] 5.4 Write unit tests for recursive dependency resolution including transitive dependencies
- [ ] 5.5 Write integration test: large project (1000+ files) → `gather()` completes in <1s
- [ ] 5.6 (Optional) Implement tree-sitter-based import parsing for improved accuracy
- [ ] 5.7 (Optional) Write unit tests comparing tree-sitter vs regex accuracy
- [ ] 5.8 Add metrics: `context_gathered_files` with `task_type` label for large projects
- [ ] 5.9 Verify feature flag `gather.recursive_dependencies=false` uses non-recursive mode
- [ ] 5.10 Verify feature flag `gather.use_tree_sitter=true` uses tree-sitter if implemented

## Phase 6: Multiagent (2 weeks)

- [ ] 6.1 Implement `ChildSessionManager.create_child()` creating isolated child session
- [ ] 6.2 Ensure child session has separate `agent_scope` and `ContextEpoch`
- [ ] 6.3 Implement `ChildSessionManager.collect_summary()` returning `SubagentResult`
- [ ] 6.4 Write unit tests for `ChildSessionManager` including isolation and summary collection
- [ ] 6.5 Implement `process_subagent_response()` summarizing subagent result for parent
- [ ] 6.6 Add summary to parent scope as `ContextType.AGENT_REPORT` with `priority=7`
- [ ] 6.7 Implement graceful degradation: if summarization fails, return truncated raw result
- [ ] 6.8 Implement subagent failure handling: return error summary to parent, do not crash parent
- [ ] 6.9 Implement subagent timeout handling: cancel child task, return timeout marker to parent
- [ ] 6.10 Write unit tests for `process_subagent_response()` including failure and timeout
- [ ] 6.11 Integrate `OrchestratedStrategy` with `ContextManager`: `build_context()` + `process_subagent_response()` + `ensure_context_fits()`
- [ ] 6.12 Write integration test: `OrchestratedStrategy` → orchestrator + subagents → summarized results
- [ ] 6.13 Integrate `ChoreographyStrategy` with `ContextManager`: `build_context()` + `process_subagent_response()` (winner only)
- [ ] 6.14 Write integration test: `ChoreographyStrategy` → broadcast → winner processed, others discarded
- [ ] 6.15 Integrate `HierarchicalStrategy` with `ContextManager`: `build_context()` + `process_subagent_response()` + `ensure_context_fits()` at each level
- [ ] 6.16 Write integration test: `HierarchicalStrategy` → tree of agents → bottom-up summarization
- [ ] 6.17 Ensure lifecycle model (hydration vs epoch) is transparent to strategies
- [ ] 6.18 Write test: strategy does not know about lifecycle model, only uses `build_context()` API
- [ ] 6.19 (Optional) Implement federated `share_item()` behind feature flag `multiagent.federation=true`
- [ ] 6.20 (Optional) Write test: federation conflicts with epoch stability → `epoch_broken=True`
- [ ] 6.21 Add metrics: `context_subagent_responses_total`, `context.subagent.failures`, `context.subagent.timeouts`
- [ ] 6.22 Verify feature flag `multiagent.federation=false` uses isolation only

## Cross-Cutting Tasks

- [ ] X.1 Write end-to-end test: full agent loop with `ContextManager` (Phase 1-6 enabled)
- [ ] X.2 Implement canary rollout logic: `CODELAB_CONTEXT_ROLLOUT_PERCENT` for gradual rollout
- [ ] X.3 Write canary monitoring dashboard: compare canary vs legacy metrics
- [ ] X.4 Define rollback criteria: error rate > 0.01, p95 latency > 400ms, cache hit rate < 0.50
- [ ] X.5 Write runbook: how to enable/disable features, how to rollback, how to monitor
- [ ] X.6 Update `README.md` with Context Manager documentation
- [ ] X.7 Update `AGENTS.md` with Context Manager conventions
- [ ] X.8 Conduct code review: all phases reviewed by architecture team
- [ ] X.9 Conduct security review: prompt injection protection, sensitive path blocking
- [ ] X.10 Conduct performance review: benchmark results vs SLO targets

## Success Criteria

- [ ] S.1 All phases 0-6 implemented according to specs
- [ ] S.2 Legacy `ContextCompactor` works when `enabled=false` without regressions
- [ ] S.3 `PayloadEnvelope` is the only payload format in the formation path
- [ ] S.4 Graceful degradation: hot path never crashes, every failure has a fallback
- [ ] S.5 Observability: 20+ metrics, tracing spans, structured logs
- [ ] S.6 Canary rollout: 5% → 25% → 50% → 100% with metrics and rollback criteria
- [ ] S.7 All edge cases from EDGE_CASES.md have acceptance tests
- [ ] S.8 All error handling from ERROR_HANDLING.md has tests
- [ ] S.9 Performance SLO met: `build_context()` p95 < 200ms, cache hit rate > 0.80
- [ ] S.10 Documentation updated: CONSOLIDATED_ARCHITECTURE.md, INTERFACES.md, DATA_MODELS.md

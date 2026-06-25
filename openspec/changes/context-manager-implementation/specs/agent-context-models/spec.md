# agent-context-models Delta Specification

## ADDED Requirements

### Requirement: PayloadEnvelope Data Model
The system MUST provide `PayloadEnvelope` as a frozen dataclass:
- `baseline: list[LLMMessage]` — immutable prefix (system + stable sources)
- `tail: list[LLMMessage]` — current turn deltas (user/assistant/tool)
- `baseline_fingerprint: str` — Codec fingerprint of baseline (for prompt-cache hit)
- `token_count: int` — total token estimate

#### Scenario: PayloadEnvelope creation
- **WHEN** `build_context()` is called
- **THEN** the system returns `PayloadEnvelope` with separated baseline and tail

#### Scenario: to_messages flattens baseline and tail
- **WHEN** `envelope.to_messages()` is called
- **THEN** the system returns `[*baseline, *tail]` as flat `list[LLMMessage]`

### Requirement: TaskProfile Data Model
The system MUST provide `TaskProfile` as a frozen dataclass:
- `task_type: TaskType` — classification (BUG_FIX, FEATURE, REFACTOR, ARCHITECTURE)
- `search_terms: list[str]` — extracted search terms
- `target_modules: list[str]` — target modules
- `investigation_depth: int` — 1-3
- `needs_tests: bool` — whether tests are needed

#### Scenario: TaskProfile from TaskAnalyzer
- **WHEN** `TaskAnalyzer.analyze()` completes
- **THEN** the system returns `TaskProfile` with classification and search strategy

### Requirement: BudgetAllocation Data Model
The system MUST provide `BudgetAllocation` as a frozen dataclass:
- `system_tokens: int`
- `history_tokens: int`
- `tool_output_tokens: int`
- `response_buffer_tokens: int`

#### Scenario: BudgetAllocation from TokenBudgetManager
- **WHEN** `TokenBudgetManager.allocate(total_tokens)` is called
- **THEN** the system returns `BudgetAllocation` with token shares

### Requirement: BuildOptions Data Model
The system MUST provide `BuildOptions` as a frozen dataclass:
- `incremental: bool | None = None` — None means use config
- `skeletonize: bool | None = None`
- `max_files: int | None = None`

#### Scenario: BuildOptions overrides config
- **WHEN** `BuildOptions(incremental=True)` is passed to `build_context()`
- **THEN** the system uses `True` for incremental, overriding config value

### Requirement: ContextConfig Data Model
The system MUST provide `ContextConfig` as a frozen dataclass with feature flags:
- `enabled: bool = False` — master switch
- `gather_enabled: bool = True`
- `recursive_dependencies: bool = False`
- `use_tree_sitter: bool = False`
- `use_tiktoken: bool = True`
- `file_cache: bool = True`
- `skeletonize: bool = True`
- `cache_max_files: int = 1000`
- `incremental: bool = False`
- `max_context_tokens: int = 128000`
- `reserved_tokens: int = 4096`
- `system_share: float = 0.20`
- `history_share: float = 0.50`
- `tool_output_share: float = 0.20`
- `response_buffer_share: float = 0.10`
- `federation: bool = False`

#### Scenario: ContextConfig from TOML
- **WHEN** TOML `[agents.context.*]` is loaded
- **THEN** the system creates `ContextConfig` with values from TOML

#### Scenario: ContextConfig env override
- **WHEN** environment variable `CODELAB_CONTEXT_ENABLED=true` is set
- **THEN** the system overrides TOML value with env value

### Requirement: ContextItem Data Model
The system MUST provide `ContextItem` as a frozen dataclass:
- `id: str` — usually file path or unique key
- `type: ContextType` — FILE_CONTENT, FILE_SKELETON, TERMINAL_OUTPUT, etc.
- `content: str`
- `priority: int` — 0-10; >=10 not evicted during compaction
- `owner_scope: str`
- `token_count: int`
- `last_accessed: float = 0.0` — last access timestamp (for LRU eviction)

#### Scenario: ContextItem with priority
- **WHEN** context item is created
- **THEN** item has priority for eviction ordering

### Requirement: ContextEpoch Data Model
The system MUST provide `ContextEpoch` as a frozen dataclass:
- `epoch_id: str`
- `baseline: list[LLMMessage]`
- `baseline_fingerprint: str`
- `mid_conversation_messages: list[LLMMessage] = field(default_factory=list)`

#### Scenario: ContextEpoch get_full_context
- **WHEN** `epoch.get_full_context()` is called
- **THEN** the system returns `[*baseline, *mid_conversation_messages]`

### Requirement: ContextSnapshot Data Model
The system MUST provide `ContextSnapshot` as a frozen dataclass:
- `fingerprints: dict[str, str]` — source_id → Codec fingerprint

#### Scenario: ContextSnapshot diff
- **WHEN** `snapshot.diff(other)` is called
- **THEN** the system returns list of changed source_ids

### Requirement: ReconcileResult Data Model
The system MUST provide `ReconcileResult` as a frozen dataclass:
- `state: ChangeState` — UNCHANGED, UPDATED, DEFERRED
- `updated_sources: list[str]`
- `new_tail_messages: list[LLMMessage]`
- `epoch_broken: bool` — True means baseline was rebuilt (cache loss)

#### Scenario: ReconcileResult with epoch broken
- **WHEN** reconciliation detects baseline change
- **THEN** `ReconcileResult` has `epoch_broken=True`

### Requirement: SubagentResult Data Model
The system MUST provide `SubagentResult` as a frozen dataclass:
- `summary: str` — summarized result (isolation)
- `token_count: int`
- `source_scope: str`
- `shared_items: list[ContextItem] = field(default_factory=list)` — empty without federation

#### Scenario: SubagentResult from process_subagent_response
- **WHEN** `process_subagent_response()` completes
- **THEN** the system returns `SubagentResult` with summary for parent

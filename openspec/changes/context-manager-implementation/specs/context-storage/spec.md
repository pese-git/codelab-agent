# Context Storage Capability Specification

## ADDED Requirements

### Requirement: FileContentCache Eliminates Duplicate RPCs
The system MUST cache file contents per-session to eliminate duplicate ACP `read_file()` calls.

#### Scenario: Cache hit on repeated read
- **WHEN** file is read via `fs/read` and then read again in same session
- **THEN** second read returns content from `FileContentCache` without ACP RPC, logs debug `file_cache_miss` on first, no log on hit

#### Scenario: Cache miss on first read
- **WHEN** file is read for first time
- **THEN** the system calls ACP RPC `read_file()`, stores content in cache via `set(path, content)`, returns content

#### Scenario: LRU eviction at capacity
- **WHEN** cache reaches `cache_max_files` limit
- **THEN** the system evicts least-recently-used entry, logs debug `file_cache_evicted`

#### Scenario: Invalidate on fs/write
- **WHEN** `fs/write` succeeds for a path
- **THEN** the system calls `FileContentCache.invalidate(path)`, subsequent `get(path)` returns `None`

#### Scenario: Invalidate publishes change signal
- **WHEN** `invalidate(path)` is called
- **THEN** the system publishes change signal to unified source of truth (Phase 2 ↔ Phase 4 integration point)

### Requirement: SessionFileCacheRegistry Manages Cache Lifecycle
The system MUST manage per-session file caches with proper lifecycle.

#### Scenario: Cache creation per session
- **WHEN** new session starts
- **THEN** `SessionFileCacheRegistry` creates new `FileContentCache` for session

#### Scenario: Cache cleanup on session close
- **WHEN** session closes
- **THEN** registry releases cache memory, ensures budget < 2 MB per session

### Requirement: FileCacheDecorator Wraps ToolExecutor
The system MUST wrap `ToolExecutor` with `FileCacheDecorator` to intercept `fs/read` and `fs/write`.

#### Scenario: Decorator intercepts fs/read
- **WHEN** `fs/read` tool is executed successfully
- **THEN** decorator calls `FileContentCache.set(path, content)` after tool returns

#### Scenario: Decorator intercepts fs/write
- **WHEN** `fs/write` tool is executed successfully
- **THEN** decorator calls `FileContentCache.invalidate(path)` and publishes change signal

#### Scenario: Decorator I/O through ToolRegistry
- **WHEN** decorator needs to read/write files
- **THEN** the system uses ACP `ToolRegistry`, not direct file system access

#### Scenario: Decorator error handling
- **WHEN** `invalidate()` or `set()` fails
- **THEN** decorator logs error, does not propagate exception (tool execution succeeds), logs `file_cache_invalidation_failed` or `file_cache_set_failed`

### Requirement: CodeSkeletonizer Compresses Code via AST
The system MUST compress code to signatures using AST analysis, preserving structure.

#### Scenario: Python AST skeletonization
- **WHEN** `skeletonize()` is called on Python code
- **THEN** the system replaces function/method bodies with `...`, preserves signatures, imports, class definitions

#### Scenario: Skeleton achieves 80-85% token savings
- **WHEN** skeleton is produced from 3500-token file
- **THEN** skeleton is ~250 tokens (80-85% savings)

#### Scenario: Skeleton is deterministic
- **WHEN** `skeletonize()` is called 100 times on same input
- **THEN** all 100 outputs are byte-identical

#### Scenario: Skeleton preserves structure
- **WHEN** code has classes, methods, functions
- **THEN** skeleton preserves class hierarchy, method signatures, function signatures

#### Scenario: Skeleton is not beneficial
- **WHEN** skeleton token count >= original token count
- **THEN** the system uses original code, logs info `skeleton_not_beneficial`

### Requirement: CodeSkeletonizer Handles Unsupported Languages
The system MUST gracefully handle files in unsupported languages.

#### Scenario: can_handle returns False for unsupported language
- **WHEN** file is `.json`, `.md`, `.dart`, etc.
- **THEN** `can_handle(path)` returns `False`

#### Scenario: Skeletonization skipped for unsupported
- **WHEN** `can_handle()` is `False`
- **THEN** the system does not call `skeletonize()`, uses original content

#### Scenario: SyntaxError in supported language
- **WHEN** Python file has syntax error
- **THEN** `skeletonize()` catches `SyntaxError`, returns original code, logs warning `skeletonize_syntax_error`

### Requirement: TokenCounter Provides Accurate Counting
The system MUST count tokens accurately using tiktoken with fallback.

#### Scenario: Tiktoken counting
- **WHEN** `TiktokenCounter.count(text)` is called
- **THEN** the system returns accurate token count using tiktoken encoding

#### Scenario: Tiktoken unavailable fallback
- **WHEN** tiktoken import fails
- **THEN** the system returns `ApproximateTokenCounter` with `len(text) // 4`, logs warning `tiktoken_not_available_using_fallback`

#### Scenario: Tiktoken count failure
- **WHEN** tiktoken encoding fails on specific input
- **THEN** the system falls back to approximate count for that call, logs error `tiktoken_encoding_failed_using_fallback`

#### Scenario: count_messages for list
- **WHEN** `count_messages(messages)` is called
- **THEN** the system returns total token count for all messages

### Requirement: ContextItem Represents Context Unit
The system MUST represent each context element as `ContextItem` with priority.

#### Scenario: ContextItem structure
- **WHEN** context item is created
- **THEN** item has `id`, `type`, `content`, `priority` (0-10), `owner_scope`, `token_count`, `last_accessed`

#### Scenario: Priority-based eviction
- **WHEN** compactor needs to evict items
- **THEN** the system evicts lowest priority first (`file_skeleton=3` → `terminal_output=4` → `file_content=5` → ... → `system_rules=10`)

#### Scenario: Priority >= 10 not evicted
- **WHEN** item has `priority >= 10`
- **THEN** the system does not evict item during compaction

### Requirement: Deterministic Output for Cache Stability
The system MUST ensure deterministic output for `CodeSkeletonizer` and `FileContentCache` to maintain cache stability.

#### Scenario: Deterministic skeleton output
- **WHEN** same code is skeletonized multiple times
- **THEN** output is byte-identical (stable AST order, sorted imports, normalized whitespace)

#### Scenario: Deterministic cache content
- **WHEN** same file is read multiple times
- **THEN** cached content is byte-identical

#### Scenario: Baseline fingerprint stability
- **WHEN** baseline content is unchanged
- **THEN** `baseline_fingerprint` is identical across calls (deterministic hash)

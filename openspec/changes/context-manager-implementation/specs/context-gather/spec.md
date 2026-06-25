# Context Gather Capability Specification

## ADDED Requirements

### Requirement: Task Analysis Classifies User Intent
The system MUST analyze the user's prompt to classify the task type and extract search strategy.

#### Scenario: Bug fix task classification
- **WHEN** user submits prompt "Fix crash when email is empty in auth"
- **THEN** the system classifies task as `BUG_FIX` with `investigation_depth=2` and `needs_tests=True`

#### Scenario: Feature task classification
- **WHEN** user submits prompt "Add user authentication with OAuth"
- **THEN** the system classifies task as `FEATURE` with `investigation_depth=3` and `needs_tests=True`

#### Scenario: LLM classification failure fallback
- **WHEN** LLM-based classification fails (network error, timeout, invalid response)
- **THEN** the system returns default `TaskProfile` with `task_type=FEATURE`, `investigation_depth=1`, and heuristic search terms extracted from prompt text

### Requirement: Context Gatherer Collects Relevant Files
The system MUST collect relevant files through ACP ToolRegistry using the pipeline: `project_tree()` → `search()` → `read_file()` → dependency graph → selection.

#### Scenario: Successful file collection
- **WHEN** TaskProfile has `search_terms=["email", "auth"]` and `target_modules=["auth"]`
- **THEN** the system calls `project_tree()`, `search(["email", "auth"])`, reads candidate files, and returns `list[ContextItem]` with `type=FILE_CONTENT`

#### Scenario: ACP RPC failure for project_tree
- **WHEN** RPC `project_tree()` fails
- **THEN** the system continues with empty tree, relies on `search()` and `target_modules` from TaskProfile, logs warning `gather_project_tree_failed`

#### Scenario: ACP RPC failure for search
- **WHEN** RPC `search()` fails
- **THEN** the system skips search step, continues with tree + dependencies from DependencyGraph, logs warning `gather_search_failed`

#### Scenario: ACP RPC failure for read_file
- **WHEN** RPC `read_file()` fails for a specific file
- **THEN** the system skips that file, continues with remaining files, logs warning `gather_read_file_failed` with field `path`

#### Scenario: All RPCs fail
- **WHEN** all ACP RPCs fail simultaneously
- **THEN** the system returns empty or partial `list[ContextItem]`, logs error `gather_all_sources_failed`, payload builds from `session.history` + system prompt only

### Requirement: Binary Files Are Filtered
The system MUST detect and exclude binary files from context collection.

#### Scenario: Binary file detection by extension
- **WHEN** file has binary extension (`.png`, `.zip`, `.pdf`, `.exe`)
- **THEN** the system skips file without calling `read_file()`, logs info `gather_file_skipped` with `reason=binary`

#### Scenario: Binary file detection by content
- **WHEN** `read_file()` returns content that fails UTF-8 decoding
- **THEN** the system catches `UnicodeDecodeError`, excludes file from result, logs info `gather_file_skipped` with `reason=binary`

### Requirement: Empty Files Are Filtered
The system MUST exclude empty files or files with only whitespace from context collection.

#### Scenario: Empty file filtering
- **WHEN** file content is `""` or contains only whitespace
- **THEN** the system does not add `ContextItem` for this file, continues with remaining files

### Requirement: Dependency Graph Resolves Imports
The system MUST build and query a dependency graph to resolve file imports.

#### Scenario: Regex-based dependency resolution (Phase 1)
- **WHEN** file `auth/login.py` imports `auth/validators.py`
- **THEN** `DependencyGraph.get_dependencies("auth/login.py")` returns `["auth/validators.py"]`

#### Scenario: Cyclic import handling
- **WHEN** files have cyclic imports (`a.py` → `b.py` → `a.py`)
- **THEN** `get_dependencies(recursive=True)` uses visited set to prevent infinite recursion, returns each file exactly once, result order is deterministic

#### Scenario: Recursive dependency resolution (Phase 5)
- **WHEN** `recursive=True` and file has transitive dependencies
- **THEN** the system resolves all transitive dependencies, returns complete dependency tree

### Requirement: Token Budget Allocation
The system MUST allocate token budget across system, history, tool output, and response buffer.

#### Scenario: Budget allocation with default shares
- **WHEN** `max_context_tokens=128000` and default shares (system=0.20, history=0.50, tool_output=0.20, response_buffer=0.10)
- **THEN** `allocate()` returns `BudgetAllocation` with `system_tokens=25600`, `history_tokens=64000`, `tool_output_tokens=25600`, `response_buffer_tokens=12800`

#### Scenario: Content bounding
- **WHEN** file content exceeds allocated `max_tokens`
- **THEN** `bound_content(content, max_tokens)` truncates content preserving start and end, logs info `content_bounded` with `original_tokens` and `bound_tokens`

### Requirement: Context Registry Manages Sources
The system MUST manage context sources through a registry pattern with baseline and updates rendering.

#### Scenario: Source registration
- **WHEN** `ContextSource` is registered via `register(source)`
- **THEN** source is added to registry with unique `source_id`

#### Scenario: Baseline rendering
- **WHEN** `render_baseline()` is called
- **THEN** the system renders all registered sources, returns combined string

#### Scenario: Change detection via fingerprint
- **WHEN** `detect_changes()` is called
- **THEN** the system compares current fingerprints with previous snapshot, returns list of changed `source_id`

### Requirement: Gatherer Has No Direct I/O
The system MUST ensure that `ContextGatherer` performs all I/O through ACP `ToolRegistry`, not directly.

#### Scenario: I/O through ToolRegistry
- **WHEN** `ContextGatherer.gather()` needs to read files
- **THEN** the system calls `ToolRegistry` methods (`project_tree`, `search`, `read_file`), does not perform direct file system access

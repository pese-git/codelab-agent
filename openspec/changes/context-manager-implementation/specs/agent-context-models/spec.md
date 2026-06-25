# Delta-спецификация agent-context-models

## ADDED Requirements

### Requirement: Модель данных PayloadEnvelope
Система ДОЛЖНА предоставлять `PayloadEnvelope` как frozen dataclass:
- `baseline: list[LLMMessage]` — иммутабельный префикс (system + стабильные источники)
- `tail: list[LLMMessage]` — дельты текущего хода (user/assistant/tool)
- `baseline_fingerprint: str` — Codec-отпечаток baseline (для попадания в prompt-cache)
- `token_count: int` — общая оценка токенов

#### Scenario: Создание PayloadEnvelope
- **WHEN** вызывается `build_context()`
- **THEN** система возвращает `PayloadEnvelope` с разделёнными baseline и tail

#### Scenario: to_messages уплощает baseline и tail
- **WHEN** вызывается `envelope.to_messages()`
- **THEN** система возвращает `[*baseline, *tail]` как плоский `list[LLMMessage]`

### Requirement: Модель данных TaskProfile
Система ДОЛЖНА предоставлять `TaskProfile` как frozen dataclass:
- `task_type: TaskType` — классификация (BUG_FIX, FEATURE, REFACTOR, ARCHITECTURE)
- `search_terms: list[str]` — извлечённые поисковые термины
- `target_modules: list[str]` — целевые модули
- `investigation_depth: int` — 1-3
- `needs_tests: bool` — нужны ли тесты

#### Scenario: TaskProfile от TaskAnalyzer
- **WHEN** `TaskAnalyzer.analyze()` завершается
- **THEN** система возвращает `TaskProfile` с классификацией и стратегией поиска

### Requirement: Модель данных BudgetAllocation
Система ДОЛЖНА предоставлять `BudgetAllocation` как frozen dataclass:
- `system_tokens: int`
- `history_tokens: int`
- `tool_output_tokens: int`
- `response_buffer_tokens: int`

#### Scenario: BudgetAllocation от TokenBudgetManager
- **WHEN** вызывается `TokenBudgetManager.allocate(total_tokens)`
- **THEN** система возвращает `BudgetAllocation` с долями токенов

### Requirement: Модель данных BuildOptions
Система ДОЛЖНА предоставлять `BuildOptions` как frozen dataclass:
- `incremental: bool | None = None` — None означает использовать конфиг
- `skeletonize: bool | None = None`
- `max_files: int | None = None`

#### Scenario: BuildOptions переопределяет конфиг
- **WHEN** `BuildOptions(incremental=True)` передаётся в `build_context()`
- **THEN** система использует `True` для incremental, переопределяя значение конфига

### Requirement: Модель данных ContextConfig
Система ДОЛЖНА предоставлять `ContextConfig` как frozen dataclass с feature flags:
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

#### Scenario: ContextConfig из TOML
- **WHEN** TOML `[agents.context.*]` загружается
- **THEN** система создаёт `ContextConfig` со значениями из TOML

#### Scenario: ContextConfig переопределение через env
- **WHEN** установлена переменная окружения `CODELAB_CONTEXT_ENABLED=true`
- **THEN** система переопределяет значение TOML значением из env

### Requirement: Модель данных ContextItem
Система ДОЛЖНА предоставлять `ContextItem` как frozen dataclass:
- `id: str` — обычно путь к файлу или уникальный ключ
- `type: ContextType` — FILE_CONTENT, FILE_SKELETON, TERMINAL_OUTPUT, и т.д.
- `content: str`
- `priority: int` — 0-10; >=10 не вытесняется при компактировании
- `owner_scope: str`
- `token_count: int`
- `last_accessed: float = 0.0` — временная метка последнего доступа (для LRU eviction)

#### Scenario: ContextItem с приоритетом
- **WHEN** создаётся элемент контекста
- **THEN** элемент имеет приоритет для упорядочивания eviction

### Requirement: Модель данных ContextEpoch
Система ДОЛЖНА предоставлять `ContextEpoch` как frozen dataclass:
- `epoch_id: str`
- `baseline: list[LLMMessage]`
- `baseline_fingerprint: str`
- `mid_conversation_messages: list[LLMMessage] = field(default_factory=list)`

#### Scenario: ContextEpoch get_full_context
- **WHEN** вызывается `epoch.get_full_context()`
- **THEN** система возвращает `[*baseline, *mid_conversation_messages]`

### Requirement: Модель данных ContextSnapshot
Система ДОЛЖНА предоставлять `ContextSnapshot` как frozen dataclass:
- `fingerprints: dict[str, str]` — source_id → Codec-отпечаток

#### Scenario: ContextSnapshot diff
- **WHEN** вызывается `snapshot.diff(other)`
- **THEN** система возвращает список изменённых source_id

### Requirement: Модель данных ReconcileResult
Система ДОЛЖНА предоставлять `ReconcileResult` как frozen dataclass:
- `state: ChangeState` — UNCHANGED, UPDATED, DEFERRED
- `updated_sources: list[str]`
- `new_tail_messages: list[LLMMessage]`
- `epoch_broken: bool` — True означает, что baseline был перестроен (потеря кэша)

#### Scenario: ReconcileResult с поломкой эпохи
- **WHEN** реконсиляция обнаруживает изменение baseline
- **THEN** `ReconcileResult` имеет `epoch_broken=True`

### Requirement: Модель данных SubagentResult
Система ДОЛЖНА предоставлять `SubagentResult` как frozen dataclass:
- `summary: str` — суммаризированный результат (изоляция)
- `token_count: int`
- `source_scope: str`
- `shared_items: list[ContextItem] = field(default_factory=list)` — пусто без федерации

#### Scenario: SubagentResult от process_subagent_response
- **WHEN** `process_subagent_response()` завершается
- **THEN** система возвращает `SubagentResult` с summary для родителя

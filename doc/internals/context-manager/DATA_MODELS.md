# Context Manager — Модели данных

> **Статус:** Канон (Phase 0) — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Дата:** 25 июня 2026
>
> Структуры данных, на которых строятся [интерфейсы](./INTERFACES.md). Все — `@dataclass`,
> предпочтительно `frozen=True` (иммутабельность для кэш-стабильности).

---

## 1. PayloadEnvelope — фундамент жизненного цикла

> Ключевая структура. Заменяет «плоский» `list[LLMMessage]` во всём пути формирования payload.
> Разделение `baseline / tail` закладывается в Phase 0, даже если в MVP baseline пересобирается.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class PayloadEnvelope:
    """Конверт payload с явным разделением иммутабельного префикса и дельт."""

    baseline: list[LLMMessage]        # иммутабельный префикс (system + стабильные источники)
    tail: list[LLMMessage]            # дельты текущего хода (user/assistant/tool)
    baseline_fingerprint: str         # Codec-отпечаток baseline (для prompt-cache хита)
    token_count: int                  # суммарная оценка токенов

    def to_messages(self) -> list[LLMMessage]:
        """Плоский список для LLM-провайдера: baseline + tail."""
        return [*self.baseline, *self.tail]
```

**Поведение по фазам:**
- **Phase 1 (гидрация):** `baseline` пересобирается каждый ход; `baseline_fingerprint` может меняться.
- **Phase 4 (инкрементальная):** `baseline` фиксируется на старте эпохи; меняется только `tail`; стабильный `baseline_fingerprint` → кэш-хит.

---

## 2. Слой A — модели сбора

```python
from enum import Enum

class TaskType(str, Enum):
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    ARCHITECTURE = "architecture"

@dataclass(frozen=True)
class TaskProfile:
    """Результат TaskAnalyzer."""
    task_type: TaskType
    search_terms: list[str]
    target_modules: list[str]
    investigation_depth: int          # 1–3
    needs_tests: bool

@dataclass(frozen=True)
class BudgetAllocation:
    """Результат TokenBudgetManager.allocate()."""
    system_tokens: int
    history_tokens: int
    tool_output_tokens: int
    response_buffer_tokens: int

@dataclass(frozen=True)
class BuildOptions:
    """Опции build_context() (перекрывают конфиг для конкретного вызова)."""
    incremental: bool | None = None   # None → брать из конфига
    skeletonize: bool | None = None
    max_files: int | None = None
```

---

## 3. ContextItem — единица контекста (слой C)

```python
class ContextType(str, Enum):
    FILE_CONTENT = "file_content"
    FILE_SKELETON = "file_skeleton"
    TERMINAL_OUTPUT = "terminal_output"
    USER_PROMPT = "user_prompt"
    SYSTEM_RULES = "system_rules"
    AGENT_REPORT = "agent_report"
    SKILL_CATALOG = "skill_catalog"

@dataclass(frozen=True)
class ContextItem:
    """Единица информации в контексте. priority управляет eviction."""
    id: str                           # обычно путь файла или уникальный ключ
    type: ContextType
    content: str
    priority: int                     # 0–10; >=10 не вытесняется при сжатии
    owner_scope: str
    token_count: int
    last_accessed: float = 0.0        # передаётся снаружи (Date.now недоступен в воркфлоу-движке;
                                      # в рантайме — обычный time.monotonic())
```

**Приоритеты по умолчанию** (роль → priority): `system_rules`=10, `user_prompt`=8, `agent_report`=7, `file_content`=5, `terminal_output`=4, `file_skeleton`=3.

---

## 4. Слой B — модели жизненного цикла

```python
@dataclass(frozen=True)
class ContextEpoch:
    """Иммутабельный baseline + инкрементальные обновления."""
    epoch_id: str
    baseline: list[LLMMessage]
    baseline_fingerprint: str
    mid_conversation_messages: list[LLMMessage] = field(default_factory=list)

    def get_full_context(self) -> list[LLMMessage]:
        return [*self.baseline, *self.mid_conversation_messages]

class ChangeState(str, Enum):
    UNCHANGED = "unchanged"
    UPDATED = "updated"
    DEFERRED = "deferred"             # изменение замечено, но применяется позже (вне границы хода)

@dataclass(frozen=True)
class ContextSnapshot:
    """Снимок отпечатков всех источников в момент времени."""
    fingerprints: dict[str, str]      # source_id → Codec-отпечаток

    def diff(self, other: "ContextSnapshot") -> list[str]:
        """source_id источников с изменившимся отпечатком."""
        return [
            sid for sid, fp in other.fingerprints.items()
            if self.fingerprints.get(sid) != fp
        ]

@dataclass(frozen=True)
class ReconcileResult:
    """Результат ContextReconciliation.reconcile()."""
    state: ChangeState
    updated_sources: list[str]
    new_tail_messages: list[LLMMessage]
    epoch_broken: bool                # True → baseline пересобран (потеря кэша)
```

---

## 5. Слой D — модели мультиагента

```python
@dataclass(frozen=True)
class SubagentResult:
    """Результат process_subagent_response() — то, что попадает родителю."""
    summary: str                      # суммаризованный результат (изоляция)
    token_count: int
    source_scope: str
    shared_items: list[ContextItem] = field(default_factory=list)  # пусто без федерации
```

---

## 6. Конфигурация

Соответствует [схеме флагов в ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md). Маппинг на dataclass:

```python
@dataclass(frozen=True)
class ContextConfig:
    enabled: bool = False
    # gather (Phase 1 / 5)
    gather_enabled: bool = True
    recursive_dependencies: bool = False
    use_tree_sitter: bool = False
    # storage (Phase 2)
    use_tiktoken: bool = True
    file_cache: bool = True
    skeletonize: bool = True
    cache_max_files: int = 1000
    # lifecycle (Phase 4)
    incremental: bool = False
    # budget (Phase 1)
    max_context_tokens: int = 128000
    reserved_tokens: int = 4096
    system_share: float = 0.20
    history_share: float = 0.50
    tool_output_share: float = 0.20
    response_buffer_share: float = 0.10
    # multiagent (Phase 6)
    federation: bool = False
```

Загрузка: TOML `[agents.context.*]` → `ContextConfig`, затем env-overrides `CODELAB_CONTEXT_*` (приоритет выше TOML).

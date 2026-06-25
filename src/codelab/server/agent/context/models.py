"""Модели данных Context Manager.

Канонические структуры данных для 4-слойной архитектуры (A-D).
Все модели — frozen dataclass для иммутабельности и кэш-стабильности.

См. doc/internals/context-manager/DATA_MODELS.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from codelab.server.llm.models import LLMMessage


class TaskType(StrEnum):
    """Классификация задачи (Слой A — TaskAnalyzer)."""

    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    ARCHITECTURE = "architecture"


class ContextType(StrEnum):
    """Тип единицы контекста (Слой C)."""

    FILE_CONTENT = "file_content"
    FILE_SKELETON = "file_skeleton"
    TERMINAL_OUTPUT = "terminal_output"
    USER_PROMPT = "user_prompt"
    SYSTEM_RULES = "system_rules"
    AGENT_REPORT = "agent_report"
    SKILL_CATALOG = "skill_catalog"


class ChangeState(StrEnum):
    """Состояние изменения для ContextReconciler (Слой B)."""

    UNCHANGED = "unchanged"
    UPDATED = "updated"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class PayloadEnvelope:
    """Конверт payload с явным разделением иммутабельного префикса и дельт.

    Фундамент инкрементальной модели. baseline — стабильный префикс,
    tail — дельты текущего хода. to_messages() — единственная точка
    конвертации в плоский список для LLM-провайдера.
    """

    baseline: list[LLMMessage]
    tail: list[LLMMessage]
    baseline_fingerprint: str = ""
    token_count: int = 0

    def to_messages(self) -> list[LLMMessage]:
        """Плоский список для LLM-провайдера: baseline + tail."""
        return [*self.baseline, *self.tail]


@dataclass(frozen=True)
class TaskProfile:
    """Результат TaskAnalyzer.analyze() (Слой A)."""

    task_type: TaskType
    search_terms: list[str]
    target_modules: list[str]
    investigation_depth: int
    needs_tests: bool


@dataclass(frozen=True)
class BudgetAllocation:
    """Результат TokenBudgetManager.allocate() (Слой A)."""

    system_tokens: int
    history_tokens: int
    tool_output_tokens: int
    response_buffer_tokens: int


@dataclass(frozen=True)
class BuildOptions:
    """Опции build_context() — per-call override конфига.

    None означает «взять значение из ContextConfig».
    """

    incremental: bool | None = None
    skeletonize: bool | None = None
    max_files: int | None = None


@dataclass(frozen=True)
class ContextConfig:
    """Feature flags Context Manager.

    Загрузка: TOML [agents.context.*] → env-overrides CODELAB_CONTEXT_*.
    """

    enabled: bool = False
    gather_enabled: bool = True
    recursive_dependencies: bool = False
    use_tree_sitter: bool = False
    use_tiktoken: bool = True
    file_cache: bool = True
    skeletonize: bool = True
    cache_max_files: int = 1000
    incremental: bool = False
    max_context_tokens: int = 128000
    reserved_tokens: int = 4096
    system_share: float = 0.20
    history_share: float = 0.50
    tool_output_share: float = 0.20
    response_buffer_share: float = 0.10
    federation: bool = False


@dataclass(frozen=True)
class ContextItem:
    """Единица информации в контексте (Слой C).

    priority управляет eviction: >=10 не вытесняется при сжатии.
    """

    id: str
    type: ContextType
    content: str
    priority: int
    owner_scope: str
    token_count: int
    last_accessed: float = 0.0


@dataclass(frozen=True)
class ContextEpoch:
    """Иммутабельный baseline + инкрементальные обновления (Слой B)."""

    epoch_id: str
    baseline: list[LLMMessage]
    baseline_fingerprint: str
    mid_conversation_messages: list[LLMMessage] = field(default_factory=list)

    def get_full_context(self) -> list[LLMMessage]:
        """Полный контекст: baseline + mid_conversation_messages."""
        return [*self.baseline, *self.mid_conversation_messages]


@dataclass(frozen=True)
class ContextSnapshot:
    """Снимок отпечатков всех источников (Слой B)."""

    fingerprints: dict[str, str]

    def diff(self, other: ContextSnapshot) -> list[str]:
        """source_id источников с изменившимся отпечатком."""
        return [
            sid
            for sid, fp in other.fingerprints.items()
            if self.fingerprints.get(sid) != fp
        ]


@dataclass(frozen=True)
class ReconcileResult:
    """Результат ContextReconciler.reconcile() (Слой B)."""

    state: ChangeState
    updated_sources: list[str]
    new_tail_messages: list[LLMMessage]
    epoch_broken: bool


@dataclass(frozen=True)
class SubagentResult:
    """Результат process_subagent_response() (Слой D).

    summary — суммаризированный результат для родителя (изоляция).
    shared_items — пусто без федерации.
    """

    summary: str
    token_count: int
    source_scope: str
    shared_items: list[ContextItem] = field(default_factory=list)

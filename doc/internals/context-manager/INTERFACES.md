# Context Manager — Интерфейсы (контракты Phase 0)

> **Статус:** Канон (заморозка интерфейсов на Phase 0 по [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md))
> **Дата:** 25 июня 2026
>
> Эти ABC замораживаются в **Phase 0** и не меняются по сигнатурам в последующих фазах —
> фазы добавляют только реализации. См. [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md)
> и [DATA_MODELS.md](./DATA_MODELS.md).

Базовые типы берутся из существующего кода:
- `LLMMessage`, `LLMToolCall`, `ToolDefinition` — `codelab.server.agent.*` (как в `base.py`/`context_compactor.py`)
- `AgentContext`, `ContinuationContext` — `codelab.server.agent.base`
- `SessionState` — `codelab.server.protocol.state`

---

## 1. Единая точка входа — `ContextManager`

```python
from abc import ABC, abstractmethod
from codelab.server.agent.context.models import (
    PayloadEnvelope, SubagentResult, BuildOptions,
)

class ContextManager(ABC):
    """Единая точка входа для всех стратегий (Слой-агностик).

    Заменяет HybridContextManager и legacy ContextCompactor.
    Все 4 стратегии (Single/Orchestrated/Choreography/Hierarchical)
    используют этот интерфейс — различие только в наборе вызываемых методов.
    """

    @abstractmethod
    async def build_context(
        self,
        session: "SessionState",
        prompt: list[dict],
        *,
        agent_scope: str = "single",
        system_prompt: str | None = None,
        options: BuildOptions | None = None,
    ) -> PayloadEnvelope:
        """Собрать payload для LLM-вызова.

        Используется ВСЕМИ стратегиями. Возвращает PayloadEnvelope с явным
        разделением baseline (иммутабельный префикс) и tail (дельты).
        Phase 1: baseline пересобирается каждый ход (гидрация).
        Phase 4: baseline кэшируется через ContextEpoch, шлются только дельты.
        """

    @abstractmethod
    async def ensure_context_fits(
        self,
        envelope: PayloadEnvelope,
        *,
        max_context_tokens: int,
        reserved_tokens: int,
    ) -> PayloadEnvelope:
        """Гарантировать, что payload помещается в окно.

        Используется ВСЕМИ стратегиями. Запускает 3-фазное сжатие
        (Prune → Skeletonize → Summarize) при превышении лимита.
        """

    @abstractmethod
    async def process_subagent_response(
        self,
        parent_scope: str,
        subagent_scope: str,
        response: "AgentResponse",
    ) -> SubagentResult:
        """Обработать ответ субагента для родителя.

        Используется ТОЛЬКО мультиагентными стратегиями. По умолчанию —
        суммаризация (изоляция). Федеративный шеринг — опционально, за флагом.
        """
```

---

## 2. Слой A — Сбор контекста

```python
class TaskAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, prompt: str, session: "SessionState") -> "TaskProfile":
        """Классифицировать задачу и извлечь стратегию сбора."""


class ContextGatherer(ABC):
    @abstractmethod
    async def gather(
        self, profile: "TaskProfile", session: "SessionState",
    ) -> list["ContextItem"]:
        """Собрать релевантные файлы через ACP ToolRegistry.

        Пайплайн: project_tree() → search() → read_file() → graph → отбор.
        """


class DependencyGraph(ABC):
    @abstractmethod
    def add_file(self, path: str, imports: list[str]) -> None: ...

    @abstractmethod
    def get_dependencies(self, path: str, *, recursive: bool = False) -> list[str]: ...

    @abstractmethod
    def get_dependents(self, path: str) -> list[str]: ...


class TokenBudgetManager(ABC):
    @abstractmethod
    def allocate(self, total_tokens: int) -> "BudgetAllocation": ...

    @abstractmethod
    def bound_content(self, content: str, max_tokens: int) -> str:
        """Усечь содержимое, сохранив начало и конец."""


class ContextSource(ABC):
    """Источник контекста для ContextRegistry (Registry pattern)."""

    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    async def render(self) -> str:
        """Отрендерить текущее содержимое источника."""

    @abstractmethod
    async def fingerprint(self) -> str:
        """Codec-отпечаток для детекта изменений (НЕ таймстемп)."""


class ContextRegistry(ABC):
    @abstractmethod
    def register(self, source: ContextSource) -> None: ...

    @abstractmethod
    async def render_baseline(self) -> str:
        """Отрендерить все источники (один раз на старте эпохи)."""

    @abstractmethod
    async def render_updates(self, changes: list[str]) -> str:
        """Отрендерить только изменённые источники."""

    @abstractmethod
    async def detect_changes(self) -> list[str]:
        """Вернуть source_id источников, изменившихся с последнего снимка."""
```

---

## 3. Слой B — Жизненный цикл

```python
class ConversationSummarizer(ABC):
    @abstractmethod
    async def summarize(
        self, messages: list["LLMMessage"], *, target_tokens: int,
    ) -> "LLMMessage":
        """Суммаризовать диалог, сохранив ключевые решения и состояние задачи."""


class ContextReconciler(ABC):
    """ContextSnapshot + ContextReconciler (Phase 4)."""

    @abstractmethod
    async def snapshot(self, registry: ContextRegistry) -> "ContextSnapshot": ...

    @abstractmethod
    async def reconcile(
        self, epoch: "ContextEpoch", registry: ContextRegistry,
    ) -> "ReconcileResult":
        """Определить изменения на границе хода и применить как дельты."""
```

> `ContextEpoch`, `ContextSnapshot`, `ReconcileResult` — структуры данных, см. [DATA_MODELS.md](./DATA_MODELS.md).

---

## 4. Слой C — Хранение и эффективность

```python
class TokenCounter(ABC):
    @abstractmethod
    def count(self, text: str) -> int: ...

    @abstractmethod
    def count_messages(self, messages: list["LLMMessage"]) -> int: ...


class CodeSkeletonizer(ABC):
    @abstractmethod
    def can_handle(self, path: str) -> bool:
        """Поддерживается ли язык файла."""

    @abstractmethod
    def skeletonize(self, code: str) -> str:
        """Сжать код до сигнатур. ДЕТЕРМИНИРОВАННО: один вход → один выход
        (требование стабильности baseline для кэш-хита)."""


class FileContentCache(ABC):
    @abstractmethod
    def get(self, path: str) -> str | None: ...

    @abstractmethod
    def set(self, path: str, content: str) -> None: ...

    @abstractmethod
    def invalidate(self, path: str) -> None:
        """Сбросить кэш по пути. ОБЯЗАН публиковать сигнал изменения файла
        в единый источник истины (стык Phase 2 ↔ Phase 4)."""


class ContextCompactor(ABC):
    """3-фазное сжатие: Prune → Skeletonize → Summarize."""

    @abstractmethod
    async def compact_if_needed(
        self,
        messages: list["LLMMessage"],
        *,
        max_context_tokens: int,
        reserved_tokens: int,
    ) -> list["LLMMessage"]:
        """Совместимо по сигнатуре с legacy ContextCompactor.compact_if_needed()
        для бесшовной миграции."""
```

> `SessionFileCacheRegistry` и `FileCacheDecorator` — не ABC, а конкретные компоненты;
> их контракты см. в [CONSOLIDATED_ARCHITECTURE.md §3 (Слой C)](./CONSOLIDATED_ARCHITECTURE.md).

---

## 5. Слой D — Мультиагент

```python
class ChildSessionManager(ABC):
    @abstractmethod
    async def create_child(
        self, parent: "SessionState", subagent_scope: str,
    ) -> "SessionState": ...

    @abstractmethod
    async def collect_summary(self, child: "SessionState") -> SubagentResult: ...
```

> Федеративный `share_item()` НЕ входит в замораживаемые интерфейсы Phase 0 —
> он кандидат на отказ (ADR-002 §«Мультиагент») и появится, если будет включён, в Phase 6.

---

## 6. Правила эволюции интерфейсов

1. **Заморозка в Phase 0.** Сигнатуры методов выше не меняются — фазы добавляют реализации.
2. **`PayloadEnvelope` (baseline/tail) — фундамент.** Любой новый метод сборки возвращает `PayloadEnvelope`, не «плоский» список сообщений.
3. **Совместимость с legacy.** `ContextCompactor.compact_if_needed()` сохраняет сигнатуру текущего `context_compactor.py` для миграции под флагом.
4. **Расширение — через новые ABC/источники**, а не изменение существующих (Open/Closed).

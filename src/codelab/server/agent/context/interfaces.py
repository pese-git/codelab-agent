"""ABC интерфейсы Context Manager.

Замороженные контракты Phase 0 — сигнатуры не меняются в последующих фазах.
Фазы добавляют только реализации.

См. doc/internals/context-manager/INTERFACES.md
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from codelab.server.agent.context.models import (
    BudgetAllocation,
    BuildOptions,
    ContextItem,
    ContextSnapshot,
    PayloadEnvelope,
    ReconcileResult,
    SubagentResult,
    TaskProfile,
)

if TYPE_CHECKING:
    from codelab.server.agent.context.models import ContextEpoch
    from codelab.server.llm.models import LLMMessage


class ContextManager(ABC):
    """Единая точка входа для всех стратегий.

    Заменяет HybridContextManager и legacy ContextCompactor.
    Все 4 стратегии (Single/Orchestrated/Choreography/Hierarchical)
    используют этот интерфейс.
    """

    @abstractmethod
    async def build_context(
        self,
        session: object,
        prompt: list[dict],
        *,
        agent_scope: str = "single",
        system_prompt: str | None = None,
        options: BuildOptions | None = None,
    ) -> PayloadEnvelope:
        """Собрать payload для LLM-вызова.

        Возвращает PayloadEnvelope с явным разделением baseline и tail.
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

        Запускает 3-фазное сжатие при превышении лимита.
        """

    @abstractmethod
    async def process_subagent_response(
        self,
        parent_scope: str,
        subagent_scope: str,
        response: object,
    ) -> SubagentResult:
        """Обработать ответ субагента для родителя.

        По умолчанию — суммаризация (изоляция).
        """


class TaskAnalyzer(ABC):
    """Классификатор задач (Слой A)."""

    @abstractmethod
    async def analyze(self, prompt: str, session: object) -> TaskProfile:
        """Классифицировать задачу и извлечь стратегию сбора."""


class ContextGatherer(ABC):
    """Сборщик релевантных файлов (Слой A)."""

    @abstractmethod
    async def gather(
        self, profile: TaskProfile, session: object,
    ) -> list[ContextItem]:
        """Собрать релевантные файлы через ACP ToolRegistry."""


class DependencyGraph(ABC):
    """Граф зависимостей файлов (Слой A)."""

    @abstractmethod
    def add_file(self, path: str, imports: list[str]) -> None:
        """Добавить файл в граф."""

    @abstractmethod
    def get_dependencies(self, path: str, *, recursive: bool = False) -> list[str]:
        """Получить зависимости файла."""

    @abstractmethod
    def get_dependents(self, path: str) -> list[str]:
        """Получить файлы, зависящие от данного."""


class TokenBudgetManager(ABC):
    """Менеджер бюджета токенов (Слой A)."""

    @abstractmethod
    def allocate(self, total_tokens: int) -> BudgetAllocation:
        """Распределить бюджет токенов по категориям."""

    @abstractmethod
    def bound_content(self, content: str, max_tokens: int) -> str:
        """Усечь содержимое, сохранив начало и конец."""


class ContextSource(ABC):
    """Источник контекста для ContextRegistry."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Уникальный идентификатор источника."""

    @abstractmethod
    async def render(self) -> str:
        """Отрендерить текущее содержимое источника."""

    @abstractmethod
    async def fingerprint(self) -> str:
        """Codec-отпечаток для детекта изменений."""


class ContextRegistry(ABC):
    """Реестр источников контекста."""

    @abstractmethod
    def register(self, source: ContextSource) -> None:
        """Зарегистрировать источник."""

    @abstractmethod
    async def render_baseline(self) -> str:
        """Отрендерить все источники."""

    @abstractmethod
    async def render_updates(self, changes: list[str]) -> str:
        """Отрендерить только изменённые источники."""

    @abstractmethod
    async def detect_changes(self) -> list[str]:
        """Вернуть source_id изменившихся источников."""


class ConversationSummarizer(ABC):
    """Суммаризатор диалога (Слой B)."""

    @abstractmethod
    async def summarize(
        self, messages: list[LLMMessage], *, target_tokens: int,
    ) -> LLMMessage:
        """Суммаризовать диалог, сохранив ключевые решения."""


class ContextReconciler(ABC):
    """Реконсилятор контекста (Слой B)."""

    @abstractmethod
    async def snapshot(self, registry: ContextRegistry) -> ContextSnapshot:
        """Собрать снимок отпечатков всех источников."""

    @abstractmethod
    async def reconcile(
        self, epoch: ContextEpoch, registry: ContextRegistry,
    ) -> ReconcileResult:
        """Определить изменения на границе хода."""


class TokenCounter(ABC):
    """Счётчик токенов (Слой C)."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Подсчитать токены в тексте."""

    @abstractmethod
    def count_messages(self, messages: list[LLMMessage]) -> int:
        """Подсчитать токены в сообщениях."""


class CodeSkeletonizer(ABC):
    """Скелетизатор кода (Слой C)."""

    @abstractmethod
    def can_handle(self, path: str) -> bool:
        """Поддерживается ли язык файла."""

    @abstractmethod
    def skeletonize(self, code: str) -> str:
        """Сжать код до сигнатур. Детерминированно."""


class FileContentCache(ABC):
    """Кэш содержимого файлов (Слой C)."""

    @abstractmethod
    def get(self, path: str) -> str | None:
        """Получить содержимое из кэша."""

    @abstractmethod
    def set(self, path: str, content: str) -> None:
        """Сохранить содержимое в кэш."""

    @abstractmethod
    def invalidate(self, path: str) -> None:
        """Сбросить кэш по пути. Публикует сигнал изменения."""


class ContextCompactor(ABC):
    """3-фазное сжатие: Prune -> Skeletonize -> Summarize (Слой C)."""

    @abstractmethod
    async def compact_if_needed(
        self,
        messages: list[LLMMessage],
        *,
        max_context_tokens: int,
        reserved_tokens: int,
    ) -> list[LLMMessage]:
        """Сжать историю если превышает лимит."""


class ChildSessionManager(ABC):
    """Менеджер дочерних сессий (Слой D)."""

    @abstractmethod
    async def create_child(
        self, parent: object, subagent_scope: str,
    ) -> object:
        """Создать изолированную дочернюю сессию."""

    @abstractmethod
    async def collect_summary(self, child: object) -> SubagentResult:
        """Собрать результат дочерней сессии."""

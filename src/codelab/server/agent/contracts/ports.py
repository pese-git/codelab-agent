"""Hexagon ports ядра агента (change acp-independent-agent-core, ADR-005).

Ядро ``server/agent/core/`` объявляет эти порты как зависимости в
**доменном словаре**. ACP (и любой другой драйвер) реализует их
через адаптеры в ``server/protocol/``.

Phase 1 вводит ``SessionView`` и использует его в core/.
Phase 2 вводит ``ContentCodec``.
Phase 3 вводит ``ToolGateway`` и ``UpdateSink``.
Phase 4 вводит ``AgentRunner`` (driving) и ``ChildSessionFactory``.

ABC интерфейсы из ``agent/context/interfaces.py`` заморожены (Phase 0)
и не дублируются здесь.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codelab.server.domain.conversation import ConversationMessage
    from codelab.server.domain.session import SessionConfig
    from codelab.server.domain.value_objects import SessionId
    from codelab.server.llm.content_parts import ContentPart


@runtime_checkable
class SessionView(Protocol):
    """Read-only порт ядра для данных сессии (ADR-005, Фаза 1).

    Ядро ``core/`` зависит от этого протокола, а НЕ от
    ``protocol.state.SessionState``. Реализация ``SessionStateView``
    живёт в ``server/protocol/session_view.py`` и читает сквозь
    живую ``SessionState`` через ``SessionMapper.to_domain`` —
    turn-loop мутирует ``SessionState`` по ходу turn'а, и
    ``messages()`` обязан видеть свежие данные (не снимок).
    """

    @property
    def id(self) -> SessionId:
        """Идентификатор сессии."""
        ...

    @property
    def config(self) -> SessionConfig:
        """Конфигурация сессии: cwd, config_values, runtime_capabilities.

        ``runtime_capabilities`` — доменный ``ClientCapabilities`` (из
        ``shared.capabilities``), не протокольный ``ClientRuntimeCapabilities``.
        """
        ...

    def messages(self) -> Sequence[ConversationMessage]:
        """История сообщений в доменных VO.

        Возвращает полные ``ConversationMessage`` с прокинутыми
        ``tool_calls`` / ``tool_call_id`` / ``timestamp``
        (sub-task 1.2a change). Чтение живое (не снимок) — см. ADR-003.
        """
        ...


@runtime_checkable
class ContentCodec(Protocol):
    """Порт декодирования входного контента (ADR-005, Фаза 2).

    Ядро декодирует prompt через этот порт. ACP-специфичный
    ``ACPContentCodec`` живёт в ``server/protocol/content/``;
    ``llm.ContentPart`` — канон контента.
    """

    def decode(self, blocks: Sequence[Mapping[str, Any]]) -> list[ContentPart]:
        """Декодировать список content-блоков в ``ContentPart``."""
        ...


@runtime_checkable
class ToolGateway(Protocol):
    """Порт исполнения инструментов (ADR-005, Фаза 3).

    Существующий ``tools.base.ToolRegistry(ABC)`` уже структурно
    совместим с этим протоколом; ``ToolGateway`` — формализация
    зависимости ядра от реестра инструментов.
    """

    def execute_tool(
        self,
        session: SessionView,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Исполнить инструмент и вернуть результат."""
        ...

    def get_available_tools(
        self,
        session: SessionView,
    ) -> list[Any]:
        """Получить инструменты, доступные сессии (после capabilities filter)."""
        ...


@runtime_checkable
class UpdateSink(Protocol):
    """Порт эмиссии прогресса turn'а (ADR-005, Фаза 3).

    Доменные события: текст, план, tool call, tool call update.
    ACP wire-формат строится внутри адаптера.
    """

    async def emit_agent_message(self, session: SessionView, text: str) -> None: ...

    async def emit_streaming_delta(self, session: SessionView, text: str) -> None: ...

    async def emit_plan(self, session: SessionView, plan: Any) -> None: ...

    async def emit_tool_call(self, session: SessionView, call: Any) -> None: ...

    async def emit_tool_update(self, session: SessionView, update: Any) -> None: ...


@runtime_checkable
class AgentRunner(Protocol):
    """Driving-порт для входа в turn ядра (ADR-005, Фаза 4).

    ACP turn-loop (и любой другой драйвер: A2A, тест-харнесс) вызывает
    ``run_turn`` / ``continue_turn`` через этот порт.
    """

    async def run_turn(self, session: SessionView, request: Any) -> Any: ...

    async def continue_turn(self, session: SessionView, request: Any) -> Any: ...


@runtime_checkable
class ChildSessionFactory(Protocol):
    """Порт создания дочерних сессий для мультиагента (ADR-005, Фаза 4)."""

    async def create_child(
        self,
        parent: SessionView,
        subagent_scope: str,
    ) -> SessionView:
        """Создать изолированную child-сессию с parent_session_id."""
        ...

    async def collect_summary(self, child: SessionView) -> Any:
        """Собрать summary результата child-сессии."""
        ...


@runtime_checkable
class LLMPort(Protocol):
    """Порт вызова LLM (ADR-001, формализация в ADR-005).

    ``server.llm.LLMAdapter`` уже структурно совместим.
    """

    async def call(self, request: Any) -> Any:
        """Один вызов LLM с историей сообщений и инструментами."""
        ...


__all__ = [
    "SessionView",
    "ContentCodec",
    "ToolGateway",
    "UpdateSink",
    "AgentRunner",
    "ChildSessionFactory",
    "LLMPort",
]

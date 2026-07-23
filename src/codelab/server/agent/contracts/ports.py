"""Порты ядра агента (hexagonal ports).

Ядро объявляет здесь абстракции в доменном словаре; driving-адаптеры (ACP,
потенциально A2A) и driven-адаптеры реализуют их снаружи. Цель `import-linter` —
ноль рёбер `agent.core -> protocol` (см. ADR-005, ADR-003).

Порты наполняются по мере фаз change `acp-independent-agent-core`:
- Фаза 1: `SessionView`, `ClientCapabilitiesView` (read-поверхность ядра)
- Фаза 2: `ContentCodec`
- Фаза 3: `ToolGateway`, `UpdateSink`
- Фаза 4: `AgentRunner`, `ChildSessionFactory`, `LLMPort`
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from codelab.server.agent.contracts.events import AgentResult
    from codelab.server.llm.content_parts import ContentPart
    from codelab.server.llm.models import LLMMessage
    from codelab.server.observability.tracer import SpanContext
    from codelab.server.tools.base import ToolDefinition, ToolExecutionResult


class ClientCapabilitiesView(Protocol):
    """Read-only возможности клиентского runtime как feature-gate.

    Структурный порт: удовлетворяется и `protocol.state.ClientRuntimeCapabilities`,
    и `shared.capabilities.ClientCapabilities` без конверсии — ядро не зависит от
    конкретной протокольной модели (снимает дубль P2-32 на стороне ядра).
    """

    @property
    def fs_read(self) -> bool: ...
    @property
    def fs_write(self) -> bool: ...
    @property
    def terminal(self) -> bool: ...


class SessionView(Protocol):
    """Read-only проекция сессии для ядра агента (read-фаза ADR-003).

    Сужает поверхность до полей, которые фактически читает ядро при формировании
    turn-а, и убирает зависимость `agent.core -> protocol.state`. Живая сессия
    (`protocol.state.SessionState`) удовлетворяет порт структурно — чтение идёт
    «сквозь» неё (не снимок): дописанная mid-turn история видна сразу.

    `history` — последовательность записей в исходной форме (`HistoryMessage`/dict);
    ядро трактует их duck-typed через `HistoryBuilder`. Доменный content-VO не
    вводится до появления второго драйвера (см. design.md, вне области).
    """

    @property
    def session_id(self) -> str: ...
    @property
    def cwd(self) -> str: ...
    @property
    def config_values(self) -> dict[str, str]: ...
    @property
    def runtime_capabilities(self) -> ClientCapabilitiesView | None: ...
    @property
    def history(self) -> Sequence[Any]: ...


class ContentCodec(Protocol):
    """Декодер контент-блоков драйвера в канонический `llm.ContentPart`.

    Снимает шов №2 (ADR-005): ACP-специфика маппинга `ContentBlock` уезжает из
    ядра в driving-адаптер (`protocol.content.acp_codec.ACPContentCodec`). Ядро
    (`HistoryBuilder`) держит порт; второй драйвер (A2A) подставит свой кодек без
    правки ядра. Канон контента — `llm.ContentPart` (доменный content-VO не
    вводим до второго драйвера, см. design.md).
    """

    def decode(self, blocks: list[dict[str, Any]]) -> list[ContentPart]: ...


class ToolGateway(Protocol):
    """Порт доступа ядра к инструментам (ADR-005, шов №3).

    Сужение существующего `tools.base.ToolRegistry(ABC)` до поверхности, нужной
    ядру: перечисление, конвертация в LLM-формат и выполнение. Живой
    `ToolRegistry` удовлетворяет порт структурно (формализация, не переписывание).
    """

    def get_available_tools(
        self, session_id: str, include_permission_required: bool = True
    ) -> list[ToolDefinition]: ...
    def to_llm_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]: ...
    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
    ) -> ToolExecutionResult: ...


class UpdateSink(Protocol):
    """Порт эмиссии прогресса turn-а в доменных терминах (ADR-005, шов №3).

    Ядро эмитит через этот порт; driving-адаптер (`protocol...updates.SessionUpdateSink`)
    мапит в ACP `session/update` wire и доставляет НЕМЕДЛЕННО (не батчит в конце
    turn'а). Порт умышленно минимален — доменные методы для plan/tool_call/
    tool_update добавит их потребитель (`AgentRunner`, Фаза 4): форму порта диктует
    вызывающая сторона, а не спекуляция (см. design.md, consumer-driven ports).
    """

    async def emit_agent_message(self, session_id: str, text: str) -> None: ...
    async def emit_streaming_delta(self, session_id: str, text: str) -> None: ...


class ChildSessionFactory(Protocol):
    """Порт создания дочерних (субагентских) сессий (ADR-005, Фаза 4).

    Доменная замена `protocol.session_factory.SessionFactory`: ядро
    (`DefaultChildSessionManager`) создаёт child-сессии через порт, не завися от
    протокольной фабрики. ACP-реализация (`SessionFactory`) удовлетворяет порт
    структурно. Результат трактуется duck-typed (`session_id`, `config_values`, …).
    """

    def create_session(self, cwd: str, *, session_id: str | None = None) -> object: ...


class LLMPort(Protocol):
    """Driven-порт вызова LLM (фиксация `LLMAdapter`, граница ADR-001).

    Один вызов провайдера: история + инструменты → `AgentResult`. Tool-calling
    циклом управляет вызывающая сторона (`AgentRunner`/loop), не порт.
    """

    async def call(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        config: dict[str, Any] | None = None,
        parent_span: SpanContext | None = None,
        session_id: str = "",
    ) -> AgentResult: ...


class AgentRunner(Protocol):
    """Driving-порт входа turn-а (ADR-005, Фаза 4).

    Точка входа ядра, не зависящая от драйвера: ACP-адаптер (turn-loop) и
    fake/A2A-драйверы вызывают её одинаково. `run_turn` — начало turn-а (есть
    prompt), `continue_turn` — продолжение после tool_results (prompt уже в истории).
    Возвращает доменный `AgentResult` (обёртку в wire делает driving-адаптер).
    """

    async def run_turn(
        self, session: SessionView, prompt: str, *, system_prompt: str | None = None
    ) -> AgentResult: ...
    async def continue_turn(
        self, session: SessionView, *, system_prompt: str | None = None
    ) -> AgentResult: ...

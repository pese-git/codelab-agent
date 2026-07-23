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
    from codelab.server.llm.content_parts import ContentPart


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

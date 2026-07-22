"""SessionStateView — ACP-адаптер для SessionView.

Реализует driven-порт ``codelab.server.agent.contracts.ports.SessionView``
над живой ``protocol.state.SessionState`` (не над снимком).

Чтение живое: turn-loop мутирует ``SessionState.history`` по ходу
turn'а, и каждый вызов ``messages()`` обязан отражать свежие данные.
Для этого используем ``SessionMapper.to_domain(state)`` на каждом
обращении — стоимость конвертации оправдана отсутствием снимков
(см. ADR-003 read-фаза).

Удаляется вместе с ``pyproject.toml [tool.importlinter] ignore_imports``
строкой ``protocol -> agent`` в Фазе 4 (когда turn-loop станет
driving-адаптером и перестанет импортировать ``agent``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from codelab.server.domain.conversation import ConversationMessage
from codelab.server.domain.session import SessionConfig
from codelab.server.domain.value_objects import SessionId
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.shared.capabilities import ClientCapabilities

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState


class SessionStateView:
    """Read-only адаптер ``SessionView`` поверх живой ``SessionState``.

    Не хранит снимок ``SessionState``: каждое обращение к
    ``messages()``/``config``/``id`` транслирует через
    ``SessionMapper.to_domain`` (кроме ``id``, который неизменный).
    """

    __slots__ = ("_state",)

    def __init__(self, state: SessionState) -> None:
        self._state = state

    @property
    def id(self) -> SessionId:
        return SessionId(self._state.session_id)

    @property
    def config(self) -> SessionConfig:
        """Конфигурация сессии в доменных VO.

        ``runtime_capabilities`` берётся из ``SessionState.runtime_capabilities``
        (Pydantic ``ClientRuntimeCapabilities``) и транслируется в
        доменный ``ClientCapabilities`` из ``shared.capabilities`` —
        единственное представление capabilities, которое видит ядро
        (P2-32 / ADR-005 Фаза 1.6).

        ``parent_session_id`` (ADR-005 Фаза 4) — first-class поле
        SessionState, schema_version 7.
        """
        state = self._state
        runtime_caps: ClientCapabilities | None = None
        if state.runtime_capabilities is not None:
            rc = state.runtime_capabilities
            runtime_caps = ClientCapabilities(
                fs_read=rc.fs_read,
                fs_write=rc.fs_write,
                terminal=rc.terminal,
            )

        return SessionConfig(
            cwd=state.cwd,
            config_values=dict(state.config_values),
            active_strategy=state.active_strategy,
            runtime_capabilities=runtime_caps,
            parent_session_id=state.parent_session_id,
        )

    def messages(self) -> Sequence[ConversationMessage]:
        """История сообщений — живое чтение через ``SessionMapper``.

        Round-trip ``tool_calls``/``tool_call_id``/``timestamp``
        обеспечен sub-task 1.2a change acp-independent-agent-core.
        """
        session = SessionMapper.to_domain(self._state)
        return session.history.get_messages()

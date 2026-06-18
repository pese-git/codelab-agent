"""Контекст для обработки session/update.

ChatUpdateContext содержит всё необходимое для handler'а:
- session_id: ID текущей сессии
- state: ChatSessionState (может модифицироваться)
- sink: ChatUpdateSink для синхронизации с UI
- services: дополнительные сервисы (plan_vm, event_bus, logger)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from codelab.client.infrastructure.events.bus import EventBus
    from codelab.client.presentation.chat.chat_session_state import ChatSessionState
    from codelab.client.presentation.chat.contracts import ChatUpdateSink
    from codelab.client.presentation.plan_view_model import PlanViewModel


@dataclass
class ChatUpdateContext:
    """Контекст для обработки session/update.

    Содержит всё необходимое для handler'а:
    - session_id: ID текущей сессии
    - state: ChatSessionState (может модифицироваться handler'ом)
    - sink: ChatUpdateSink для синхронизации Observable с UI
    - plan_vm: PlanViewModel для обработки plan updates (опционально)
    - event_bus: EventBus для публикации событий (опционально)
    - logger: Logger для логирования (опционально)

    Context создаётся один раз dispatcher'ом и передаётся handler'ам.
    Handler'ы могут модифицировать state, но не должны изменять session_id или sink.
    """

    session_id: str
    """ID текущей сессии. Не должен изменяться handler'ами."""

    state: ChatSessionState
    """Состояние чата. Handler'ы могут модифицировать это поле."""

    sink: ChatUpdateSink
    """Sink для синхронизации Observable с UI. Не должен изменяться."""

    plan_vm: PlanViewModel | None = None
    """PlanViewModel для обработки plan updates. Опционально."""

    event_bus: EventBus | None = None
    """EventBus для публикации событий. Опционально."""

    _logger: Any = field(default=None, repr=False)
    """Logger для логирования. Создаётся автоматически если не предоставлен."""

    @property
    def logger(self) -> Any:
        """Возвращает logger, создавая его при необходимости."""
        if self._logger is None:
            self._logger = structlog.get_logger("chat_update_context")
        return self._logger

    def create_child(
        self,
        *,
        session_id: str | None = None,
        state: ChatSessionState | None = None,
    ) -> ChatUpdateContext:
        """Создаёт дочерний контекст с переопределёнными полями.

        Полезно для обработки обновлений для другой сессии
        или с другим состоянием.

        Args:
            session_id: Новый session_id (если None, используется текущий)
            state: Новое состояние (если None, используется текущее)

        Returns:
            Новый ChatUpdateContext с переопределёнными полями
        """
        return ChatUpdateContext(
            session_id=session_id or self.session_id,
            state=state or self.state,
            sink=self.sink,
            plan_vm=self.plan_vm,
            event_bus=self.event_bus,
            _logger=self._logger,
        )

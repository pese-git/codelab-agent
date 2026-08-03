"""Стадия управления жизненным циклом turn."""

from __future__ import annotations

from codelab.server.domain.session import Session as DomainSession
from codelab.server.protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager

from ..base import PromptStage
from ..context import PromptContext


class TurnLifecycleStage(PromptStage):
    """Управление началом и завершением turn, обновление events_history."""

    def __init__(
        self,
        turn_manager: TurnLifecycleManager,
        action: str = "close",  # "open" или "close"
    ) -> None:
        self._turn_manager = turn_manager
        self._action = action

    async def process(self, context: PromptContext) -> PromptContext:
        if self._action == "open":
            # Открытие turn'а — команда: `active_turn` на диске нужен всем, кто
            # придёт по ходу turn'а отдельным запросом (ответ на разрешение,
            # ответ клиента, отмена).
            await context.commands.apply(
                lambda session: setattr(
                    session,
                    "active_turn",
                    self._turn_manager.create_active_turn(
                        context.session_id,
                        context.request_id,
                    ),
                ),
                name="turn_opened",
            )
        elif self._action == "close":

            def _close(session: DomainSession) -> None:
                self._turn_manager.finalize_turn(session, context.stop_reason)
                self._turn_manager.clear_active_turn(session)

            await context.commands.apply(_close, name="turn_closed")

        return context

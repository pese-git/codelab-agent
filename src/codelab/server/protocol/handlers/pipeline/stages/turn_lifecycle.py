"""Стадия управления жизненным циклом turn."""

from __future__ import annotations

from codelab.server.domain.session import Session as DomainSession
from codelab.server.protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager
from codelab.server.protocol.turn_runtime import TurnEndCause, finish_turn
from codelab.server.protocol.turn_terminals import TurnTerminalReleaser

from ..base import PromptStage
from ..context import PromptContext


class TurnLifecycleStage(PromptStage):
    """Управление началом и завершением turn, обновление events_history."""

    def __init__(
        self,
        turn_manager: TurnLifecycleManager,
        action: str = "close",  # "open" или "close"
        terminal_releaser: TurnTerminalReleaser | None = None,
    ) -> None:
        self._turn_manager = turn_manager
        self._action = action
        self._terminal_releaser = terminal_releaser

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
                # `finalize_turn` только нормализует и логирует причину; снятие
                # turn'а принадлежит шву (ADR-008, шаг 5). Ответ здесь не строится:
                # его отправляет транспорт своим путём, как и прежде.
                self._turn_manager.finalize_turn(session, context.stop_reason)
                finish_turn(session, cause=TurnEndCause.PIPELINE_CLOSED)

            await context.commands.apply(_close, name="turn_closed")

            # Освобождение остатка — **после** команды и здесь же, а не только в
            # отложенной задаче завершения: turn, дошедший до конца внутри пайплайна,
            # снимается тут, `session/prompt` отдаёт ответ сразу, и отложенной задачи
            # не возникает вовсе (`transport/stdio.py`: она создаётся при пустом
            # ответе). `BackgroundExecutor.complete_active_turn` в этом случае выходит
            # первой же строкой — `active_turn` уже снят, — и остаток утекал у
            # клиента до смерти процесса.
            #
            # Измерено живьём (`sess_8fa73fe08f55`, 2026-08-13): `cause=pipeline_closed`
            # при `live=2` и нуле освобождений. Приёмка шага 5.3 (`released=15`)
            # оказалась снята на подмножестве путей — там каждый turn проходил через
            # возобновление после разрешения.
            #
            # Шов законен по тому же основанию, что и остальные два: стадия
            # исполняется внутри фоновой задачи `session/prompt`, где клиентский RPC
            # не взаимоблокирует stdio.
            if self._terminal_releaser is not None:
                await self._terminal_releaser.release_turn_remainder(
                    context.session, cause=TurnEndCause.PIPELINE_CLOSED.value
                )

        return context

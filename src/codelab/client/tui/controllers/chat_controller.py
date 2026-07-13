"""Контроллер отправки и отмены prompt-turn в TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codelab.client.presentation.chat_view_model import ChatViewModel
    from codelab.client.presentation.session_view_model import SessionViewModel

    from ..app import ACPClientApp


class ChatController:
    """Отправка промпта и отмена текущего LLM-запроса."""

    def __init__(
        self,
        app: ACPClientApp,
        session_vm: SessionViewModel,
        chat_vm: ChatViewModel,
        logger: Any,
    ) -> None:
        self._app = app
        self._session_vm = session_vm
        self._chat_vm = chat_vm
        self._logger = logger

    def submit_prompt(self, text: str) -> None:
        """Отправляет промпт в активную сессию."""
        session_id = self._session_vm.selected_session_id.value
        if not session_id:
            self._logger.warning("prompt_submitted_without_active_session")
            return

        self._logger.info("prompt_submitted", session_id=session_id, prompt_length=len(text))

        self._chat_vm.add_message("user", text, session_id=session_id)
        # Состояние загрузки до запуска worker'а — чтобы индикатор показался сразу.
        self._chat_vm.is_streaming.value = True
        self._app.run_worker(
            self._chat_vm.send_prompt_cmd.execute(session_id, text),
            exclusive=False,
        )
        self._app.show_toast("Запрос отправлен", level="info")

    def cancel_prompt(self) -> None:
        """Отменяет текущий LLM-запрос активной сессии (Ctrl+C / Stop)."""
        session_id = self._session_vm.selected_session_id.value
        is_streaming = self._chat_vm.is_streaming.value
        is_executing = self._chat_vm.cancel_prompt_cmd.is_executing.value
        self._logger.info(
            "action_cancel_prompt_called",
            session_id=session_id,
            is_streaming=is_streaming,
            is_executing=is_executing,
        )
        if not session_id:
            self._logger.warning("cancel_prompt_no_active_session")
            return
        if not is_streaming:
            self._logger.debug("cancel_prompt_skipped_not_streaming")
            return
        if is_executing:
            self._logger.debug("cancel_prompt_skipped_already_executing")
            return
        self._logger.info("cancel_prompt_dispatching", session_id=session_id)
        self._app.run_worker(
            self._chat_vm.cancel_prompt_cmd.execute(session_id),
            exclusive=False,
        )

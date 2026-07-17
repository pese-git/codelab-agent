"""Контроллер жизненного цикла сессий в TUI: создание/переключение/загрузка."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..components import Sidebar

if TYPE_CHECKING:
    from codelab.client.application.session_coordinator import SessionCoordinator
    from codelab.client.presentation.chat_view_model import ChatViewModel
    from codelab.client.presentation.session_view_model import SessionViewModel

    from ..app import ACPClientApp


class SessionController:
    """Создание, переключение и загрузка истории сессий."""

    def __init__(
        self,
        app: ACPClientApp,
        session_vm: SessionViewModel,
        chat_vm: ChatViewModel,
        coordinator: SessionCoordinator,
        logger: Any,
        *,
        host: str,
        port: int,
        cwd: str,
        mcp_servers: list[dict[str, Any]],
    ) -> None:
        self._app = app
        self._session_vm = session_vm
        self._chat_vm = chat_vm
        self._coordinator = coordinator
        self._logger = logger
        self._host = host
        self._port = port
        self._cwd = cwd
        self._mcp_servers = mcp_servers
        # Предотвращает параллельные session/load, перемешивающие session/update.
        self._history_load_lock = asyncio.Lock()

    def create_session(self) -> None:
        """Создаёт новую сессию с client_capabilities TUI-клиента."""
        self._logger.info("new_session_requested", cwd=self._cwd)
        client_capabilities = {"fs_read": True, "fs_write": True, "terminal": True}
        self._app.run_worker(
            self._session_vm.create_session_cmd.execute(
                self._host,
                self._port,
                cwd=self._cwd,
                mcp_servers=self._mcp_servers,
                client_capabilities=client_capabilities,
            ),
            exclusive=False,
        )

    def select_relative(self, *, reverse: bool) -> None:
        """Выбирает соседнюю сессию в sidebar и применяет выбор."""
        sidebar = self._app.query_one(Sidebar)
        if reverse:
            sidebar.select_previous()
        else:
            sidebar.select_next()
        selected_session_id = sidebar.get_selected_session_id()
        if selected_session_id is None:
            return
        self.switch_to(selected_session_id)

    def switch_to(self, session_id: str) -> None:
        """Применяет выбор сессии."""
        self._app.run_worker(
            self._session_vm.switch_session_cmd.execute(session_id),
            exclusive=False,
        )

    def on_selected_session_changed(self, session_id: str | None) -> None:
        """Обновляет ChatView и грузит историю при смене активной сессии."""
        self._chat_vm.set_active_session(session_id)
        if session_id is None:
            return
        self._app.run_worker(self._load_history(session_id), exclusive=False)

    async def _load_history(self, session_id: str) -> None:
        """Загружает историю выбранной сессии через session/load."""
        async with self._history_load_lock:
            try:
                loaded = await self._coordinator.load_session(
                    session_id,
                    self._host,
                    self._port,
                    cwd=self._cwd,
                    mcp_servers=self._mcp_servers,
                )
                replay_updates = loaded.get("replay_updates", [])
                if isinstance(replay_updates, list):
                    self._chat_vm.restore_session_from_replay(session_id, replay_updates)

                self._logger.info(
                    "session_history_loaded",
                    session_id=session_id,
                    replay_updates_count=(
                        len(replay_updates) if isinstance(replay_updates, list) else 0
                    ),
                )
            except Exception as error:
                self._logger.warning(
                    "session_history_load_failed",
                    session_id=session_id,
                    error=str(error),
                )

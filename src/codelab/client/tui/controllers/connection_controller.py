"""Контроллер инициализации подключения к серверу ACP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from codelab.client.infrastructure.services.acp_transport_service import ACPTransportService
from codelab.client.presentation.ui_view_model import ConnectionStatus

if TYPE_CHECKING:
    from codelab.client.application.session_coordinator import SessionCoordinator
    from codelab.client.domain.services import TransportService
    from codelab.client.presentation.session_view_model import SessionViewModel
    from codelab.client.presentation.ui_view_model import UIViewModel

    from ..app import ACPClientApp


class ConnectionController:
    """Устанавливает соединение, регистрирует permission-callback и грузит сессии."""

    def __init__(
        self,
        app: ACPClientApp,
        coordinator: SessionCoordinator,
        transport: TransportService,
        ui_vm: UIViewModel,
        session_vm: SessionViewModel,
        logger: Any,
        host: str,
        port: int,
    ) -> None:
        self._app = app
        self._coordinator = coordinator
        self._transport = transport
        self._ui_vm = ui_vm
        self._session_vm = session_vm
        self._logger = logger
        self._host = host
        self._port = port

    async def initialize(self) -> None:
        """Инициализирует подключение к серверу и загружает список сессий."""
        self._logger.info("connection_worker_started")
        self._ui_vm.set_connection_status(ConnectionStatus.CONNECTING)
        self._ui_vm.set_loading(True, "connecting to server")
        try:
            self._logger.info("initializing_server_connection")
            server_info = await self._coordinator.initialize()

            self._logger.info(
                "server_connection_initialized",
                protocol_version=server_info.get("protocol_version"),
                auth_methods=len(server_info.get("available_auth_methods", [])),
            )

            self._ui_vm.set_connection_status(ConnectionStatus.CONNECTED)
            self._ui_vm.set_loading(False)
            self._app.show_toast("Подключено к серверу", level="success")

            # Callback для показа permission modal при session/request_permission.
            try:
                cast(ACPTransportService, self._transport).set_permission_callback(
                    self._app.show_permission_modal
                )
                self._logger.info("permission_callback_registered_in_transport")
            except Exception as e:
                self._logger.warning("failed_to_set_permission_callback", error=str(e))

            # Запрашиваем список сессий, чтобы sidebar показал их сразу.
            await self._session_vm.load_sessions_cmd.execute()
            loaded_count = self._session_vm.session_count.value
            self._logger.info(
                "sessions_loaded_on_startup",
                count=loaded_count,
                host=self._host,
                port=self._port,
            )
            if loaded_count == 0:
                self._logger.warning(
                    "session_list_is_empty_on_startup",
                    hint="Проверьте, что сервер запущен с persistent --storage json:<path>",
                )

        except Exception as e:
            self._logger.error("failed_to_initialize_connection", error=str(e), exc_info=True)
            self._ui_vm.set_connection_status(ConnectionStatus.DISCONNECTED)
            self._ui_vm.set_loading(False)
            self._app.show_toast(f"Ошибка подключения: {e}", level="error")

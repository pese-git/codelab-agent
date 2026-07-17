"""HTTP-сервер ACP с WebSocket транспортом.

Модуль поднимает endpoint `GET /acp/ws` для двустороннего потока с
`session/update` и server->client RPC.

Архитектура:
- ACPHttpServer — HTTP-сервер (aiohttp), маршрутизация
- WebSocketTransport — обработка WebSocket соединения (вынесено в transport/)
- WebUIManager — управление Web UI subprocess (вынесено в web_ui.py)

Пример использования:
    server = ACPHttpServer(host="127.0.0.1", port=8080)
    await server.run()
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from aiohttp import web
from dishka import AsyncContainer

from codelab.shared.web_ui import WebUIManager

from .config import AppConfig
from .di import ObservabilityFlushManager, make_container
from .storage import SessionStorage
from .transport.websocket import WebSocketTransport
from .transport.websocket_connection import AiohttpWebSocketConnection

# Получаем структурированный logger
logger = structlog.get_logger()


class ACPHttpServer:
    """HTTP-сервер ACP с WebSocket транспортом.

    Принимает HTTP-соединения, маршрутизирует WebSocket на /acp/ws,
    опционально обслуживает Web UI на /.

    Обработка WebSocket делегируется WebSocketTransport.
    Управление Web UI делегируется WebUIManager.

    Пример использования:
        server = ACPHttpServer(port=8080)
        await server.run()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        *,
        require_auth: bool = False,
        auth_api_key: str | None = None,
        storage: SessionStorage | None = None,
        config: AppConfig | None = None,
        enable_web: bool = True,
        trace_messages: bool = False,
        observability_debug: bool = False,
    ) -> None:
        """Создает транспортный сервер с адресом прослушивания.

        Args:
            host: IP адрес для прослушивания (по умолчанию 127.0.0.1).
            port: Порт для прослушивания (по умолчанию 8080).
            require_auth: Требовать аутентификацию перед session/new и session/load.
            auth_api_key: API ключ для аутентификации.
            storage: Backend для хранения сессий (по умолчанию InMemoryStorage).
            config: Глобальная конфигурация приложения (LLM, агент и т.д.).
            enable_web: Включить Web UI на корневом пути "/" (по умолчанию True).
            trace_messages: Включить детальное логирование всех JSON-RPC сообщений.
            observability_debug: Включить debug mode для observability.

        Пример использования:
            ACPHttpServer(host="0.0.0.0", port=8080)
        """

        self.host = host
        self.port = port
        self.require_auth = require_auth
        self.auth_api_key = auth_api_key
        self.storage = storage
        self.config = config or AppConfig()
        self.enable_web = enable_web
        self.trace_messages = trace_messages
        self.observability_debug = observability_debug
        # DI контейнер приложения
        self._app_container: AsyncContainer | None = None
        # Web UI менеджер
        self._web_ui_manager: WebUIManager | None = None

        # Логируем инициализацию сервера
        logger.debug(
            "acp http server initialized",
            host=host,
            port=port,
            require_auth=require_auth,
            has_auth_key=bool(auth_api_key),
            enable_web=enable_web,
            trace_messages=trace_messages,
        )

    async def run(self) -> None:
        """Запускает WS endpoint и держит процесс живым.

        Инициализирует DI контейнер и поднимает WS endpoint.

        Пример использования:
            await ACPHttpServer().run()
        """
        if self.storage is None:
            from .storage import InMemoryStorage

            self.storage = InMemoryStorage()

        logger.debug(
            "creating DI container",
            llm_provider=self.config.llm.provider,
            storage_type=type(self.storage).__name__,
        )

        self._app_container = make_container(
            config=self.config,
            storage=self.storage,
            require_auth=self.require_auth,
            auth_api_key=self.auth_api_key,
            trace_messages=self.trace_messages,
            observability_debug=self.observability_debug,
        )

        # Запуск background services (observability flush)
        await self._app_container.get(ObservabilityFlushManager)

        # Инициализация Web UI менеджера
        if self.enable_web:
            self._web_ui_manager = WebUIManager(self.host, self.port)
            web_ui_started = self._web_ui_manager.start_subprocess()
            if web_ui_started and self._web_ui_manager.web_ui_url:
                logger.info(
                    "web ui enabled with textual-web",
                    main_url=f"http://{self.host}:{self.port}/",
                    web_ui_url=self._web_ui_manager.web_ui_url,
                )
            else:
                logger.info(
                    "web ui enabled (fallback mode)",
                    url=f"http://{self.host}:{self.port}/",
                )

        app = web.Application()
        app.router.add_get("/acp/ws", self.handle_ws_request)

        if self.enable_web:
            app.router.add_get("/", self.handle_web_ui_request)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=self.host, port=self.port)
        await site.start()

        logger.info(
            "server started",
            host=self.host,
            port=self.port,
            endpoint="/acp/ws",
        )

        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            if self._web_ui_manager:
                self._web_ui_manager.stop_subprocess()
            logger.info("server shutting down")
            await runner.cleanup()
            if self._app_container is not None:
                await self._app_container.close()

    async def handle_web_ui_request(self, request: web.Request) -> web.Response:
        """Обрабатывает запрос на Web UI.

        Делегирует обработку WebUIManager.

        Пример использования:
            # вызывается aiohttp автоматически на GET /
        """
        if self._web_ui_manager is None:
            return web.Response(text="Web UI not enabled", status=404)
        return self._web_ui_manager.get_response()

    async def handle_ws_request(self, request: web.Request) -> web.WebSocketResponse:
        """Обрабатывает WebSocket-сессию с поддержкой update-потока.

        Делегирует обработку WebSocketTransport.

        Пример использования:
            # вызывается aiohttp автоматически на GET /acp/ws
        """
        connection_id = str(uuid.uuid4())[:8]
        remote_addr = request.remote or "unknown"

        logger.info(
            "ws connection request received",
            connection_id=connection_id,
            remote_addr=remote_addr,
        )

        ws = web.WebSocketResponse(
            max_msg_size=self.config.websocket.max_msg_size,
            heartbeat=self.config.websocket.heartbeat_interval,
        )
        await ws.prepare(request)

        if self._app_container is None:
            await ws.close(code=1011, message=b"Server not initialized")
            return ws

        # Создаём WebSocketTransport и делегируем обработку
        connection = AiohttpWebSocketConnection(ws)
        transport = WebSocketTransport(
            connection=connection,
            app_container=self._app_container,
            config=self.config,
            connection_id=connection_id,
            remote_addr=remote_addr,
        )

        await transport.run()

        return ws

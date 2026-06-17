"""Тесты для непокрытых веток run_stdio_server.

Покрывают send_rpc_request callback, callbacks интеграции protocol
и загрузку pending prompt response.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.protocol.state import SessionState

_MAKE_CONTAINER_PATH = "codelab.server.transport.stdio_runner.make_container"
_CLIENT_RPC_SERVICE_PATH = "codelab.server.client_rpc.service.ClientRPCService"
_STDIO_TRANSPORT_PATH = "codelab.server.transport.stdio_runner.StdioServerTransport"
_LOGGER_PATH = "codelab.server.transport.stdio_runner.logger"


def _make_mock_container(
    *,
    request_scope_get_return: object | None = None,
    get_side_effect: object | None = None,
) -> MagicMock:
    """Создаёт mock DI-контейнера."""
    mock_container = MagicMock()
    mock_container.get = AsyncMock()
    mock_container.close = AsyncMock()

    mock_request_scope = MagicMock()
    if request_scope_get_return is not None:
        mock_request_scope.get = AsyncMock(return_value=request_scope_get_return)
    else:
        mock_request_scope.get = AsyncMock(return_value=AsyncMock())

    mock_request_scope.__aenter__ = AsyncMock(return_value=mock_request_scope)
    mock_request_scope.__aexit__ = AsyncMock(return_value=False)

    mock_container.return_value = mock_request_scope

    if get_side_effect is not None:
        mock_container.get = get_side_effect

    return mock_container


async def _run_stdio_server(
    *,
    container: MagicMock,
    transport_mock: MagicMock,
) -> None:
    """Запускает run_stdio_server с заданными моками."""
    from codelab.server.transport.stdio_runner import run_stdio_server

    with (
        patch(_MAKE_CONTAINER_PATH, return_value=container),
        patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        patch(_STDIO_TRANSPORT_PATH, return_value=transport_mock),
    ):
        mock_rpc_service = AsyncMock()
        mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
        mock_rpc_cls.return_value = mock_rpc_service

        await run_stdio_server(
            storage=MagicMock(),
            config=MagicMock(),
        )


class TestStdioRunnerSendRpcCallback:
    """Тесты send_rpc_request callback."""

    @pytest.mark.asyncio
    async def test_send_rpc_request_uses_transport_send(self) -> None:
        """send_rpc_request callback отправляет сообщение через transport.send."""
        container = _make_mock_container()
        transport_mock = MagicMock()
        transport_mock.send = AsyncMock()

        captured_callback = None

        def capture_rpc_service(*args, **kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("send_request_callback") or args[0]
            mock_service = AsyncMock()
            mock_service.cancel_all_pending_requests = MagicMock(return_value=0)
            return mock_service

        from codelab.server.transport.stdio_runner import run_stdio_server

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=container),
            patch(_CLIENT_RPC_SERVICE_PATH, side_effect=capture_rpc_service),
            patch(_STDIO_TRANSPORT_PATH, return_value=transport_mock),
        ):
            await run_stdio_server(storage=MagicMock(), config=MagicMock())

        assert captured_callback is not None
        await captured_callback({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "test",
            "params": {},
        })

        transport_mock.send.assert_awaited_once()


class TestStdioRunnerProtocolCallbacks:
    """Тесты callback'ов интеграции с protocol."""

    @pytest.fixture
    async def _setup(
        self,
    ) -> tuple[MagicMock, MagicMock, dict[str, object]]:
        """Создаёт моки и запускает сервер, возвращая callback'и."""
        protocol = AsyncMock()
        protocol._storage = MagicMock()

        holder = MagicMock()
        holder.service = None

        async def fake_get(cls):
            if hasattr(cls, "__name__") and cls.__name__ == "ClientRPCServiceHolder":
                return holder
            if hasattr(cls, "__name__") and cls.__name__ == "ObservabilityFlushManager":
                return AsyncMock()
            return protocol

        container = _make_mock_container(
            request_scope_get_return=protocol,
            get_side_effect=fake_get,
        )

        captured_callbacks = {}

        def capture_transport(**callbacks):
            captured_callbacks.update(callbacks)
            mock_t = AsyncMock()
            mock_t.send = AsyncMock()

            async def fake_run(*, on_message):
                return None

            mock_t.run = fake_run
            return mock_t

        from codelab.server.transport.stdio_runner import run_stdio_server

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
            patch(_STDIO_TRANSPORT_PATH, side_effect=capture_transport),
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            run_task = asyncio.create_task(
                run_stdio_server(storage=MagicMock(), config=MagicMock())
            )
            await asyncio.sleep(0.05)
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

        return protocol, container, captured_callbacks

    @pytest.mark.asyncio
    async def test_should_auto_complete_callback(self, _setup) -> None:
        """should_auto_complete callback делегирует вызов protocol."""
        protocol, _, callbacks = _setup

        await callbacks["should_auto_complete"]("sess_1")

        protocol.should_auto_complete_active_turn.assert_awaited_once_with("sess_1")

    @pytest.mark.asyncio
    async def test_complete_active_turn_callback(self, _setup) -> None:
        """complete_active_turn callback делегирует вызов protocol."""
        protocol, _, callbacks = _setup

        await callbacks["complete_active_turn"]("sess_1", "end_turn")

        protocol.complete_active_turn.assert_awaited_once_with(
            "sess_1", stop_reason="end_turn"
        )


class TestStdioRunnerLoadPendingPromptResponse:
    """Тесты _load_pending_prompt_response callback."""

    @pytest.fixture
    async def _setup(
        self,
    ) -> tuple[MagicMock, MagicMock, dict[str, object]]:
        """Создаёт моки и возвращает callback."""
        protocol = AsyncMock()
        storage = AsyncMock()
        protocol._storage = storage

        holder = MagicMock()
        holder.service = None

        async def fake_get(cls):
            if hasattr(cls, "__name__") and cls.__name__ == "ClientRPCServiceHolder":
                return holder
            if hasattr(cls, "__name__") and cls.__name__ == "ObservabilityFlushManager":
                return AsyncMock()
            return protocol

        container = _make_mock_container(
            request_scope_get_return=protocol,
            get_side_effect=fake_get,
        )

        captured_callbacks = {}

        def capture_transport(**callbacks):
            captured_callbacks.update(callbacks)
            mock_t = AsyncMock()
            mock_t.send = AsyncMock()

            async def fake_run(*, on_message):
                return None

            mock_t.run = fake_run
            return mock_t

        from codelab.server.transport.stdio_runner import run_stdio_server

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
            patch(_STDIO_TRANSPORT_PATH, side_effect=capture_transport),
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            run_task = asyncio.create_task(
                run_stdio_server(storage=MagicMock(), config=MagicMock())
            )
            await asyncio.sleep(0.05)
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

        return protocol, storage, captured_callbacks

    @pytest.mark.asyncio
    async def test_load_pending_prompt_response_success(self, _setup) -> None:
        """Callback корректно строит response из pending_prompt_response."""
        _, storage, callbacks = _setup

        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            pending_prompt_response={
                "request_id": "req_1",
                "stop_reason": "cancelled",
            },
        )
        storage.load_session = AsyncMock(return_value=session)
        storage.save_session = AsyncMock()

        result = await callbacks["load_pending_prompt_response"]("sess_1")

        assert result is not None
        assert result.id == "req_1"
        assert result.result["stopReason"] == "cancelled"
        assert session.pending_prompt_response is None
        storage.save_session.assert_awaited_once_with(session)

    @pytest.mark.asyncio
    async def test_load_pending_prompt_response_load_error(self, _setup) -> None:
        """Ошибка загрузки сессии возвращает None."""
        _, storage, callbacks = _setup

        storage.load_session = AsyncMock(side_effect=RuntimeError("storage down"))

        result = await callbacks["load_pending_prompt_response"]("sess_1")

        assert result is None

    @pytest.mark.asyncio
    async def test_load_pending_prompt_response_save_error(
        self,
        _setup,
    ) -> None:
        """Ошибка сохранения сессии не мешает вернуть response."""
        _, storage, callbacks = _setup

        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            pending_prompt_response={
                "request_id": "req_1",
                "stop_reason": "end_turn",
            },
        )
        storage.load_session = AsyncMock(return_value=session)
        storage.save_session = AsyncMock(side_effect=RuntimeError("save failed"))

        with patch(_LOGGER_PATH) as mock_logger:
            result = await callbacks["load_pending_prompt_response"]("sess_1")

        assert result is not None
        assert result.result["stopReason"] == "end_turn"
        mock_logger.debug.assert_called()
        assert "save error" in str(mock_logger.debug.call_args_list)

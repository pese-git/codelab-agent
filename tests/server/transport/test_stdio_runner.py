"""Тесты для run_stdio_server().

Покрывают инициализацию, жизненный цикл transport, graceful shutdown
и интеграцию с mock transport.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import ProtocolOutcome

# Пути для patch (ClientRPCService импортируется внутри функции)
_CLIENT_RPC_SERVICE_PATH = "codelab.server.client_rpc.service.ClientRPCService"
_STDIO_TRANSPORT_PATH = "codelab.server.transport.stdio_runner.StdioServerTransport"
_MAKE_CONTAINER_PATH = "codelab.server.transport.stdio_runner.make_container"
_LOGGER_PATH = "codelab.server.transport.stdio_runner.logger"


def _make_mock_container(
    *,
    request_scope_get_return: object | None = None,
    get_side_effect: object | None = None,
) -> MagicMock:
    """Создаёт mock контейнера с корректной поддержкой async context manager."""
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


def _make_default_transport_mock(
    *,
    run_side_effect: object | None = None,
) -> AsyncMock:
    """Создаёт стандартный mock для StdioServerTransport."""
    mock_transport = AsyncMock()

    async def default_run(**kwargs):
        return None

    mock_transport.run = run_side_effect or default_run
    mock_transport.send = AsyncMock()
    return mock_transport


async def _run_with_mocks(
    storage,
    config,
    mock_container,
    *,
    require_auth: bool = False,
    auth_api_key: str | None = None,
    transport_mock: object | None = None,
    transport_side_effect: object | None = None,
) -> None:
    """Запускает run_stdio_server с настроенными моками."""
    from codelab.server.transport.stdio_runner import run_stdio_server

    if transport_mock is not None:
        with patch(_STDIO_TRANSPORT_PATH, return_value=transport_mock):
            await run_stdio_server(
                storage=storage,
                config=config,
                require_auth=require_auth,
                auth_api_key=auth_api_key,
            )
    elif transport_side_effect is not None:
        with patch(_STDIO_TRANSPORT_PATH, side_effect=transport_side_effect):
            await run_stdio_server(
                storage=storage,
                config=config,
                require_auth=require_auth,
                auth_api_key=auth_api_key,
            )
    else:
        mock_transport = _make_default_transport_mock()
        with patch(_STDIO_TRANSPORT_PATH, return_value=mock_transport):
            await run_stdio_server(
                storage=storage,
                config=config,
                require_auth=require_auth,
                auth_api_key=auth_api_key,
            )


class TestRunStdioServerInit:
    """Тесты инициализации run_stdio_server."""

    @pytest.mark.asyncio
    async def test_creates_container_with_correct_args(self) -> None:
        """make_container вызывается с переданными аргументами."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"
        mock_container = _make_mock_container()

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container) as mock_make,
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service
            mock_transport = _make_default_transport_mock()

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            mock_make.assert_called_once()
            call_kwargs = mock_make.call_args[1]
            assert call_kwargs["config"] is mock_config
            assert call_kwargs["storage"] is mock_storage
            assert call_kwargs["require_auth"] is False
            assert call_kwargs["trace_messages"] is False

    @pytest.mark.asyncio
    async def test_container_gets_observability_flush_manager(self) -> None:
        """ObservabilityFlushManager запускается через container.get()."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"
        mock_flush_mgr = AsyncMock()

        get_calls = []

        async def fake_get(cls):
            get_calls.append(cls)
            if hasattr(cls, "__name__") and cls.__name__ == "ObservabilityFlushManager":
                return mock_flush_mgr
            if hasattr(cls, "__name__") and cls.__name__ == "ClientRPCServiceHolder":
                holder = MagicMock()
                holder.service = None
                return holder
            return AsyncMock()

        mock_container = _make_mock_container(get_side_effect=fake_get)
        mock_transport = _make_default_transport_mock()

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            assert any(
                hasattr(c, "__name__") and c.__name__ == "ObservabilityFlushManager"
                for c in get_calls
            )

    @pytest.mark.asyncio
    async def test_client_rpc_service_created_with_correct_capabilities(self) -> None:
        """ClientRPCService создаётся с ожидаемыми capabilities."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"
        mock_container = _make_mock_container()

        captured_send_callback = None
        captured_capabilities = None

        def capture_rpc_service(send_request_callback, client_capabilities, **kwargs):
            nonlocal captured_send_callback, captured_capabilities
            captured_send_callback = send_request_callback
            captured_capabilities = client_capabilities
            mock_service = AsyncMock()
            mock_service.cancel_all_pending_requests = MagicMock(return_value=0)
            return mock_service

        mock_transport = _make_default_transport_mock()

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH, side_effect=capture_rpc_service),
        ):
            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            assert captured_capabilities is not None
            assert captured_capabilities["fs"]["readTextFile"] is True
            assert captured_capabilities["fs"]["writeTextFile"] is True
            assert captured_capabilities["terminal"] is True
            assert captured_send_callback is not None

    @pytest.mark.asyncio
    async def test_holder_receives_client_rpc_service(self) -> None:
        """ClientRPCServiceHolder.service устанавливается в созданный сервис."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        mock_holder = MagicMock()
        mock_holder.service = None

        mock_rpc_service = AsyncMock()
        mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)

        async def fake_get(cls):
            if hasattr(cls, "__name__") and cls.__name__ == "ClientRPCServiceHolder":
                return mock_holder
            if hasattr(cls, "__name__") and cls.__name__ == "ObservabilityFlushManager":
                return AsyncMock()
            return AsyncMock()

        mock_container = _make_mock_container(get_side_effect=fake_get)

        async def run_with_sleep(**kwargs):
            await asyncio.sleep(0.01)

        mock_transport = _make_default_transport_mock(run_side_effect=run_with_sleep)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH, return_value=mock_rpc_service),
        ):
            run_task = asyncio.create_task(
                _run_with_mocks(
                    mock_storage, mock_config, mock_container,
                    transport_mock=mock_transport,
                )
            )
            await asyncio.sleep(0.1)
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

            assert mock_holder.service is mock_rpc_service

    @pytest.mark.asyncio
    async def test_transport_created_with_callbacks(self) -> None:
        """StdioServerTransport создаётся с callbacks для protocol integration."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        captured_callbacks: dict = {}

        def capture_transport(**callbacks):
            captured_callbacks.update(callbacks)
            mock_t = AsyncMock()

            async def run(**kwargs):
                await asyncio.sleep(0.01)

            mock_t.run = run
            mock_t.send = AsyncMock()
            return mock_t

        mock_protocol = AsyncMock()
        mock_container = _make_mock_container(request_scope_get_return=mock_protocol)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_side_effect=capture_transport,
            )

            assert "should_auto_complete" in captured_callbacks
            assert "complete_active_turn" in captured_callbacks
            assert "load_pending_prompt_response" in captured_callbacks


class TestRunStdioServerLifecycle:
    """Тесты жизненного цикла transport."""

    @pytest.mark.asyncio
    async def test_transport_run_called_with_on_message_callback(self) -> None:
        """transport.run() вызывается с on_message callback."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        captured_on_message = None

        async def fake_run(*, on_message):
            nonlocal captured_on_message
            captured_on_message = on_message
            return None

        mock_container = _make_mock_container()
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            assert captured_on_message is not None
            assert asyncio.iscoroutinefunction(captured_on_message)

    @pytest.mark.asyncio
    async def test_on_message_calls_protocol_handle_and_process(self) -> None:
        """on_message callback вызывает protocol.handle_and_process."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        captured_on_message = None
        mock_protocol = AsyncMock()
        mock_protocol.handle_and_process = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response("1", {"ok": True}))
        )

        async def fake_run(*, on_message):
            nonlocal captured_on_message
            captured_on_message = on_message
            return None

        mock_container = _make_mock_container(request_scope_get_return=mock_protocol)
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            test_msg = ACPMessage(jsonrpc="2.0", id="1", method="test", params={})
            await captured_on_message(test_msg)

            mock_protocol.handle_and_process.assert_awaited_once_with(test_msg)

    @pytest.mark.asyncio
    async def test_protocol_send_callback_set_to_transport_send(self) -> None:
        """protocol._send_callback устанавливается в transport.send."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        async def fake_run(*, on_message):
            return None

        mock_protocol = MagicMock()
        mock_protocol._send_callback = None
        mock_container = _make_mock_container(request_scope_get_return=mock_protocol)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service
            mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            assert mock_protocol._send_callback is not None


class TestRunStdioServerShutdown:
    """Тесты graceful shutdown."""

    @pytest.mark.asyncio
    async def test_cancelled_error_handled_gracefully(self) -> None:
        """asyncio.CancelledError обрабатывается без exception."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        async def fake_run(*, on_message):
            raise asyncio.CancelledError()

        mock_container = _make_mock_container()
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            mock_container.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_logged_and_container_closed(self) -> None:
        """Exception логируется и container закрывается в finally."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        async def fake_run(*, on_message):
            raise RuntimeError("test error")

        mock_container = _make_mock_container()
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
            patch(_LOGGER_PATH) as mock_logger,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            mock_logger.error.assert_called_once()
            mock_container.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pending_rpc_cancelled_on_shutdown(self) -> None:
        """cancel_all_pending_requests вызывается при shutdown."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        mock_rpc_service = AsyncMock()
        mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=3)

        async def fake_run(*, on_message):
            return None

        mock_container = _make_mock_container()
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH, return_value=mock_rpc_service),
        ):
            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            mock_rpc_service.cancel_all_pending_requests.assert_called_once()
            call_args = mock_rpc_service.cancel_all_pending_requests.call_args[1]
            assert "reason" in call_args
            assert "shutting down" in call_args["reason"]

    @pytest.mark.asyncio
    async def test_container_closed_in_finally(self) -> None:
        """container.close() вызывается в finally блоке."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        async def fake_run(*, on_message):
            return None

        mock_container = _make_mock_container()
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH) as mock_rpc_cls,
        ):
            mock_rpc_service = AsyncMock()
            mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)
            mock_rpc_cls.return_value = mock_rpc_service

            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            mock_container.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancelled_rpc_logged_when_count_greater_than_zero(self) -> None:
        """Логирование cancelled RPC когда count > 0."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        mock_rpc_service = AsyncMock()
        mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=5)

        async def fake_run(*, on_message):
            return None

        mock_container = _make_mock_container()
        mock_transport = _make_default_transport_mock(run_side_effect=fake_run)

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH, return_value=mock_rpc_service),
            patch(_LOGGER_PATH) as mock_logger,
        ):
            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            info_calls = [c for c in mock_logger.info.call_args_list]
            assert any(
                "cancelled" in str(call).lower()
                for call in info_calls
            )


class TestRunStdioServerIntegration:
    """Интеграционные тесты с mock transport."""

    @pytest.mark.asyncio
    async def test_full_flow_with_mock_transport(self) -> None:
        """Полный поток: init → setup → run → shutdown."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        mock_rpc_service = AsyncMock()
        mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)

        mock_holder = MagicMock()
        mock_holder.service = None

        mock_protocol = AsyncMock()
        mock_protocol._send_callback = None
        mock_protocol.handle_and_process = AsyncMock(
            return_value=ProtocolOutcome(response=ACPMessage.response("1", {"ok": True}))
        )
        mock_protocol.should_auto_complete_active_turn = AsyncMock(return_value=False)
        mock_protocol.complete_active_turn = AsyncMock(return_value=None)
        mock_protocol._storage = MagicMock()

        run_called = False
        run_callback = None

        async def fake_run(*, on_message):
            nonlocal run_called, run_callback
            run_called = True
            run_callback = on_message

        mock_transport = AsyncMock()
        mock_transport.run = fake_run
        mock_transport.send = AsyncMock()

        async def fake_get(cls):
            if hasattr(cls, "__name__") and cls.__name__ == "ObservabilityFlushManager":
                return AsyncMock()
            if hasattr(cls, "__name__") and cls.__name__ == "ClientRPCServiceHolder":
                return mock_holder
            return mock_protocol

        mock_container = _make_mock_container(
            request_scope_get_return=mock_protocol,
            get_side_effect=fake_get,
        )

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH, return_value=mock_rpc_service),
        ):
            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_mock=mock_transport,
            )

            assert run_called is True
            assert run_callback is not None

            test_msg = ACPMessage(jsonrpc="2.0", id="test-1", method="session/list", params={})
            await run_callback(test_msg)
            mock_protocol.handle_and_process.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_rpc_request_uses_transport(self) -> None:
        """send_rpc_request callback использует transport.send."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"

        mock_rpc_service = AsyncMock()
        mock_rpc_service.cancel_all_pending_requests = MagicMock(return_value=0)

        captured_transport = None

        def capture_transport(**callbacks):
            nonlocal captured_transport
            mock_t = AsyncMock()
            mock_t.send = AsyncMock()
            captured_transport = mock_t

            async def fake_run(*, on_message):
                return None

            mock_t.run = fake_run
            return mock_t

        mock_container = _make_mock_container()

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container),
            patch(_CLIENT_RPC_SERVICE_PATH, return_value=mock_rpc_service),
        ):
            await _run_with_mocks(
                mock_storage, mock_config, mock_container,
                transport_side_effect=capture_transport,
            )

            assert captured_transport is not None
            assert asyncio.iscoroutinefunction(captured_transport.send)

    @pytest.mark.asyncio
    async def test_auth_params_passed_to_container(self) -> None:
        """Параметры аутентификации передаются в make_container."""
        mock_storage = MagicMock()
        mock_config = MagicMock()
        mock_config.llm.provider = "mock"
        mock_container = _make_mock_container()

        with (
            patch(_MAKE_CONTAINER_PATH, return_value=mock_container) as mock_make,
            patch(_CLIENT_RPC_SERVICE_PATH),
        ):
            mock_transport = _make_default_transport_mock()
            run_task = asyncio.create_task(
                _run_with_mocks(
                    mock_storage,
                    mock_config,
                    mock_container,
                    require_auth=True,
                    auth_api_key="test-key-123",
                    transport_mock=mock_transport,
                )
            )
            await asyncio.sleep(0.05)
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)

            call_kwargs = mock_make.call_args[1]
            assert call_kwargs["require_auth"] is True
            assert call_kwargs["auth_api_key"] == "test-key-123"

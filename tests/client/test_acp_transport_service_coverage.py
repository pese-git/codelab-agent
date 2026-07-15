"""Дополнительные тесты покрытия для ACPTransportService."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.client.infrastructure.services.acp_transport_service import (
    ACPTransportService,
)
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport
from codelab.client.messages import ACPMessage


def _create_service() -> ACPTransportService:
    """Создаёт сервис с mock WebSocket транспортом."""
    transport = AsyncMock(spec=WebSocketTransport)
    transport.is_connected.return_value = True
    return ACPTransportService(transport=transport)


class TestContextManager:
    """Тесты async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_returns_service(self) -> None:
        """__aenter__ возвращает текущий экземпляр сервиса."""
        service = _create_service()
        async with service as entered:
            assert entered is service

    @pytest.mark.asyncio
    async def test_aexit_catches_disconnect_errors(self) -> None:
        """Ошибка в disconnect при выходе из контекста не прокидывается."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        service._background_loop = MagicMock()  # noqa: SLF001
        service._background_loop.stop = AsyncMock(side_effect=ValueError("fail"))  # noqa: SLF001

        async with service:
            pass

        service._logger.warning.assert_called_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_aexit_catches_disconnect_exception(self) -> None:
        """Исключение из disconnect ловится и логируется в __aexit__."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        service.disconnect = AsyncMock(side_effect=ValueError("disconnect fail"))  # noqa: SLF001

        async with service:
            pass

        service._logger.warning.assert_called_once()  # noqa: SLF001
        call_kwargs = service._logger.warning.call_args[1]  # noqa: SLF001
        assert "disconnect fail" in call_kwargs["error"]


class TestConnect:
    """Тесты подключения и инициализации инфраструктуры."""

    @pytest.mark.asyncio
    async def test_connect_skips_when_already_connected(self) -> None:
        """Не выполняет подключение если транспорт уже активен."""
        service = _create_service()
        service._transport.is_connected.return_value = True  # noqa: SLF001

        with patch(
            "codelab.client.infrastructure.services.acp_transport_service.BackgroundReceiveLoop"
        ) as mock_loop_class:
            await service.connect()

        mock_loop_class.assert_not_called()
        service._transport.__aenter__.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_connect_initializes_background_loop(self) -> None:
        """Подключение создаёт и запускает background receive loop."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001

        mock_loop = MagicMock()
        mock_loop.start = AsyncMock()
        mock_loop.is_running.return_value = True

        with patch(
            "codelab.client.infrastructure.services.acp_transport_service.BackgroundReceiveLoop",
            return_value=mock_loop,
        ):
            await service.connect()

        service._transport.__aenter__.assert_awaited_once()  # noqa: SLF001
        mock_loop.start.assert_awaited_once()
        assert service._background_loop is mock_loop  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_connect_failure_cleans_resources(self) -> None:
        """При ошибке подключения ресурсы очищаются и бросается RuntimeError."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001

        with patch(
            "codelab.client.infrastructure.services.acp_transport_service.BackgroundReceiveLoop",
            side_effect=RuntimeError("init fail"),
        ):
            with pytest.raises(RuntimeError, match="Failed to connect"):
                await service.connect()

        assert service._background_loop is None  # noqa: SLF001
        assert service._queues is None  # noqa: SLF001
        assert service._router is None  # noqa: SLF001


class TestDisconnect:
    """Тесты разрыва соединения и очистки ресурсов."""

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Disconnect ничего не делает если соединение уже разорвано."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001

        await service.disconnect()

        service._transport.__aexit__.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_disconnect_closes_resources(self) -> None:
        """Disconnect останавливает loop, очищает очереди и закрывает транспорт."""
        service = _create_service()
        background_loop = MagicMock()
        background_loop.stop = AsyncMock()
        queues = MagicMock()
        queues.clear_all = AsyncMock()
        service._background_loop = background_loop  # noqa: SLF001
        service._queues = queues  # noqa: SLF001

        await service.disconnect()

        background_loop.stop.assert_awaited_once()
        queues.clear_all.assert_awaited_once()
        service._transport.__aexit__.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_disconnect_handles_loop_stop_error(self) -> None:
        """Ошибка при остановке loop логируется, но не прокидывается."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        background_loop = MagicMock()
        background_loop.stop = AsyncMock(side_effect=ValueError("stop fail"))
        queues = MagicMock()
        queues.clear_all = AsyncMock()
        service._background_loop = background_loop  # noqa: SLF001
        service._queues = queues  # noqa: SLF001

        await service.disconnect()

        service._logger.warning.assert_called_once()  # noqa: SLF001


class TestSend:
    """Тесты отправки сообщений через транспорт."""

    @pytest.mark.asyncio
    async def test_send_reconnects_when_disconnected(self) -> None:
        """Send автоматически переподключается при потере соединения."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001
        service.connect = AsyncMock()  # noqa: SLF001

        await service.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})

        service.connect.assert_awaited_once()  # noqa: SLF001
        service._transport.send_str.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_send_permission_response_logs_info(self) -> None:
        """Ответ на permission request логируется на уровне info."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        await service.send(
            {
                "jsonrpc": "2.0",
                "id": "perm-1",
                "result": {"outcome": "selected", "optionId": "allow_once"},
            }
        )

        service._logger.info.assert_any_call(  # noqa: SLF001
            "permission_response_sent_via_transport",
            message_id="perm-1",
            outcome="selected",
            option_id="allow_once",
        )

    @pytest.mark.asyncio
    async def test_send_failure_raises_runtime_error(self) -> None:
        """Ошибка транспорта при отправке оборачивается в RuntimeError."""
        service = _create_service()
        service._transport.send_str = AsyncMock(side_effect=ConnectionError("fail"))  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Failed to send message"):
            await service.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})

    @pytest.mark.asyncio
    async def test_send_reconnect_failure_raises(self) -> None:
        """Неудача переподключения при send оборачивается в RuntimeError."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001
        service.connect = AsyncMock(side_effect=ConnectionError("reconnect fail"))  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Failed to reconnect to server"):
            await service.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})


class TestReceive:
    """Тесты получения сообщений из очередей маршрутизации."""

    @pytest.mark.asyncio
    async def test_receive_raises_when_not_connected(self) -> None:
        """Receive бросает RuntimeError если нет соединения."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Not connected to server"):
            await service.receive()

    @pytest.mark.asyncio
    async def test_receive_raises_when_queues_missing(self) -> None:
        """Receive бросает RuntimeError если очереди не инициализированы."""
        service = _create_service()
        service._queues = None  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Routing queues not initialized"):
            await service.receive()

    @pytest.mark.asyncio
    async def test_receive_by_request_id(self) -> None:
        """Receive с request_id забирает ответ из соответствующей очереди."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        await queues.put_response("req-1", {"jsonrpc": "2.0", "id": "req-1", "result": {}})

        message = await service.receive("req-1")
        assert message["id"] == "req-1"

    @pytest.mark.asyncio
    async def test_receive_notification(self) -> None:
        """Receive без request_id забирает уведомление из общей очереди."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        await queues.put_notification({"jsonrpc": "2.0", "method": "session/update", "params": {}})

        message = await service.receive()
        assert message["method"] == "session/update"

    @pytest.mark.asyncio
    async def test_receive_failure(self) -> None:
        """Неожиданная ошибка при получении оборачивается в RuntimeError."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        async def failing_get() -> None:
            raise ValueError("boom")

        queues.get_or_create_response_queue = AsyncMock()  # noqa: SLF001
        mock_queue = AsyncMock()
        mock_queue.get = failing_get
        queues.get_or_create_response_queue.return_value = mock_queue  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Failed to receive message"):
            await service.receive(request_id="test")


class TestListen:
    """Тесты асинхронного итератора входящих сообщений."""

    @pytest.mark.asyncio
    async def test_listen_not_connected_raises(self) -> None:
        """Listen бросает RuntimeError если нет соединения."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Not connected to server"):
            async for _ in service.listen():
                pass

    @pytest.mark.asyncio
    async def test_listen_yields_messages(self) -> None:
        """Listen выдаёт сообщения из receive."""
        service = _create_service()
        messages = [
            {"jsonrpc": "2.0", "id": 1, "result": {}},
            {"jsonrpc": "2.0", "id": 2, "result": {}},
        ]
        service.receive = AsyncMock(side_effect=messages + [RuntimeError("done")])  # noqa: SLF001

        result = [m async for m in service.listen()]
        assert result == messages

    @pytest.mark.asyncio
    async def test_listen_breaks_on_receive_runtime_error(self) -> None:
        """RuntimeError в receive прерывает цикл listen."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        service.receive = AsyncMock(  # noqa: SLF001
            side_effect=[{"jsonrpc": "2.0", "id": 1, "result": {}}, RuntimeError("lost")]
        )

        result = [m async for m in service.listen()]
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_listen_propagates_unexpected_error(self) -> None:
        """Неожиданный тип ошибки прокидывается из listen."""
        service = _create_service()
        service.receive = AsyncMock(side_effect=ValueError("boom"))  # noqa: SLF001

        with pytest.raises(ValueError, match="boom"):
            async for _ in service.listen():
                pass


class TestConnectionState:
    """Тесты проверки состояния соединения и инициализации."""

    def test_is_connected_transport_none(self) -> None:
        """Если транспорт не задан, сервис считается отключённым."""
        service = _create_service()
        service._transport = None  # noqa: SLF001

        assert service.is_connected() is False

    def test_is_connected_reports_lost(self) -> None:
        """Потеря соединения логируется на уровне debug."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        service._transport.is_connected.return_value = False  # noqa: SLF001

        assert service.is_connected() is False
        service._logger.debug.assert_called_once()  # noqa: SLF001

    def test_set_and_get_server_capabilities(self) -> None:
        """Capabilities сохраняются и возвращаются."""
        service = _create_service()
        capabilities = {"loadSession": True}

        service.set_server_capabilities(capabilities)

        assert service.get_server_capabilities() is capabilities

    def test_get_server_capabilities_without_set_raises(self) -> None:
        """Получение capabilities до инициализации бросает RuntimeError."""
        service = _create_service()

        with pytest.raises(RuntimeError, match="Server not initialized"):
            service.get_server_capabilities()

    def test_is_initialized(self) -> None:
        """is_initialized отражает наличие сохранённых capabilities."""
        service = _create_service()

        assert service.is_initialized() is False
        service.set_server_capabilities({})
        assert service.is_initialized() is True


class TestCancelPrompt:
    """Тесты операции session/cancel."""

    @pytest.mark.asyncio
    async def test_cancel_prompt_not_connected_returns(self) -> None:
        """Cancel prompt ничего не делает при отсутствии соединения."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001

        await service.cancel_prompt("sess-1")

        service._transport.send_str.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_cancel_prompt_queues_none_returns(self) -> None:
        """Cancel prompt ничего не делает если очереди не инициализированы."""
        service = _create_service()
        service._queues = None  # noqa: SLF001

        await service.cancel_prompt("sess-1")

        service._transport.send_str.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_cancel_prompt_sends_and_waits_response(self) -> None:
        """Cancel prompt отправляет запрос и ожидает ответ."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        async def send_str_side_effect(raw: str) -> None:
            payload = json.loads(raw)
            if payload.get("method") == "session/cancel":
                request_id = payload["id"]
                await queues.put_response(
                    request_id, {"jsonrpc": "2.0", "id": request_id, "result": {}}
                )

        service._transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # noqa: SLF001

        await service.cancel_prompt("sess-1")

        service._transport.send_str.assert_awaited_once()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_cancel_prompt_timeout_is_ignored(self) -> None:
        """Таймаут ожидания ответа на cancel prompt игнорируется."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        def _timeout(coro: object, *_a: object, **_k: object) -> None:
            # Закрываем переданную queue.get()-корутину, иначе она утекает
            # незавершённой (замоканный wait_for её не awaited) → unraisable (P0-3a).
            if hasattr(coro, "close"):
                coro.close()
            raise TimeoutError

        with patch.object(asyncio, "wait_for", side_effect=_timeout):
            await service.cancel_prompt("sess-1")

    @pytest.mark.asyncio
    async def test_cancel_prompt_request_id_none_returns(self) -> None:
        """Cancel prompt возвращается если request.id отсутствует."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        with patch.object(
            ACPMessage,
            "request",
            return_value=ACPMessage(method="session/cancel", params={"sessionId": "s"}),
        ):
            await service.cancel_prompt("sess-1")

        service._transport.send_str.assert_not_awaited()  # noqa: SLF001


class TestRequestHelpers:
    """Тесты вспомогательных методов запросов."""

    @pytest.mark.asyncio
    async def test_ensure_connected_failure_raises(self) -> None:
        """Ошибка переподключения оборачивается в RuntimeError."""
        service = _create_service()
        service._transport.is_connected.return_value = False  # noqa: SLF001
        service.connect = AsyncMock(side_effect=ConnectionError("fail"))  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Failed to reconnect to server"):
            await service._ensure_connected()

class TestRequestWithCallbacks:
    """Тесты полного цикла request_with_callbacks."""

    @pytest.mark.asyncio
    async def test_request_with_callbacks_permission_task_done(self) -> None:
        """Завершение permission task обрабатывается до возврата ответа."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        async def send_str_side_effect(raw: str) -> None:
            payload = json.loads(raw)
            request_id = payload["id"]
            await queues.put_permission_request(
                {
                    "jsonrpc": "2.0",
                    "id": "perm-1",
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": "s",
                        "toolCall": {"toolCallId": "tc-1", "title": "Run"},
                        "options": [],
                    },
                }
            )
            await queues.put_response(
                request_id, {"jsonrpc": "2.0", "id": request_id, "result": {"ok": True}}
            )

        service._transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # noqa: SLF001

        response = await service.request_with_callbacks("session/prompt")
        assert response["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_request_with_callbacks_outer_exception(self) -> None:
        """Исключение до старта цикла пробрасывается."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001
        service.send = AsyncMock(side_effect=ValueError("fail"))  # noqa: SLF001

        with pytest.raises(ValueError, match="fail"):
            await service.request_with_callbacks("session/prompt")

    @pytest.mark.asyncio
    async def test_request_with_callbacks_invalid_request_id(self) -> None:
        """RuntimeError если сгенерирован запрос без валидного id."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001
        service.send = AsyncMock()  # noqa: SLF001

        with patch.object(
            ACPMessage, "request", return_value=ACPMessage(method="session/prompt", params={})
        ):
            with pytest.raises(RuntimeError, match="Generated request without valid id"):
                await service.request_with_callbacks("session/prompt")

class TestSyncCleanup:
    """Тесты синхронных методов очистки."""

    def test_cleanup(self) -> None:
        """Cleanup логирует вызов."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        service.cleanup()

        service._logger.debug.assert_called_once_with("cleanup_called")  # noqa: SLF001

    def test_close(self) -> None:
        """Close логирует вызов."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        service.close()

        service._logger.debug.assert_called_once_with("close_called")  # noqa: SLF001

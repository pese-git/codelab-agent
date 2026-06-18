"""Дополнительные тесты покрытия для ACPTransportService."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.client.infrastructure.services.acp_transport_service import (
    ACPTransportService,
    _call_callback,
)
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport
from codelab.client.messages import ACPMessage


def _create_service() -> ACPTransportService:
    """Создаёт сервис с mock WebSocket транспортом."""
    transport = AsyncMock(spec=WebSocketTransport)
    transport.is_connected.return_value = True
    return ACPTransportService(transport=transport)


class TestCallCallback:
    """Тесты вспомогательной функции _call_callback."""

    @pytest.mark.asyncio
    async def test_call_callback_with_none_returns_none(self) -> None:
        """При None callback функция возвращает None."""
        result = await _call_callback(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_call_callback_awaits_async_function(self) -> None:
        """Async callback ожидается и возвращает результат."""

        async def async_cb(value: int) -> int:
            return value * 2

        assert await _call_callback(async_cb, 5) == 10


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

        await queues.put_notification(
            {"jsonrpc": "2.0", "method": "session/update", "params": {}}
        )

        message = await service.receive()
        assert message["method"] == "session/update"

    @pytest.mark.asyncio
    async def test_receive_timeout(self) -> None:
        """Таймаут ожидания сообщения оборачивается в RuntimeError."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        with patch.object(asyncio, "wait_for", side_effect=TimeoutError):
            with pytest.raises(RuntimeError, match="Timeout waiting for message"):
                await service.receive()

    @pytest.mark.asyncio
    async def test_receive_failure(self) -> None:
        """Неожиданная ошибка при получении оборачивается в RuntimeError."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        with patch.object(asyncio, "wait_for", side_effect=ValueError("boom")):
            with pytest.raises(RuntimeError, match="Failed to receive message"):
                await service.receive()


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

        with patch.object(asyncio, "wait_for", side_effect=TimeoutError):
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

    @pytest.mark.asyncio
    async def test_validate_request_setup_missing_queues_raises(self) -> None:
        """Отсутствие очередей валидируется перед запросом."""
        service = _create_service()
        service._queues = None  # noqa: SLF001

        with pytest.raises(RuntimeError, match="Routing queues not initialized"):
            await service._validate_request_setup()


class TestDrainRemainingNotifications:
    """Тесты забора оставшихся уведомлений после финального ответа."""

    @pytest.mark.asyncio
    async def test_drain_handles_session_update(self) -> None:
        """Оставшиеся session/update передаются в on_update."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        update = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "s",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "x"},
                },
            },
        }
        await queues.put_notification(update)
        on_update = MagicMock()

        count = await service._drain_remaining_notifications(
            method="session/prompt", request_id="req-1", on_update=on_update
        )

        assert count == 1
        on_update.assert_called_once_with(update)

    @pytest.mark.asyncio
    async def test_drain_timeout_returns_zero(self) -> None:
        """При пустой очереди drain завершается с нулём."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        count = await service._drain_remaining_notifications(
            method="m", request_id="r", on_update=None
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_drain_exception_breaks_loop(self) -> None:
        """Ошибка при обработке уведомления прерывает drain."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001

        await queues.put_notification(
            {"jsonrpc": "2.0", "method": "session/update", "params": {}}
        )

        with patch.object(
            queues.notification_queue,
            "get",
            side_effect=[
                {"jsonrpc": "2.0", "method": "session/update", "params": {}},
                ValueError("boom"),
            ],
        ):
            count = await service._drain_remaining_notifications(
                method="m", request_id="r", on_update=None
            )

        assert count == 1


class TestProcessResponse:
    """Тесты обработки финального RPC ответа."""

    @pytest.mark.asyncio
    async def test_process_response_mismatch_raises(self) -> None:
        """Несовпадение id ответа бросает RuntimeError."""
        service = _create_service()
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        future.set_result({"jsonrpc": "2.0", "id": "other", "result": {}})

        with pytest.raises(RuntimeError, match="Response id mismatch"):
            await service._process_response(
                future, method="m", request_id="req-1", on_update=None
            )

    @pytest.mark.asyncio
    async def test_process_response_error_payload_logs(self) -> None:
        """Error payload в ответе логируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        future.set_result(
            {"jsonrpc": "2.0", "id": "req-1", "error": {"code": -1, "message": "fail"}}
        )

        result = await service._process_response(
            future, method="m", request_id="req-1", on_update=None
        )

        assert result["error"]["code"] == -1
        service._logger.error.assert_any_call(  # noqa: SLF001
            "request_error", method="m", error_code=-1, error_message="fail"
        )


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

    @pytest.mark.asyncio
    async def test_request_with_callbacks_cancels_pending_tasks_on_error(self) -> None:
        """При ошибке в цикле ожидания отменяются незавершённые задачи."""
        service = _create_service()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001
        service.send = AsyncMock()  # noqa: SLF001
        service._wait_for_response_with_events = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("loop fail")
        )

        with pytest.raises(RuntimeError, match="loop fail"):
            await service.request_with_callbacks("session/prompt")


class TestPermissionHandling:
    """Тесты обработки permission запросов."""

    @pytest.mark.asyncio
    async def test_handle_permission_request_without_handler(self) -> None:
        """При отсутствии handler permission request игнорируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        await service._handle_permission_request_with_handler(
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

        service._logger.debug.assert_any_call(  # noqa: SLF001
            "permission_handler_not_configured_skipping"
        )

    @pytest.mark.asyncio
    async def test_handle_permission_request_exception_sends_error(self) -> None:
        """Исключение в handler приводит к отправке error response."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        handler = AsyncMock()
        handler.handle_request = AsyncMock(side_effect=ValueError("bad"))  # noqa: SLF001
        service._permission_handler = handler  # noqa: SLF001
        service.send = AsyncMock()  # noqa: SLF001

        await service._handle_permission_request_with_handler(
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

        service.send.assert_awaited_once()  # noqa: SLF001
        payload = service.send.call_args[0][0]  # noqa: SLF001
        assert payload["error"]["code"] == -32603

    @pytest.mark.asyncio
    async def test_handle_permission_request_send_error_fails(self) -> None:
        """Ошибка отправки error response логируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        handler = AsyncMock()
        handler.handle_request = AsyncMock(side_effect=ValueError("bad"))  # noqa: SLF001
        service._permission_handler = handler  # noqa: SLF001
        service.send = AsyncMock(side_effect=ConnectionError("send fail"))  # noqa: SLF001

        await service._handle_permission_request_with_handler(
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

        error_events = [
            call.args[0] for call in service._logger.error.call_args_list if call.args
        ]
        assert "failed_to_send_error_response" in error_events

    @pytest.mark.asyncio
    async def test_handle_permission_task_exception(self) -> None:
        """Исключение в permission task логируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        async def failing() -> dict[str, Any]:
            raise ValueError("perm fail")

        task = asyncio.create_task(failing())
        await asyncio.sleep(0)

        service._handle_permission_task(task, method="m", request_id="req-1")

        warning_events = [
            call.args[0] for call in service._logger.warning.call_args_list if call.args
        ]
        assert "tool_lifecycle_permission_request_failed" in warning_events

    @pytest.mark.asyncio
    async def test_handle_notification_task_timeout(self) -> None:
        """TimeoutError в notification task игнорируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        async def raise_timeout() -> dict[str, Any]:
            raise TimeoutError

        task = asyncio.create_task(raise_timeout())
        await asyncio.sleep(0)

        await service._handle_notification_task(
            task,
            method="m",
            request_id="r",
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

    @pytest.mark.asyncio
    async def test_handle_notification_task_exception(self) -> None:
        """Неожиданная ошибка в notification task логируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        async def raise_value() -> dict[str, Any]:
            raise ValueError("boom")

        task = asyncio.create_task(raise_value())
        await asyncio.sleep(0)

        await service._handle_notification_task(
            task,
            method="m",
            request_id="r",
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        warning_events = [
            call.args[0] for call in service._logger.warning.call_args_list if call.args
        ]
        assert "tool_lifecycle_notification_failed" in warning_events


class TestSessionUpdate:
    """Тесты обработки session/update уведомлений."""

    @pytest.mark.asyncio
    async def test_handle_session_update_with_callback(self) -> None:
        """Update передаётся в пользовательский callback."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        on_update = MagicMock()
        data = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "s",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "x"},
                },
            },
        }

        await service._handle_session_update(
            data, method="m", request_id="r", on_update=on_update
        )

        on_update.assert_called_once_with(data)
        service._logger.debug.assert_any_call(  # noqa: SLF001
            "handling_session_update", method="m", request_id="r", has_callback=True
        )

    @pytest.mark.asyncio
    async def test_handle_session_update_without_callback(self) -> None:
        """Update без callback логирует предупреждение."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        data = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "s", "update": {}},
        }

        await service._handle_session_update(
            data, method="m", request_id="r", on_update=None
        )

        service._logger.warning.assert_any_call(  # noqa: SLF001
            "session_update_received_but_no_callback", method="m", request_id="r"
        )


class TestClientRpcRouting:
    """Тесты маршрутизации входящих server->client RPC."""

    @pytest.mark.asyncio
    async def test_invalid_rpc_ignored(self) -> None:
        """RPC без id или метода игнорируется."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={"jsonrpc": "2.0", "method": "fs/read_text_file", "params": {}},
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        service._transport.send_str.assert_not_awaited()  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_session_update_dispatched_to_callback(self) -> None:
        """session/update маршрутизируется в _handle_session_update."""
        service = _create_service()
        service._logger = MagicMock()  # noqa: SLF001
        on_update = MagicMock()
        data = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "s", "update": {}},
        }

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data=data,
            on_update=on_update,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        on_update.assert_called_once_with(data)


class TestTerminalHandlers:
    """Тесты обработки terminal/* RPC."""

    @pytest.mark.asyncio
    async def test_terminal_create_without_callback_sends_error(self) -> None:
        """terminal/create без callback возвращает ошибку."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/create",
                "params": {"command": "ls"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["error"]["code"] == -32000

    @pytest.mark.asyncio
    async def test_terminal_create_with_callback(self) -> None:
        """terminal/create возвращает terminalId из callback."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/create",
                "params": {"command": "ls"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=lambda _: "term-1",
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["result"]["terminalId"] == "term-1"

    @pytest.mark.asyncio
    async def test_terminal_output_without_callback_sends_error(self) -> None:
        """terminal/output без callback возвращает ошибку."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/output",
                "params": {"terminalId": "term-1"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["error"]["code"] == -32000

    @pytest.mark.asyncio
    async def test_terminal_output_with_callback(self) -> None:
        """terminal/output возвращает данные из callback."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/output",
                "params": {"terminalId": "term-1"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=lambda _: {"output": "hello"},
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["result"] == {"output": "hello"}

    @pytest.mark.asyncio
    async def test_terminal_wait_with_tuple_result(self) -> None:
        """terminal/wait корректно обрабатывает tuple (exitCode, output)."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/wait_for_exit",
                "params": {"terminalId": "term-1"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=lambda _: (42, "done"),
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["result"] == {"exitCode": 42, "output": "done"}

    @pytest.mark.asyncio
    async def test_terminal_wait_with_int_result(self) -> None:
        """terminal/wait корректно обрабатывает только exitCode."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/wait_for_exit",
                "params": {"terminalId": "term-1"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=lambda _: 0,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["result"] == {"exitCode": 0}

    @pytest.mark.asyncio
    async def test_terminal_release_calls_callback(self) -> None:
        """terminal/release вызывает callback и возвращает пустой ответ."""
        service = _create_service()
        callback = MagicMock()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/release",
                "params": {"terminalId": "term-1"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=callback,
            on_terminal_kill=None,
        )

        callback.assert_called_once_with("term-1")
        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["result"] == {}

    @pytest.mark.asyncio
    async def test_terminal_kill_with_callback(self) -> None:
        """terminal/kill возвращает флаг killed из callback."""
        service = _create_service()

        await service._handle_notification_or_client_rpc(
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "terminal/kill",
                "params": {"terminalId": "term-1"},
            },
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=lambda _: True,
        )

        payload = json.loads(service._transport.send_str.call_args[0][0])  # noqa: SLF001
        assert payload["result"]["killed"] is True


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

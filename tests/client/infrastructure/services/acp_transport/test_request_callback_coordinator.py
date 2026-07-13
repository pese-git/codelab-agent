"""Тесты для RequestCallbackCoordinator."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.client.infrastructure.services.acp_transport import RequestCallbackCoordinator
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.messages import ACPMessage


def _make_coordinator(
    *,
    queues: RoutingQueues | None = None,
    dispatcher: Any = None,
    send: Any = None,
    permission_responder: Any = None,
) -> RequestCallbackCoordinator:
    """Создаёт координатор с указанными (или mock) зависимостями."""
    return RequestCallbackCoordinator(
        queues_provider=lambda: queues,
        dispatcher_provider=lambda: dispatcher,
        send=send or AsyncMock(),
        permission_responder=permission_responder or AsyncMock(),
        request_lock=asyncio.Lock(),
    )


class TestExecute:
    """Полный цикл execute()."""

    @pytest.mark.asyncio
    async def test_missing_queues_raises(self) -> None:
        """Отсутствие очередей валидируется перед запросом."""
        coordinator = _make_coordinator(queues=None)

        with pytest.raises(RuntimeError, match="Routing queues not initialized"):
            await coordinator.execute("session/prompt")

    @pytest.mark.asyncio
    async def test_permission_task_done(self) -> None:
        """Завершение permission task обрабатывается до возврата ответа."""
        queues = RoutingQueues()
        permission_responder = AsyncMock()

        async def send(raw: dict[str, Any]) -> None:
            request_id = raw["id"]
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

        coordinator = _make_coordinator(
            queues=queues, send=send, permission_responder=permission_responder
        )

        response = await coordinator.execute("session/prompt")
        assert response["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_outer_exception_propagates(self) -> None:
        """Исключение при отправке пробрасывается."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(
            queues=queues, send=AsyncMock(side_effect=ValueError("fail"))
        )

        with pytest.raises(ValueError, match="fail"):
            await coordinator.execute("session/prompt")

    @pytest.mark.asyncio
    async def test_invalid_request_id(self) -> None:
        """RuntimeError если сгенерирован запрос без валидного id."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues, send=AsyncMock())

        with patch.object(
            ACPMessage, "request", return_value=ACPMessage(method="session/prompt", params={})
        ):
            with pytest.raises(RuntimeError, match="Generated request without valid id"):
                await coordinator.execute("session/prompt")

    @pytest.mark.asyncio
    async def test_cancels_pending_tasks_on_error(self) -> None:
        """При ошибке в цикле ожидания отменяются незавершённые задачи."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues, send=AsyncMock())
        coordinator._wait_for_response_with_events = AsyncMock(  # noqa: SLF001
            side_effect=RuntimeError("loop fail")
        )

        with pytest.raises(RuntimeError, match="loop fail"):
            await coordinator.execute("session/prompt")


class TestDrainRemainingNotifications:
    """Забор оставшихся уведомлений после финального ответа."""

    @pytest.mark.asyncio
    async def test_drain_handles_session_update(self) -> None:
        """Оставшиеся session/update передаются в on_update."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues)

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

        count = await coordinator._drain_remaining_notifications(  # noqa: SLF001
            method="session/prompt", request_id="req-1", on_update=on_update, queues=queues
        )

        assert count == 1
        on_update.assert_called_once_with(update)

    @pytest.mark.asyncio
    async def test_drain_timeout_returns_zero(self) -> None:
        """При пустой очереди drain завершается с нулём."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues)

        count = await coordinator._drain_remaining_notifications(  # noqa: SLF001
            method="m", request_id="r", on_update=None, queues=queues
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_drain_exception_breaks_loop(self) -> None:
        """Ошибка при обработке уведомления прерывает drain."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues)

        with patch.object(
            queues.notification_queue,
            "get",
            side_effect=[
                {"jsonrpc": "2.0", "method": "session/update", "params": {}},
                ValueError("boom"),
            ],
        ):
            count = await coordinator._drain_remaining_notifications(  # noqa: SLF001
                method="m", request_id="r", on_update=None, queues=queues
            )

        assert count == 1


class TestProcessResponse:
    """Обработка финального RPC ответа."""

    @pytest.mark.asyncio
    async def test_process_response_mismatch_raises(self) -> None:
        """Несовпадение id ответа бросает RuntimeError."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        future.set_result({"jsonrpc": "2.0", "id": "other", "result": {}})

        with pytest.raises(RuntimeError, match="Response id mismatch"):
            await coordinator._process_response(  # noqa: SLF001
                future, method="m", request_id="req-1", on_update=None, queues=queues
            )

    @pytest.mark.asyncio
    async def test_process_response_error_payload_logs(self) -> None:
        """Error payload в ответе логируется."""
        queues = RoutingQueues()
        coordinator = _make_coordinator(queues=queues)
        coordinator._logger = MagicMock()  # noqa: SLF001
        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        future.set_result(
            {"jsonrpc": "2.0", "id": "req-1", "error": {"code": -1, "message": "fail"}}
        )

        result = await coordinator._process_response(  # noqa: SLF001
            future, method="m", request_id="req-1", on_update=None, queues=queues
        )

        assert result["error"]["code"] == -1
        coordinator._logger.error.assert_any_call(  # noqa: SLF001
            "request_error", method="m", error_code=-1, error_message="fail"
        )


class TestPermissionTask:
    """Обработка завершённого permission task."""

    @pytest.mark.asyncio
    async def test_exception_logged(self) -> None:
        """Исключение в permission task логируется."""
        coordinator = _make_coordinator()
        coordinator._logger = MagicMock()  # noqa: SLF001

        async def failing() -> dict[str, Any]:
            raise ValueError("perm fail")

        task = asyncio.create_task(failing())
        await asyncio.sleep(0)

        coordinator._handle_permission_task(task, method="m", request_id="req-1")  # noqa: SLF001

        warning_events = [
            call.args[0] for call in coordinator._logger.warning.call_args_list if call.args
        ]
        assert "tool_lifecycle_permission_request_failed" in warning_events

    @pytest.mark.asyncio
    async def test_success_delegates_to_responder(self) -> None:
        """Успешный permission task передаётся в PermissionResponder."""
        permission_responder = AsyncMock()
        coordinator = _make_coordinator(permission_responder=permission_responder)

        data = {"jsonrpc": "2.0", "id": "perm-1", "method": "session/request_permission"}

        async def ready() -> dict[str, Any]:
            return data

        task = asyncio.create_task(ready())
        await asyncio.sleep(0)

        coordinator._handle_permission_task(task, method="m", request_id="req-1")  # noqa: SLF001
        await asyncio.sleep(0)

        permission_responder.handle.assert_awaited_once_with(data)


class TestNotificationTask:
    """Обработка завершённого notification task."""

    @pytest.mark.asyncio
    async def test_timeout_ignored(self) -> None:
        """TimeoutError в notification task игнорируется."""
        coordinator = _make_coordinator()

        async def raise_timeout() -> dict[str, Any]:
            raise TimeoutError

        task = asyncio.create_task(raise_timeout())
        await asyncio.sleep(0)

        await coordinator._handle_notification_task(  # noqa: SLF001
            task, method="m", request_id="r", on_update=None
        )

    @pytest.mark.asyncio
    async def test_exception_logged(self) -> None:
        """Неожиданная ошибка в notification task логируется."""
        coordinator = _make_coordinator()
        coordinator._logger = MagicMock()  # noqa: SLF001

        async def raise_value() -> dict[str, Any]:
            raise ValueError("boom")

        task = asyncio.create_task(raise_value())
        await asyncio.sleep(0)

        await coordinator._handle_notification_task(  # noqa: SLF001
            task, method="m", request_id="r", on_update=None
        )

        warning_events = [
            call.args[0] for call in coordinator._logger.warning.call_args_list if call.args
        ]
        assert "tool_lifecycle_notification_failed" in warning_events


class TestSessionUpdate:
    """Обработка session/update уведомлений."""

    @pytest.mark.asyncio
    async def test_with_callback(self) -> None:
        """Update передаётся в пользовательский callback."""
        coordinator = _make_coordinator()
        coordinator._logger = MagicMock()  # noqa: SLF001
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

        await coordinator._handle_session_update(  # noqa: SLF001
            data, method="m", request_id="r", on_update=on_update
        )

        on_update.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_without_callback_warns(self) -> None:
        """Update без callback логирует предупреждение."""
        coordinator = _make_coordinator()
        coordinator._logger = MagicMock()  # noqa: SLF001
        data = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "s", "update": {}},
        }

        await coordinator._handle_session_update(  # noqa: SLF001
            data, method="m", request_id="r", on_update=None
        )

        coordinator._logger.warning.assert_any_call(  # noqa: SLF001
            "session_update_received_but_no_callback", method="m", request_id="r"
        )


class TestClientRpcRouting:
    """Маршрутизация входящих server->client RPC."""

    @pytest.mark.asyncio
    async def test_invalid_rpc_ignored(self) -> None:
        """RPC без id или метода игнорируется."""
        send = AsyncMock()
        coordinator = _make_coordinator(send=send)

        await coordinator._handle_notification_or_client_rpc(  # noqa: SLF001
            method="m",
            request_id="r",
            notification_data={"jsonrpc": "2.0", "method": "fs/read_text_file", "params": {}},
            on_update=None,
        )

        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_session_update_dispatched(self) -> None:
        """session/update маршрутизируется в on_update."""
        coordinator = _make_coordinator()
        on_update = MagicMock()
        data = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "s", "update": {}},
        }

        await coordinator._handle_notification_or_client_rpc(  # noqa: SLF001
            method="m", request_id="r", notification_data=data, on_update=on_update
        )

        on_update.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_unknown_rpc_without_dispatcher_sends_empty(self) -> None:
        """Без dispatcher client-RPC получает пустой ответ."""
        send = AsyncMock()
        coordinator = _make_coordinator(send=send, dispatcher=None)

        await coordinator._handle_notification_or_client_rpc(  # noqa: SLF001
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "fs/read_text_file",
                "params": {"path": "x"},
            },
            on_update=None,
        )

        send.assert_awaited_once()
        payload = send.call_args[0][0]
        assert payload["id"] == "rpc-1"
        assert payload["result"] == {}

    @pytest.mark.asyncio
    async def test_rpc_dispatched_to_dispatcher(self) -> None:
        """С dispatcher client-RPC уходит в него, ответ отправляется серверу."""
        send = AsyncMock()
        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock(return_value={"content": "data"})
        coordinator = _make_coordinator(send=send, dispatcher=dispatcher)

        await coordinator._handle_notification_or_client_rpc(  # noqa: SLF001
            method="m",
            request_id="r",
            notification_data={
                "jsonrpc": "2.0",
                "id": "rpc-1",
                "method": "fs/read_text_file",
                "params": {"path": "x"},
            },
            on_update=None,
        )

        dispatcher.dispatch.assert_awaited_once_with("fs/read_text_file", "rpc-1", {"path": "x"})
        send.assert_awaited_once()
        payload = send.call_args[0][0]
        assert payload["result"] == {"content": "data"}

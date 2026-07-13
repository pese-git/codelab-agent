"""Тесты для ACPTransportService request_with_callbacks."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.infrastructure.services.acp_transport_service import (
    ACPTransportService,
)
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport


def _create_service_for_test() -> ACPTransportService:
    """Создаёт ACPTransportService для тестов с mock транспортом."""
    transport = AsyncMock(spec=WebSocketTransport)
    transport.is_connected.return_value = True
    return ACPTransportService(transport=transport)


class TestACPTransportServiceRequestWithCallbacks:
    """Тесты обработки server->client RPC внутри request_with_callbacks."""

    @pytest.mark.asyncio
    async def test_permission_request_routing_via_handler(self) -> None:
        """Permission requests маршрутизируются через PermissionHandler."""
        service = _create_service_for_test()

        # Проверяем что request_with_callbacks не принимает on_permission параметр
        # Если попытаться передать on_permission, будет TypeError
        try:
            # Это должно вызвать TypeError так как параметра на_permission больше нет
            await service.request_with_callbacks(
                method="test",
                on_permission=lambda x: None,  # type: ignore[call-arg]
            )
            pytest.fail("Expected TypeError for on_permission parameter")
        except TypeError as e:
            # Ожидаемая ошибка - параметр удален
            assert "on_permission" in str(e) or "unexpected keyword argument" in str(e)

    @pytest.mark.asyncio
    async def test_unknown_server_rpc_with_id_gets_fallback_response(self) -> None:
        """На неизвестный server->client RPC отправляется пустой response."""
        service = _create_service_for_test()
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001 - test setup

        transport = service._transport  # noqa: SLF001 - test setup
        sent_messages: list[dict[str, object]] = []

        async def send_str_side_effect(raw_payload: str) -> None:
            payload = json.loads(raw_payload)
            sent_messages.append(payload)

            if payload.get("method") != "session/prompt":
                return

            if not isinstance(payload.get("id"), str | int):
                return
            request_id: str | int = payload["id"]

            async def produce_server_messages() -> None:
                await queues.notification_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": "rpc-unknown-1",
                        "method": "custom/unknown_rpc",
                        "params": {"sessionId": "sess-1"},
                    }
                )
                response_queue = await queues.get_or_create_response_queue(request_id)
                await response_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"status": "ok"},
                    }
                )

            asyncio.create_task(produce_server_messages())

        transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # type: ignore[union-attr]

        response = await service.request_with_callbacks(
            method="session/prompt",
            params={"sessionId": "sess-1", "prompt": [{"type": "text", "text": "hi"}]},
        )

        assert response["result"]["status"] == "ok"

        fallback_reply = next(
            message
            for message in sent_messages
            if message.get("id") == "rpc-unknown-1" and "result" in message
        )
        assert fallback_reply["result"] == {}


class TestPermissionCallback:
    """Тесты делегирования permission callback в PermissionResponder."""

    def test_set_permission_callback_delegates_to_responder(self) -> None:
        """set_permission_callback сохраняет callback в responder."""
        service = _create_service_for_test()

        callback = MagicMock()
        service.set_permission_callback(callback)

        assert service._permission_responder.callback is callback  # noqa: SLF001

    def test_set_permission_handler_delegates_to_responder(self) -> None:
        """set_permission_handler сохраняет handler в responder."""
        service = _create_service_for_test()

        handler = AsyncMock()
        service.set_permission_handler(handler)

        assert service._permission_responder.handler is handler  # noqa: SLF001


class TestMultiplePermissionRequests:
    """Тесты для обработки множественных permission requests в последовательности."""

    @pytest.mark.asyncio
    async def test_multiple_permission_requests_in_sequence(self) -> None:
        """Два последовательных permission request оба обрабатываются."""
        service = _create_service_for_test()
        service._logger = MagicMock()  # noqa: SLF001 - test setup
        service._coordinator._logger = service._logger  # noqa: SLF001 - coordinator логи в тот же mock
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001 - test setup

        transport = service._transport  # noqa: SLF001 - test setup
        sent_messages: list[dict[str, object]] = []

        async def send_str_side_effect(raw_payload: str) -> None:
            payload = json.loads(raw_payload)
            sent_messages.append(payload)

            if payload.get("method") != "session/prompt":
                return

            if not isinstance(payload.get("id"), str | int):
                return
            request_id: str | int = payload["id"]

            async def produce_server_messages() -> None:
                # Первый permission request
                await queues.permission_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": "perm-1",
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": "sess-1",
                            "toolCall": {"toolCallId": "tool-1", "title": "Read File"},
                            "options": [
                                {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                            ],
                        },
                    }
                )

                # Даём время обработать первый permission
                await asyncio.sleep(0.05)

                # Второй permission request
                await queues.permission_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": "perm-2",
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": "sess-1",
                            "toolCall": {"toolCallId": "tool-2", "title": "Execute Command"},
                            "options": [
                                {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                            ],
                        },
                    }
                )

                # Даём время обработать второй permission
                await asyncio.sleep(0.05)

                # Финальный ответ
                response_queue = await queues.get_or_create_response_queue(request_id)
                await response_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"status": "ok"},
                    }
                )

            asyncio.create_task(produce_server_messages())

        transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # type: ignore[union-attr]

        # Mock permission handler для быстрой обработки
        mock_permission_handler = AsyncMock()
        from codelab.client.application.permission_handler import SelectedPermissionOutcome

        mock_permission_handler.handle_request.return_value = SelectedPermissionOutcome(
            outcome="selected",
            optionId="allow",
        )
        service._permission_responder.set_handler(mock_permission_handler)  # noqa: SLF001
        service.set_permission_callback(lambda req: None)

        response = await service.request_with_callbacks(
            method="session/prompt",
            params={"sessionId": "sess-1", "prompt": [{"type": "text", "text": "test"}]},
        )

        assert response["result"]["status"] == "ok"

        # Проверяем что оба permission request были обработаны
        assert mock_permission_handler.handle_request.await_count == 2

        # Проверяем логирование создания нового permission task
        info_events = [call.args[0] for call in service._logger.info.call_args_list if call.args]
        assert "permission_task_created" in info_events
        assert "new_permission_task_created_after_handling" in info_events

    @pytest.mark.asyncio
    async def test_permission_request_during_notification_processing(self) -> None:
        """Permission request не теряется при обработке notification."""
        service = _create_service_for_test()
        service._logger = MagicMock()  # noqa: SLF001 - test setup
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001 - test setup

        transport = service._transport  # noqa: SLF001 - test setup
        sent_messages: list[dict[str, object]] = []

        async def send_str_side_effect(raw_payload: str) -> None:
            payload = json.loads(raw_payload)
            sent_messages.append(payload)

            if payload.get("method") != "session/prompt":
                return

            if not isinstance(payload.get("id"), str | int):
                return
            request_id: str | int = payload["id"]

            async def produce_server_messages() -> None:
                # Notification приходит первым
                await queues.notification_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {"sessionId": "sess-1", "update": {"type": "progress"}},
                    }
                )

                # Permission request приходит во время обработки notification
                await asyncio.sleep(0.02)
                await queues.permission_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": "perm-1",
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": "sess-1",
                            "toolCall": {"toolCallId": "tool-1", "title": "Read File"},
                            "options": [
                                {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                            ],
                        },
                    }
                )

                # Даём время обработать permission
                await asyncio.sleep(0.05)

                # Финальный ответ
                response_queue = await queues.get_or_create_response_queue(request_id)
                await response_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"status": "ok"},
                    }
                )

            asyncio.create_task(produce_server_messages())

        transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # type: ignore[union-attr]

        # Mock permission handler
        mock_permission_handler = AsyncMock()
        from codelab.client.application.permission_handler import SelectedPermissionOutcome

        mock_permission_handler.handle_request.return_value = SelectedPermissionOutcome(
            outcome="selected",
            optionId="allow",
        )
        service._permission_responder.set_handler(mock_permission_handler)  # noqa: SLF001
        service.set_permission_callback(lambda req: None)

        response = await service.request_with_callbacks(
            method="session/prompt",
            params={"sessionId": "sess-1", "prompt": [{"type": "text", "text": "test"}]},
        )

        assert response["result"]["status"] == "ok"

        # Проверяем что permission request был обработан
        assert mock_permission_handler.handle_request.await_count == 1

    @pytest.mark.asyncio
    async def test_permission_task_recreated_immediately(self) -> None:
        """Новый permission task создаётся сразу после обработки предыдущего."""
        service = _create_service_for_test()
        service._logger = MagicMock()  # noqa: SLF001 - test setup
        service._coordinator._logger = service._logger  # noqa: SLF001 - coordinator логи в тот же mock
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001 - test setup

        transport = service._transport  # noqa: SLF001 - test setup
        sent_messages: list[dict[str, object]] = []

        async def send_str_side_effect(raw_payload: str) -> None:
            payload = json.loads(raw_payload)
            sent_messages.append(payload)

            if payload.get("method") != "session/prompt":
                return

            if not isinstance(payload.get("id"), str | int):
                return
            request_id: str | int = payload["id"]

            async def produce_server_messages() -> None:
                # Первый permission request
                await queues.permission_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": "perm-1",
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": "sess-1",
                            "toolCall": {"toolCallId": "tool-1", "title": "Read File"},
                            "options": [
                                {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                            ],
                        },
                    }
                )

                # Второй permission request приходит СРАЗУ после первого
                # (без задержки)
                await queues.permission_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": "perm-2",
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": "sess-1",
                            "toolCall": {"toolCallId": "tool-2", "title": "Execute Command"},
                            "options": [
                                {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                            ],
                        },
                    }
                )

                # Даём время обработать оба permission
                await asyncio.sleep(0.1)

                # Финальный ответ
                response_queue = await queues.get_or_create_response_queue(request_id)
                await response_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"status": "ok"},
                    }
                )

            asyncio.create_task(produce_server_messages())

        transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # type: ignore[union-attr]

        # Mock permission handler
        mock_permission_handler = AsyncMock()
        from codelab.client.application.permission_handler import SelectedPermissionOutcome

        mock_permission_handler.handle_request.return_value = SelectedPermissionOutcome(
            outcome="selected",
            optionId="allow",
        )
        service._permission_responder.set_handler(mock_permission_handler)  # noqa: SLF001
        service.set_permission_callback(lambda req: None)

        response = await service.request_with_callbacks(
            method="session/prompt",
            params={"sessionId": "sess-1", "prompt": [{"type": "text", "text": "test"}]},
        )

        assert response["result"]["status"] == "ok"

        # Проверяем что оба permission request были обработаны
        # Это доказывает что новый task был создан сразу и не потерял сообщение
        assert mock_permission_handler.handle_request.await_count == 2

        # Проверяем логирование: новый task создаётся сразу после обработки
        info_events = [call.args[0] for call in service._logger.info.call_args_list if call.args]
        # Должно быть как минимум 2 создания task (начальное + после обработки)
        permission_task_created_count = info_events.count("permission_task_created")
        assert permission_task_created_count >= 2

    @pytest.mark.asyncio
    async def test_permission_task_cancelled_on_response(self) -> None:
        """Permission task отменяется при получении response.

        Предотвращает осиротевшие tasks которые потребляют сообщения из очереди.
        """
        service = _create_service_for_test()
        service._logger = MagicMock()  # noqa: SLF001 - test setup
        service._coordinator._logger = service._logger  # noqa: SLF001 - coordinator логи в тот же mock
        queues = RoutingQueues()
        service._queues = queues  # noqa: SLF001 - test setup

        transport = service._transport  # noqa: SLF001 - test setup

        async def send_str_side_effect(raw_payload: str) -> None:
            payload = json.loads(raw_payload)

            if payload.get("method") != "session/prompt":
                return

            if not isinstance(payload.get("id"), str | int):
                return
            request_id: str | int = payload["id"]

            async def produce_server_messages() -> None:
                # Response приходит БЕЗ permission requests
                response_queue = await queues.get_or_create_response_queue(request_id)
                await response_queue.put(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"status": "ok"},
                    }
                )

            asyncio.create_task(produce_server_messages())

        transport.send_str = AsyncMock(side_effect=send_str_side_effect)  # type: ignore[union-attr]

        response = await service.request_with_callbacks(
            method="session/prompt",
            params={"sessionId": "sess-1", "prompt": [{"type": "text", "text": "test"}]},
        )

        assert response["result"]["status"] == "ok"

        # Проверяем что permission_task был отменён при завершении response
        info_events = [call.args[0] for call in service._logger.info.call_args_list if call.args]
        assert "cancelling_orphaned_permission_task" in info_events

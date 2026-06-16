"""Тесты для MessageRouter - маршрутизации сообщений."""

from codelab.client.infrastructure.services.message_router import (
    MessageRouter,
)


class TestMessageRouter:
    """Тесты для MessageRouter."""

    def test_route_response_message_with_id(self) -> None:
        """Сообщение с id маршрутизируется как response."""
        router = MessageRouter()
        message = {
            "id": 123,
            "result": {"status": "ok"},
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "response"
        assert routing_key.request_id == 123

    def test_route_response_message_with_error(self) -> None:
        """Сообщение об ошибке с id маршрутизируется как response."""
        router = MessageRouter()
        message = {
            "id": 456,
            "error": {
                "code": -1,
                "message": "Error",
            },
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "response"
        assert routing_key.request_id == 456

    def test_route_notification_session_update(self) -> None:
        """Сообщение session/update без id маршрутизируется как notification."""
        router = MessageRouter()
        message = {
            "method": "session/update",
            "params": {
                "sessionId": "sess-1",
                "status": "ready",
            },
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "notification"
        assert routing_key.request_id is None

    def test_route_notification_session_cancel(self) -> None:
        """Сообщение session/cancel без id маршрутизируется как notification."""
        router = MessageRouter()
        message = {
            "method": "session/cancel",
            "params": {
                "sessionId": "sess-1",
            },
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "notification"
        assert routing_key.request_id is None

    def test_route_permission_request(self) -> None:
        """Сообщение session/request_permission маршрутизируется как permission."""
        router = MessageRouter()
        message = {
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "permission": "read",
            },
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "permission"
        assert routing_key.request_id is None

    def test_route_permission_request_with_id(self) -> None:
        """session/request_permission c id маршрутизируется как permission."""
        router = MessageRouter()
        message = {
            "id": "perm-1",
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
            },
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "permission"
        assert routing_key.request_id is None

    def test_route_fs_rpc_request_with_id(self) -> None:
        """fs/* request c id маршрутизируется в notification queue."""
        router = MessageRouter()
        message = {
            "id": "rpc-1",
            "method": "fs/read_text_file",
            "params": {
                "path": "/tmp/test.txt",
            },
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "notification"
        assert routing_key.request_id is None

    def test_route_unknown_message(self) -> None:
        """Неизвестное сообщение маршрутизируется как unknown."""
        router = MessageRouter()
        message = {
            "method": "unknown/method",
            "data": {},
        }

        routing_key = router.route(message)

        assert routing_key.queue_type == "unknown"
        assert routing_key.request_id is None

    def test_route_empty_message(self) -> None:
        """Пустое сообщение маршрутизируется как unknown."""
        router = MessageRouter()
        message = {}

        routing_key = router.route(message)

        assert routing_key.queue_type == "unknown"

    def test_is_response_with_id(self) -> None:
        """is_response возвращает True для сообщения с id."""
        router = MessageRouter()
        message = {
            "id": 123,
            "result": {},
        }

        assert router.is_response(message) is True

    def test_is_response_without_id(self) -> None:
        """is_response возвращает False для сообщения без id."""
        router = MessageRouter()
        message = {
            "method": "session/update",
        }

        assert router.is_response(message) is False

    def test_is_notification_session_update(self) -> None:
        """is_notification возвращает True для session/update."""
        router = MessageRouter()
        message = {
            "method": "session/update",
        }

        assert router.is_notification(message) is True

    def test_is_notification_session_cancel(self) -> None:
        """is_notification возвращает True для session/cancel."""
        router = MessageRouter()
        message = {
            "method": "session/cancel",
        }

        assert router.is_notification(message) is True

    def test_is_notification_permission_request(self) -> None:
        """is_notification возвращает False для session/request_permission."""
        router = MessageRouter()
        message = {
            "method": "session/request_permission",
        }

        assert router.is_notification(message) is False

    def test_is_notification_response(self) -> None:
        """is_notification возвращает False для response с id."""
        router = MessageRouter()
        message = {
            "id": 123,
            "result": {},
        }

        assert router.is_notification(message) is False

    def test_is_permission_request_true(self) -> None:
        """is_permission_request возвращает True для session/request_permission."""
        router = MessageRouter()
        message = {
            "method": "session/request_permission",
        }

        assert router.is_permission_request(message) is True

    def test_is_permission_request_false_for_response(self) -> None:
        """is_permission_request возвращает False для response."""
        router = MessageRouter()
        message = {
            "id": 123,
            "result": {},
        }

        assert router.is_permission_request(message) is False

    def test_is_permission_request_false_for_update(self) -> None:
        """is_permission_request возвращает False для session/update."""
        router = MessageRouter()
        message = {
            "method": "session/update",
        }

        assert router.is_permission_request(message) is False

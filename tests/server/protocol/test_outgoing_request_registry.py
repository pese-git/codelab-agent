"""Корреляция «исходящий запрос → сессия» (P1-61, шаг 5 ADR-008).

Домен научился помнить несколько незакрытых разрешений, но этого мало: ответ
клиента приходит отдельным сообщением и должен найти **свою** сессию. Раньше
поиск сравнивал единственный `permission_request_id` из документа, поэтому ответ
на любой запрос, кроме последнего, сессию не находил — вторая половина той же
потери.

Гейт держит три вещи:

* запись заводится на границе транспорта, а не в месте создания запроса — иначе
  её минует любой путь отправки, которого мы не предусмотрели;
* записываются **запросы**, а не ответы и нотификации: они ответа не ждут, и
  реестр бы рос;
* закрытый запрос забывается, иначе `session/load` считал бы отвеченное
  разрешение живым.
"""

from __future__ import annotations

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.pending_registry import PendingRequestRegistry
from tests.server._protocol_factory import build_protocol

SESSION = "sess_1"
OTHER = "sess_2"


@pytest.fixture
def protocol_with_registry() -> tuple[ACPProtocol, PendingRequestRegistry]:
    """Протокол и его реестр — шов проверяется на настоящем объекте, не на моке."""
    registry = PendingRequestRegistry()
    return build_protocol(pending_registry=registry), registry


def _permission_request(session_id: str, tool_call_id: str) -> ACPMessage:
    return ACPMessage.request(
        "session/request_permission",
        {
            "sessionId": session_id,
            "toolCall": {"toolCallId": tool_call_id, "title": "t", "kind": "read"},
            "options": [],
        },
    )


class TestOutgoingCorrelation:
    def test_two_concurrent_requests_are_both_findable(self) -> None:
        """Ровно то, чего не умел скан по документу: помнить оба запроса."""
        registry = PendingRequestRegistry()

        registry.record_outgoing("f5614636", SESSION)
        registry.record_outgoing("aaaa1111", SESSION)

        assert registry.session_for("f5614636") == SESSION
        assert registry.session_for("aaaa1111") == SESSION

    def test_requests_of_different_sessions_do_not_mix(self) -> None:
        registry = PendingRequestRegistry()

        registry.record_outgoing("req_a", SESSION)
        registry.record_outgoing("req_b", OTHER)

        assert registry.session_for("req_a") == SESSION
        assert registry.session_for("req_b") == OTHER

    def test_unknown_request_is_not_ours(self) -> None:
        assert PendingRequestRegistry().session_for("посторонний") is None

    def test_closed_request_is_forgotten(self) -> None:
        registry = PendingRequestRegistry()
        registry.record_outgoing("f5614636", SESSION)

        assert registry.forget("f5614636") is True
        assert registry.session_for("f5614636") is None
        assert registry.forget("f5614636") is False

    def test_forgetting_one_keeps_the_other(self) -> None:
        registry = PendingRequestRegistry()
        registry.record_outgoing("f5614636", SESSION)
        registry.record_outgoing("aaaa1111", SESSION)

        registry.forget("f5614636")

        assert registry.session_for("aaaa1111") == SESSION
        assert registry.outstanding_outgoing == 1

    def test_session_can_be_forgotten_wholesale(self) -> None:
        """Отмена закрывает все незакрытые запросы сессии, а не последний."""
        registry = PendingRequestRegistry()
        registry.record_outgoing("req_a", SESSION)
        registry.record_outgoing("req_b", SESSION)
        registry.record_outgoing("req_c", OTHER)

        assert registry.forget_session(SESSION) == 2
        assert registry.session_for("req_a") is None
        assert registry.session_for("req_c") == OTHER


class TestOrphanCheck:
    """`has()` наконец отвечает по существу: до появления писателя он всегда лгал."""

    def test_outstanding_request_is_not_orphan(self) -> None:
        registry = PendingRequestRegistry()
        registry.record_outgoing("f5614636", SESSION)

        assert registry.has("f5614636") is True

    def test_unknown_request_looks_orphaned(self) -> None:
        """После рестарта реестр пуст — и это правильный ответ, а не потеря."""
        assert PendingRequestRegistry().has("f5614636") is False


class TestProtocolSeam:
    """Что именно транспорт отдаёт реестру."""

    def test_request_with_session_is_recorded(
        self, protocol_with_registry: tuple[ACPProtocol, PendingRequestRegistry]
    ) -> None:
        protocol, registry = protocol_with_registry
        message = _permission_request(SESSION, "call_007")

        protocol.record_outgoing_request(message)

        assert registry.session_for(message.id) == SESSION

    def test_notification_is_not_recorded(
        self, protocol_with_registry: tuple[ACPProtocol, PendingRequestRegistry]
    ) -> None:
        """Нотификация ответа не ждёт: записать её значило бы копить мусор."""
        protocol, registry = protocol_with_registry

        protocol.record_outgoing_request(
            ACPMessage.notification("session/update", {"sessionId": SESSION, "update": {}})
        )

        assert registry.outstanding_outgoing == 0

    def test_response_is_not_recorded(
        self, protocol_with_registry: tuple[ACPProtocol, PendingRequestRegistry]
    ) -> None:
        protocol, registry = protocol_with_registry

        protocol.record_outgoing_request(ACPMessage.response("req_1", {"ok": True}))

        assert registry.outstanding_outgoing == 0

    def test_request_without_session_is_skipped(
        self, protocol_with_registry: tuple[ACPProtocol, PendingRequestRegistry]
    ) -> None:
        """Без сессии корреляция бессмысленна — записывать нечего."""
        protocol, registry = protocol_with_registry

        protocol.record_outgoing_request(ACPMessage.request("some/method", {}))

        assert registry.outstanding_outgoing == 0

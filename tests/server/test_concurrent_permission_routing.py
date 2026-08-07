"""Ответ на неактуальное разрешение находит свою сессию (P1-61, шаг 5 ADR-008).

Это вторая половина потери, и без неё домен бесполезен. Сценарий, измеренный
живьём 2026-08-07: два вызова запросили разрешение подряд, ответ пришёл на
**первый**. Документ хранит один `permission_request_id` — последний, — поэтому
поиск сессии сканом по документам первый запрос не находил, и ответ отбрасывался
как «неизвестный запрос».

Гейт держит именно связь: маршрутизация обязана идти через реестр исходящих
запросов, а не через скан. Проверяется на настоящем `ACPProtocol` — подмена
роутера мока́ми проверяла бы наш тест, а не поведение.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from _protocol_factory import build_protocol

from codelab.server.messages import ACPMessage
from codelab.server.protocol import ACPProtocol
from codelab.server.storage.document import ActiveTurnState, SessionDocument, ToolCallState
from codelab.server.storage.memory import InMemoryStorage

SESSION_ID = "sess_concurrent"
FIRST_REQUEST = "f5614636"
SECOND_REQUEST = "aaaa1111"


def _permission_response(request_id: str) -> ACPMessage:
    """Ответ клиента: JSON-RPC response без метода, как приходит из Zed."""
    return ACPMessage(
        id=request_id,
        result={"outcome": {"outcome": "selected", "optionId": "allow_once"}},
    )


@pytest_asyncio.fixture
async def protocol_with_session() -> tuple[ACPProtocol, InMemoryStorage]:
    """Сессия, где два вызова ждут разрешения, а документ помнит только последний.

    Форма документа воспроизводит ровно то, что лежало на диске в прогоне: одно
    поле `permission_request_id`, и в нём — идентификатор **второго** запроса.
    """
    storage = InMemoryStorage()
    protocol = build_protocol(storage=storage)

    session = SessionDocument(
        session_id=SESSION_ID,
        cwd="/tmp",
        mcp_servers=[],
        config_values={"mode": "ask"},
    )
    session.active_turn = ActiveTurnState(
        prompt_request_id="req_1",
        session_id=SESSION_ID,
        permission_request_id=SECOND_REQUEST,
        permission_tool_call_id="call_008",
    )
    for tool_call_id in ("call_007", "call_008"):
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="Read File",
            kind="read",
            status="pending",
            tool_name="fs/read_text_file",
            tool_arguments={"path": "/tmp/a"},
        )
    await storage.save_session(session)
    return protocol, storage


class TestAnswerToTheOlderRequest:
    """Ответ приходит на первый запрос — тот, которого в документе нет."""

    @pytest.mark.asyncio
    async def test_registry_makes_the_older_request_routable(
        self, protocol_with_session: tuple[ACPProtocol, InMemoryStorage]
    ) -> None:
        """Без записи в реестре сессия не находится — с записью находится.

        Первая половина утверждения важна не меньше второй: она показывает, что
        скан по документу этот случай действительно не покрывает, и тест
        проверяет не тавтологию.
        """
        protocol, _ = protocol_with_session

        assert await protocol.handle(_permission_response(FIRST_REQUEST)) is not None
        assert protocol._pending_registry.session_for(FIRST_REQUEST) is None

        protocol.record_outgoing_request(
            ACPMessage(
                id=FIRST_REQUEST,
                method="session/request_permission",
                params={"sessionId": SESSION_ID, "toolCall": {"toolCallId": "call_007"}},
            )
        )

        assert protocol._pending_registry.session_for(FIRST_REQUEST) == SESSION_ID

    @pytest.mark.asyncio
    async def test_recorded_request_is_forgotten_after_the_answer(
        self, protocol_with_session: tuple[ACPProtocol, InMemoryStorage]
    ) -> None:
        """Иначе реестр рос бы всё соединение, а `session/load` считал бы запрос живым."""
        protocol, _ = protocol_with_session
        protocol.record_outgoing_request(
            ACPMessage(
                id=SECOND_REQUEST,
                method="session/request_permission",
                params={"sessionId": SESSION_ID, "toolCall": {"toolCallId": "call_008"}},
            )
        )
        assert protocol._pending_registry.outstanding_outgoing == 1

        await protocol.handle(_permission_response(SECOND_REQUEST))

        assert protocol._pending_registry.session_for(SECOND_REQUEST) is None
        assert protocol._pending_registry.outstanding_outgoing == 0


class TestRegistryIsShared:
    """Писатель и читатель обязаны работать с одним объектом.

    Найдено при написании этого гейта: у `PendingRequestRegistry` есть `__len__`,
    поэтому пустой реестр **ложен**, и идиома `registry or PendingRequestRegistry()`
    молча подменяла переданный экземпляр новым. Транспорт писал бы в один реестр,
    маршрутизация читала бы из другого, и правка не работала бы вовсе — при
    зелёных тестах.
    """

    def test_protocol_and_router_share_the_injected_registry(self) -> None:
        from codelab.server.protocol.pending_registry import PendingRequestRegistry

        registry = PendingRequestRegistry()

        protocol = build_protocol(pending_registry=registry)

        assert protocol._pending_registry is registry
        assert protocol._response_router._pending_registry is registry

    def test_empty_registry_is_falsy_which_is_why_or_was_wrong(self) -> None:
        """Фиксируем причину, а не только следствие: пустой реестр ложен."""
        from codelab.server.protocol.pending_registry import PendingRequestRegistry

        assert not PendingRequestRegistry()

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
    """Сессия, где два вызова ждут разрешения одновременно.

    Это состояние и было невыразимым до шага 5: документ хранил одно поле
    `permission_request_id`, поэтому запись переживало только последнее ожидание.
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
        phase="awaiting_permission",
        permission_waits=[
            {"request_id": FIRST_REQUEST, "tool_call_id": "call_007"},
            {"request_id": SECOND_REQUEST, "tool_call_id": "call_008"},
        ],
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
    """Ответ приходит на первый запрос — не на тот, что заведён последним."""

    @pytest.mark.asyncio
    async def test_older_request_is_applied_and_resumes_its_own_call(
        self, protocol_with_session: tuple[ACPProtocol, InMemoryStorage]
    ) -> None:
        """Главное утверждение: ответ **применяется** и возобновляет свой вызов.

        Именно этого не хватало прежней версии гейта — она проверяла содержимое
        реестра, а не то, что решение доходит до вызова. Ровно здесь и терялся
        `call_008` живьём: сессия либо не находилась, либо находилась с фазой,
        которая о старом запросе уже не знала.
        """
        protocol, _ = protocol_with_session

        outcome = await protocol.handle(_permission_response(FIRST_REQUEST))

        assert outcome.pending_tool_execution is not None
        assert outcome.pending_tool_execution.tool_call_id == "call_007"

    @pytest.mark.asyncio
    async def test_the_other_wait_survives_the_answer(
        self, protocol_with_session: tuple[ACPProtocol, InMemoryStorage]
    ) -> None:
        """Turn обязан продолжать ждать второе решение, а не считать себя разбуженным."""
        protocol, storage = protocol_with_session

        await protocol.handle(_permission_response(FIRST_REQUEST))

        session = await storage.load_session(SESSION_ID)
        assert session is not None
        assert session.active_turn is not None
        assert [w.request_id for w in session.active_turn.permission_waits] == [SECOND_REQUEST]

    @pytest.mark.asyncio
    async def test_both_answers_close_the_turn(
        self, protocol_with_session: tuple[ACPProtocol, InMemoryStorage]
    ) -> None:
        """Оба вызова получают своё решение — ни один не остаётся `pending` навсегда."""
        protocol, storage = protocol_with_session

        first = await protocol.handle(_permission_response(FIRST_REQUEST))
        second = await protocol.handle(_permission_response(SECOND_REQUEST))

        assert first.pending_tool_execution is not None
        assert second.pending_tool_execution is not None
        assert {
            first.pending_tool_execution.tool_call_id,
            second.pending_tool_execution.tool_call_id,
        } == {"call_007", "call_008"}

        session = await storage.load_session(SESSION_ID)
        assert session is not None
        assert session.active_turn is not None
        assert session.active_turn.permission_waits == []
        assert session.active_turn.phase == "running"

    @pytest.mark.asyncio
    async def test_registry_makes_the_older_request_routable(
        self, protocol_with_session: tuple[ACPProtocol, InMemoryStorage]
    ) -> None:
        """Корреляция заводится записью исходящего запроса, а не сканом документа."""
        protocol, _ = protocol_with_session

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

"""Unit-тесты доменного порта `SessionRepository` (каркас D4-d1, ADR-006).

Фиксируют контракт порта и его **behavior-neutrality**: жизненный цикл объектов
остаётся таким же, как у сегодняшнего прод-стека (`JsonFileStorage` без кэша) —
каждый `load_session` отдаёт свежий агрегат, резидентной идентичности нет.
Резидентный кэш — отдельный осознанный шаг D4-d2, здесь его быть не должно.
"""

from codelab.server.domain.conversation import ConversationMessage, Image, MessageContent
from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.value_objects import MessageRole, SessionId
from codelab.server.protocol.state import SessionState
from codelab.server.storage import InMemoryStorage, SessionRepository


def _state(session_id: str = "sess_1", cwd: str = "/tmp") -> SessionState:
    return SessionState(session_id=session_id, cwd=cwd, mcp_servers=[])


class TestDomainTyping:
    """`load_session`/`save_session` — доменные (write-model)."""

    async def test_load_returns_domain_aggregate(self) -> None:
        backend = InMemoryStorage()
        await backend.save_session(_state(cwd="/work"))
        repository = SessionRepository(backend=backend)

        session = await repository.load_session("sess_1")

        assert isinstance(session, Session)
        assert str(session.id) == "sess_1"
        assert session.config.cwd == "/work"

    async def test_load_missing_returns_none(self) -> None:
        repository = SessionRepository(backend=InMemoryStorage())
        assert await repository.load_session("absent") is None

    async def test_save_accepts_domain_aggregate(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        session = Session(id=SessionId("sess_1"), config=SessionConfig(cwd="/work"))

        await repository.save_session(session)

        persisted = await backend.load_session("sess_1")
        assert isinstance(persisted, SessionState)
        assert persisted.cwd == "/work"

    async def test_roundtrip_preserves_rich_domain_state(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)

        session = Session(id=SessionId("sess_rt"), config=SessionConfig(cwd="/work"))
        session.add_message(
            ConversationMessage(
                role=MessageRole.USER,
                content=MessageContent(text="see", images=[Image(data="B64")]),
            )
        )
        session.set_permission_policy("read", "allow_always")
        session.set_config_value("mode", "plan")
        await repository.save_session(session)

        reloaded = await repository.load_session("sess_rt")

        assert reloaded is not None
        assert reloaded.config.cwd == "/work"
        assert reloaded.config.config_values["mode"] == "plan"
        assert reloaded.permissions.policy == {"read": "allow_always"}
        message = reloaded.history.get_messages()[0]
        assert message.content.text == "see"
        assert len(message.content.images) == 1


class TestBehaviorNeutrality:
    """Порт не вводит резидентную идентичность — жизненный цикл как сегодня."""

    async def test_each_load_returns_fresh_aggregate(self) -> None:
        backend = InMemoryStorage()
        await backend.save_session(_state())
        repository = SessionRepository(backend=backend)

        first = await repository.load_session("sess_1")
        second = await repository.load_session("sess_1")

        assert first is not second, "резидентный кэш — шаг D4-d2, здесь его быть не должно"

    async def test_unsaved_mutations_do_not_leak_to_next_load(self) -> None:
        """Мутация без `save` испаряется — так же, как в текущем прод-стеке.

        Это защищает `session/load` (правит cwd/mcp_servers без save) от
        незаявленной смены поведения при switch.
        """
        backend = InMemoryStorage()
        await backend.save_session(_state())
        repository = SessionRepository(backend=backend)

        first = await repository.load_session("sess_1")
        assert first is not None
        first.set_title("не сохранено")

        second = await repository.load_session("sess_1")
        assert second is not None
        assert second.title is None

    async def test_saved_mutations_are_visible(self) -> None:
        backend = InMemoryStorage()
        await backend.save_session(_state())
        repository = SessionRepository(backend=backend)

        first = await repository.load_session("sess_1")
        assert first is not None
        first.set_title("сохранено")
        await repository.save_session(first)

        second = await repository.load_session("sess_1")
        assert second is not None
        assert second.title == "сохранено"


class TestUpdatedAtSync:
    """Backend штампует метку на wire-DTO — вызывающий обязан увидеть её сразу."""

    async def test_save_syncs_storage_stamp_into_domain(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        session = Session(id=SessionId("sess_1"), config=SessionConfig(cwd="/tmp"))
        assert session.updated_at is None

        await repository.save_session(session)

        persisted = await backend.load_session("sess_1")
        assert persisted is not None
        assert session.updated_at is not None
        assert session.updated_at == persisted.updated_at


class TestReadModelProjection:
    """Тезис 3 (ADR-006): `list_sessions` — wire-проекция, не доменная."""

    async def test_list_returns_wire_states(self) -> None:
        backend = InMemoryStorage()
        await backend.save_session(_state(session_id="sess_a"))
        await backend.save_session(_state(session_id="sess_b"))
        repository = SessionRepository(backend=backend)

        sessions, cursor = await repository.list_sessions()

        assert cursor is None
        assert all(isinstance(item, SessionState) for item in sessions)
        assert {item.session_id for item in sessions} == {"sess_a", "sess_b"}


class TestLifecycleDelegation:
    async def test_delete_delegates_to_backend(self) -> None:
        backend = InMemoryStorage()
        await backend.save_session(_state())
        repository = SessionRepository(backend=backend)

        assert await repository.delete_session("sess_1") is True
        assert await repository.load_session("sess_1") is None

    async def test_exists_delegates_to_backend(self) -> None:
        backend = InMemoryStorage()
        await backend.save_session(_state())
        repository = SessionRepository(backend=backend)

        assert await repository.session_exists("sess_1") is True
        assert await repository.session_exists("absent") is False

"""Unit-тесты доменного порта `SessionRepository` (каркас D4-d, ADR-006).

Фиксируют инварианты, на которых держится атомарный switch резидента:
идентичность резидента на cache-hit, конверсия только на границе, wire-проекция
для `list_sessions`, синхронизация storage-метки обратно в домен.
"""

import pytest

from codelab.server.domain.conversation import ConversationMessage, Image, MessageContent
from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.value_objects import MessageRole, SessionId
from codelab.server.protocol.state import SessionState
from codelab.server.storage import InMemoryStorage, SessionRepository


def _state(session_id: str = "sess_1", cwd: str = "/tmp") -> SessionState:
    return SessionState(session_id=session_id, cwd=cwd, mcp_servers=[])


async def _seed(repository: SessionRepository, backend: InMemoryStorage, **kwargs) -> None:
    """Положить wire-состояние в backend, минуя репозиторий."""
    await backend.save_session(_state(**kwargs))


class TestResidentIdentity:
    """Тезис 1 (ADR-006): кэш держит домен, cache-hit возвращает ТОТ ЖЕ объект."""

    async def test_cache_hit_returns_same_object(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend)

        first = await repository.load_session("sess_1")
        second = await repository.load_session("sess_1")

        assert first is not None
        assert first is second, "cache-hit обязан вернуть тот же резидент (иначе split-brain)"

    async def test_mutation_visible_through_second_load(self) -> None:
        """In-place-мутация одного участка turn'а видна другому."""
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend)

        first = await repository.load_session("sess_1")
        assert first is not None
        first.set_title("Моя сессия")

        second = await repository.load_session("sess_1")
        assert second is not None
        assert second.title == "Моя сессия"

    async def test_save_keeps_same_resident(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        session = Session(id=SessionId("sess_1"), config=SessionConfig(cwd="/tmp"))

        await repository.save_session(session)
        loaded = await repository.load_session("sess_1")

        assert loaded is session

    async def test_conversion_only_on_cache_miss(self) -> None:
        """Повторный load не ходит в backend (значит, и не конвертирует заново)."""
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend)

        calls = 0
        original = backend.load_session

        async def counting_load(session_id: str):
            nonlocal calls
            calls += 1
            return await original(session_id)

        backend.load_session = counting_load  # type: ignore[method-assign]

        await repository.load_session("sess_1")
        await repository.load_session("sess_1")

        assert calls == 1


class TestDomainTyping:
    """`load_session`/`save_session` — доменные (write-model)."""

    async def test_load_returns_domain_aggregate(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend, cwd="/work")

        session = await repository.load_session("sess_1")

        assert isinstance(session, Session)
        assert str(session.id) == "sess_1"
        assert session.config.cwd == "/work"

    async def test_load_missing_returns_none(self) -> None:
        repository = SessionRepository(backend=InMemoryStorage())
        assert await repository.load_session("absent") is None

    async def test_roundtrip_preserves_rich_domain_state(self) -> None:
        """Сохранение и повторная загрузка с чистым кэшем не теряют тело сессии."""
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

        # Свежий репозиторий поверх того же backend — гарантированный cache-miss.
        reloaded = await SessionRepository(backend=backend).load_session("sess_rt")

        assert reloaded is not None
        assert reloaded.config.cwd == "/work"
        assert reloaded.config.config_values["mode"] == "plan"
        assert reloaded.permissions.policy == {"read": "allow_always"}
        message = reloaded.history.get_messages()[0]
        assert message.content.text == "see"
        assert len(message.content.images) == 1


class TestUpdatedAtSync:
    """Storage штампует метку на wire-DTO — резидент не должен разъезжаться с диском."""

    async def test_save_syncs_storage_stamp_into_domain(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        session = Session(id=SessionId("sess_1"), config=SessionConfig(cwd="/tmp"))
        assert session.updated_at is None

        await repository.save_session(session)

        persisted = await backend.load_session("sess_1")
        assert persisted is not None
        assert session.updated_at == persisted.updated_at
        assert session.updated_at is not None


class TestReadModelProjection:
    """Тезис 3 (ADR-006): `list_sessions` — wire-проекция, не доменная."""

    async def test_list_returns_wire_states(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend, session_id="sess_a")
        await _seed(repository, backend, session_id="sess_b")

        sessions, cursor = await repository.list_sessions()

        assert cursor is None
        assert all(isinstance(item, SessionState) for item in sessions)
        assert {item.session_id for item in sessions} == {"sess_a", "sess_b"}


class TestCacheLifecycle:
    async def test_delete_invalidates_cache(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend)
        await repository.load_session("sess_1")
        assert repository.cache_size == 1

        deleted = await repository.delete_session("sess_1")

        assert deleted is True
        assert repository.cache_size == 0
        assert await repository.load_session("sess_1") is None

    async def test_exists_uses_cache_then_backend(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend)
        await _seed(repository, backend)

        assert await repository.session_exists("sess_1") is True
        assert await repository.session_exists("absent") is False

    async def test_lru_evicts_oldest(self) -> None:
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend, max_size=2)
        for session_id in ("sess_a", "sess_b", "sess_c"):
            await _seed(repository, backend, session_id=session_id)
            await repository.load_session(session_id)

        assert repository.cache_size == 2
        # sess_a вытеснен, но остаётся доступен через backend (уже другой объект).
        evicted = await repository.load_session("sess_a")
        assert evicted is not None

    async def test_evicted_session_reloads_from_backend(self) -> None:
        """После вытеснения резидент пересобирается — несохранённые мутации теряются."""
        backend = InMemoryStorage()
        repository = SessionRepository(backend=backend, max_size=1)
        await _seed(repository, backend, session_id="sess_a")
        await _seed(repository, backend, session_id="sess_b")

        first = await repository.load_session("sess_a")
        assert first is not None
        first.set_title("не сохранено")
        await repository.load_session("sess_b")

        reloaded = await repository.load_session("sess_a")
        assert reloaded is not first
        assert reloaded is not None
        assert reloaded.title is None


@pytest.mark.parametrize("max_size", [1, 5, 200])
def test_cache_starts_empty(max_size: int) -> None:
    repository = SessionRepository(backend=InMemoryStorage(), max_size=max_size)
    assert repository.cache_size == 0

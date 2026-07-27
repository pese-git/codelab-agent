"""DI отдаёт `SessionRepository` рядом с `SessionStorage` (шаг 0 D4-d1, ADR-006).

Параллельная выдача обоих типов — транзитивный механизм миграции: прикладные пути
переезжают на доменный порт по одному. Безопасна потому, что резидентного кэша нет
и транзакции не делят объект сессии в памяти (только диск).
"""

import pytest

from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.domain.session import Session
from codelab.server.protocol.state import SessionState
from codelab.server.storage import SessionRepository, SessionStorage
from codelab.server.storage.memory import InMemoryStorage


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


class TestSessionRepositoryWiring:
    async def test_container_resolves_repository(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        container = make_container(config, storage)
        async with container() as request_container:
            repository = await request_container.get(SessionRepository)
            assert isinstance(repository, SessionRepository)

    async def test_container_still_resolves_storage(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        """Wire-порт остаётся доступен, пока не переехали все прикладные пути."""
        container = make_container(config, storage)
        async with container() as request_container:
            assert await request_container.get(SessionStorage) is storage

    async def test_repository_shares_the_same_backend(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        """Оба порта смотрят в один backend — записанное через один видно другому."""
        await storage.save_session(SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[]))

        container = make_container(config, storage)
        async with container() as request_container:
            repository = await request_container.get(SessionRepository)
            session = await repository.load_session("sess_1")

        assert isinstance(session, Session)
        assert str(session.id) == "sess_1"
        assert session.config.cwd == "/tmp"

    async def test_write_through_repository_visible_via_storage(
        self, config: AppConfig, storage: InMemoryStorage
    ) -> None:
        await storage.save_session(SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[]))

        container = make_container(config, storage)
        async with container() as request_container:
            repository = await request_container.get(SessionRepository)
            session = await repository.load_session("sess_1")
            assert session is not None
            session.set_title("через порт")
            await repository.save_session(session)

        persisted = await storage.load_session("sess_1")
        assert persisted is not None
        assert persisted.title == "через порт"

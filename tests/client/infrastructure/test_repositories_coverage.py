"""Тесты покрытия для InMemorySessionRepository.

Покрывает все методы in-memory реализации SessionRepository.
"""

from __future__ import annotations

import pytest

from codelab.client.domain.entities import Session
from codelab.client.infrastructure.repositories import InMemorySessionRepository


@pytest.fixture
def repository() -> InMemorySessionRepository:
    """Создать пустой репозиторий."""
    return InMemorySessionRepository()


@pytest.fixture
def sample_session() -> Session:
    """Пример сессии."""
    return Session.create(
        server_host="localhost",
        server_port=8765,
        client_capabilities={"fs": True},
        server_capabilities={"tools": True},
        session_id="sess-001",
    )


class TestInMemorySessionRepository:
    """Тесты InMemorySessionRepository."""

    async def test_save_stores_session(
        self,
        repository: InMemorySessionRepository,
        sample_session: Session,
    ) -> None:
        """save сохраняет сессию в памяти."""
        await repository.save(sample_session)

        assert repository._sessions[sample_session.id] is sample_session

    async def test_load_existing_session(
        self,
        repository: InMemorySessionRepository,
        sample_session: Session,
    ) -> None:
        """load возвращает сохранённую сессию."""
        await repository.save(sample_session)

        loaded = await repository.load(sample_session.id)

        assert loaded is sample_session

    async def test_load_missing_session_returns_none(
        self,
        repository: InMemorySessionRepository,
    ) -> None:
        """load возвращает None для отсутствующей сессии."""
        loaded = await repository.load("missing")

        assert loaded is None

    async def test_delete_removes_session(
        self,
        repository: InMemorySessionRepository,
        sample_session: Session,
    ) -> None:
        """delete удаляет сохранённую сессию."""
        await repository.save(sample_session)
        await repository.delete(sample_session.id)

        assert await repository.load(sample_session.id) is None

    async def test_delete_missing_session_is_noop(
        self,
        repository: InMemorySessionRepository,
    ) -> None:
        """delete не падает для отсутствующей сессии."""
        await repository.delete("missing")

        assert repository._sessions == {}

    async def test_list_all_returns_sessions(
        self,
        repository: InMemorySessionRepository,
        sample_session: Session,
    ) -> None:
        """list_all возвращает список всех сессий."""
        await repository.save(sample_session)

        sessions = await repository.list_all()

        assert sessions == [sample_session]

    async def test_list_all_empty(
        self,
        repository: InMemorySessionRepository,
    ) -> None:
        """list_all возвращает пустой список."""
        sessions = await repository.list_all()

        assert sessions == []

    async def test_exists_true(
        self,
        repository: InMemorySessionRepository,
        sample_session: Session,
    ) -> None:
        """exists возвращает True для сохранённой сессии."""
        await repository.save(sample_session)

        assert await repository.exists(sample_session.id) is True

    async def test_exists_false(
        self,
        repository: InMemorySessionRepository,
    ) -> None:
        """exists возвращает False для отсутствующей сессии."""
        assert await repository.exists("missing") is False

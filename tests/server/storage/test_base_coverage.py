"""Тесты покрытия абстрактных методов SessionStorage."""

from __future__ import annotations

from codelab.server.protocol.state import SessionState
from codelab.server.storage.base import SessionStorage


class ConcreteSessionStorage(SessionStorage):
    """Конкретная реализация для покрытия абстрактных методов."""

    async def save_session(self, session: SessionState) -> None:
        await super().save_session(session)

    async def load_session(self, session_id: str) -> SessionState | None:
        return await super().load_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        return await super().delete_session(session_id)

    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionState], str | None]:
        return await super().list_sessions(cwd=cwd, cursor=cursor, limit=limit)

    async def session_exists(self, session_id: str) -> bool:
        return await super().session_exists(session_id)


class TestSessionStorageAbstractMethods:
    """Тесты вызова абстрактных методов базового класса."""

    async def test_save_session_pass_executed(self) -> None:
        """Абстрактный save_session возвращает None через pass."""
        storage = ConcreteSessionStorage()
        session = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])
        result = await storage.save_session(session)
        assert result is None

    async def test_load_session_pass_executed(self) -> None:
        """Абстрактный load_session возвращает None через pass."""
        storage = ConcreteSessionStorage()
        result = await storage.load_session("s1")
        assert result is None

    async def test_delete_session_pass_executed(self) -> None:
        """Абстрактный delete_session возвращает None через pass."""
        storage = ConcreteSessionStorage()
        result = await storage.delete_session("s1")
        assert result is None

    async def test_list_sessions_pass_executed(self) -> None:
        """Абстрактный list_sessions возвращает None через pass."""
        storage = ConcreteSessionStorage()
        result = await storage.list_sessions()
        assert result is None

    async def test_session_exists_pass_executed(self) -> None:
        """Абстрактный session_exists возвращает None через pass."""
        storage = ConcreteSessionStorage()
        result = await storage.session_exists("s1")
        assert result is None

"""Unit-тесты для InMemoryStorage."""

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.storage import InMemoryStorage


@pytest.mark.asyncio
async def test_save_and_load_session() -> None:
    """Тест сохранения и загрузки сессии."""
    storage = InMemoryStorage()
    session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

    await storage.save_session(session)
    loaded = await storage.load_session("sess_1")

    assert loaded is not None
    assert loaded.session_id == "sess_1"
    assert loaded.cwd == "/tmp"


@pytest.mark.asyncio
async def test_load_nonexistent_session() -> None:
    """Тест загрузки несуществующей сессии."""
    storage = InMemoryStorage()
    loaded = await storage.load_session("nonexistent")
    assert loaded is None


@pytest.mark.asyncio
async def test_delete_session() -> None:
    """Тест удаления сессии."""
    storage = InMemoryStorage()
    session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

    await storage.save_session(session)
    deleted = await storage.delete_session("sess_1")
    assert deleted is True

    loaded = await storage.load_session("sess_1")
    assert loaded is None


@pytest.mark.asyncio
async def test_delete_nonexistent_session() -> None:
    """Тест удаления несуществующей сессии."""
    storage = InMemoryStorage()
    deleted = await storage.delete_session("nonexistent")
    assert deleted is False


@pytest.mark.asyncio
async def test_session_exists() -> None:
    """Тест проверки существования сессии."""
    storage = InMemoryStorage()
    session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

    assert not await storage.session_exists("sess_1")
    await storage.save_session(session)
    assert await storage.session_exists("sess_1")


@pytest.mark.asyncio
async def test_list_sessions_empty() -> None:
    """Тест получения пустого списка сессий."""
    storage = InMemoryStorage()
    sessions, cursor = await storage.list_sessions()

    assert sessions == []
    assert cursor is None


@pytest.mark.asyncio
async def test_list_sessions() -> None:
    """Тест получения списка сессий."""
    storage = InMemoryStorage()
    session1 = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
    session2 = SessionState(session_id="sess_2", cwd="/home", mcp_servers=[])

    await storage.save_session(session1)
    await storage.save_session(session2)

    sessions, cursor = await storage.list_sessions()
    assert len(sessions) == 2
    assert cursor is None


@pytest.mark.asyncio
async def test_list_sessions_with_cwd_filter() -> None:
    """Тест фильтрации сессий по рабочей директории."""
    storage = InMemoryStorage()
    session1 = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
    session2 = SessionState(session_id="sess_2", cwd="/home", mcp_servers=[])

    await storage.save_session(session1)
    await storage.save_session(session2)

    sessions, cursor = await storage.list_sessions(cwd="/tmp")
    assert len(sessions) == 1
    assert sessions[0].session_id == "sess_1"


@pytest.mark.asyncio
async def test_list_sessions_pagination() -> None:
    """Тест пагинации при получении списка сессий."""
    storage = InMemoryStorage()

    # Создаем 5 сессий
    for i in range(5):
        session = SessionState(session_id=f"sess_{i}", cwd="/tmp", mcp_servers=[])
        await storage.save_session(session)

    # Получаем первую страницу с лимитом 2
    page1, cursor1 = await storage.list_sessions(limit=2)
    assert len(page1) == 2
    assert cursor1 is not None

    # Получаем вторую страницу
    page2, cursor2 = await storage.list_sessions(cursor=cursor1, limit=2)
    assert len(page2) == 2
    assert cursor2 is not None

    # Проверяем, что идентификаторы не повторяются
    ids1 = {s.session_id for s in page1}
    ids2 = {s.session_id for s in page2}
    assert len(ids1 & ids2) == 0


@pytest.mark.asyncio
async def test_list_sessions_sorted_by_updated_at() -> None:
    """Тест сортировки сессий по updated_at (новые первыми)."""
    storage = InMemoryStorage()
    session1 = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

    await storage.save_session(session1)
    # Сохраняем первую сессию, затем вторую - вторая должна быть "новее"
    session2 = SessionState(session_id="sess_2", cwd="/tmp", mcp_servers=[])
    await storage.save_session(session2)

    sessions, _ = await storage.list_sessions()
    # Новая сессия должна быть первой
    assert sessions[0].session_id == "sess_2"
    assert sessions[1].session_id == "sess_1"


@pytest.mark.asyncio
async def test_update_session_updates_timestamp() -> None:
    """Тест обновления временной метки при сохранении."""
    storage = InMemoryStorage()
    session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
    original_time = session.updated_at

    await storage.save_session(session)
    loaded = await storage.load_session("sess_1")

    assert loaded is not None
    # Временная метка должна быть обновлена
    assert loaded.updated_at != original_time
    # И она должна быть более свежей
    assert loaded.updated_at > original_time

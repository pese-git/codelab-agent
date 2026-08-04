"""Unit-тесты для session_set_mode handler.

Тестирует:
- Валидация modeId (valid, invalid, old-mode normalization)
- current_mode_update notification
- Session not found
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.config import session_set_mode
from codelab.server.storage import InMemoryStorage, SessionRepository
from codelab.server.storage.document import SessionDocument


async def _make_repository(session: SessionDocument | None = None) -> SessionRepository:
    """Репозиторий над реальным backend'ом с опционально засеянной сессией.

    Транзакция config работает доменным агрегатом (фаза D ADR-006), поэтому
    мутирует не переданный wire-объект, а свою копию: проверять нужно
    сохранённое состояние, а не объект-аргумент. Реальный backend вместо мока
    заодно прогоняет конверсию wire↔domain на настоящем мапперe.
    """
    backend = InMemoryStorage()
    if session is not None:
        await backend.save_session(session)
    return SessionRepository(backend=backend)


async def _reloaded(repository: SessionRepository, session_id: str = "sess_1"):
    """Сессия, перечитанная из репозитория."""
    saved = await repository.load_session(session_id)
    assert saved is not None
    return saved


async def _saved_mode(repository: SessionRepository, session_id: str = "sess_1") -> str | None:
    """Значение `mode` в сохранённой сессии."""
    saved = await repository.load_session(session_id)
    assert saved is not None
    return saved.get_config_value("mode")


def _make_config_specs():
    """Создать config_specs с mode опцией."""
    return {
        "mode": {
            "id": "mode",
            "name": "Mode",
            "category": "mode",
            "type": "select",
            "default": "standard",
            "options": [
                {"value": "plan", "name": "Plan"},
                {"value": "standard", "name": "Standard"},
                {"value": "bypass", "name": "Bypass"},
            ],
        },
    }


class TestSessionSetModeValidModes:
    """Тесты установки валидных mode."""

    @pytest.mark.asyncio
    async def test_set_mode_plan(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "plan"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "plan"
        # Проверяем current_mode_update через session/update
        mode_update = next(
            (
                n
                for n in outcome.notifications
                if n.method == "session/update"
                and n.params is not None
                and n.params.get("update", {}).get("sessionUpdate") == "current_mode_update"
            ),
            None,
        )
        assert mode_update is not None
        assert mode_update.params["update"]["currentModeId"] == "plan"

    @pytest.mark.asyncio
    async def test_set_mode_standard(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "standard"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "standard"

    @pytest.mark.asyncio
    async def test_set_mode_bypass(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "bypass"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "bypass"


class TestSessionSetModeOldModeNormalization:
    """Тесты нормализации старых mode значений."""

    @pytest.mark.asyncio
    async def test_old_mode_ask_normalizes_to_standard(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "ask"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "standard"
        # Проверяем current_mode_update через session/update
        mode_update = next(
            (
                n
                for n in outcome.notifications
                if n.method == "session/update"
                and n.params is not None
                and n.params.get("update", {}).get("sessionUpdate") == "current_mode_update"
            ),
            None,
        )
        assert mode_update is not None
        assert mode_update.params["update"]["currentModeId"] == "standard"

    @pytest.mark.asyncio
    async def test_old_mode_code_normalizes_to_bypass(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "code"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "bypass"

    @pytest.mark.asyncio
    async def test_old_mode_architect_normalizes_to_plan(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "architect"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "plan"

    @pytest.mark.asyncio
    async def test_old_mode_debug_normalizes_to_standard(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "debug"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert await _saved_mode(repository) == "standard"


class TestSessionSetModeInvalid:
    """Тесты невалидных modeId."""

    @pytest.mark.asyncio
    async def test_invalid_mode_id(self) -> None:
        session = SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        repository = await _make_repository(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "unknown_mode"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602
        assert "modeId must be one of" in outcome.response.error.message

    @pytest.mark.asyncio
    async def test_missing_session_id(self) -> None:
        repository = await _make_repository()
        outcome = await session_set_mode(
            "req_1",
            {"modeId": "plan"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602

    @pytest.mark.asyncio
    async def test_missing_mode_id(self) -> None:
        repository = await _make_repository()
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602

    @pytest.mark.asyncio
    async def test_session_not_found(self) -> None:
        repository = await _make_repository()
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "nonexistent", "modeId": "plan"},
            repository,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32001
        assert "Session not found" in outcome.response.error.message


class TestConfigObservability:
    """Наблюдаемость config-транзакции (фаза D ADR-006).

    До этого успешная смена опции не логировала ничего, и переключение
    транзакции на доменный агрегат нельзя было подтвердить живым прогоном —
    только сверкой файла сессии.
    """

    @pytest.mark.asyncio
    async def test_successful_change_is_logged(self) -> None:
        import structlog

        session = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "standard", "model": "openai/gpt"},
        )
        repository = await _make_repository(session)

        with structlog.testing.capture_logs() as logs:
            outcome = await session_set_mode(
                "req_1",
                {"sessionId": "sess_1", "modeId": "plan"},
                repository,
                _make_config_specs(),
            )

        assert outcome.response is not None
        entry = next(log for log in logs if log["event"] == "session_config_option_changed")
        assert entry["config_id"] == "mode"
        assert entry["value"] == "plan"
        # Метка после save — та же, что ушла на диск и в session_info-нотификацию
        assert entry["updated_at"] == (await _reloaded(repository)).updated_at
        # Сторонние ключи config_values не теряются доменным round-trip'ом
        assert entry["config_values"] == 2

    @pytest.mark.asyncio
    async def test_missing_session_is_logged(self) -> None:
        import structlog

        repository = await _make_repository()

        with structlog.testing.capture_logs() as logs:
            outcome = await session_set_mode(
                "req_1",
                {"sessionId": "sess_absent", "modeId": "plan"},
                repository,
                _make_config_specs(),
            )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert any(
            log["event"] == "session_config_option_session_not_found" for log in logs
        )

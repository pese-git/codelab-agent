"""Тесты для SessionFactory.

Проверяют корректную работу фабрики при создании новых сессий.
"""

import pytest

from codelab.server.exceptions import ValidationError
from codelab.server.protocol.session_factory import SessionFactory
from codelab.server.protocol.state import SessionState


class TestSessionFactoryCreateSession:
    """Тесты метода create_session."""

    def test_create_session_with_minimal_params(self, tmp_path) -> None:
        """Тест создания сессии с минимальными параметрами."""
        # Подготовка
        cwd = str(tmp_path)

        # Действие
        session = SessionFactory.create_session(cwd=cwd)

        # Проверка
        assert isinstance(session, SessionState)
        assert session.cwd == cwd
        assert session.session_id is not None
        assert session.session_id.startswith("sess_")
        assert session.mcp_servers == []
        assert session.config_values == {}
        assert session.available_commands == []
        assert session.runtime_capabilities is None

    def test_create_session_with_all_params(self, tmp_path) -> None:
        """Тест создания сессии со всеми параметрами."""
        # Подготовка
        cwd = str(tmp_path)
        mcp_servers = [{"name": "test-server", "command": "python"}]
        config_values = {"mode": "code", "model": "gpt-4"}
        available_commands = [{"id": "cmd1", "name": "Test"}]

        # Действие
        session = SessionFactory.create_session(
            cwd=cwd,
            mcp_servers=mcp_servers,
            config_values=config_values,
            available_commands=available_commands,
        )

        # Проверка
        assert session.cwd == cwd
        assert session.mcp_servers == mcp_servers
        assert session.config_values == config_values
        assert session.available_commands == available_commands

    def test_create_session_autogenerates_session_id(self, tmp_path) -> None:
        """Тест автогенерации session_id."""
        # Подготовка
        cwd = str(tmp_path)

        # Действие
        session1 = SessionFactory.create_session(cwd=cwd)
        session2 = SessionFactory.create_session(cwd=cwd)

        # Проверка
        assert session1.session_id != session2.session_id
        assert session1.session_id.startswith("sess_")
        assert session2.session_id.startswith("sess_")

    def test_create_session_custom_session_id(self, tmp_path) -> None:
        """Тест создания сессии с кастомным session_id."""
        # Подготовка
        cwd = str(tmp_path)
        custom_id = "custom_session_123"

        # Действие
        session = SessionFactory.create_session(
            cwd=cwd,
            session_id=custom_id,
        )

        # Проверка
        assert session.session_id == custom_id

    def test_create_session_filters_non_dict_mcp_servers(self, tmp_path) -> None:
        """Тест фильтрации не-dict серверов MCP."""
        # Подготовка
        cwd = str(tmp_path)
        # Передаём только допустимые dict элементы
        mcp_servers = [
            {"name": "server1"},
            {"name": "server2"},
        ]

        # Действие
        session = SessionFactory.create_session(
            cwd=cwd,
            mcp_servers=mcp_servers,
        )

        # Проверка
        assert len(session.mcp_servers) == 2
        assert session.mcp_servers[0] == {"name": "server1"}
        assert session.mcp_servers[1] == {"name": "server2"}

    def test_create_session_empty_mcp_servers(self, tmp_path) -> None:
        """Тест с пустым списком MCP-серверов."""
        # Подготовка
        cwd = str(tmp_path)

        # Действие
        session = SessionFactory.create_session(
            cwd=cwd,
            mcp_servers=[],
        )

        # Проверка
        assert session.mcp_servers == []

    def test_create_session_none_mcp_servers(self, tmp_path) -> None:
        """Тест с None вместо MCP-серверов."""
        # Подготовка
        cwd = str(tmp_path)

        # Действие
        session = SessionFactory.create_session(
            cwd=cwd,
            mcp_servers=None,
        )

        # Проверка
        assert session.mcp_servers == []

    def test_create_session_timestamp_fields(self, tmp_path) -> None:
        """Тест наличия временных меток при создании."""
        # Подготовка
        cwd = str(tmp_path)

        # Действие
        session = SessionFactory.create_session(cwd=cwd)

        # Проверка
        assert session.updated_at is not None
        assert isinstance(session.updated_at, str)


class TestSessionFactoryValidateParams:
    """Тесты метода validate_session_params."""

    def test_validate_valid_params(self, tmp_path) -> None:
        """Тест валидации корректных параметров."""
        # Подготовка
        params = {
            "cwd": str(tmp_path),
            "mcp_servers": [{"name": "test"}],
            "config_values": {"mode": "code"},
        }

        # Действие и проверка (не должно быть исключения)
        SessionFactory.validate_session_params(params)

    def test_validate_missing_cwd(self) -> None:
        """Тест ошибки при отсутствии cwd."""
        # Подготовка
        params = {
            "mcp_servers": [],
        }

        # Действие и проверка
        with pytest.raises(ValidationError, match="cwd обязателен"):
            SessionFactory.validate_session_params(params)

    def test_validate_non_string_cwd(self) -> None:
        """Тест ошибки при cwd не строка."""
        # Подготовка
        params = {
            "cwd": 123,
        }

        # Действие и проверка
        with pytest.raises(ValidationError, match="cwd обязателен"):
            SessionFactory.validate_session_params(params)

    def test_validate_non_list_mcp_servers(self) -> None:
        """Тест ошибки при mcp_servers не список."""
        # Подготовка
        params = {
            "cwd": "/tmp",
            "mcp_servers": "not a list",
        }

        # Действие и проверка
        with pytest.raises(ValidationError, match="mcp_servers должен быть списком"):
            SessionFactory.validate_session_params(params)

    def test_validate_non_dict_config_values(self) -> None:
        """Тест ошибки при config_values не dict."""
        # Подготовка
        params = {
            "cwd": "/tmp",
            "config_values": "not a dict",
        }

        # Действие и проверка
        with pytest.raises(ValidationError, match="config_values должен быть dict"):
            SessionFactory.validate_session_params(params)

    def test_validate_none_mcp_servers(self, tmp_path) -> None:
        """Тест валидации None для mcp_servers (допустимо)."""
        # Подготовка
        params = {
            "cwd": str(tmp_path),
            "mcp_servers": None,
        }

        # Действие и проверка (не должно быть исключения)
        SessionFactory.validate_session_params(params)

    def test_validate_none_config_values(self, tmp_path) -> None:
        """Тест валидации None для config_values (допустимо)."""
        # Подготовка
        params = {
            "cwd": str(tmp_path),
            "config_values": None,
        }

        # Действие и проверка (не должно быть исключения)
        SessionFactory.validate_session_params(params)

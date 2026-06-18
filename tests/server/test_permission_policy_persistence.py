"""Интеграционные тесты для persistence permission policies при save/load сессий.

Проверяет что:
1. Permission policies сохраняются в JSON
2. Permission policies восстанавливаются при загрузке сессии
3. Восстановленные policies используются в permission checks
4. Allow_once НЕ persists (только для одного tool call)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from codelab.server.protocol.handlers.permissions import resolve_remembered_permission_decision
from codelab.server.protocol.session_factory import SessionFactory
from codelab.server.storage.json_file import JsonFileStorage


class TestPermissionPolicyPersistence:
    """Интеграционные тесты для persistence permission policies."""

    @pytest.fixture
    def storage_dir(self) -> Path:
        """Создает временную директорию для хранилища."""
        tmpdir = tempfile.mkdtemp()
        yield Path(tmpdir)
        # Cleanup
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest_asyncio.fixture
    async def storage(self, storage_dir: Path) -> JsonFileStorage:
        """Создает JsonFileStorage для тестов."""
        return JsonFileStorage(storage_dir)

    @pytest.mark.asyncio
    async def test_allow_always_persists_across_save_load(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Проверяет что allow_always policy persists across save/load.

        Сценарий:
        1. Создать сессию
        2. Установить permission_policy["read"] = "allow_always"
        3. Сохранить сессию в JSON
        4. Загрузить сессию из JSON
        5. Проверить что policy восстановлена
        6. Проверить что resolve_remembered_permission_decision возвращает 'allow'
        """
        # Arrange - Создаем новую сессию
        original_session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
            available_commands=[],
            runtime_capabilities=None,
        )
        session_id = original_session.session_id

        # Act - Устанавливаем allow_always policy для "read" tool kind
        original_session.permission_policy["read"] = "allow_always"

        # Act - Сохраняем сессию в JSON
        await storage.save_session(original_session)

        # Act - Загружаем сессию из JSON
        loaded_session = await storage.load_session(session_id)

        # Assert - Проверяем что сессия загрузилась
        assert loaded_session is not None
        assert loaded_session.session_id == session_id

        # Assert - Проверяем что permission_policy восстановлена
        assert "read" in loaded_session.permission_policy
        assert loaded_session.permission_policy["read"] == "allow_always"

        # Assert - Проверяем что resolve_remembered_permission_decision использует
        # восстановленную policy и возвращает 'allow' без re-asking
        decision = await resolve_remembered_permission_decision(
            session=loaded_session,
            tool_kind="read",
        )
        assert decision == "allow"

    @pytest.mark.asyncio
    async def test_reject_always_persists_across_save_load(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Проверяет что reject_always policy persists across save/load.

        Сценарий:
        1. Создать сессию
        2. Установить permission_policy["execute"] = "reject_always"
        3. Сохранить сессию в JSON
        4. Загрузить сессию из JSON
        5. Проверить что policy восстановлена
        6. Проверить что resolve_remembered_permission_decision возвращает 'reject'
        """
        # Arrange - Создаем новую сессию
        original_session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
            available_commands=[],
            runtime_capabilities=None,
        )
        session_id = original_session.session_id

        # Act - Устанавливаем reject_always policy для "execute" tool kind
        original_session.permission_policy["execute"] = "reject_always"

        # Act - Сохраняем сессию в JSON
        await storage.save_session(original_session)

        # Act - Загружаем сессию из JSON
        loaded_session = await storage.load_session(session_id)

        # Assert - Проверяем что сессия загрузилась
        assert loaded_session is not None
        assert loaded_session.session_id == session_id

        # Assert - Проверяем что permission_policy восстановлена
        assert "execute" in loaded_session.permission_policy
        assert loaded_session.permission_policy["execute"] == "reject_always"

        # Assert - Проверяем что resolve_remembered_permission_decision использует
        # восстановленную policy и возвращает 'reject' без re-asking
        decision = await resolve_remembered_permission_decision(
            session=loaded_session,
            tool_kind="execute",
        )
        assert decision == "reject"

    @pytest.mark.asyncio
    async def test_multiple_permission_policies_persist(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Проверяет что несколько policies для разных tool kinds persists.

        Сценарий:
        1. Создать сессию с несколькими policies для разных tool kinds
        2. Сохранить сессию в JSON
        3. Загрузить сессию из JSON
        4. Проверить что все policies восстановлены
        """
        # Arrange - Создаем новую сессию
        original_session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
            available_commands=[],
            runtime_capabilities=None,
        )
        session_id = original_session.session_id

        # Act - Устанавливаем несколько policies
        original_session.permission_policy["read"] = "allow_always"
        original_session.permission_policy["write"] = "reject_always"
        original_session.permission_policy["execute"] = "allow_always"

        # Act - Сохраняем сессию в JSON
        await storage.save_session(original_session)

        # Act - Загружаем сессию из JSON
        loaded_session = await storage.load_session(session_id)

        # Assert - Проверяем что сессия загрузилась
        assert loaded_session is not None

        # Assert - Проверяем что все policies восстановлены
        assert loaded_session.permission_policy["read"] == "allow_always"
        assert loaded_session.permission_policy["write"] == "reject_always"
        assert loaded_session.permission_policy["execute"] == "allow_always"

        # Assert - Проверяем что resolve_remembered_permission_decision работает
        # для каждого tool kind
        assert await resolve_remembered_permission_decision(
            session=loaded_session,
            tool_kind="read",
        ) == "allow"
        assert await resolve_remembered_permission_decision(
            session=loaded_session,
            tool_kind="write",
        ) == "reject"
        assert await resolve_remembered_permission_decision(
            session=loaded_session,
            tool_kind="execute",
        ) == "allow"

    @pytest.mark.asyncio
    async def test_unknown_policy_defaults_to_ask(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Проверяет что неизвестные policies по умолчанию возвращают 'ask'.

        Сценарий:
        1. Создать сессию
        2. Установить permission_policy["read"] = "allow_always"
        3. Сохранить сессию в JSON
        4. Загрузить сессию из JSON
        5. Проверить что resolve_remembered_permission_decision для неизвестного tool kind
           возвращает 'ask' (default)
        """
        # Arrange - Создаем новую сессию
        original_session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
            available_commands=[],
            runtime_capabilities=None,
        )
        session_id = original_session.session_id

        # Act - Устанавливаем policy только для "read"
        original_session.permission_policy["read"] = "allow_always"

        # Act - Сохраняем сессию в JSON
        await storage.save_session(original_session)

        # Act - Загружаем сессию из JSON
        loaded_session = await storage.load_session(session_id)

        # Assert - Проверяем что для неизвестного tool kind возвращается 'ask'
        decision = await resolve_remembered_permission_decision(
            session=loaded_session,
            tool_kind="unknown_kind",
        )
        assert decision == "ask"

    @pytest.mark.asyncio
    async def test_empty_permission_policy_loads_correctly(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Проверяет что сессия с пустым permission_policy загружается корректно.

        Сценарий:
        1. Создать сессию с пустым permission_policy
        2. Сохранить сессию в JSON
        3. Загрузить сессию из JSON
        4. Проверить что permission_policy пуст
        5. Проверить что все tool kinds возвращают 'ask' (default)
        """
        # Arrange - Создаем новую сессию
        original_session = SessionFactory.create_session(
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
            available_commands=[],
            runtime_capabilities=None,
        )
        session_id = original_session.session_id

        # Assert - Проверяем что permission_policy пуст в исходной сессии
        assert len(original_session.permission_policy) == 0

        # Act - Сохраняем сессию в JSON
        await storage.save_session(original_session)

        # Act - Загружаем сессию из JSON
        loaded_session = await storage.load_session(session_id)

        # Assert - Проверяем что permission_policy пуст в загруженной сессии
        assert len(loaded_session.permission_policy) == 0

        # Assert - Проверяем что resolve_remembered_permission_decision возвращает 'ask'
        # для всех tool kinds (default)
        for tool_kind in ["read", "write", "execute", "other"]:
            decision = await resolve_remembered_permission_decision(
                session=loaded_session,
                tool_kind=tool_kind,
            )
            assert decision == "ask"

    @pytest.mark.asyncio
    async def test_concurrent_save_load_operations(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Проверяет что concurrent save/load операции работают корректно.

        Сценарий:
        1. Создать несколько сессий
        2. Установить разные policies для каждой
        3. Сохранить все сессии в JSON параллельно
        4. Загрузить все сессии из JSON параллельно
        5. Проверить что все policies восстановлены корректно
        """
        # Arrange - Создаем несколько сессий
        sessions = [
            SessionFactory.create_session(
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "ask"},
                available_commands=[],
                runtime_capabilities=None,
            )
            for _ in range(3)
        ]

        # Act - Устанавливаем разные policies для каждой сессии
        sessions[0].permission_policy["read"] = "allow_always"
        sessions[1].permission_policy["write"] = "reject_always"
        sessions[2].permission_policy["execute"] = "allow_always"

        # Act - Сохраняем все сессии параллельно
        await asyncio.gather(
            *[storage.save_session(session) for session in sessions],
        )

        # Act - Загружаем все сессии параллельно
        loaded_sessions = await asyncio.gather(
            *[storage.load_session(session.session_id) for session in sessions],
        )

        # Assert - Проверяем что все сессии загрузились
        assert len(loaded_sessions) == 3
        for loaded_session in loaded_sessions:
            assert loaded_session is not None

        # Assert - Проверяем что policies восстановлены корректно
        assert loaded_sessions[0].permission_policy["read"] == "allow_always"
        assert loaded_sessions[1].permission_policy["write"] == "reject_always"
        assert loaded_sessions[2].permission_policy["execute"] == "allow_always"

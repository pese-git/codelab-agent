"""Полный интеграционный тест жизненного цикла сессии с replay.

Проверяет end-to-end сценарий:
1. Создание новой сессии
2. Отправка session/prompt
3. Загрузка сессии через session/load
4. Воспроизведение истории через notifications
"""

from typing import Any

import pytest
from factories import make_orchestrator

from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.protocol.handlers.session import session_load
from codelab.server.protocol.session_factory import SessionFactory


class TestFullSessionLifecycle:
    """Полный цикл создания, использования и загрузки сессии."""

    @pytest.fixture
    def config_specs(self) -> dict[str, dict[str, Any]]:
        """Создает спецификацию конфигурации."""
        return {
            "mode": {
                "default": "auto",
                "description": "Mode",
                "name": "Mode",
                "category": "Agent",
                "options": ["auto", "manual"],
            }
        }

    @pytest.mark.asyncio
    async def test_session_lifecycle_with_events_replay(
        self,
        config_specs: dict[str, dict[str, Any]],
    ) -> None:
        """Полный цикл: создание → использование → загрузка с replay."""
        # Arrange - Создаем новую сессию через factory
        # Сессия рождается wire-документом (фабрика), а turn-путь работает
        # доменным агрегатом — как в проде после флипа (ADR-006, фаза D шаг 3).
        session = SessionMapper.to_domain(
            SessionFactory.create_session(
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "auto"},
                available_commands=[],
                runtime_capabilities=None,
            )
        )

        # Act - Симулируем использование сессии (добавляем события вручную)
        orchestrator = make_orchestrator()

        # Добавляем user message и сохраняем в events_history
        user_prompt = [{"type": "text", "text": "Hello, how are you?"}]
        orchestrator.state_manager.add_user_message(session, user_prompt)

        for block in user_prompt:
            EventHistoryWriter().save_user_message_chunk(session, block)

        # Добавляем agent message и сохраняем в events_history
        agent_response = "I'm doing great, thank you!"
        orchestrator.state_manager.add_assistant_message(session, agent_response)

        EventHistoryWriter().save_agent_message_chunk(
            session, {"type": "text", "text": agent_response}
        )

        # Assert - Проверяем что события сохранены
        assert len(session.runtime.events_history) >= 2

        user_events = [
            e
            for e in session.runtime.events_history
            if e.get("type") == "session_update"
            and e.get("update", {}).get("sessionUpdate") == "user_message_chunk"
        ]
        assert len(user_events) == 1

        agent_events = [
            e
            for e in session.runtime.events_history
            if e.get("type") == "session_update"
            and e.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
        ]
        assert len(agent_events) == 1

        # Сохраняем сессию в storage
        from codelab.server.storage import InMemoryStorage

        storage = InMemoryStorage()
        await storage.save_session(SessionMapper.to_protocol(session))

        # Act - Загружаем сессию через session/load (симулирует переподключение клиента)
        outcome = await session_load(
            request_id="req_load",
            params={"sessionId": str(session.id), "cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs=config_specs,
            auth_methods=[],
            storage=storage,
        )

        # Assert - Проверяем что notifications содержат полную историю
        assert outcome.notifications is not None
        assert len(outcome.notifications) > 0

        # Ищем replayed user_message_chunk
        replayed_user_notifications = [
            n
            for n in outcome.notifications
            if (
                n.method == "session/update"
                and n.params.get("update", {}).get("sessionUpdate") == "user_message_chunk"
            )
        ]
        assert len(replayed_user_notifications) == 1
        user_text = replayed_user_notifications[0].params["update"]["content"]["text"]
        assert user_text == "Hello, how are you?"

        # Ищем replayed agent_message_chunk
        replayed_agent_notifications = [
            n
            for n in outcome.notifications
            if (
                n.method == "session/update"
                and n.params.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
            )
        ]
        assert len(replayed_agent_notifications) == 1
        agent_text = replayed_agent_notifications[0].params["update"]["content"]["text"]
        assert agent_text == "I'm doing great, thank you!"

    @pytest.mark.asyncio
    async def test_session_lifecycle_multiple_turns(
        self,
        config_specs: dict[str, dict[str, Any]],
    ) -> None:
        """Полный цикл с несколькими turn'ами (диалог)."""
        # Arrange
        # Сессия рождается wire-документом (фабрика), а turn-путь работает
        # доменным агрегатом — как в проде после флипа (ADR-006, фаза D шаг 3).
        session = SessionMapper.to_domain(
            SessionFactory.create_session(
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "auto"},
                available_commands=[],
                runtime_capabilities=None,
            )
        )

        orchestrator = make_orchestrator()

        # Act - Первый turn (пользователь)
        user_prompt_1 = [{"type": "text", "text": "What is Python?"}]
        orchestrator.state_manager.add_user_message(session, user_prompt_1)

        for block in user_prompt_1:
            EventHistoryWriter().save_user_message_chunk(session, block)

        # Act - Первый turn (агент)
        agent_response_1 = "Python is a programming language"
        orchestrator.state_manager.add_assistant_message(session, agent_response_1)

        EventHistoryWriter().save_agent_message_chunk(
            session, {"type": "text", "text": agent_response_1}
        )

        # Act - Второй turn (пользователь)
        user_prompt_2 = [{"type": "text", "text": "What are its features?"}]
        orchestrator.state_manager.add_user_message(session, user_prompt_2)

        for block in user_prompt_2:
            EventHistoryWriter().save_user_message_chunk(session, block)

        # Act - Второй turn (агент)
        agent_response_2 = "Python has many great features like simplicity and readability"
        orchestrator.state_manager.add_assistant_message(session, agent_response_2)

        EventHistoryWriter().save_agent_message_chunk(
            session, {"type": "text", "text": agent_response_2}
        )

        # Assert - Проверяем что все события сохранены
        assert len(session.runtime.events_history) == 4  # 2 user + 2 agent

        # Сохраняем сессию в storage
        from codelab.server.storage import InMemoryStorage

        storage = InMemoryStorage()
        await storage.save_session(SessionMapper.to_protocol(session))

        # Act - Загружаем сессию
        outcome = await session_load(
            request_id="req_load",
            params={"sessionId": str(session.id), "cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs=config_specs,
            auth_methods=[],
            storage=storage,
        )

        # Assert - Проверяем что все сообщения воспроизведены в правильном порядке
        user_notifications = [
            n
            for n in outcome.notifications
            if (
                n.method == "session/update"
                and n.params.get("update", {}).get("sessionUpdate") == "user_message_chunk"
            )
        ]
        assert len(user_notifications) == 2
        assert user_notifications[0].params["update"]["content"]["text"] == "What is Python?"
        assert user_notifications[1].params["update"]["content"]["text"] == "What are its features?"

        agent_notifications = [
            n
            for n in outcome.notifications
            if (
                n.method == "session/update"
                and n.params.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
            )
        ]
        assert len(agent_notifications) == 2
        assert agent_notifications[0].params["update"]["content"]["text"] == agent_response_1
        assert agent_notifications[1].params["update"]["content"]["text"] == agent_response_2

    @pytest.mark.asyncio
    async def test_session_lifecycle_order_preservation(
        self,
        config_specs: dict[str, dict[str, Any]],
    ) -> None:
        """Проверяет что порядок событий сохраняется при replay."""
        # Arrange
        # Сессия рождается wire-документом (фабрика), а turn-путь работает
        # доменным агрегатом — как в проде после флипа (ADR-006, фаза D шаг 3).
        session = SessionMapper.to_domain(
            SessionFactory.create_session(
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "auto"},
                available_commands=[],
                runtime_capabilities=None,
            )
        )

        orchestrator = make_orchestrator()

        # Act - Добавляем события в строгом порядке
        events_sequence = [
            ("user", "First question"),
            ("agent", "First answer"),
            ("user", "Second question"),
            ("agent", "Second answer"),
        ]

        for role, text in events_sequence:
            if role == "user":
                prompt = [{"type": "text", "text": text}]
                orchestrator.state_manager.add_user_message(session, prompt)

                for block in prompt:
                    EventHistoryWriter().save_user_message_chunk(session, block)
            else:
                orchestrator.state_manager.add_assistant_message(session, text)

                EventHistoryWriter().save_agent_message_chunk(
                    session, {"type": "text", "text": text}
                )

        # Сохраняем сессию в storage
        from codelab.server.storage import InMemoryStorage

        storage = InMemoryStorage()
        await storage.save_session(SessionMapper.to_protocol(session))

        # Act - Загружаем сессию
        outcome = await session_load(
            request_id="req_load",
            params={"sessionId": str(session.id), "cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs=config_specs,
            auth_methods=[],
            storage=storage,
        )

        # Assert - Проверяем порядок событий в notifications
        # Извлекаем только session/update notifications для проверки порядка
        session_updates = [
            n
            for n in outcome.notifications
            if n.method == "session/update"
            and n.params.get("update", {}).get("sessionUpdate")
            in ["user_message_chunk", "agent_message_chunk"]
        ]

        # Должны быть все 4 события в правильном порядке
        assert len(session_updates) == 4

        # Проверяем последовательность
        expected_order = [
            ("user_message_chunk", "First question"),
            ("agent_message_chunk", "First answer"),
            ("user_message_chunk", "Second question"),
            ("agent_message_chunk", "Second answer"),
        ]

        for i, (expected_type, expected_text) in enumerate(expected_order):
            actual_type = session_updates[i].params["update"]["sessionUpdate"]
            actual_content = session_updates[i].params["update"]["content"]

            if expected_type == "user_message_chunk":
                actual_text = actual_content.get("text")
            else:
                actual_text = actual_content.get("text")

            assert actual_type == expected_type, (
                f"Event {i}: expected {expected_type}, got {actual_type}"
            )
            assert actual_text == expected_text, (
                f"Event {i}: expected '{expected_text}', got '{actual_text}'"
            )

"""Тесты для FileChatPersistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codelab.client.presentation.chat.persistence.file_chat_persistence import (
    FileChatPersistence,
)


class TestFileChatPersistence:
    """Тесты для FileChatPersistence."""

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Создаёт временную директорию для тестов."""
        return tmp_path / "history"

    @pytest.fixture
    def persistence(self, temp_dir: Path) -> FileChatPersistence:
        """Создаёт экземпляр FileChatPersistence для тестов."""
        return FileChatPersistence(temp_dir)

    def test_init_creates_directory(self, temp_dir: Path) -> None:
        """Инициализация должна создавать директорию если она не существует."""
        assert not temp_dir.exists()

        FileChatPersistence(temp_dir)

        assert temp_dir.exists()
        assert temp_dir.is_dir()

    def test_init_with_existing_directory(self, temp_dir: Path) -> None:
        """Инициализация должна работать с существующей директорией."""
        temp_dir.mkdir(parents=True)

        persistence = FileChatPersistence(temp_dir)

        assert persistence._history_dir == temp_dir

    def test_sanitize_session_id(self, persistence: FileChatPersistence) -> None:
        """_sanitize_session_id должен заменять '/' и '\\' на '_'."""
        assert persistence._sanitize_session_id("normal-id") == "normal-id"
        assert (
            persistence._sanitize_session_id("session/with/slashes")
            == "session_with_slashes"
        )
        assert (
            persistence._sanitize_session_id("session\\with\\backslashes")
            == "session_with_backslashes"
        )
        assert (
            persistence._sanitize_session_id("mixed/path\\separators")
            == "mixed_path_separators"
        )

    def test_get_file_path(self, persistence: FileChatPersistence) -> None:
        """_get_file_path должен возвращать правильный путь к файлу."""
        file_path = persistence._get_file_path("test-session")

        assert file_path.name == "test-session.json"
        assert file_path.parent == persistence._history_dir

    def test_get_file_path_sanitizes_id(self, persistence: FileChatPersistence) -> None:
        """_get_file_path должен очищать session_id."""
        file_path = persistence._get_file_path("session/with/slashes")

        assert file_path.name == "session_with_slashes.json"

    @pytest.mark.asyncio
    async def test_save_and_load_messages(self, persistence: FileChatPersistence) -> None:
        """save_messages и load_messages должны работать корректно."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        await persistence.save_messages("session-1", messages)
        loaded = await persistence.load_messages("session-1")

        assert loaded == messages

    @pytest.mark.asyncio
    async def test_save_messages_with_replay_updates(
        self, persistence: FileChatPersistence
    ) -> None:
        """save_messages должен сохранять replay updates."""
        messages = [{"role": "user", "content": "Hello"}]
        replay_updates = [
            {"params": {"update": {"sessionUpdate": "agent_message_chunk"}}},
        ]

        await persistence.save_messages("session-1", messages, replay_updates)
        loaded_updates = await persistence.load_replay_updates("session-1")

        assert loaded_updates == replay_updates

    @pytest.mark.asyncio
    async def test_save_messages_with_none_replay_updates(
        self, persistence: FileChatPersistence
    ) -> None:
        """save_messages должен обрабатывать None replay_updates."""
        messages = [{"role": "user", "content": "Hello"}]

        await persistence.save_messages("session-1", messages, replay_updates=None)
        loaded_updates = await persistence.load_replay_updates("session-1")

        assert loaded_updates == []

    @pytest.mark.asyncio
    async def test_load_messages_nonexistent_session(
        self, persistence: FileChatPersistence
    ) -> None:
        """load_messages должен возвращать пустой список для несуществующей сессии."""
        loaded = await persistence.load_messages("nonexistent")

        assert loaded == []

    @pytest.mark.asyncio
    async def test_load_replay_updates_nonexistent_session(
        self, persistence: FileChatPersistence
    ) -> None:
        """load_replay_updates должен возвращать пустой список для несуществующей сессии."""
        loaded = await persistence.load_replay_updates("nonexistent")

        assert loaded == []

    @pytest.mark.asyncio
    async def test_load_messages_corrupted_file(
        self, persistence: FileChatPersistence, temp_dir: Path
    ) -> None:
        """load_messages должен возвращать пустой список для повреждённого файла."""
        # Создаём повреждённый JSON файл
        file_path = temp_dir / "corrupted.json"
        file_path.write_text("invalid json content", encoding="utf-8")

        loaded = await persistence.load_messages("corrupted")

        assert loaded == []

    @pytest.mark.asyncio
    async def test_load_messages_invalid_structure(
        self, persistence: FileChatPersistence, temp_dir: Path
    ) -> None:
        """load_messages должен возвращать пустой список для невалидной структуры."""
        # Создаём файл с невалидной структурой
        file_path = temp_dir / "invalid.json"
        file_path.write_text(json.dumps({"messages": "not a list"}), encoding="utf-8")

        loaded = await persistence.load_messages("invalid")

        assert loaded == []

    @pytest.mark.asyncio
    async def test_load_messages_filters_invalid_messages(
        self, persistence: FileChatPersistence, temp_dir: Path
    ) -> None:
        """load_messages должен фильтровать невалидные сообщения."""
        # Создаём файл с валидными и невалидными сообщениями
        file_path = temp_dir / "mixed.json"
        data = {
            "messages": [
                {"role": "user", "content": "Valid message"},
                {"role": 123, "content": "Invalid role"},  # type: ignore
                {"role": "assistant"},  # Missing content
                {"invalid": "structure"},
                {"role": "assistant", "content": "Another valid"},
            ],
            "replay_updates": [],
        }
        file_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = await persistence.load_messages("mixed")

        assert len(loaded) == 2
        assert loaded[0] == {"role": "user", "content": "Valid message"}
        assert loaded[1] == {"role": "assistant", "content": "Another valid"}

    @pytest.mark.asyncio
    async def test_load_replay_updates_filters_invalid(
        self, persistence: FileChatPersistence, temp_dir: Path
    ) -> None:
        """load_replay_updates должен фильтровать невалидные updates."""
        # Создаём файл с валидными и невалидными updates
        file_path = temp_dir / "mixed_updates.json"
        data = {
            "messages": [],
            "replay_updates": [
                {"params": {"update": {"sessionUpdate": "agent_message_chunk"}}},
                "not a dict",
                123,
                {"valid": "update"},
            ],
        }
        file_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = await persistence.load_replay_updates("mixed_updates")

        assert len(loaded) == 2
        assert loaded[0] == {"params": {"update": {"sessionUpdate": "agent_message_chunk"}}}
        assert loaded[1] == {"valid": "update"}

    @pytest.mark.asyncio
    async def test_save_messages_unicode(
        self, persistence: FileChatPersistence
    ) -> None:
        """save_messages должен корректно сохранять Unicode символы."""
        messages = [
            {"role": "user", "content": "Привет, мир!"},
            {"role": "assistant", "content": "Hello, 世界!"},
        ]

        await persistence.save_messages("unicode-session", messages)
        loaded = await persistence.load_messages("unicode-session")

        assert loaded == messages

    @pytest.mark.asyncio
    async def test_round_trip_complex_data(
        self, persistence: FileChatPersistence
    ) -> None:
        """Полный цикл save/load должен сохранять сложные данные."""
        messages = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
        ]
        replay_updates = [
            {
                "params": {
                    "sessionId": "test",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Hello"},
                    },
                },
            },
            {
                "params": {
                    "sessionId": "test",
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": "tc-1",
                    },
                },
            },
        ]

        await persistence.save_messages("complex-session", messages, replay_updates)

        loaded_messages = await persistence.load_messages("complex-session")
        loaded_updates = await persistence.load_replay_updates("complex-session")

        assert loaded_messages == messages
        assert loaded_updates == replay_updates

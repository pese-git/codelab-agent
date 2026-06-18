"""File-based реализация ChatPersistencePort.

Сохраняет историю чата в JSON файлы в указанной директории.
Все операции async-safe через asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog


class FileChatPersistence:
    """File-based реализация ChatPersistencePort.

    Сохраняет сообщения и replay updates в JSON файлы.
    Все файловые операции выполняются в thread pool для неблокирования event loop.

    Attributes:
        _history_dir: Директория для хранения файлов истории
        _logger: Logger для логирования операций
    """

    def __init__(self, history_dir: Path) -> None:
        """Инициализирует FileChatPersistence.

        Args:
            history_dir: Директория для хранения файлов истории.
                        Создаётся если не существует.
        """
        self._history_dir = history_dir
        self._logger = structlog.get_logger("file_chat_persistence")

        # Создаём директорию если не существует
        try:
            self._history_dir.mkdir(parents=True, exist_ok=True)
            self._logger.info(
                "history_directory_ready",
                path=str(self._history_dir),
            )
        except OSError as e:
            self._logger.warning(
                "history_directory_creation_failed",
                path=str(self._history_dir),
                error=str(e),
            )

    def _sanitize_session_id(self, session_id: str) -> str:
        """Очищает session_id для использования в имени файла.

        Заменяет '/' и '\\' на '_' для предотвращения path traversal.

        Args:
            session_id: ID сессии для очистки

        Returns:
            Очищенный session_id безопасный для использования в имени файла
        """
        return session_id.replace("/", "_").replace("\\", "_")

    def _get_file_path(self, session_id: str) -> Path:
        """Возвращает путь к файлу истории для сессии.

        Args:
            session_id: ID сессии

        Returns:
            Путь к JSON файлу истории
        """
        sanitized_id = self._sanitize_session_id(session_id)
        return self._history_dir / f"{sanitized_id}.json"

    def _write_json_sync(self, file_path: Path, data: dict[str, Any]) -> None:
        """Синхронная запись JSON файла.

        Args:
            file_path: Путь к файлу
            data: Данные для записи
        """
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2)
            file_path.write_text(content, encoding="utf-8")
        except OSError as e:
            self._logger.error(
                "file_write_failed",
                path=str(file_path),
                error=str(e),
            )
            raise

    def _read_json_sync(self, file_path: Path) -> dict[str, Any]:
        """Синхронное чтение JSON файла.

        Args:
            file_path: Путь к файлу

        Returns:
            Данные из JSON файла или пустой dict если файл не существует
        """
        if not file_path.exists():
            return {}

        try:
            content = file_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            self._logger.warning(
                "file_read_failed",
                path=str(file_path),
                error=str(e),
            )
            return {}

    async def save_messages(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        replay_updates: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет сообщения и replay updates в JSON файл.

        Args:
            session_id: ID сессии
            messages: Список сообщений с role и content
            replay_updates: Опциональные replay updates для восстановления
        """
        file_path = self._get_file_path(session_id)
        data = {
            "messages": messages,
            "replay_updates": replay_updates or [],
        }

        try:
            await asyncio.to_thread(self._write_json_sync, file_path, data)
            self._logger.debug(
                "messages_saved",
                session_id=session_id,
                messages_count=len(messages),
                replay_updates_count=len(replay_updates or []),
            )
        except OSError as e:
            self._logger.error(
                "save_messages_failed",
                session_id=session_id,
                error=str(e),
            )

    async def load_messages(self, session_id: str) -> list[dict[str, str]]:
        """Загружает сообщения для сессии из JSON файла.

        Args:
            session_id: ID сессии

        Returns:
            Список сообщений или пустой список если файл не существует
        """
        file_path = self._get_file_path(session_id)

        try:
            data = await asyncio.to_thread(self._read_json_sync, file_path)
            messages = data.get("messages", [])

            # Валидация структуры
            if not isinstance(messages, list):
                self._logger.warning(
                    "invalid_messages_structure",
                    session_id=session_id,
                    messages_type=type(messages).__name__,
                )
                return []

            # Фильтрация валидных сообщений
            valid_messages = [
                msg
                for msg in messages
                if isinstance(msg, dict)
                and isinstance(msg.get("role"), str)
                and isinstance(msg.get("content"), str)
            ]

            self._logger.debug(
                "messages_loaded",
                session_id=session_id,
                messages_count=len(valid_messages),
            )
            return valid_messages

        except Exception as e:
            self._logger.error(
                "load_messages_failed",
                session_id=session_id,
                error=str(e),
            )
            return []

    async def load_replay_updates(self, session_id: str) -> list[dict[str, Any]]:
        """Загружает replay updates для сессии из JSON файла.

        Args:
            session_id: ID сессии

        Returns:
            Список replay updates или пустой список если файл не существует
        """
        file_path = self._get_file_path(session_id)

        try:
            data = await asyncio.to_thread(self._read_json_sync, file_path)
            replay_updates = data.get("replay_updates", [])

            # Валидация структуры
            if not isinstance(replay_updates, list):
                self._logger.warning(
                    "invalid_replay_updates_structure",
                    session_id=session_id,
                    updates_type=type(replay_updates).__name__,
                )
                return []

            # Фильтрация валидных updates
            valid_updates = [
                update for update in replay_updates if isinstance(update, dict)
            ]

            self._logger.debug(
                "replay_updates_loaded",
                session_id=session_id,
                updates_count=len(valid_updates),
            )
            return valid_updates

        except Exception as e:
            self._logger.error(
                "load_replay_updates_failed",
                session_id=session_id,
                error=str(e),
            )
            return []

    def load_messages_sync(self, session_id: str) -> list[dict[str, str]]:
        """Синхронная загрузка сообщений (для sync контекста).

        Используется в _get_or_create_session_state который вызывается
        из sync методов ChatViewModel.

        Args:
            session_id: ID сессии

        Returns:
            Список сообщений или пустой список если файл не существует
        """
        file_path = self._get_file_path(session_id)

        try:
            data = self._read_json_sync(file_path)
            messages = data.get("messages", [])

            # Валидация структуры
            if not isinstance(messages, list):
                self._logger.warning(
                    "invalid_messages_structure_sync",
                    session_id=session_id,
                    messages_type=type(messages).__name__,
                )
                return []

            # Фильтрация валидных сообщений
            valid_messages = [
                msg
                for msg in messages
                if isinstance(msg, dict)
                and isinstance(msg.get("role"), str)
                and isinstance(msg.get("content"), str)
            ]

            return valid_messages

        except Exception as e:
            self._logger.error(
                "load_messages_sync_failed",
                session_id=session_id,
                error=str(e),
            )
            return []

    def load_replay_updates_sync(self, session_id: str) -> list[dict[str, Any]]:
        """Синхронная загрузка replay updates (для sync контекста).

        Используется в _get_or_create_session_state который вызывается
        из sync методов ChatViewModel.

        Args:
            session_id: ID сессии

        Returns:
            Список replay updates или пустой список если файл не существует
        """
        file_path = self._get_file_path(session_id)

        try:
            data = self._read_json_sync(file_path)
            replay_updates = data.get("replay_updates", [])

            # Валидация структуры
            if not isinstance(replay_updates, list):
                self._logger.warning(
                    "invalid_replay_updates_structure_sync",
                    session_id=session_id,
                    updates_type=type(replay_updates).__name__,
                )
                return []

            # Фильтрация валидных updates
            valid_updates = [
                update for update in replay_updates if isinstance(update, dict)
            ]

            return valid_updates

        except Exception as e:
            self._logger.error(
                "load_replay_updates_sync_failed",
                session_id=session_id,
                error=str(e),
            )
            return []

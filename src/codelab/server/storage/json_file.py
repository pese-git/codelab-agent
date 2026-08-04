"""JSON файловое хранилище для сессий ACP.

Использует Pydantic model_dump/model_validate для сериализации,
что устраняет ~250 строк ручного кода _serialize_* / _deserialize_*.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiofiles
from pydantic import ValidationError

from codelab.server.storage.document import SessionDocument

from ..exceptions import SessionRevisionConflictError, StorageError
from .base import SessionStorage


class JsonFileStorage(SessionStorage):
    """Хранилище сессий в JSON файлах.

    Каждая сессия сохраняется в отдельный файл:
    {base_path}/{session_id}.json

    Использует Pydantic model_dump(mode="json") для сериализации
    и SessionDocument.model_validate() для десериализации.

    Пример использования:
        storage = JsonFileStorage(Path.home() / ".acp" / "sessions")
        await storage.save_session(session)
        loaded = await storage.load_session(session_id)
    """

    def __init__(self, base_path: Path | str) -> None:
        """Инициализирует хранилище.

        Args:
            base_path: Директория для хранения JSON файлов
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _session_file_path(self, session_id: str) -> Path:
        """Возвращает путь к файлу сессии."""
        # Экранировать session_id для безопасности
        safe_id = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self.base_path / f"{safe_id}.json"

    async def _read_revision(self, file_path: Path) -> int | None:
        """Ревизия документа на диске или `None`, если документа нет.

        Битый или нечитаемый файл трактуется как «ревизия неизвестна»: CAS не должен
        превращать повреждение в невозможность записи — иначе сессия окажется
        заперта навсегда.
        """
        if not file_path.exists():
            return None
        try:
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                data = json.loads(await f.read())
        except Exception:
            return None
        revision = data.get("revision") if isinstance(data, dict) else None
        return revision if isinstance(revision, int) else None

    async def save_session(self, session: SessionDocument) -> None:
        """Сохраняет сессию в JSON файл.

        Использует Pydantic model_dump(mode="json") для корректной
        конвертации всех типов включая set → list.

        Args:
            session: Состояние сессии для сохранения.

        Raises:
            StorageError: При ошибке сохранения.
        """
        try:
            file_path = self._session_file_path(session.session_id)
            # Compare-and-set: документ мог измениться, пока писатель держал копию
            # (ADR-007). Отклоняем запись вместо затирания — конфликт должен быть
            # видимым. Стоимость — лишнее чтение (1.8 мс на 575 КБ); сайдкар-файл с
            # ревизией отвергнут: он добавил бы вторую задачу атомарности.
            stored_revision = await self._read_revision(file_path)
            if stored_revision is None and session.revision > 0:
                # Документа нет, а копия уже была записана — значит сессию удалили,
                # пока писатель держал копию. Воскрешать её записью нельзя: удаление
                # было осознанным решением (ADR-007). `actual=0` здесь означает
                # «документа нет».
                raise SessionRevisionConflictError(session.session_id, session.revision, 0)
            if stored_revision is not None and stored_revision != session.revision:
                raise SessionRevisionConflictError(
                    session.session_id, session.revision, stored_revision
                )

            # Обновить временную метку
            session.updated_at = datetime.now(UTC).isoformat()
            session.revision = session.revision + 1

            # model_dump(mode="json") — корректно конвертирует все типы
            data = session.model_dump(mode="json")

            # Запись через временный файл + os.replace: прямая запись в целевой файл
            # оставляла обрезанный документ при падении или двух писателях, а сессия
            # уже занимает сотни килобайт (ADR-007). os.replace атомарен в пределах
            # файловой системы, поэтому читатель видит либо прежний документ, либо
            # новый целиком.
            # Имя уникально на каждую запись, а не на процесс: два одновременных
            # сохранения одной сессии (например `execute_pending_tool` и обработчик
            # запроса) делили бы один временный файл — первый `os.replace` забирал
            # бы его, второй падал с ENOENT. Поймано полным прогоном тестов.
            tmp_path = file_path.with_name(f"{file_path.name}.{uuid4().hex}.tmp")
            try:
                async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(data, indent=2, ensure_ascii=False))
                os.replace(tmp_path, file_path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

        except SessionRevisionConflictError:
            # Не оборачиваем: вызывающий различает конфликт и сбой ввода-вывода.
            # Ревизию в объекте не откатываем — она инкрементируется после проверки.
            raise
        except Exception as e:
            raise StorageError(f"Failed to save session {session.session_id}: {e}") from e

    async def load_session(self, session_id: str) -> SessionDocument | None:
        """Загружает сессию из JSON файла.

        Использует SessionDocument.model_validate() для десериализации
        с автоматической миграцией схемы через model_validator.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            SessionDocument если найдена, None если не существует.

        Raises:
            StorageError: При ошибке загрузки.
        """
        try:
            file_path = self._session_file_path(session_id)
            if not file_path.exists():
                return None

            async with aiofiles.open(file_path, encoding="utf-8") as f:
                content = await f.read()

            data = json.loads(content)

            # model_validate автоматически применяет миграцию схемы
            session = SessionDocument.model_validate(data)
            return session

        except json.JSONDecodeError as e:
            raise StorageError(f"Corrupted session file {session_id}") from e
        except ValidationError as e:
            raise StorageError(f"Invalid session data {session_id}: {e}") from e
        except Exception as e:
            raise StorageError(f"Failed to load session {session_id}: {e}") from e

    async def delete_session(self, session_id: str) -> bool:
        """Удаляет JSON файл сессии.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            True если сессия была удалена, False если не существовала.

        Raises:
            StorageError: При ошибке удаления.
        """
        try:
            file_path = self._session_file_path(session_id)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            raise StorageError(f"Failed to delete session {session_id}: {e}") from e

    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionDocument], str | None]:
        """Возвращает список сессий из файлов.

        Args:
            cwd: Фильтр по рабочей директории (опционально).
            cursor: Курсор для пагинации (session_id последней сессии предыдущей страницы).
            limit: Максимальное количество сессий на странице.

        Returns:
            Кортеж (список сессий, следующий курсор или None).

        Raises:
            StorageError: При ошибке получения списка.
        """
        try:
            # Загрузить все сессии
            sessions: list[SessionDocument] = []
            for file_path in self.base_path.glob("*.json"):
                session_id = file_path.stem
                session = await self.load_session(session_id)
                if session:
                    sessions.append(session)

            # Фильтрация по cwd
            if cwd:
                sessions = [s for s in sessions if s.cwd == cwd]

            # Сортировка по updated_at (новые первыми)
            sessions.sort(key=lambda s: s.updated_at, reverse=True)

            # Пагинация с курсором
            start_index = 0
            if cursor:
                for i, s in enumerate(sessions):
                    if s.session_id == cursor:
                        start_index = i + 1
                        break

            page = sessions[start_index : start_index + limit]
            next_cursor = (
                page[-1].session_id if len(sessions) > start_index + limit and page else None
            )

            return page, next_cursor

        except Exception as e:
            raise StorageError(f"Failed to list sessions: {e}") from e

    async def session_exists(self, session_id: str) -> bool:
        """Проверяет существование файла сессии.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            True если сессия существует, False иначе.
        """
        return self._session_file_path(session_id).exists()

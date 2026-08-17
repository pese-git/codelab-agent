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
    """Хранилище сессий: снимок в JSON, журнал в JSONL (шаг 6b ADR-008).

    Сессия лежит в двух файлах:

    * `{base_path}/{session_id}.json` — снимок: всё состояние, кроме журнала;
    * `{base_path}/{session_id}.jsonl` — журнал: по записи на строку, дописывается.

    **Почему двумя файлами, а не одним.** Снимок остаётся обычным `indent=2`
    JSON и читается тем же `jq .`, что и прежде: разбор документа глазами — часть
    приёмки в этом ADR, все его находки получены так. В одном файле снимок стал
    бы строкой на десяток килобайт. Вторая причина — `list_sessions`: ему нужен
    только снимок, и раздельная раскладка снимает лишнее чтение журнала.

    **Почему снимок пишется каждый раз, хотя шаг называется «снимок редок».**
    Редким он может стать, только когда всё состояние выводится из журнала. Пока
    это не так: `active_turn`, `tool_call_counter`, `cancelled_permission_requests`
    и `pending_prompt_response` меняются на каждом шаге turn'а, а журнал их не
    описывает — он несёт семь видов событий, все про диалог. Снимок раз в N
    событий терял бы ровно то, что чинили шаги 2 и 5 этого ADR.

    Выигрыш от этого почти не страдает: нежурнальное состояние — 1.9 КБ против
    52 КБ журнала на живой сессии, и оно не растёт с длиной разговора. Квадратичная
    стоимость снимается всё равно, потому что журнал перестал переписываться.

    **Порядок записи значим.** Сначала дописывается журнал, потом пишется снимок.
    Смерть процесса между ними даёт журнал длиннее снимка — безобидный исход,
    лишние записи прочитаются как есть. Обратный порядок дал бы снимок,
    ссылающийся на записи, которых нет.

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
        # Сколько записей журнала уже на диске — чтобы дописывать хвост, а не
        # считать строки на каждой записи. Кэш процессный и может устареть, если
        # сессию писал другой процесс; от расхождения защищает CAS по ревизии,
        # который стоит до дописывания.
        self._journal_lengths: dict[str, int] = {}

    def _session_file_path(self, session_id: str) -> Path:
        """Возвращает путь к файлу снимка сессии."""
        # Экранировать session_id для безопасности
        safe_id = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self.base_path / f"{safe_id}.json"

    def _journal_file_path(self, session_id: str) -> Path:
        """Возвращает путь к файлу журнала сессии."""
        return self._session_file_path(session_id).with_suffix(".jsonl")

    async def _read_journal(self, session_id: str) -> list[dict] | None:
        """Записи журнала с диска или `None`, если файла журнала нет.

        `None` и `[]` различаются намеренно: пустой файл — это расщеплённая
        сессия без событий, а отсутствие файла — документ, записанный до 6b,
        чей журнал лежит внутри снимка.
        """
        path = self._journal_file_path(session_id)
        if not path.exists():
            return None

        async with aiofiles.open(path, encoding="utf-8") as f:
            content = await f.read()

        records: list[dict] = []
        for line in content.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                records.append(record)
        return records

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

            # Журнал дописывается ДО снимка: см. «порядок записи значим» в
            # докстринге класса. CAS уже пройден, поэтому дописывать безопасно.
            await self._append_journal(session)

            # model_dump(mode="json") — корректно конвертирует все типы.
            # Журнал в снимок не попадает: он живёт своим файлом, и вторая копия
            # была бы ровно тем, что этот ADR убирает. `exclude`, а не очистка
            # после дампа: иначе pydantic сериализовал бы все записи журнала, и
            # снимок остался бы O(длина журнала) — на 5000 событий это 3.8 мс
            # против 0.7 мс, то есть ровно та стоимость, от которой уходим.
            data = session.model_dump(mode="json", exclude={"events_history"})
            data["events_history"] = []

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

    async def _append_journal(self, session: SessionDocument) -> None:
        """Дописывает в журнал записи, которых на диске ещё нет.

        Журнал append-only, поэтому файл всегда префикс `events_history`: сколько
        записей на диске — столько и пропускается. Отсюда же расщепление
        однофайловых документов: у них журнала нет вовсе, и первая же запись
        переносит все накопленные записи в JSONL. Отдельной миграции не
        потребовалось — по тому же признаку, что в 4f и 4g, и по тому же решению:
        признак несёт документ, а не версия схемы.
        """
        session_id = session.session_id
        path = self._journal_file_path(session_id)

        written = self._journal_lengths.get(session_id)
        if written is None:
            on_disk = await self._read_journal(session_id)
            written = 0 if on_disk is None else len(on_disk)

        tail = session.events_history[written:]
        if not tail:
            self._journal_lengths[session_id] = written
            return

        # Дописывание, а не перезапись: в этом весь шаг. `a` создаёт файл, если
        # его нет, поэтому расщепление и обычное дописывание — один путь.
        async with aiofiles.open(path, "a", encoding="utf-8") as f:
            await f.write(
                "".join(f"{json.dumps(record, ensure_ascii=False)}\n" for record in tail)
            )

        self._journal_lengths[session_id] = written + len(tail)

    async def _load_snapshot(self, session_id: str) -> SessionDocument | None:
        """Только снимок, без журнала — для тех, кому журнал не нужен.

        Кэш длины журнала здесь **не** трогается: журнал не читался, и записать в
        кэш ноль значило бы соврать — следующая запись сочла бы диск пустым и
        продублировала бы весь журнал.
        """
        file_path = self._session_file_path(session_id)
        if not file_path.exists():
            return None

        async with aiofiles.open(file_path, encoding="utf-8") as f:
            data = json.loads(await f.read())

        return SessionDocument.model_validate(data)

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

            # Журнал из своего файла. Его отсутствие — документ до 6b: журнал
            # лежит внутри снимка и остаётся там до первой записи, которая его
            # расщепит. Пустой файл журнала от отсутствующего отличается: первый
            # означает расщеплённую сессию без событий.
            records = await self._read_journal(session_id)
            if records is not None:
                data["events_history"] = records
                self._journal_lengths[session_id] = len(records)
            else:
                self._journal_lengths[session_id] = 0

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
            self._journal_lengths.pop(session_id, None)
            # Журнал снимается всегда, даже если снимка нет: иначе он пережил бы
            # удаление и достался бы новой сессии с тем же идентификатором.
            self._journal_file_path(session_id).unlink(missing_ok=True)
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
                # Только снимок: списку нужны `title`, `cwd`, `updated_at`, а поиску
                # сессии по идентификатору запроса — `active_turn`. Журнал не нужен
                # никому из них, а тащил он на живой сессии 52 КБ из 55 КБ. Полный
                # скан каталога остаётся (P2-52) — здесь снимается только цена
                # каждой сессии в нём.
                session = await self._load_snapshot(session_id)
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

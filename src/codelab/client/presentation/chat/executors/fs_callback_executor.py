"""FsCallbackExecutor - исполнитель callback'ов для файловой системы.

Обеспечивает async-safe операции с файлами через asyncio.to_thread.
Включает sandbox для предотвращения выхода за пределы рабочей директории.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog


class FsCallbackExecutor:
    """Исполнитель callback'ов для файловой системы.

    Предоставляет async-safe методы для чтения и записи файлов.
    Все файловые операции выполняются в thread pool для неблокирования event loop.

    Включает sandbox для предотвращения path traversal атак.

    Attributes:
        _base_path: Базовая директория (sandbox)
        _logger: Logger для логирования операций
    """

    def __init__(self, base_path: Path) -> None:
        """Инициализирует FsCallbackExecutor.

        Args:
            base_path: Базовая директория для sandbox.
                      Все операции с файлами ограничены этой директорией.

        Raises:
            ValueError: Если base_path не существует или не является директорией
        """
        if not base_path.exists():
            raise ValueError(f"Base path does not exist: {base_path}")
        if not base_path.is_dir():
            raise ValueError(f"Base path is not a directory: {base_path}")

        self._base_path = base_path.resolve()
        self._logger = structlog.get_logger("fs_callback_executor")

    def _validate_path(self, path: str) -> Path:
        """Валидирует путь и проверяет что он находится в sandbox.

        Args:
            path: Путь для валидации

        Returns:
           Resolved Path объект

        Raises:
            ValueError: Если путь находится вне sandbox
        """
        # Преобразуем в Path и разрешаем относительные пути
        if Path(path).is_absolute():
            target_path = Path(path).resolve()
        else:
            target_path = (self._base_path / path).resolve()

        # Проверяем что путь находится в sandbox
        if not str(target_path).startswith(str(self._base_path)):
            raise ValueError(
                f"Path traversal detected: {path} is outside sandbox {self._base_path}"
            )

        return target_path

    def _read_file_sync(self, path: Path) -> str:
        """Синхронное чтение файла.

        Args:
            path: Путь к файлу

        Returns:
            Содержимое файла

        Raises:
            FileNotFoundError: Если файл не существует
            PermissionError: Если нет прав на чтение
            IsADirectoryError: Если путь является директорией
        """
        return path.read_text(encoding="utf-8")

    def _write_file_sync(self, path: Path, content: str) -> None:
        """Синхронная запись файла.

        Args:
            path: Путь к файлу
            content: Содержимое для записи

        Raises:
            PermissionError: Если нет прав на запись
            IsADirectoryError: Если путь является директорией
        """
        # Создаём родительские директории если нужно
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def read_file(self, path: str) -> tuple[str | None, str | None]:
        """Читает файл асинхронно.

        Args:
            path: Путь к файлу (относительный или абсолютный в пределах sandbox)

        Returns:
            Tuple (content, error):
            - (content, None) при успехе
            - (None, error_message) при ошибке
        """
        try:
            validated_path = self._validate_path(path)

            content = await asyncio.to_thread(self._read_file_sync, validated_path)

            self._logger.debug(
                "file_read_success",
                path=path,
                content_size=len(content),
            )
            return content, None

        except ValueError as e:
            error_msg = f"Path validation failed: {e}"
            self._logger.warning(
                "file_read_path_validation_failed",
                path=path,
                error=str(e),
            )
            return None, error_msg

        except FileNotFoundError:
            error_msg = f"File not found: {path}"
            self._logger.debug(
                "file_read_not_found",
                path=path,
            )
            return None, error_msg

        except PermissionError:
            error_msg = f"Permission denied: {path}"
            self._logger.warning(
                "file_read_permission_denied",
                path=path,
            )
            return None, error_msg

        except IsADirectoryError:
            error_msg = f"Path is a directory: {path}"
            self._logger.warning(
                "file_read_is_directory",
                path=path,
            )
            return None, error_msg

        except Exception as e:
            error_msg = f"Failed to read file: {e}"
            self._logger.error(
                "file_read_error",
                path=path,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, error_msg

    async def write_file(
        self, path: str, content: str
    ) -> tuple[bool, str | None]:
        """Записывает файл асинхронно.

        Args:
            path: Путь к файлу (относительный или абсолютный в пределах sandbox)
            content: Содержимое для записи

        Returns:
            Tuple (success, error):
            - (True, None) при успехе
            - (False, error_message) при ошибке
        """
        try:
            validated_path = self._validate_path(path)

            await asyncio.to_thread(self._write_file_sync, validated_path, content)

            self._logger.debug(
                "file_write_success",
                path=path,
                content_size=len(content),
            )
            return True, None

        except ValueError as e:
            error_msg = f"Path validation failed: {e}"
            self._logger.warning(
                "file_write_path_validation_failed",
                path=path,
                error=str(e),
            )
            return False, error_msg

        except PermissionError:
            error_msg = f"Permission denied: {path}"
            self._logger.warning(
                "file_write_permission_denied",
                path=path,
            )
            return False, error_msg

        except IsADirectoryError:
            error_msg = f"Path is a directory: {path}"
            self._logger.warning(
                "file_write_is_directory",
                path=path,
            )
            return False, error_msg

        except Exception as e:
            error_msg = f"Failed to write file: {e}"
            self._logger.error(
                "file_write_error",
                path=path,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False, error_msg

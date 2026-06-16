"""Unit-тесты для базового интерфейса хранилища сессий.

Проверяет, что SessionStorage - абстрактный класс с правильно
определенными абстрактными методами.
"""

from abc import ABC

import pytest

from codelab.server.exceptions import StorageError
from codelab.server.protocol.state import SessionState
from codelab.server.storage.base import SessionStorage


class TestSessionStorageAbstraction:
    """Тесты для проверки абстрактности SessionStorage."""

    def test_session_storage_is_abstract(self) -> None:
        """Проверяет, что SessionStorage нельзя инстанцировать напрямую.

        SessionStorage должен быть абстрактным классом и не позволять
        создание экземпляров без реализации всех абстрактных методов.
        """
        # Попытка создать экземпляр прямо должна выбросить TypeError
        with pytest.raises(TypeError) as exc_info:
            SessionStorage()

        # Сообщение об ошибке должно упоминать абстрактные методы
        assert "abstract" in str(exc_info.value).lower()

    def test_session_storage_is_abc_subclass(self) -> None:
        """Проверяет, что SessionStorage наследуется от ABC.

        SessionStorage должен быть подклассом ABC для правильной работы
        абстрактных методов.
        """
        assert issubclass(SessionStorage, ABC)

    def test_all_methods_are_abstract(self) -> None:
        """Проверяет, что все основные методы помечены как абстрактные.

        Все методы SessionStorage должны быть абстрактными (__abstractmethods__).
        """
        abstract_methods = SessionStorage.__abstractmethods__
        required_methods = {
            "save_session",
            "load_session",
            "delete_session",
            "list_sessions",
            "session_exists",
        }

        # Все требуемые методы должны быть в абстрактных методах
        assert required_methods.issubset(abstract_methods), (
            f"Missing abstract methods: {required_methods - abstract_methods}"
        )

    def test_save_session_is_abstract(self) -> None:
        """Проверяет, что save_session отмечен как абстрактный метод."""
        assert "save_session" in SessionStorage.__abstractmethods__

    def test_load_session_is_abstract(self) -> None:
        """Проверяет, что load_session отмечен как абстрактный метод."""
        assert "load_session" in SessionStorage.__abstractmethods__

    def test_delete_session_is_abstract(self) -> None:
        """Проверяет, что delete_session отмечен как абстрактный метод."""
        assert "delete_session" in SessionStorage.__abstractmethods__

    def test_list_sessions_is_abstract(self) -> None:
        """Проверяет, что list_sessions отмечен как абстрактный метод."""
        assert "list_sessions" in SessionStorage.__abstractmethods__

    def test_session_exists_is_abstract(self) -> None:
        """Проверяет, что session_exists отмечен как абстрактный метод."""
        assert "session_exists" in SessionStorage.__abstractmethods__

    def test_incomplete_implementation_raises_error(self) -> None:
        """Проверяет, что неполная реализация также выбросит TypeError.

        Если создать подкласс SessionStorage, но реализовать только часть
        методов, то его нельзя будет инстанцировать.
        """

        # Создаем неполную реализацию
        class IncompleteStorage(SessionStorage):
            """Неполная реализация с одним методом."""

            async def save_session(self, session: SessionState) -> None:
                """Реализован только один метод."""
                pass

        # Попытка создания экземпляра должна выбросить TypeError
        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_complete_implementation_succeeds(self) -> None:
        """Проверяет, что полная реализация может быть инстанцирована.

        Если создать подкласс SessionStorage и реализовать все методы,
        то экземпляр может быть создан успешно.
        """

        # Создаем полную реализацию
        class CompleteStorage(SessionStorage):
            """Полная реализация хранилища."""

            async def save_session(self, session: SessionState) -> None:
                pass

            async def load_session(self, session_id: str) -> SessionState | None:
                return None

            async def delete_session(self, session_id: str) -> bool:
                return False

            async def list_sessions(
                self,
                cwd: str | None = None,
                cursor: str | None = None,
                limit: int = 100,
            ) -> tuple[list[SessionState], str | None]:
                return [], None

            async def session_exists(self, session_id: str) -> bool:
                return False

        # Создание экземпляра должно пройти успешно
        storage = CompleteStorage()
        assert storage is not None
        assert isinstance(storage, SessionStorage)


class TestStorageError:
    """Тесты для класса исключения StorageError."""

    def test_storage_error_is_exception(self) -> None:
        """Проверяет, что StorageError наследуется от Exception."""
        assert issubclass(StorageError, Exception)

    def test_storage_error_can_be_raised(self) -> None:
        """Проверяет, что StorageError может быть выброшен и поймана."""
        with pytest.raises(StorageError):
            raise StorageError("Test error message")

    def test_storage_error_message(self) -> None:
        """Проверяет, что сообщение об ошибке сохраняется."""
        message = "Failed to save session"
        with pytest.raises(StorageError) as exc_info:
            raise StorageError(message)

        assert str(exc_info.value) == message

    def test_storage_error_with_cause(self) -> None:
        """Проверяет, что StorageError может быть вызван другой ошибкой."""
        original_error = ValueError("Original error")
        with pytest.raises(StorageError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise StorageError(f"Storage failed: {e}") from e

        assert exc_info.value.__cause__ is original_error

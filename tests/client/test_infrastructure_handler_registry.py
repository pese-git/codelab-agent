"""Тесты для infrastructure.handler_registry модуля.

Тестирует:
- Регистрацию обработчиков
- Вызов обработчиков
- Обработку ошибок
- Async/sync обработчики
"""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.handler_registry import HandlerRegistry


class TestHandlerRegistryPermission:
    """Тесты для permission обработчиков."""

    @pytest.mark.asyncio
    async def test_register_and_call_permission_handler(self) -> None:
        """Проверяет регистрацию и вызов permission обработчика."""
        registry = HandlerRegistry()

        def handler(data: dict) -> str:
            return "approve"

        registry.register_permission_handler(handler)
        result = await registry.handle_permission({})

        assert result == "approve"

    @pytest.mark.asyncio
    async def test_permission_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            await registry.handle_permission({})

    @pytest.mark.asyncio
    async def test_async_permission_handler(self) -> None:
        """Проверяет поддержку async permission обработчика."""
        registry = HandlerRegistry()

        async def async_handler(data: dict) -> str:
            return "approve_async"

        registry.register_permission_handler(async_handler)
        result = await registry.handle_permission({})

        assert result == "approve_async"


class TestHandlerRegistryFileSystem:
    """Тесты для FileSystem обработчиков."""

    def test_register_fs_read_handler(self) -> None:
        """Проверяет регистрацию fs_read обработчика."""
        registry = HandlerRegistry()

        def handler(path: str) -> str:
            return "file content"

        registry.register_fs_read_handler(handler)
        result = registry.handle_fs_read("/test/path")

        assert result == "file content"

    def test_fs_read_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии fs_read обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_fs_read("/test/path")

    def test_register_fs_write_handler(self) -> None:
        """Проверяет регистрацию fs_write обработчика."""
        registry = HandlerRegistry()

        def handler(path: str, content: str) -> str | None:
            return None  # OK

        registry.register_fs_write_handler(handler)
        result = registry.handle_fs_write("/test/path", "content")

        assert result is None

    def test_fs_write_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии fs_write обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_fs_write("/test/path", "content")


class TestHandlerRegistryTerminal:
    """Тесты для Terminal обработчиков."""

    def test_register_terminal_create_handler(self) -> None:
        """Проверяет регистрацию terminal_create обработчика."""
        registry = HandlerRegistry()

        def handler(shell: str) -> str:
            return "terminal_id_123"

        registry.register_terminal_create_handler(handler)
        result = registry.handle_terminal_create("bash")

        assert result == "terminal_id_123"

    def test_terminal_create_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии terminal_create обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_terminal_create("bash")

    def test_register_terminal_output_handler(self) -> None:
        """Проверяет регистрацию terminal_output обработчика."""
        registry = HandlerRegistry()

        def handler(terminal_id: str) -> str:
            return "output"

        registry.register_terminal_output_handler(handler)
        result = registry.handle_terminal_output("term_1")

        assert result == "output"

    def test_register_terminal_kill_handler(self) -> None:
        """Проверяет регистрацию terminal_kill обработчика."""
        registry = HandlerRegistry()

        def handler(terminal_id: str) -> bool:
            return True

        registry.register_terminal_kill_handler(handler)
        result = registry.handle_terminal_kill("term_1")

        assert result is True


class TestHandlerRegistryRegisterAll:
    """Тесты для batch регистрации обработчиков."""

    def test_register_all(self) -> None:
        """Проверяет регистрацию всех обработчиков за раз."""
        registry = HandlerRegistry()

        def perm_handler(data: dict) -> str:
            return "approve"

        def fs_read(path: str) -> str:
            return "content"

        def fs_write(path: str, content: str) -> str | None:
            return None

        registry.register_all(
            permission=perm_handler,
            fs_read=fs_read,
            fs_write=fs_write,
        )

        assert registry.handle_fs_read("/path") == "content"
        assert registry.handle_fs_write("/path", "data") is None

    def test_clear(self) -> None:
        """Проверяет очистку всех обработчиков."""
        registry = HandlerRegistry()
        registry.register_permission_handler(lambda x: "approve")
        registry.register_fs_read_handler(lambda x: "content")

        registry.clear()

        with pytest.raises(RuntimeError):
            registry.handle_fs_read("/path")


class TestHandlerRegistryTerminalExtended:
    """Дополнительные тесты для Terminal обработчиков."""

    def test_register_terminal_wait_handler(self) -> None:
        """Проверяет регистрацию terminal_wait обработчика."""
        registry = HandlerRegistry()

        def handler(terminal_id: str) -> int:
            return 0

        registry.register_terminal_wait_handler(handler)
        result = registry.handle_terminal_wait("term_1")

        assert result == 0

    def test_terminal_wait_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии terminal_wait обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_terminal_wait("term_1")

    def test_register_terminal_release_handler(self) -> None:
        """Проверяет регистрацию terminal_release обработчика."""
        registry = HandlerRegistry()

        def handler(terminal_id: str) -> None:
            pass

        registry.register_terminal_release_handler(handler)
        registry.handle_terminal_release("term_1")

    def test_terminal_release_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии terminal_release обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_terminal_release("term_1")

    def test_terminal_output_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии terminal_output обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_terminal_output("term_1")

    def test_terminal_kill_handler_not_registered(self) -> None:
        """Проверяет ошибку при отсутствии terminal_kill обработчика."""
        registry = HandlerRegistry()
        with pytest.raises(RuntimeError, match="not registered"):
            registry.handle_terminal_kill("term_1")


class TestHandlerRegistryGeneric:
    """Тесты для generic обработчиков."""

    def test_register_and_get_generic_handler(self) -> None:
        """Проверяет регистрацию и получение generic обработчика."""
        registry = HandlerRegistry()

        def custom_handler() -> str:
            return "custom"

        registry.register("custom_handler", custom_handler)
        result = registry.get("custom_handler")

        assert result is custom_handler

    def test_get_nonexistent_handler(self) -> None:
        """Проверяет получение несуществующего обработчика."""
        registry = HandlerRegistry()
        result = registry.get("nonexistent")

        assert result is None


class TestHandlerRegistryExceptions:
    """Тесты обработки исключений в обработчиках."""

    @pytest.mark.asyncio
    async def test_permission_handler_exception(self) -> None:
        """Проверяет обработку исключения в permission обработчике."""
        registry = HandlerRegistry()

        def bad_handler(data: dict) -> str:
            raise ValueError("Handler error")

        registry.register_permission_handler(bad_handler)

        with pytest.raises(RuntimeError, match="Permission handler failed"):
            await registry.handle_permission({})

    def test_fs_read_handler_exception(self) -> None:
        """Проверяет обработку исключения в fs_read обработчике."""
        registry = HandlerRegistry()

        def bad_handler(path: str) -> str:
            raise OSError("Read error")

        registry.register_fs_read_handler(bad_handler)

        with pytest.raises(RuntimeError, match="FS read handler failed"):
            registry.handle_fs_read("/path")

    def test_fs_write_handler_exception(self) -> None:
        """Проверяет обработку исключения в fs_write обработчике."""
        registry = HandlerRegistry()

        def bad_handler(path: str, content: str) -> str | None:
            raise OSError("Write error")

        registry.register_fs_write_handler(bad_handler)

        with pytest.raises(RuntimeError, match="FS write handler failed"):
            registry.handle_fs_write("/path", "content")

    def test_terminal_create_handler_exception(self) -> None:
        """Проверяет обработку исключения в terminal_create обработчике."""
        registry = HandlerRegistry()

        def bad_handler(shell: str) -> str:
            raise RuntimeError("Create error")

        registry.register_terminal_create_handler(bad_handler)

        with pytest.raises(RuntimeError, match="Terminal create handler failed"):
            registry.handle_terminal_create("bash")

    def test_terminal_output_handler_exception(self) -> None:
        """Проверяет обработку исключения в terminal_output обработчике."""
        registry = HandlerRegistry()

        def bad_handler(terminal_id: str) -> str:
            raise RuntimeError("Output error")

        registry.register_terminal_output_handler(bad_handler)

        with pytest.raises(RuntimeError, match="Terminal output handler failed"):
            registry.handle_terminal_output("term_1")

    def test_terminal_wait_handler_exception(self) -> None:
        """Проверяет обработку исключения в terminal_wait обработчике."""
        registry = HandlerRegistry()

        def bad_handler(terminal_id: str) -> int:
            raise RuntimeError("Wait error")

        registry.register_terminal_wait_handler(bad_handler)

        with pytest.raises(RuntimeError, match="Terminal wait handler failed"):
            registry.handle_terminal_wait("term_1")

    def test_terminal_release_handler_exception(self) -> None:
        """Проверяет обработку исключения в terminal_release обработчике."""
        registry = HandlerRegistry()

        def bad_handler(terminal_id: str) -> None:
            raise RuntimeError("Release error")

        registry.register_terminal_release_handler(bad_handler)

        with pytest.raises(RuntimeError, match="Terminal release handler failed"):
            registry.handle_terminal_release("term_1")

    def test_terminal_kill_handler_exception(self) -> None:
        """Проверяет обработку исключения в terminal_kill обработчике."""
        registry = HandlerRegistry()

        def bad_handler(terminal_id: str) -> bool:
            raise RuntimeError("Kill error")

        registry.register_terminal_kill_handler(bad_handler)

        with pytest.raises(RuntimeError, match="Terminal kill handler failed"):
            registry.handle_terminal_kill("term_1")

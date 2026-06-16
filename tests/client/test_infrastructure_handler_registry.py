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

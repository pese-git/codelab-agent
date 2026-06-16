"""Unit-тесты для StdioClientTransport timeout механизма.

Проверяет:
- Увеличенный timeout (300s вместо 60s)
- Информативные сообщения об ошибках timeout
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from codelab.client.infrastructure.stdio_transport import StdioClientTransport


class TestStdioClientTransportTimeout:
    """Тесты timeout механизма в StdioClientTransport."""

    def test_default_timeout_is_300_seconds(self) -> None:
        """Проверяет, что default timeout увеличен до 300 секунд."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
        )
        
        assert transport._receive_timeout == 300.0

    def test_custom_timeout_can_be_set(self) -> None:
        """Проверяет, что можно установить custom timeout."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
            receive_timeout=600.0,
        )
        
        assert transport._receive_timeout == 600.0

    @pytest.mark.asyncio
    async def test_timeout_error_message_is_informative(self) -> None:
        """Проверяет, что сообщение об ошибке timeout информативное."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
            receive_timeout=1.0,  # Короткий timeout для теста
        )
        
        # Имитируем запущенный процесс
        transport._process = MagicMock()
        transport._process.returncode = None
        transport._stdout_queue = asyncio.Queue()
        
        # Пытаемся получить сообщение с коротким timeout
        with pytest.raises(RuntimeError) as exc_info:
            await asyncio.wait_for(
                transport.receive_text(),
                timeout=2.0,
            )
        
        error_message = str(exc_info.value)
        
        # Проверяем, что сообщение содержит полезную информацию
        assert "Timeout" in error_message
        assert "1.0" in error_message  # timeout value
        assert "long-running operation" in error_message or "stalled" in error_message

    @pytest.mark.asyncio
    async def test_receive_text_returns_message_when_available(self) -> None:
        """Проверяет, что receive_text возвращает сообщение, когда оно доступно."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
            receive_timeout=5.0,
        )
        
        # Имитируем запущенный процесс
        transport._process = MagicMock()
        transport._process.returncode = None
        transport._stdout_queue = asyncio.Queue()
        
        # Добавляем сообщение в очередь
        test_message = '{"jsonrpc": "2.0", "id": 1, "result": {}}'
        await transport._stdout_queue.put(test_message)
        
        # Получаем сообщение
        result = await transport.receive_text()
        
        assert result == test_message

    @pytest.mark.asyncio
    async def test_receive_text_raises_when_process_exited(self) -> None:
        """Проверяет, что receive_text выбрасывает ошибку, если процесс завершился."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
            receive_timeout=5.0,
        )
        
        # Имитируем завершённый процесс
        transport._process = MagicMock()
        transport._process.returncode = 1
        transport._stdout_queue = asyncio.Queue()
        
        with pytest.raises(RuntimeError, match="Subprocess exited"):
            await transport.receive_text()

    @pytest.mark.asyncio
    async def test_receive_text_raises_when_transport_closed(self) -> None:
        """Проверяет, что receive_text выбрасывает ошибку, если транспорт закрыт."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
            receive_timeout=5.0,
        )
        
        transport._closed = True
        
        with pytest.raises(RuntimeError, match="Transport is closed"):
            await transport.receive_text()

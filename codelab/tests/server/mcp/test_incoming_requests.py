"""Тесты для обработки входящих запросов от сервера к клиенту.

Согласно MCP спецификации, сервер может отправлять запросы клиенту
(например, roots/list). Клиент должен правильно обрабатывать такие запросы.

Эти тесты проверяют:
1. Правильную классификацию JSON-RPC 2.0 сообщений
2. Обработку входящих запросов
3. Регистрацию обработчиков
4. Отправку ответов и ошибок
"""

import json
from unittest.mock import AsyncMock

import pytest

from codelab.server.mcp.transport import (
    HttpTransport,
    SseTransport,
    StdioTransport,
)


class TestJsonRpcMessageClassification:
    """Тесты правильной классификации JSON-RPC 2.0 сообщений."""
    
    @pytest.mark.asyncio
    async def test_classify_request_message(self):
        """Сообщение с method и id классифицируется как Request."""
        transport = StdioTransport(command="test")
        
        # Mock для проверки вызова _handle_incoming_request
        transport._handle_incoming_request = AsyncMock()
        transport._handle_response_message = AsyncMock()
        transport._handle_notification = AsyncMock()
        
        # Request: method + id
        request_message = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": 1
        }
        
        await transport._handle_message(request_message)
        
        # Должен быть вызван _handle_incoming_request
        transport._handle_incoming_request.assert_called_once_with(request_message)
        transport._handle_response_message.assert_not_called()
        transport._handle_notification.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_classify_response_message(self):
        """Сообщение с result/error и id классифицируется как Response."""
        transport = StdioTransport(command="test")
        
        # Mock для проверки вызова _handle_response_message
        transport._handle_incoming_request = AsyncMock()
        transport._handle_response_message = AsyncMock()
        transport._handle_notification = AsyncMock()
        
        # Response: result + id
        response_message = {
            "jsonrpc": "2.0",
            "result": {"roots": []},
            "id": 1
        }
        
        await transport._handle_message(response_message)
        
        # Должен быть вызван _handle_response_message
        transport._handle_response_message.assert_called_once_with(response_message)
        transport._handle_incoming_request.assert_not_called()
        transport._handle_notification.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_classify_error_response_message(self):
        """Сообщение с error и id классифицируется как Response (error)."""
        transport = StdioTransport(command="test")
        
        # Mock для проверки вызова _handle_response_message
        transport._handle_incoming_request = AsyncMock()
        transport._handle_response_message = AsyncMock()
        transport._handle_notification = AsyncMock()
        
        # Error Response: error + id
        error_message = {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": 1
        }
        
        await transport._handle_message(error_message)
        
        # Должен быть вызван _handle_response_message
        transport._handle_response_message.assert_called_once_with(error_message)
        transport._handle_incoming_request.assert_not_called()
        transport._handle_notification.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_classify_notification_message(self):
        """Сообщение с method без id классифицируется как Notification."""
        transport = StdioTransport(command="test")
        
        # Mock для проверки вызова _handle_notification
        transport._handle_incoming_request = AsyncMock()
        transport._handle_response_message = AsyncMock()
        transport._handle_notification = AsyncMock()
        
        # Notification: method без id
        notification_message = {
            "jsonrpc": "2.0",
            "method": "notifications/roots/list_changed",
            "params": {}
        }
        
        await transport._handle_message(notification_message)
        
        # Должен быть вызван _handle_notification
        transport._handle_notification.assert_called_once_with(notification_message)
        transport._handle_incoming_request.assert_not_called()
        transport._handle_response_message.assert_not_called()


class TestIncomingRequestHandling:
    """Тесты обработки входящих запросов от сервера."""
    
    @pytest.mark.asyncio
    async def test_handle_incoming_request_with_handler(self):
        """Входящий запрос обрабатывается зарегистрированным обработчиком."""
        transport = StdioTransport(command="test")
        
        # Mock для отправки ответа
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        
        # Регистрируем обработчик
        async def mock_handler(params):
            return {"roots": [{"uri": "file:///test", "name": "Test"}]}
        
        transport.register_request_handler("roots/list", mock_handler)
        
        # Входящий запрос
        request_message = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": 1
        }
        
        await transport._handle_incoming_request(request_message)
        
        # Должен быть отправлен ответ
        transport.send_response.assert_called_once()
        transport.send_error.assert_not_called()
        
        # Проверяем содержимое ответа
        call_args = transport.send_response.call_args
        assert call_args[0][0] == 1  # request_id
        assert call_args[0][1] == {"roots": [{"uri": "file:///test", "name": "Test"}]}
    
    @pytest.mark.asyncio
    async def test_handle_incoming_request_without_handler(self):
        """Входящий запрос без обработчика возвращает ошибку Method not found."""
        transport = StdioTransport(command="test")
        
        # Mock для отправки ошибки
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        
        # НЕ регистрируем обработчик
        
        # Входящий запрос
        request_message = {
            "jsonrpc": "2.0",
            "method": "unknown/method",
            "params": {},
            "id": 1
        }
        
        await transport._handle_incoming_request(request_message)
        
        # Должна быть отправлена ошибка
        transport.send_response.assert_not_called()
        transport.send_error.assert_called_once()
        
        # Проверяем код ошибки
        call_args = transport.send_error.call_args
        assert call_args[0][0] == 1  # request_id
        assert call_args[0][1] == -32601  # Method not found
    
    @pytest.mark.asyncio
    async def test_handle_incoming_request_handler_exception(self):
        """Исключение в обработчике возвращает ошибку Internal error."""
        transport = StdioTransport(command="test")
        
        # Mock для отправки ошибки
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        
        # Регистрируем обработчик, который выбрасывает исключение
        async def failing_handler(params):
            raise ValueError("Test error")
        
        transport.register_request_handler("roots/list", failing_handler)
        
        # Входящий запрос
        request_message = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": 1
        }
        
        await transport._handle_incoming_request(request_message)
        
        # Должна быть отправлена ошибка
        transport.send_response.assert_not_called()
        transport.send_error.assert_called_once()
        
        # Проверяем код ошибки
        call_args = transport.send_error.call_args
        assert call_args[0][0] == 1  # request_id
        assert call_args[0][1] == -32603  # Internal error


class TestHttpTransportIncomingRequests:
    """Тесты обработки входящих запросов в HttpTransport."""
    
    @pytest.mark.asyncio
    async def test_http_classify_request_message(self):
        """HttpTransport правильно классифицирует Request."""
        transport = HttpTransport(url="http://test")
        
        # Mock для проверки вызова
        transport._handle_incoming_request = AsyncMock()
        transport._handle_response_message = AsyncMock()
        transport._handle_notification = AsyncMock()
        
        request_message = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": 1
        }
        
        await transport._handle_response(request_message)
        
        transport._handle_incoming_request.assert_called_once_with(request_message)


class TestSseTransportIncomingRequests:
    """Тесты обработки входящих запросов в SseTransport."""
    
    @pytest.mark.asyncio
    async def test_sse_classify_request_message(self):
        """SseTransport правильно классифицирует Request."""
        transport = SseTransport(url="http://test")
        
        # Mock для проверки вызова
        transport._handle_incoming_request = AsyncMock()
        transport._handle_response_message = AsyncMock()
        transport._handle_notification = AsyncMock()
        
        request_message = {
            "jsonrpc": "2.0",
            "method": "roots/list",
            "params": {},
            "id": 1
        }
        
        await transport._handle_sse_event("message", json.dumps(request_message))
        
        transport._handle_incoming_request.assert_called_once_with(request_message)

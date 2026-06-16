"""Сервис парсинга ACP-сообщений.

Модуль предоставляет:
- Централизованный парсинг JSON-сообщений
- Классификацию сообщений по типам (request/response/notification)
- Типизированный парсинг результатов методов (initialize, authenticate, etc.)

Пример использования:
    parser = MessageParser()
    message = parser.parse_json('{"jsonrpc": "2.0", "id": 1, ...}')
    init_result = parser.parse_initialize_result(message)
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import ValidationError

from ..messages import (
    ACPMessage,
    AuthenticateResult,
    InitializeResult,
    parse_authenticate_result,
    parse_initialize_result,
    parse_prompt_result,
    parse_request_permission_request,
    parse_session_list_result,
    parse_session_setup_result,
    parse_session_update_notification,
)

logger = structlog.get_logger("acp_client.message_parser")


class MessageParser:
    """Парсер ACP-сообщений с типизацией результатов.

    Класс предоставляет методы для:
    - Базового парсинга JSON-сообщений в ACPMessage
    - Типизированного парсинга результатов специфичных методов
    - Классификации сообщений (request/response/notification)

    Пример использования:
        parser = MessageParser()
        msg = parser.parse_json('{"jsonrpc": "2.0", "id": "1", "result": {...}}')
        init_result = parser.parse_initialize_result(msg)
    """

    @staticmethod
    def parse_json(data: str) -> ACPMessage:
        """Парсит JSON-строку в ACPMessage с валидацией.

        Args:
            data: JSON-строка для парсинга

        Returns:
            Распарсенное ACPMessage

        Raises:
            ValueError: Если JSON невалиден или не соответствует схеме ACP
            json.JSONDecodeError: Если JSON синтаксис ошибочен

        Пример:
            msg = parser.parse_json('{"jsonrpc": "2.0", "id": "1", "result": {}}')
        """
        try:
            # Парсим JSON
            payload = json.loads(data)
            logger.debug("json_parsed", length=len(data))

            # Валидируем и преобразуем в ACPMessage
            message = ACPMessage.model_validate(payload)
            logger.debug("message_validated", has_error=message.error is not None)
            return message
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON: {e}"
            logger.error("json_decode_error", error=str(e))
            raise ValueError(msg) from e
        except ValidationError as e:
            msg = f"Message validation failed: {e}"
            logger.error("message_validation_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_dict(payload: dict[str, Any]) -> ACPMessage:
        """Парсит dict в ACPMessage с валидацией.

        Args:
            payload: Dict-объект для парсинга

        Returns:
            Распарсенное ACPMessage

        Raises:
            ValueError: Если payload не соответствует схеме ACP

        Пример:
            msg = parser.parse_dict({"jsonrpc": "2.0", "id": "1", "result": {}})
        """
        try:
            message = ACPMessage.model_validate(payload)
            logger.debug("message_validated_from_dict", has_error=message.error is not None)
            return message
        except ValidationError as e:
            msg = f"Message validation failed: {e}"
            logger.error("message_validation_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def classify_message(message: ACPMessage) -> str:
        """Классифицирует сообщение по типу.

        Args:
            message: ACPMessage для классификации

        Returns:
            "request", "notification" или "response"

        Пример:
            msg_type = parser.classify_message(msg)
            # Возвращает "response"
        """
        if message.method is not None:
            if message.id is not None:
                return "request"
            else:
                return "notification"
        else:
            return "response"

    @staticmethod
    def parse_initialize_result(message: ACPMessage) -> InitializeResult:
        """Парсит ответ на `initialize` в типизированный объект.

        Args:
            message: ACPMessage ответ от `initialize`

        Returns:
            Типизированный InitializeResult

        Raises:
            ValueError: Если парсинг не удался

        Пример:
            init_result = parser.parse_initialize_result(response)
            print(init_result.serverCapabilities)
        """
        try:
            result = parse_initialize_result(message)
            logger.debug("initialize_result_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse initialize result: {e}"
            logger.error("initialize_parse_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_authenticate_result(message: ACPMessage) -> AuthenticateResult:
        """Парсит ответ на `authenticate` в типизированный объект.

        Args:
            message: ACPMessage ответ от `authenticate`

        Returns:
            Типизированный AuthenticateResult

        Raises:
            ValueError: Если парсинг не удался

        Пример:
            auth_result = parser.parse_authenticate_result(response)
        """
        try:
            result = parse_authenticate_result(message)
            logger.debug("authenticate_result_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse authenticate result: {e}"
            logger.error("authenticate_parse_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_session_setup_result(
        message: ACPMessage,
        *,
        method_name: str = "session/new",
    ) -> Any:
        """Парсит ответ на `session/new` или `session/load` в типизированный объект.

        Args:
            message: ACPMessage ответ от `session/new` или `session/load`
            method_name: Имя метода (для логирования ошибок)

        Returns:
            Типизированный SessionSetupResult

        Raises:
            ValueError: Если парсинг не удался
        """
        try:
            result = parse_session_setup_result(message, method_name=method_name)
            logger.debug("session_setup_result_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse session setup result: {e}"
            logger.error("session_setup_parse_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_session_list_result(message: ACPMessage) -> Any:
        """Парсит ответ на `session/list` в типизированный объект.

        Args:
            message: ACPMessage ответ от `session/list`

        Returns:
            Типизированный SessionListResult

        Raises:
            ValueError: Если парсинг не удался
        """
        try:
            result = parse_session_list_result(message)
            logger.debug("session_list_result_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse session list result: {e}"
            logger.error("session_list_parse_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_prompt_result(message: ACPMessage) -> Any:
        """Парсит ответ на `session/prompt` в типизированный объект.

        Args:
            message: ACPMessage ответ от `session/prompt`

        Returns:
            Типизированный PromptResult

        Raises:
            ValueError: Если парсинг не удался
        """
        try:
            result = parse_prompt_result(message)
            logger.debug("prompt_result_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse prompt result: {e}"
            logger.error("prompt_parse_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_session_update(message: dict[str, Any]) -> Any:
        """Парсит `session/update` уведомление.

        Args:
            message: Dict содержащий session/update

        Returns:
            Типизированный SessionUpdateNotification

        Raises:
            ValueError: Если парсинг не удался

        Пример:
            update = parser.parse_session_update(update_dict)
        """
        try:
            result = parse_session_update_notification(message)
            logger.debug("session_update_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse session update: {e}"
            logger.error("session_update_parse_error", error=str(e))
            raise ValueError(msg) from e

    @staticmethod
    def parse_permission_request(message: dict[str, Any]) -> Any:
        """Парсит `session/request_permission` запрос.

        Args:
            message: Dict содержащий session/request_permission

        Returns:
            Типизированный PermissionRequest или None если не permission запрос

        Пример:
            perm_req = parser.parse_permission_request(message_dict)
            if perm_req:
                # Это permission запрос
        """
        try:
            result = parse_request_permission_request(message)
            if result is not None:
                logger.debug("permission_request_parsed")
            return result
        except Exception as e:
            msg = f"Failed to parse permission request: {e}"
            logger.error("permission_request_parse_error", error=str(e))
            raise ValueError(msg) from e

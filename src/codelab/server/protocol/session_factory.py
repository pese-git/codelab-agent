"""Фабрика для создания сессий ACP.

Централизует логику создания новых сессий, устраняя дублирование кода
между различными обработчиками протокола.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ..exceptions import ValidationError
from .state import SessionState

if TYPE_CHECKING:
    from .state import ClientRuntimeCapabilities


class SessionFactory:
    """Фабрика для создания новых сессий."""

    @staticmethod
    def create_session(
        cwd: str,
        mcp_servers: list[dict[str, Any]] | None = None,
        config_values: dict[str, str] | None = None,
        available_commands: list[Any] | None = None,
        runtime_capabilities: ClientRuntimeCapabilities | None = None,
        session_id: str | None = None,
    ) -> SessionState:
        """Создает новую сессию с заданными параметрами.

        Args:
            cwd: Рабочая директория (обязательна, должна быть абсолютным путём)
            mcp_servers: Список MCP-серверов (опционально)
            config_values: Значения конфигурации сессии (опционально)
            available_commands: Доступные slash-команды (опционально)
            runtime_capabilities: Runtime capabilities клиента (опционально,
                используется для фильтрации tools)
            session_id: ID сессии (генерируется автоматически, если не указан)

        Returns:
            SessionState: Новая сессия

        Raises:
            ValidationError: Если параметры некорректны
        """
        # Валидация обязательных параметров
        SessionFactory.validate_session_params(
            {
                "cwd": cwd,
                "mcp_servers": mcp_servers,
                "config_values": config_values,
            }
        )

        # Генерация ID, если не указан
        if session_id is None:
            session_id = f"sess_{uuid4().hex[:12]}"

        # Подготовка значений по умолчанию
        mcp_servers = mcp_servers or []
        config_values = config_values or {}
        available_commands = available_commands or []

        # Фильтруем только dict-сервера
        filtered_mcp_servers = [srv for srv in mcp_servers if isinstance(srv, dict)]

        # Создание сессии
        return SessionState(
            session_id=session_id,
            cwd=cwd,
            mcp_servers=filtered_mcp_servers,
            config_values=config_values,
            available_commands=available_commands,
            runtime_capabilities=runtime_capabilities,
        )

    @staticmethod
    def validate_session_params(params: dict) -> None:
        """Валидирует параметры создания сессии.

        Args:
            params: Параметры для создания сессии

        Raises:
            ValidationError: Если параметры некорректны
        """
        # Проверка обязательных параметров
        if "cwd" not in params or not isinstance(params["cwd"], str):
            raise ValidationError("cwd обязателен и должен быть строкой")

        # Проверка типов опциональных параметров
        if (
            "mcp_servers" in params
            and params["mcp_servers"] is not None
            and not isinstance(params["mcp_servers"], list)
        ):
            raise ValidationError(
                f"mcp_servers должен быть списком, получен {type(params['mcp_servers'])}"
            )

        if (
            "config_values" in params
            and params["config_values"] is not None
            and not isinstance(params["config_values"], dict)
        ):
            raise ValidationError(
                f"config_values должен быть dict, получен {type(params['config_values'])}"
            )

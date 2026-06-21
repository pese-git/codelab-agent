"""SetModeCommandHandler - обработчик метода session/set_mode.

Переключает режим работы агента в сессии.
"""

from __future__ import annotations

from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers import config
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class SetModeCommandHandler:
    """Обработчик метода session/set_mode.

    Отвечает за:
    - Переключение режима работы агента (plan/standard/bypass)
    - Обновление конфигурации сессии

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/set_mode"

    def __init__(
        self,
        storage: SessionStorage,
        config_specs: dict[str, dict[str, Any]],
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
            config_specs: Спецификации конфигурационных опций.
        """
        self._storage = storage
        self._config_specs = config_specs

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/set_mode.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом переключения режима.
        """
        params = message.params or {}
        return await config.session_set_mode(
            message.id,
            params,
            self._storage,
            self._config_specs,
        )

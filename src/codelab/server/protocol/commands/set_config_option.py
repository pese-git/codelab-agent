"""SetConfigOptionCommandHandler - обработчик метода session/set_config_option.

Устанавливает значение конфигурационной опции сессии.
"""

from __future__ import annotations

from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers import config
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class SetConfigOptionCommandHandler:
    """Обработчик метода session/set_config_option.

    Отвечает за:
    - Установку значения конфигурационной опции
    - Инвалидацию кэша model resolver при смене модели

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/set_config_option"

    def __init__(
        self,
        storage: SessionStorage,
        config_specs: dict[str, dict[str, Any]],
        model_resolver: Any | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
            config_specs: Спецификации конфигурационных опций.
            model_resolver: Резолвер моделей для cache invalidation.
        """
        self._storage = storage
        self._config_specs = config_specs
        self._model_resolver = model_resolver

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/set_config_option.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом установки опции.
        """
        params = message.params or {}
        return await config.session_set_config_option(
            message.id,
            params,
            self._storage,
            self._config_specs,
            model_resolver=self._model_resolver,
        )

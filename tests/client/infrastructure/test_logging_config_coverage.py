"""Тесты покрытия для logging_config.

Покрывает ранее непокрытые сценарии:
- настройку файлового логирования в setup_logging;
- ранний выход из OperationTimer.__exit__ без __enter__.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from unittest.mock import MagicMock, patch

from codelab.client.infrastructure.logging_config import OperationTimer, setup_logging


class TestSetupLogging:
    """Тесты для setup_logging."""

    def test_setup_logging_creates_file_handler(self, tmp_path: Path) -> None:
        """setup_logging настраивает RotatingFileHandler при указании log_file."""
        log_file = tmp_path / "logs" / "acp_client.log"
        mock_handler = MagicMock()

        with patch(
            "codelab.client.infrastructure.logging_config.logging.handlers.RotatingFileHandler",
            return_value=mock_handler,
        ) as mock_rotating_handler, patch(
            "codelab.client.infrastructure.logging_config.logging.basicConfig"
        ) as mock_basic_config:
            setup_logging(level="INFO", log_file=str(log_file))

        assert log_file.parent.exists()
        mock_rotating_handler.assert_called_once_with(
            filename=str(log_file),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        mock_handler.setFormatter.assert_called_once()
        formatter = mock_handler.setFormatter.call_args.args[0]
        assert isinstance(formatter, logging.Formatter)
        assert formatter._fmt == "%(message)s"
        mock_basic_config.assert_called_once()


class TestOperationTimer:
    """Тесты для OperationTimer."""

    def test_exit_without_enter_does_not_log(self) -> None:
        """__exit__ без __enter__ не логирует, т.к. start_time не задан."""
        logger = MagicMock()
        timer = OperationTimer(logger, "test_operation")

        result = timer.__exit__(None, None, None)

        assert result is None
        logger.info.assert_not_called()
        logger.error.assert_not_called()

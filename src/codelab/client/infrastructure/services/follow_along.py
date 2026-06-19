"""Follow-along service для автоматического открытия файлов при tool calls.

Предоставляет механизм автоматического открытия файлов в IDE,
когда агент выполняет операции с файлами (read, write).
"""

from __future__ import annotations

from typing import Any, Protocol


class FileOpener(Protocol):
    """Protocol для открытия файлов в IDE."""

    async def open(self, path: str, line: int | None = None) -> None:
        """Открыть файл в IDE.

        Args:
            path: Путь к файлу
            line: Номер строки (опционально)
        """
        ...


class StubFileOpener:
    """Stub реализация FileOpener для тестов.

    Логирует вызовы без реального открытия файлов.
    """

    def __init__(self) -> None:
        """Инициализировать stub."""
        self.calls: list[dict[str, Any]] = []

    async def open(self, path: str, line: int | None = None) -> None:
        """Записать вызов в лог.

        Args:
            path: Путь к файлу
            line: Номер строки (опционально)
        """
        self.calls.append({"path": path, "line": line})


class FollowAlongService:
    """Сервис для автоматического открытия файлов при tool calls.

    Реагирует на обновления tool calls и открывает файлы,
    с которыми работал агент.
    """

    def __init__(
        self,
        file_opener: FileOpener,
        enabled: bool = True,
    ) -> None:
        """Инициализировать сервис.

        Args:
            file_opener: Реализация FileOpener
            enabled: Флаг включения сервиса
        """
        self._file_opener = file_opener
        self._enabled = enabled

    async def on_tool_call_updated(self, tool_call: dict[str, Any]) -> None:
        """Обработать обновление tool call.

        Открывает первый файл из locations, если сервис включен.

        Args:
            tool_call: Данные tool call с полями locations, status, etc.
        """
        if not self._enabled:
            return

        locations = tool_call.get("locations", [])
        if not locations:
            return

        first_location = locations[0]
        path = first_location.get("path")
        if not path:
            return

        line = first_location.get("line")
        await self._file_opener.open(path, line)

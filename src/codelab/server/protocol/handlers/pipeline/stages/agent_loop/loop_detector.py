"""Детектор зацикливания агента на повторяющемся tool-call (tech-debt #22)."""

from __future__ import annotations

import json
from typing import Protocol


class _ExecutionResult(Protocol):
    """Минимальный контракт результата исполнения для записи вывода."""

    success: bool
    output: str | None
    error: str | None


class ToolLoopDetector:
    """Отслеживает повторные вызовы одной и той же команды в рамках prompt-turn.

    Сигнал зацикливания — ПОВТОР одной команды: сигнатура ``имя tool + args``.
    Считаются вхождения сигнатуры за turn (а не «строго подряд» — устойчиво к
    чередованию, напр. ``terminal/create`` ↔ ``terminal/wait_for_exit``) и НЕ по
    результату: ``terminal/create`` каждый раз возвращает новый terminal id, поэтому
    ключ «тот же результат» никогда бы не совпал. Разные args (напр. ``wait_for_exit``
    с разными ``terminal_id``) дают разные сигнатуры и не флагаются.

    Экземпляр живёт один prompt-turn (создаётся вместе с ``ToolCallProcessor``),
    поэтому состояние — простые in-memory словари, сбрасываемые сменой turn.

    Attributes:
        limit: Порог повторов. При ``limit <= 0`` детектор отключён (feature-flag).
    """

    def __init__(self, limit: int = 3) -> None:
        self._limit = limit
        self._counts: dict[str, int] = {}
        self._outputs: dict[str, str] = {}

    @property
    def limit(self) -> int:
        """Порог повторов."""
        return self._limit

    @property
    def enabled(self) -> bool:
        """Активен ли детектор (``limit > 0``)."""
        return self._limit > 0

    @staticmethod
    def signature(tool_name: str, arguments: dict) -> str:
        """Стабильная сигнатура tool-call: имя + нормализованные аргументы."""
        try:
            args = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            args = repr(arguments)
        return f"{tool_name}\x00{args}"

    def register_attempt(self, tool_name: str, arguments: dict) -> bool:
        """Учесть попытку вызова; вернуть ``True``, если превышен лимит повторов.

        Считает вхождения сигнатуры за turn. ``True`` означает, что эту команду
        нужно отклонить (повтор не продвигает задачу).
        """
        if not self.enabled:
            return False
        signature = self.signature(tool_name, arguments)
        count = self._counts.get(signature, 0) + 1
        self._counts[signature] = count
        return count > self._limit

    def record_output(self, tool_name: str, arguments: dict, result: _ExecutionResult) -> None:
        """Запомнить последний вывод команды — для подсказки при блокировке."""
        if not self.enabled:
            return
        signature = self.signature(tool_name, arguments)
        text = (result.output if result.success else result.error) or ""
        self._outputs[signature] = text

    def repeat_count(self, tool_name: str, arguments: dict) -> int:
        """Сколько раз команда запрашивалась за turn."""
        return self._counts.get(self.signature(tool_name, arguments), 0)

    def last_output(self, tool_name: str, arguments: dict) -> str:
        """Последний зафиксированный вывод команды (или пустая строка)."""
        return self._outputs.get(self.signature(tool_name, arguments), "")

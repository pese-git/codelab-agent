"""ClientCapabilities — общий доменный VO протокола ACP.

Возможности, которые **клиент** объявляет серверу в ACP-хендшейке ``initialize``:
файловая система и терминал (``clientCapabilities`` по спецификации). Форму задаёт
спецификация ACP, а не внутренняя модель одной из сторон, поэтому это Shared Kernel:
и сервер, и клиент импортируют один и тот же тип из ``codelab.shared``.

Мультимодальный ввод — рядом, в ``shared.prompt_capabilities.PromptCapabilities``:
по ACP ``image``/``audio``/``embeddedContext`` входят в
``agentCapabilities.promptCapabilities``, то есть описывают возможности **агента**
принимать такой контент, а не возможности клиента. Здесь они лежали как дубль без
потребителей и создавали видимость лоссового маппинга (tech-debt P2-32).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClientCapabilities:
    """Возможности клиента, объявленные в ACP ``initialize``.

    Инкапсулирует возможности клиента (файловая система, терминал, мультимодальный ввод).
    """

    fs_read: bool = False
    fs_write: bool = False
    terminal: bool = False

    @property
    def supports_fs(self) -> bool:
        return self.fs_read or self.fs_write

    def can_read_files(self) -> bool:
        return self.fs_read

    def can_write_files(self) -> bool:
        return self.fs_write

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientCapabilities:
        """Собрать VO из словаря, игнорируя незнакомые ключи.

        Терпимость к лишним ключам сохранена сознательно: словари приходят из
        внешнего обмена. Ключи мультимодальности здесь больше не читаются — их
        носитель `PromptCapabilities`.
        """
        return cls(
            fs_read=bool(data.get("fs_read", False)),
            fs_write=bool(data.get("fs_write", False)),
            terminal=bool(data.get("terminal", False)),
        )

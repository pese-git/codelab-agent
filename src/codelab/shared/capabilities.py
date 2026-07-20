"""ClientCapabilities — общий доменный VO протокола ACP.

Возможности, которые клиент объявляет серверу в ACP-хендшейке ``initialize``
(файловая система, терминал, мультимодальный ввод). Форму задаёт спецификация
ACP, а не внутренняя модель одной из сторон, поэтому это Shared Kernel: и сервер,
и клиент импортируют один и тот же тип из ``codelab.shared``.
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
    image_prompts: bool = False
    embedded_context: bool = False

    @property
    def supports_fs(self) -> bool:
        return self.fs_read or self.fs_write

    @property
    def supports_multimodal(self) -> bool:
        return self.image_prompts or self.embedded_context

    def can_read_files(self) -> bool:
        return self.fs_read

    def can_write_files(self) -> bool:
        return self.fs_write

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientCapabilities:
        return cls(
            fs_read=bool(data.get("fs_read", False)),
            fs_write=bool(data.get("fs_write", False)),
            terminal=bool(data.get("terminal", False)),
            image_prompts=bool(data.get("image_prompts", False)),
            embedded_context=bool(data.get("embedded_context", False)),
        )

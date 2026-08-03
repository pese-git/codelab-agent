"""Контекст выполнения pipeline обработки prompt-turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codelab.server.domain.session import Session as DomainSession
from codelab.server.llm.content_parts import ContentPart
from codelab.server.messages import ACPMessage, JsonRpcId
from codelab.server.protocol.session_commands import SessionCommands


@dataclass
class PromptContext:
    """Изменяемый контекст, передаваемый через все стадии pipeline."""

    # Входные данные
    session_id: str
    # Носитель состояния turn'а — доменный агрегат (ADR-006, фаза D шаг 3). Wire-DTO
    # собирается только внутри репозитория, поэтому по ходу turn'а существует одна
    # правда, а не две.
    #
    # `session` — только чтение. Изменения идут через `commands`: команда
    # применяется к агрегату, загруженному в момент применения, и коммитится тут
    # же (ADR-006, фаза D шаг 4). Прямая мутация `session` не доедет до диска —
    # ближайший коммит перенесёт в неё состояние из хранилища и затрёт её.
    session: DomainSession
    commands: SessionCommands
    request_id: JsonRpcId | None
    params: dict[str, Any]
    raw_text: str

    # Мультимодальное содержимое (ContentPart-ы, маппенные из ACP блоков)
    content_parts: list[ContentPart] = field(default_factory=list)

    # Результаты, накапливаемые по ходу pipeline
    notifications: list[ACPMessage] = field(default_factory=list)
    stop_reason: str = "end_turn"
    should_stop: bool = False  # True — прервать pipeline досрочно
    error_response: ACPMessage | None = None
    pending_permission: bool = False  # True — turn отложен, ожидает разрешения

    # Метаданные для передачи между стадиями
    meta: dict[str, Any] = field(default_factory=dict)

"""Контекст выполнения pipeline обработки prompt-turn."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from codelab.server.domain.session import Session as DomainSession
from codelab.server.llm.content_parts import ContentPart
from codelab.server.messages import ACPMessage, JsonRpcId


@dataclass
class PromptContext:
    """Изменяемый контекст, передаваемый через все стадии pipeline."""

    # Входные данные
    session_id: str
    # Носитель состояния turn'а — доменный агрегат (ADR-006, фаза D шаг 3). Wire-DTO
    # собирается только на границе сохранения (`persist`), поэтому по ходу turn'а
    # существует одна правда, а не две.
    session: DomainSession
    request_id: JsonRpcId | None
    params: dict[str, Any]
    raw_text: str

    # Мультимодальное содержимое (ContentPart-ы, маппенные из ACP блоков)
    content_parts: list[ContentPart] = field(default_factory=list)

    # Результаты, накапливаемые по ходу pipeline
    # Сохранение состояния на шаге turn'а (ADR-007). Turn держит свою копию весь
    # turn, поэтому без промежуточных записей его окно расхождения измерялось
    # десятками секунд — на живом прогоне 39 с. Callback, а не storage: цикл не
    # должен знать про хранилище.
    persist: Callable[[], Awaitable[None]] | None = None

    notifications: list[ACPMessage] = field(default_factory=list)
    stop_reason: str = "end_turn"
    should_stop: bool = False  # True — прервать pipeline досрочно
    error_response: ACPMessage | None = None
    pending_permission: bool = False  # True — turn отложен, ожидает разрешения

    # Метаданные для передачи между стадиями
    meta: dict[str, Any] = field(default_factory=dict)

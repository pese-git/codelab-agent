"""Эквивалентность history-seam'ов wire и домена (фаза B ADR-006).

Сеймы одноимённы, но пишут в разных представлениях: `SessionState` — сырую
wire-запись, `domain.Session` — `ConversationMessage`. При switch резидента в
фазе D сайт останется тем же, поэтому записи обязаны быть эквивалентны с
точностью до маппера: иначе смена носителя молча изменит формат хранения.
"""

from __future__ import annotations

import pytest

from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.value_objects import SessionId
from codelab.server.mapping.history_mapper import HistoryMapper
from codelab.server.protocol.state import SessionState


def _wire_session() -> SessionState:
    return SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])


def _domain_session() -> Session:
    return Session(id=SessionId("sess_1"), config=SessionConfig(cwd="/tmp"))


def _slots(entry: object) -> dict[str, object]:
    """Смысловые слоты записи истории без timestamp (он всегда «сейчас»)."""
    data = dict(entry) if isinstance(entry, dict) else entry.model_dump(exclude_none=True)  # type: ignore[union-attr]
    data.pop("timestamp", None)
    return {k: v for k, v in data.items() if v is not None}


@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param([{"type": "text", "text": "привет"}], id="text"),
        pytest.param(
            [
                {"type": "text", "text": "смотри"},
                {"type": "image", "data": "abc", "mimeType": "image/png"},
            ],
            id="text+image",
        ),
        pytest.param(
            [
                {"type": "text", "text": "файл"},
                {"type": "resource", "resource": {"uri": "file:///a.py", "text": "code"}},
            ],
            id="text+resource",
        ),
        pytest.param(
            [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
            id="two-text",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "domain MessageContent хранит текст одной строкой, а ресурсы и "
                    "картинки отдельными списками: несколько text-блоков склеиваются "
                    "через перевод строки, а исходный порядок блоков не "
                    "восстанавливается (маппер собирает текст → ресурсы → картинки). "
                    "На живом промпте [resource, text] это даёт [text, resource], "
                    "то есть инструкция оказывается до приложенного файла"
                ),
            ),
        ),
    ],
)
def test_user_message_seams_are_equivalent(prompt: list[dict[str, object]]) -> None:
    """Запись пользователя одинакова: wire напрямую и домен через маппер."""
    wire = _wire_session()
    wire.add_user_message(prompt)

    domain = _domain_session()
    domain.add_user_message(prompt)

    mapped = HistoryMapper.to_protocol(domain.history.get_messages()[0])

    assert _slots(wire.history[0]) == _slots(mapped)


def test_assistant_text_seams_are_equivalent() -> None:
    """Ответ ассистента строкой одинаков (единственный вариант в проде)."""
    wire = _wire_session()
    wire.add_assistant_message("готово")

    domain = _domain_session()
    domain.add_assistant_message("готово")

    mapped = HistoryMapper.to_protocol(domain.history.get_messages()[0])

    assert _slots(wire.history[0]) == _slots(mapped)


def test_user_message_survives_domain_roundtrip() -> None:
    """Доменная запись читается маппером обратно без потерь."""
    prompt = [
        {"type": "text", "text": "текст"},
        {"type": "image", "data": "zz", "mimeType": "image/jpeg"},
    ]
    domain = _domain_session()
    domain.add_user_message(prompt)
    message = domain.history.get_messages()[0]

    restored = HistoryMapper.to_domain(HistoryMapper.to_protocol(message))

    assert restored.content == message.content
    assert restored.role == message.role

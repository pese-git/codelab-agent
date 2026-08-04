"""Эквивалентность history-seam'ов wire и домена (фаза B ADR-006).

Сеймы одноимённы, но пишут в разных представлениях: `SessionDocument` — сырую
wire-запись, `domain.Session` — `ConversationMessage`. При switch резидента в
фазе D сайт останется тем же, поэтому записи обязаны быть эквивалентны с
точностью до маппера: иначе смена носителя молча изменит формат хранения.
"""

from __future__ import annotations

import pytest

from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import SessionId
from codelab.server.mapping.history_mapper import HistoryMapper
from codelab.server.storage.document import SessionDocument


def _wire_session() -> SessionDocument:
    return SessionDocument(session_id="sess_1", cwd="/tmp", mcp_servers=[])


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
        ),
        pytest.param(
            [
                {"type": "resource", "resource": {"uri": "file:///README.md", "text": "# doc"}},
                {"type": "text", "text": "перепиши по этому файлу"},
            ],
            id="resource-before-text",
        ),
        pytest.param(
            [
                {"type": "image", "data": "abc", "mimeType": "image/png"},
                {"type": "text", "text": "что на картинке"},
            ],
            id="image-before-text",
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


def test_assistant_tool_call_seam_matches_the_form_turn_writes_today() -> None:
    """Запись «ассистент + tool_calls» через сейм совпадает с сырой формой turn'а.

    Wire-сейма для неё нет: turn-цикл (`agent_loop/loop.py`) собирает эту запись
    сырым dict'ом. Именно поэтому история хранит две формы одной записи — этот
    тест закрепляет, что доменный сейм даёт ту же форму, а не «похожую».
    """
    domain = _domain_session()
    domain.add_assistant_tool_call_message(
        "смотрю файлы",
        [ToolCall(id="call_1", tool_name="fs/read", arguments={"path": "/a.py"})],
    )

    mapped = HistoryMapper.to_protocol(domain.history.get_messages()[0])

    raw_form_written_by_turn_today = {
        "role": "assistant",
        "text": "смотрю файлы",
        "tool_calls": [{"id": "call_1", "name": "fs/read", "arguments": {"path": "/a.py"}}],
    }
    assert _slots(mapped) == raw_form_written_by_turn_today


def test_assistant_tool_call_seam_survives_domain_roundtrip() -> None:
    """tool_calls в записи ассистента читаются обратно без потерь."""
    domain = _domain_session()
    domain.add_assistant_tool_call_message(
        "",
        [
            ToolCall(id="call_1", tool_name="fs/read", arguments={"path": "/a.py"}),
            ToolCall(id="call_2", tool_name="terminal/create", arguments={}),
        ],
    )
    message = domain.history.get_messages()[0]

    restored = HistoryMapper.to_domain(HistoryMapper.to_protocol(message))

    assert [(tc.id, tc.tool_name, tc.arguments) for tc in restored.tool_calls] == [
        ("call_1", "fs/read", {"path": "/a.py"}),
        ("call_2", "terminal/create", {}),
    ]


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


def test_block_order_survives_domain_roundtrip() -> None:
    """Порядок блоков — часть содержимого: [resource, text] не переворачивается.

    Раньше домен держал текст одной строкой, а ресурсы и картинки — отдельными
    списками, поэтому обратная сборка шла фиксированно текст → ресурсы →
    картинки: на живом промпте инструкция оказывалась перед файлом, который она
    комментирует (блокер фазы D, ADR-006).
    """
    prompt = [
        {"type": "resource", "resource": {"uri": "file:///README.md", "text": "# doc"}},
        {"type": "text", "text": "перепиши по этому файлу"},
    ]
    domain = _domain_session()
    domain.add_user_message(prompt)

    wire = HistoryMapper.to_protocol(domain.history.get_messages()[0])

    assert wire.content is not None
    assert [block["type"] for block in wire.content] == ["resource", "text"]


def test_repeated_text_blocks_are_not_merged() -> None:
    """Несколько text-блоков остаются отдельными записями, а не склеенной строкой."""
    domain = _domain_session()
    domain.add_user_message([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])

    message = domain.history.get_messages()[0]

    assert [block.text for block in message.content.blocks] == ["a", "b"]  # type: ignore[union-attr]
    assert message.content.text == "a\nb"

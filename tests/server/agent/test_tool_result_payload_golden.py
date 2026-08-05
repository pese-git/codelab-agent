"""Golden-payload результата инструмента ДО такта 1 (change `multimodal-tool-results`, шаг 0).

Фиксирует форму, в которой результат инструмента доходит до модели **сегодня**, в обеих семьях
провайдеров. Такт 1 меняет только путь нетекстовых блоков; для текстового результата — а это
подавляющее большинство вызовов — payload обязан остаться байт-идентичным, иначе рушится prompt
cache (правило детерминизма проекта).

Ломается этот тест → изменилась форма текстового tool-ответа, то есть цена правки вышла за
заявленную область.

Семей форм две, и различие принципиально (оно определяет, куда допустимо положить изображение):
* OpenAI-совместимая (8 провайдеров) — `{"role": "tool", "tool_call_id", "content"}`, совпадает с
  внутренним каноном `LLMMessage`;
* Anthropic — `tool_result`-блок в списке `content`.

**Гейт нашёл два дефекта Anthropic-ветки, оба закрыты в такте 1.** Anthropic Messages API допускает
у сообщения только роли `user` и `assistant`, а `tool_result`-блоки кладутся в сообщение с ролью
`user`. Адаптер копировал роль канона (`tool`), то есть отдавал невалидный запрос — Anthropic с
инструментами не работал вовсе. Вторым дефектом та же ветка не конвертировала
`list[ContentPart]` и уехала бы в API объектами. Дефекты были латентными: живой путь владельца —
OpenAI-совместимая семья через litellm, поэтому ветка в поле не исполняется, и подтверждение здесь
тестом, а не прогоном.
"""

from __future__ import annotations

from codelab.server.agent.core.history_builder import HistoryBuilder
from codelab.server.llm.providers.anthropic import AnthropicProvider
from codelab.server.protocol.content.acp_codec import ACPContentCodec

TOOL_CALL_ID = "chatcmpl-tool-abc"
RESULT_TEXT = "lib/main.dart\nlib/app.dart"


def _history_with_tool_result() -> list[dict]:
    """История одного полного цикла: запрос → assistant с вызовом → ответ инструмента."""
    return [
        {"role": "user", "content": "перечисли файлы"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": TOOL_CALL_ID, "name": "fs_read_text_file", "arguments": {"path": "lib"}}
            ],
        },
        {"role": "tool", "content": RESULT_TEXT, "tool_call_id": TOOL_CALL_ID},
    ]


class TestCanonicalForm:
    """Канон `LLMMessage` — то, что производит `HistoryBuilder` для всех провайдеров."""

    def test_tool_result_is_plain_string_in_canon(self) -> None:
        messages = HistoryBuilder(ACPContentCodec()).build(_history_with_tool_result())

        tool_messages = [m for m in messages if m.role == "tool"]
        assert len(tool_messages) == 1
        tool_message = tool_messages[0]
        assert tool_message.content == RESULT_TEXT
        assert isinstance(tool_message.content, str), "текстовый результат остаётся строкой"
        assert tool_message.tool_call_id == TOOL_CALL_ID

    def test_canon_preserves_order_and_roles(self) -> None:
        """Порядок сообщений — часть контракта LLM-API: ответ инструмента идёт за вызовом."""
        messages = HistoryBuilder(ACPContentCodec()).build(_history_with_tool_result())

        assert [m.role for m in messages] == ["user", "assistant", "tool"]
        assert messages[1].tool_calls is not None
        assert messages[1].tool_calls[0].id == TOOL_CALL_ID


class TestAnthropicForm:
    """Единственный провайдер, переписывающий форму tool-ответа."""

    def test_tool_result_wire_form(self) -> None:
        """Роль `user` — требование Anthropic Messages API для `tool_result`."""
        messages = HistoryBuilder(ACPContentCodec()).build(_history_with_tool_result())

        converted = AnthropicProvider()._convert_to_anthropic_format(messages)

        tool_messages = [
            m
            for m in converted
            if isinstance(m.get("content"), list)
            and any(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in m["content"]
            )
        ]
        assert len(tool_messages) == 1
        assert tool_messages[0] == {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": TOOL_CALL_ID,
                    "content": RESULT_TEXT,
                }
            ],
        }

    def test_tool_result_content_is_converted(self) -> None:
        """Блоки внутри `tool_result` конвертируются, а не уезжают объектами `ContentPart`.

        Anthropic допускает блоки внутри `tool_result`, поэтому конвертация идёт тем же путём,
        что у user/assistant. Такт 2 (данные доходят до модели) на это опирается.
        """
        from codelab.server.llm.content_parts import ContentPart
        from codelab.server.llm.models import LLMMessage

        message = LLMMessage(
            role="tool",
            content=[
                ContentPart.make_text("описание"),
                ContentPart.make_image("BASE64", "image/png"),
            ],
            tool_call_id=TOOL_CALL_ID,
        )

        converted = AnthropicProvider()._convert_to_anthropic_format([message])

        payload = converted[0]["content"][0]["content"]
        assert payload == [
            {"type": "text", "text": "описание"},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "BASE64"},
            },
        ]
        assert not any(isinstance(part, ContentPart) for part in payload)

"""Рендер ACP-блоков результата инструмента в текст для модели.

Файл переписан в такте 1 change'а `multimodal-tool-results`. Прежде он проверял
`ContentFormatter.format_for_llm` — сборку сообщения под провайдера, — но эта поверхность была
дублем: канон сообщения производит `HistoryBuilder`, а отклонения от канона живут каждое в своём
адаптере провайдера (у Anthropic — `llm/providers/anthropic.py`). Возврат `format_for_llm` при этом
никто не присваивал, то есть проверялся путь, которого в проде не существовало.

Сам класс тоже удалён: после переноса рендера он был бы пустой прослойкой над одной функцией.
Дом рендера — `shared/content/description.py`, потому что его зовут и turn-путь, и MCP-адаптер, а
`mcp` не вправе зависеть от `protocol` (контракт `Server layers`).

**Знание тестов сохранено, а не выброшено:** как именно описывается каждый тип блока
(`text`/`diff`/`image`/`audio`/`embedded`/`resource_link`, ACP-конверт `content`, порядок,
разделитель, спецсимволы, вложенность) — проверяется здесь, но против единственной оставшейся
поверхности `render_as_text`.

Описание — не данные: base64 в текст не попадает, доставка самих данных идёт в такте 2, за шагом C
расщепления (ADR-007).
"""

from codelab.shared.content.description import describe_acp_content


class TestTextBlocks:
    def test_single_text_is_passed_through(self) -> None:
        """Для текста описание и есть само содержимое — оно не переупаковывается."""
        assert describe_acp_content([{"type": "text", "text": "готово"}]) == "готово"

    def test_multiple_texts_joined_by_blank_line(self) -> None:
        result = describe_acp_content(
            [{"type": "text", "text": "первый"}, {"type": "text", "text": "второй"}]
        )

        assert result == "первый\n\nвторой"

    def test_empty_text_is_skipped(self) -> None:
        """Пустой блок не даёт пустого абзаца в разделителе."""
        result = describe_acp_content(
            [{"type": "text", "text": ""}, {"type": "text", "text": "есть"}]
        )

        assert result == "есть"

    def test_special_characters_are_not_escaped(self) -> None:
        text = 'кавычки "" и \\ и \n перевод'

        assert describe_acp_content([{"type": "text", "text": text}]) == text


class TestAcpContentEnvelope:
    def test_envelope_is_unwrapped(self) -> None:
        """ACP `ToolCallContent` оборачивает блок в `{"type": "content", "content": {...}}`.

        Без разворачивания конверт пропускался целиком, и терминальный результат описывался
        пустой строкой.
        """
        result = describe_acp_content(
            [{"type": "content", "content": {"type": "text", "text": "вывод команды"}}]
        )

        assert result == "вывод команды"

    def test_envelope_around_image(self) -> None:
        result = describe_acp_content(
            [
                {
                    "type": "content",
                    "content": {"type": "image", "data": "BASE64", "mimeType": "image/png"},
                }
            ]
        )

        assert result == "[Image: image/png]"

    def test_malformed_envelope_is_skipped(self) -> None:
        assert describe_acp_content([{"type": "content", "content": "не блок"}]) == ""


class TestMediaBlocks:
    """Медиа описывается по настоящим полям ACP: `mimeType`, необязательный `uri`."""

    def test_image_by_mime_type(self) -> None:
        result = describe_acp_content(
            [{"type": "image", "data": "BASE64", "mimeType": "image/png"}]
        )

        assert result == "[Image: image/png]"

    def test_image_data_never_leaks_into_text(self) -> None:
        """Главный инвариант: base64 не место в тексте для модели."""
        result = describe_acp_content(
            [{"type": "image", "data": "СЕКРЕТНЫЙ_BASE64", "mimeType": "image/png"}]
        )

        assert "СЕКРЕТНЫЙ_BASE64" not in result

    def test_image_uri_is_named(self) -> None:
        """`uri` — единственная ссылка на данные, которую можно назвать без самих данных."""
        result = describe_acp_content(
            [
                {
                    "type": "image",
                    "data": "BASE64",
                    "mimeType": "image/png",
                    "uri": "file:///tmp/a.png",
                }
            ]
        )

        assert result == "[Image: image/png, file:///tmp/a.png]"

    def test_audio_by_mime_type(self) -> None:
        result = describe_acp_content(
            [{"type": "audio", "data": "BASE64", "mimeType": "audio/wav"}]
        )

        assert result == "[Audio: audio/wav]"

    def test_legacy_field_names_still_work(self) -> None:
        """`alt_text`/`format` приняты как запасные ключи — их могут прислать свои производители."""
        result = describe_acp_content(
            [{"type": "image", "format": "png", "alt_text": "график"}]
        )

        assert result == "[Image: png, график]"

    def test_unknown_mime_type_is_named_unknown(self) -> None:
        assert describe_acp_content([{"type": "image", "data": "X"}]) == "[Image: unknown]"


class TestDiffBlock:
    def test_diff_shows_both_sides(self) -> None:
        result = describe_acp_content(
            [{"type": "diff", "path": "/a.py", "oldText": "было", "newText": "стало"}]
        )

        assert result == "File: /a.py\n\nOld:\n```\nбыло\n```\n\nNew:\n```\nстало\n```"

    def test_diff_with_missing_old_text(self) -> None:
        """Новый файл: `oldText` отсутствует — блок всё равно описывается, а не пропускается."""
        result = describe_acp_content(
            [{"type": "diff", "path": "/new.py", "newText": "содержимое"}]
        )

        assert "File: /new.py" in result
        assert "содержимое" in result


class TestResourceBlocks:
    def test_resource_link_names_uri(self) -> None:
        result = describe_acp_content(
            [{"type": "resource_link", "uri": "https://example.com/doc"}]
        )

        assert result == "[Resource: https://example.com/doc]"

    def test_embedded_content_is_rendered_recursively(self) -> None:
        result = describe_acp_content(
            [{"type": "embedded", "content": [{"type": "text", "text": "внутри"}]}]
        )

        assert result == "[Embedded content]\nвнутри"

    def test_deeply_nested_embedded(self) -> None:
        result = describe_acp_content(
            [
                {
                    "type": "embedded",
                    "content": [
                        {
                            "type": "embedded",
                            "content": [{"type": "text", "text": "глубоко"}],
                        }
                    ],
                }
            ]
        )

        assert result == "[Embedded content]\n[Embedded content]\nглубоко"

    def test_embedded_with_non_list_content_is_skipped(self) -> None:
        assert describe_acp_content([{"type": "embedded", "content": "строка"}]) == ""


class TestOrderAndRobustness:
    def test_order_is_preserved(self) -> None:
        """Порядок блоков — часть содержимого, а не деталь представления."""
        result = describe_acp_content(
            [
                {"type": "image", "data": "X", "mimeType": "image/png"},
                {"type": "text", "text": "подпись под картинкой"},
            ]
        )

        assert result == "[Image: image/png]\n\nподпись под картинкой"

    def test_unknown_block_type_is_skipped_not_raised(self) -> None:
        """Расширение протокола не должно ронять путь результата инструмента."""
        result = describe_acp_content(
            [{"type": "видео-из-будущего"}, {"type": "text", "text": "есть"}]
        )

        assert result == "есть"

    def test_terminal_block_is_not_described(self) -> None:
        """`terminal` — клиентский дескриптор; модели он ничего не говорит.

        Alias терминала модель уже получает в `output` исполнителя, поэтому дублировать
        дескриптор в описании незачем.
        """
        assert describe_acp_content([{"type": "terminal", "terminalId": "abc"}]) == ""

    def test_empty_list_gives_empty_string(self) -> None:
        assert describe_acp_content([]) == ""

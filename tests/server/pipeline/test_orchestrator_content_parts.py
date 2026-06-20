"""Интеграционный тест: промпт с image → content_parts заполнены."""

from codelab.server.protocol.content.acp_mapper import ACPContentMapper


class TestOrchestratorContentPartsMapping:
    """Тесты маппинга промпт-блоков в content_parts."""

    def test_image_blocks_mapped_to_content_parts(self) -> None:
        prompt = [
            {"type": "text", "text": "Look at this:"},
            {"type": "image", "data": "abc", "mimeType": "image/png"},
        ]
        parts = ACPContentMapper().map_blocks(prompt)
        assert len(parts) == 2
        assert parts[0].type == "text"
        assert parts[0].text == "Look at this:"
        assert parts[1].type == "image"
        assert parts[1].data == "abc"
        assert parts[1].mime_type == "image/png"

    def test_text_only_blocks_mapped(self) -> None:
        prompt = [{"type": "text", "text": "Hello"}]
        parts = ACPContentMapper().map_blocks(prompt)
        assert len(parts) == 1
        assert parts[0].type == "text"
        assert parts[0].text == "Hello"

    def test_resource_blocks_mapped_to_text(self) -> None:
        prompt = [
            {"type": "resource", "resource": {"uri": "file:///test", "text": "content"}},
        ]
        parts = ACPContentMapper().map_blocks(prompt)
        assert len(parts) == 1
        assert parts[0].type == "text"
        assert "file:///test" in parts[0].text

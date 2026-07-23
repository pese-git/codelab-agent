"""Тесты для ACPContentCodec (перенесён из agent.acp_content_mapper)."""

from codelab.server.protocol.content.acp_codec import ACPContentCodec


class TestACPContentCodec:
    """Тесты маппинга ACP ContentBlock → ContentPart."""

    def setup_method(self) -> None:
        self.mapper = ACPContentCodec()

    def test_map_text_block(self) -> None:
        result = self.mapper.decode([{"type": "text", "text": "Hello"}])
        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "Hello"

    def test_map_image_block(self) -> None:
        result = self.mapper.decode(
            [
                {"type": "image", "data": "abc", "mimeType": "image/png"},
            ]
        )
        assert len(result) == 1
        assert result[0].type == "image"
        assert result[0].data == "abc"
        assert result[0].mime_type == "image/png"

    def test_map_resource_block(self) -> None:
        result = self.mapper.decode(
            [
                {"type": "resource", "resource": {"uri": "file:///test", "text": "content"}},
            ]
        )
        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "[Resource: file:///test]\ncontent"

    def test_map_resource_link_block(self) -> None:
        result = self.mapper.decode(
            [
                {"type": "resource_link", "uri": "file:///test", "name": "test.txt"},
            ]
        )
        assert len(result) == 1
        assert result[0].type == "text"
        assert result[0].text == "[Resource link: test.txt (file:///test)]"

    def test_map_mixed_blocks(self) -> None:
        result = self.mapper.decode(
            [
                {"type": "text", "text": "Look at this:"},
                {"type": "image", "data": "abc", "mimeType": "image/png"},
            ]
        )
        assert len(result) == 2
        assert result[0].type == "text"
        assert result[0].text == "Look at this:"
        assert result[1].type == "image"
        assert result[1].data == "abc"

    def test_map_unknown_type_returns_empty(self) -> None:
        result = self.mapper.decode([{"type": "unknown_xyz", "data": "xyz"}])
        assert result == []

    def test_map_audio_block(self) -> None:
        result = self.mapper.decode(
            [
                {"type": "audio", "data": "xyz", "mimeType": "audio/wav"},
            ]
        )
        assert len(result) == 1
        assert result[0].type == "audio"
        assert result[0].data == "xyz"
        assert result[0].mime_type == "audio/wav"

    def test_map_empty_blocks(self) -> None:
        result = self.mapper.decode([])
        assert result == []

"""Нетекстовый результат MCP-инструмента теряется — гейт ДО такта 1.

Change `multimodal-tool-results`, шаг 0.2. Фиксирует **текущую** потерю, чтобы правка такта 1
показала разницу наблюдаемо, а не «стало лучше на словах».

Механизм потери (проверен по коду, три звена):

1. `mcp_content_to_acp_list` честно конвертирует MCP content в ACP-блоки, включая `image` с base64
   (`mcp/content_mapper.py`);
2. `extract_text_from_acp_content` **молча отбрасывает всё, кроме `type == "text"`** — без
   плейсхолдера, без предупреждения;
3. `result.content` не задаётся вовсе, поэтому `ToolResultMapper.to_acp_content` отдаёт клиенту
   текстовый fallback, а блоки уезжают только в `raw_output`.

Следствие: инструмент, вернувший **только** изображение, даёт `output == ""`. Дальше turn-путь
пишет в историю `"Success"` — модель не узнаёт, что изображение вообще было.

**Живым прогоном не покрывается:** MCP-серверов у владельца не настроено ни одного (`is_mcp=False`
на каждом вызове прогона 2026-08-05), поэтому ветка закрывается тестом. Это сказано прямо, чтобы
«ноль ошибок в логе» не приняли за проверку.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.mcp.client import MCPClient
from codelab.server.mcp.tool_adapter import MCPToolAdapter

_BASE64_PIXEL = "iVBORw0KGgoAAAANSUhEUg=="


def _adapter_returning(content: list[dict], *, is_error: bool = False) -> MCPToolAdapter:
    client = MagicMock(spec=MCPClient)
    result = MagicMock()
    result.content = content
    result.is_error = is_error
    client.call_tool = AsyncMock(return_value=result)
    return MCPToolAdapter(server_id="test_server", client=client)


class TestImageOnlyResultIsLost:
    @pytest.mark.asyncio
    async def test_output_is_empty_for_image_only_result(self) -> None:
        """Главный гейт: изображение не оставляет следа в тексте результата."""
        adapter = _adapter_returning(
            [{"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"}]
        )
        executor = await adapter.create_executor("screenshot")

        result = await executor()

        assert result.success is True
        assert result.output == "", "текущее поведение: нетекстовый блок исчезает бесследно"

    @pytest.mark.asyncio
    async def test_blocks_are_not_offered_to_the_client(self) -> None:
        """`result.content` не задаётся, поэтому клиент тоже не получает блоки."""
        adapter = _adapter_returning(
            [{"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"}]
        )
        executor = await adapter.create_executor("screenshot")

        result = await executor()

        assert result.content is None

    @pytest.mark.asyncio
    async def test_base64_survives_only_in_raw_output(self) -> None:
        """Данные персистятся в `raw_output` — без читателей и без ограничения размера.

        Это же наблюдение — вход в решение Р2 (политика размера) такта 2.
        """
        adapter = _adapter_returning(
            [{"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"}]
        )
        executor = await adapter.create_executor("screenshot")

        result = await executor()

        assert _BASE64_PIXEL in str(result.raw_output)


class TestMixedResultKeepsOnlyText:
    @pytest.mark.asyncio
    async def test_text_survives_and_image_does_not(self) -> None:
        """Смешанный результат: текст доходит, изображение исчезает молча."""
        adapter = _adapter_returning(
            [
                {"type": "text", "text": "график за июль"},
                {"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"},
            ]
        )
        executor = await adapter.create_executor("chart")

        result = await executor()

        assert result.output == "график за июль"
        assert "image" not in result.output
        assert "Image" not in result.output, "плейсхолдера сегодня нет"


class TestTextOnlyResultIsUnaffected:
    @pytest.mark.asyncio
    async def test_text_only_is_passed_through(self) -> None:
        """Опорная точка: текстовый результат такт 1 менять не должен."""
        adapter = _adapter_returning([{"type": "text", "text": "готово"}])
        executor = await adapter.create_executor("run")

        result = await executor()

        assert result.output == "готово"
        assert result.success is True

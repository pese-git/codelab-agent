"""Нетекстовый результат MCP-инструмента больше не теряется (такт 1, шаги 0.2 и 2).

Тест заведён как гейт **до** правки — он фиксировал потерю, а теперь фиксирует её отсутствие. Так
разница видна в истории изменений: сначала `output == ""`, теперь `[Image: image/png]`.

Механизм потери, который был (проверен по коду, три звена):

1. `mcp_content_to_acp_list` честно конвертирует MCP content в ACP-блоки, включая `image` с base64
   (`mcp/content_mapper.py`);
2. `extract_text_from_acp_content` **молча отбрасывает всё, кроме `type == "text"`** — без
   плейсхолдера, без предупреждения;
3. `result.content` не задаётся вовсе, поэтому `ToolResultMapper.to_acp_content` отдаёт клиенту
   текстовый fallback, а блоки уезжают только в `raw_output`.

Следствие было: инструмент, вернувший **только** изображение, давал `output == ""`, дальше turn-путь
писал в историю `"Success"`, и модель не узнавала, что изображение вообще было.

**Что изменилось.** Нетекстовые блоки описываются одним рендером на сервер
(`ContentFormatter.render_as_text`) по настоящим полям ACP (`mimeType`, `uri`). Данные (base64) в
описание не попадают намеренно: их доставка идёт за шагом C расщепления (ADR-007), иначе один
скриншот стоит сотни МБ записи. `result.content` тоже пока не заполняется — по той же причине.

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


class TestImageOnlyResultIsDescribed:
    @pytest.mark.asyncio
    async def test_image_leaves_a_trace_in_output(self) -> None:
        """Главный гейт такта 1: модель узнаёт о существовании изображения."""
        adapter = _adapter_returning(
            [{"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"}]
        )
        executor = await adapter.create_executor("screenshot")

        result = await executor()

        assert result.success is True
        assert result.output == "[Image: image/png]"

    @pytest.mark.asyncio
    async def test_base64_is_not_put_into_output(self) -> None:
        """Инвариант такта 1: данные не попадают в текст для модели.

        Иначе base64 уехал бы и в историю, и в payload — то есть в документ сессии, чью цену
        решение Р2 отложило до шага C.
        """
        adapter = _adapter_returning(
            [{"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"}]
        )
        executor = await adapter.create_executor("screenshot")

        result = await executor()

        assert _BASE64_PIXEL not in (result.output or "")

    @pytest.mark.asyncio
    async def test_uri_is_included_when_present(self) -> None:
        """`uri` — единственная ссылка на данные, которую можно назвать без самих данных."""
        adapter = _adapter_returning(
            [
                {
                    "type": "image",
                    "data": _BASE64_PIXEL,
                    "mimeType": "image/png",
                    "uri": "file:///tmp/shot.png",
                }
            ]
        )
        executor = await adapter.create_executor("screenshot")

        result = await executor()

        assert result.output == "[Image: image/png, file:///tmp/shot.png]"

    @pytest.mark.asyncio
    async def test_blocks_are_still_not_offered_to_the_client(self) -> None:
        """`result.content` не задаётся **намеренно**: это положило бы base64 в документ.

        Клиент получает то же текстовое описание. Данные — такт 2, после шага C (решение Р2).
        """
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


class TestMixedResultKeepsBoth:
    @pytest.mark.asyncio
    async def test_text_and_image_description_both_survive(self) -> None:
        """Смешанный результат: текст доходит, изображение — описанием, порядок сохранён."""
        adapter = _adapter_returning(
            [
                {"type": "text", "text": "график за июль"},
                {"type": "image", "data": _BASE64_PIXEL, "mimeType": "image/png"},
            ]
        )
        executor = await adapter.create_executor("chart")

        result = await executor()

        assert result.output == "график за июль\n\n[Image: image/png]"


class TestTextOnlyResultIsUnaffected:
    @pytest.mark.asyncio
    async def test_text_only_is_passed_through(self) -> None:
        """Опорная точка: текстовый результат такт 1 менять не должен."""
        adapter = _adapter_returning([{"type": "text", "text": "готово"}])
        executor = await adapter.create_executor("run")

        result = await executor()

        assert result.output == "готово"
        assert result.success is True

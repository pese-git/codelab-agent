"""Unit тесты для FollowAlongService."""

import pytest

from codelab.client.infrastructure.services.follow_along import (
    FollowAlongService,
    StubFileOpener,
)


class TestStubFileOpener:
    """Тесты для StubFileOpener."""

    @pytest.mark.asyncio
    async def test_stub_records_calls(self) -> None:
        """Stub записывает вызовы."""
        stub = StubFileOpener()
        await stub.open("/tmp/test.py", line=10)
        await stub.open("/tmp/other.py")

        assert len(stub.calls) == 2
        assert stub.calls[0] == {"path": "/tmp/test.py", "line": 10}
        assert stub.calls[1] == {"path": "/tmp/other.py", "line": None}


class TestFollowAlongService:
    """Тесты для FollowAlongService."""

    @pytest.mark.asyncio
    async def test_disabled_service_does_nothing(self) -> None:
        """Выключенный сервис ничего не делает."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=False)

        await service.on_tool_call_updated({
            "locations": [{"path": "/tmp/test.py", "line": 10}],
        })

        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_empty_locations_does_nothing(self) -> None:
        """Пустые locations ничего не делают."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=True)

        await service.on_tool_call_updated({
            "locations": [],
        })

        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_missing_locations_does_nothing(self) -> None:
        """Отсутствующие locations ничего не делают."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=True)

        await service.on_tool_call_updated({})

        assert len(stub.calls) == 0

    @pytest.mark.asyncio
    async def test_single_location_opens_file(self) -> None:
        """Одна location открывает файл."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=True)

        await service.on_tool_call_updated({
            "locations": [{"path": "/tmp/test.py", "line": 42}],
        })

        assert len(stub.calls) == 1
        assert stub.calls[0] == {"path": "/tmp/test.py", "line": 42}

    @pytest.mark.asyncio
    async def test_multiple_locations_opens_first(self) -> None:
        """Несколько locations открывают первый файл."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=True)

        await service.on_tool_call_updated({
            "locations": [
                {"path": "/tmp/first.py", "line": 10},
                {"path": "/tmp/second.py", "line": 20},
            ],
        })

        assert len(stub.calls) == 1
        assert stub.calls[0] == {"path": "/tmp/first.py", "line": 10}

    @pytest.mark.asyncio
    async def test_location_without_line(self) -> None:
        """Location без line открывает файл без номера строки."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=True)

        await service.on_tool_call_updated({
            "locations": [{"path": "/tmp/test.py"}],
        })

        assert len(stub.calls) == 1
        assert stub.calls[0] == {"path": "/tmp/test.py", "line": None}

    @pytest.mark.asyncio
    async def test_location_without_path_does_nothing(self) -> None:
        """Location без path ничего не делает."""
        stub = StubFileOpener()
        service = FollowAlongService(stub, enabled=True)

        await service.on_tool_call_updated({
            "locations": [{"line": 10}],
        })

        assert len(stub.calls) == 0

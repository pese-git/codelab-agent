"""Тесты для SessionViewModel."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from codelab.client.presentation.session_view_model import SessionViewModel


class TestSessionViewModel:
    """Тесты для SessionViewModel класса."""

    @pytest.fixture
    def coordinator(self) -> AsyncMock:
        """Создать mock coordinator."""
        return AsyncMock()

    @pytest.fixture
    def event_bus(self) -> Mock:
        """Создать mock event_bus."""
        return Mock()

    @pytest.fixture
    def vm(self, coordinator: AsyncMock, event_bus: Mock) -> SessionViewModel:
        """Создать SessionViewModel с mock зависимостями."""
        return SessionViewModel(coordinator, event_bus=event_bus)

    def test_viewmodel_initialization(self, vm: SessionViewModel) -> None:
        """Проверить инициализацию SessionViewModel."""
        assert vm.sessions.value == []
        assert vm.selected_session_id.value is None
        assert vm.is_loading_sessions.value is False
        assert vm.error_message.value is None
        assert vm.session_count.value == 0

    def test_observable_properties(self, vm: SessionViewModel) -> None:
        """Проверить что свойства это Observable."""
        from codelab.client.presentation.observable import Observable

        assert isinstance(vm.sessions, Observable)
        assert isinstance(vm.selected_session_id, Observable)
        assert isinstance(vm.is_loading_sessions, Observable)
        assert isinstance(vm.error_message, Observable)

    @pytest.mark.asyncio
    async def test_load_sessions(self, vm: SessionViewModel, coordinator: AsyncMock) -> None:
        """Проверить загрузку сессий."""
        mock_sessions = [
            MagicMock(id="session1"),
            MagicMock(id="session2"),
        ]
        coordinator.list_sessions.return_value = mock_sessions

        await vm.load_sessions_cmd.execute()

        assert vm.sessions.value == mock_sessions
        assert vm.session_count.value == 2
        assert vm.is_loading_sessions.value is False
        coordinator.list_sessions.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_sessions_error(self, vm: SessionViewModel, coordinator: AsyncMock) -> None:
        """Проверить обработку ошибки при загрузке сессий."""
        coordinator.list_sessions.side_effect = RuntimeError("Connection failed")

        # _load_sessions ловит исключение и устанавливает error_message
        await vm.load_sessions_cmd.execute()

        assert vm.is_loading_sessions.value is False
        assert vm.error_message.value is not None
        assert "Failed to load sessions" in vm.error_message.value

    @pytest.mark.asyncio
    async def test_create_session(self, vm: SessionViewModel, coordinator: AsyncMock) -> None:
        """Проверить создание новой сессии."""
        # coordinator.create_session теперь возвращает dict с session_id
        coordinator.create_session.return_value = {
            "session_id": "new_session",
            "server_capabilities": {},
            "is_authenticated": False,
        }

        await vm.create_session_cmd.execute("localhost", 8080)

        assert len(vm.sessions.value) == 1
        assert vm.sessions.value[0].id == "new_session"
        assert vm.selected_session_id.value == "new_session"
        assert vm.session_count.value == 1

    @pytest.mark.asyncio
    async def test_create_session_adds_to_existing(
        self, vm: SessionViewModel, coordinator: AsyncMock
    ) -> None:
        """Проверить что новая сессия добавляется к существующим."""
        existing = MagicMock(id="existing")
        vm.sessions.value = [existing]

        coordinator.create_session.return_value = {
            "session_id": "new",
            "server_capabilities": {},
            "is_authenticated": False,
        }

        await vm.create_session_cmd.execute("localhost", 8080)

        assert len(vm.sessions.value) == 2
        assert vm.session_count.value == 2

    @pytest.mark.asyncio
    async def test_switch_session_valid(self, vm: SessionViewModel) -> None:
        """Проверить переключение на существующую сессию."""
        session1 = MagicMock(id="s1")
        session2 = MagicMock(id="s2")
        vm.sessions.value = [session1, session2]

        await vm.switch_session_cmd.execute("s2")

        assert vm.selected_session_id.value == "s2"

    @pytest.mark.asyncio
    async def test_switch_session_invalid(self, vm: SessionViewModel) -> None:
        """Проверить переключение на несуществующую сессию."""
        session1 = MagicMock(id="s1")
        vm.sessions.value = [session1]

        await vm.switch_session_cmd.execute("nonexistent")

        assert vm.error_message.value is not None
        assert "not found" in vm.error_message.value

    @pytest.mark.asyncio
    async def test_delete_session(self, vm: SessionViewModel, coordinator: AsyncMock) -> None:
        """Проверить удаление сессии."""
        session1 = MagicMock(id="s1")
        session2 = MagicMock(id="s2")
        vm.sessions.value = [session1, session2]
        vm.selected_session_id.value = "s2"

        await vm.delete_session_cmd.execute("s1")

        assert len(vm.sessions.value) == 1
        assert vm.sessions.value[0] == session2
        coordinator.delete_session.assert_called_once_with("s1")

    @pytest.mark.asyncio
    async def test_delete_selected_session(
        self, vm: SessionViewModel, coordinator: AsyncMock
    ) -> None:
        """Проверить удаление выбранной сессии."""
        session1 = MagicMock(id="s1")
        session2 = MagicMock(id="s2")
        vm.sessions.value = [session1, session2]
        vm.selected_session_id.value = "s1"

        await vm.delete_session_cmd.execute("s1")

        # Должна быть выбрана первая оставшаяся сессия
        assert vm.selected_session_id.value == "s2"

    @pytest.mark.asyncio
    async def test_delete_last_session(self, vm: SessionViewModel, coordinator: AsyncMock) -> None:
        """Проверить удаление последней сессии."""
        session1 = MagicMock(id="s1")
        vm.sessions.value = [session1]
        vm.selected_session_id.value = "s1"

        await vm.delete_session_cmd.execute("s1")

        assert vm.sessions.value == []
        assert vm.selected_session_id.value is None

    def test_handle_session_closed_event(self, vm: SessionViewModel) -> None:
        """Проверить обработку события SessionClosedEvent."""
        session1 = MagicMock(id="s1")
        session2 = MagicMock(id="s2")
        vm.sessions.value = [session1, session2]

        # Имитируем событие
        event = MagicMock(session_id="s1")
        vm._handle_session_closed(event)

        # Сессия должна быть удалена из списка
        assert len(vm.sessions.value) == 1
        assert vm.sessions.value[0] == session2

    def test_loading_observable_subscription(self, vm: SessionViewModel) -> None:
        """Проверить подписку на флаг загрузки."""
        loading_states = []
        vm.is_loading_sessions.subscribe(lambda x: loading_states.append(x))

        vm.is_loading_sessions.value = True
        vm.is_loading_sessions.value = False

        assert loading_states == [True, False]

    def test_error_message_observable_subscription(self, vm: SessionViewModel) -> None:
        """Проверить подписку на сообщение об ошибке."""
        error_messages = []
        vm.error_message.subscribe(lambda x: error_messages.append(x))

        vm.error_message.value = "Error 1"
        vm.error_message.value = "Error 2"

        assert error_messages == ["Error 1", "Error 2"]

    @pytest.mark.asyncio
    async def test_create_session_with_kwargs(
        self, vm: SessionViewModel, coordinator: AsyncMock
    ) -> None:
        """Проверить создание сессии с дополнительными параметрами."""
        new_session = MagicMock(id="new")
        coordinator.create_session.return_value = new_session

        await vm.create_session_cmd.execute("localhost", 8080, custom="value")

        # Проверяем что create_session вызван с нужными параметрами
        # Параметр cwd добавляется автоматически из текущей директории
        call_args = coordinator.create_session.call_args
        assert call_args[0] == ("localhost", 8080)  # positional args
        assert "cwd" in call_args[1]  # cwd должен быть в kwargs
        assert call_args[1].get("custom") == "value"  # custom параметр должен быть передан

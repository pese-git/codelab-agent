"""Тесты для Observable Pattern."""

import asyncio

import pytest

from codelab.client.presentation.observable import Observable, ObservableCommand


class TestObservable:
    """Тесты для Observable класса."""

    def test_observable_initialization(self) -> None:
        """Проверить инициализацию Observable."""
        obs = Observable(42)
        assert obs.value == 42

    def test_observable_value_change(self) -> None:
        """Проверить изменение значения."""
        obs = Observable(1)
        obs.value = 2
        assert obs.value == 2

    def test_observable_notify_on_change(self) -> None:
        """Проверить что observers уведомляются об изменении."""
        obs = Observable(1)
        changes = []
        
        obs.subscribe(lambda x: changes.append(x))
        
        obs.value = 2
        obs.value = 3
        
        assert changes == [2, 3]

    def test_observable_no_notify_on_same_value(self) -> None:
        """Проверить что observers не уведомляются если значение не изменилось."""
        obs = Observable(1)
        changes = []
        
        obs.subscribe(lambda x: changes.append(x))
        
        obs.value = 1  # Не изменилось
        obs.value = 1  # Не изменилось
        obs.value = 2  # Изменилось
        
        assert changes == [2]

    def test_observable_multiple_observers(self) -> None:
        """Проверить работу с множеством observers."""
        obs = Observable(0)
        results1 = []
        results2 = []
        
        obs.subscribe(lambda x: results1.append(x))
        obs.subscribe(lambda x: results2.append(x))
        
        obs.value = 1
        obs.value = 2
        
        assert results1 == [1, 2]
        assert results2 == [1, 2]

    def test_observable_unsubscribe(self) -> None:
        """Проверить отписку от Observable."""
        obs = Observable(0)
        changes = []
        
        unsubscribe = obs.subscribe(lambda x: changes.append(x))
        
        obs.value = 1
        unsubscribe()  # Отписаться
        obs.value = 2
        
        assert changes == [1]  # 2 не должно быть в списке

    def test_observable_string_value(self) -> None:
        """Проверить Observable с строковыми значениями."""
        obs = Observable("hello")
        changes = []
        
        obs.subscribe(lambda x: changes.append(x))
        
        obs.value = "world"
        
        assert changes == ["world"]

    def test_observable_list_value(self) -> None:
        """Проверить Observable со списками (сравнение по значению)."""
        list1 = [1, 2, 3]
        obs = Observable(list1)
        changes = []
        
        obs.subscribe(lambda x: changes.append(x))
        
        # Списки сравниваются по содержимому, так что это не изменит значение
        list2 = [1, 2, 3]  # Равно list1
        obs.value = list2
        
        assert len(changes) == 0  # Не должно быть уведомления
        
        # Но разное содержимое вызовет изменение
        list3 = [1, 2, 4]
        obs.value = list3
        
        assert len(changes) == 1
        assert changes[0] == list3

    def test_observable_repr(self) -> None:
        """Проверить строковое представление Observable."""
        obs = Observable(42)
        repr_str = repr(obs)
        assert "Observable" in repr_str
        assert "42" in repr_str


class TestObservableCommand:
    """Тесты для ObservableCommand класса."""

    @pytest.mark.asyncio
    async def test_command_execute_success(self) -> None:
        """Проверить успешное выполнение команды."""
        async def dummy_handler():
            return "result"
        
        cmd = ObservableCommand(dummy_handler)
        result = await cmd.execute()
        
        assert result == "result"
        assert cmd.is_executing.value is False
        assert cmd.error.value is None

    @pytest.mark.asyncio
    async def test_command_execute_with_args(self) -> None:
        """Проверить выполнение команды с аргументами."""
        async def add(a: int, b: int) -> int:
            return a + b
        
        cmd = ObservableCommand(add)
        result = await cmd.execute(2, 3)
        
        assert result == 5

    @pytest.mark.asyncio
    async def test_command_execute_with_kwargs(self) -> None:
        """Проверить выполнение команды с именованными аргументами."""
        async def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"
        
        cmd = ObservableCommand(greet)
        result = await cmd.execute(name="World", greeting="Hi")
        
        assert result == "Hi, World!"

    @pytest.mark.asyncio
    async def test_command_executing_flag(self) -> None:
        """Проверить флаг is_executing во время выполнения."""
        executing_flags = []
        
        async def slow_handler() -> None:
            await asyncio.sleep(0.01)
        
        cmd = ObservableCommand(slow_handler)
        
        # Подписаться на флаг
        cmd.is_executing.subscribe(lambda x: executing_flags.append(x))
        
        # Выполнить команду
        await cmd.execute()
        
        # Должны быть: True (начало), False (конец)
        assert True in executing_flags
        assert False in executing_flags

    @pytest.mark.asyncio
    async def test_command_execute_error(self) -> None:
        """Проверить обработку ошибки при выполнении."""
        async def failing_handler() -> None:
            raise ValueError("Test error")
        
        cmd = ObservableCommand(failing_handler)
        
        with pytest.raises(ValueError):
            await cmd.execute()
        
        assert cmd.is_executing.value is False
        assert cmd.error.value is not None
        assert "Test error" in cmd.error.value

    @pytest.mark.asyncio
    async def test_command_sync_handler(self) -> None:
        """Проверить работу с синхронным обработчиком."""
        def sync_handler():
            return "sync result"
        
        cmd = ObservableCommand(sync_handler)
        result = await cmd.execute()
        
        assert result == "sync result"

    @pytest.mark.asyncio
    async def test_command_last_result(self) -> None:
        """Проверить сохранение последнего результата."""
        async def get_value():
            return 42
        
        cmd = ObservableCommand(get_value)
        await cmd.execute()
        
        assert cmd.last_result == 42

    @pytest.mark.asyncio
    async def test_command_error_clears_on_retry(self) -> None:
        """Проверить что ошибка очищается при повторном выполнении."""
        async def maybe_fail(should_fail: bool):
            if should_fail:
                raise RuntimeError("Failed!")
            return "success"
        
        cmd = ObservableCommand(maybe_fail)
        
        # Первое выполнение с ошибкой
        with pytest.raises(RuntimeError):
            await cmd.execute(True)
        
        assert cmd.error.value is not None
        
        # Повторное выполнение без ошибки
        result = await cmd.execute(False)
        
        assert result == "success"
        assert cmd.error.value is None

    def test_command_repr(self) -> None:
        """Проверить строковое представление ObservableCommand."""
        async def dummy():
            pass
        
        cmd = ObservableCommand(dummy)
        repr_str = repr(cmd)
        assert "ObservableCommand" in repr_str
        assert "executing" in repr_str


class TestObservableIntegration:
    """Интеграционные тесты для Observable."""

    def test_observable_chain_updates(self) -> None:
        """Проверить цепочку обновлений нескольких observables."""
        obs1 = Observable(1)
        obs2 = Observable(0)
        
        def update_obs2(value):
            obs2.value = value * 10
        
        obs1.subscribe(update_obs2)
        
        obs1.value = 2
        assert obs2.value == 20
        
        obs1.value = 3
        assert obs2.value == 30

    @pytest.mark.asyncio
    async def test_command_with_observable_update(self) -> None:
        """Проверить обновление observable из команды."""
        obs = Observable("initial")
        
        async def update_value():
            obs.value = "updated"
            return "done"
        
        cmd = ObservableCommand(update_value)
        result = await cmd.execute()
        
        assert result == "done"
        assert obs.value == "updated"

    def test_observable_with_exception_in_observer(self) -> None:
        """Проверить что исключение в observer не влияет на других."""
        obs = Observable(0)
        results = []
        
        def failing_observer(x):
            raise ValueError("Observer error")
        
        def good_observer(x):
            results.append(x)
        
        obs.subscribe(failing_observer)
        obs.subscribe(good_observer)
        
        # Не должно выбросить исключение, good_observer все еще вызывается
        obs.value = 1
        
        assert results == [1]

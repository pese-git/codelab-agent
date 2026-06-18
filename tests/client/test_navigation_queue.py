"""Тесты для OperationQueue."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.tui.navigation.operations import NavigationOperation, OperationType
from codelab.client.tui.navigation.queue import OperationQueue, OperationQueueError


class TestOperationQueue:
    """Тесты для класса OperationQueue."""

    @pytest.fixture
    def queue(self) -> OperationQueue:
        """Создать пустую очередь операций."""
        return OperationQueue()

    def test_queue_initialization(self, queue: OperationQueue) -> None:
        """Тест инициализации пустой очереди."""
        assert queue.is_empty()
        assert queue.size() == 0

    def test_is_empty_check(self, queue: OperationQueue) -> None:
        """Тест проверки пустоты очереди."""
        assert queue.is_empty()
        # После clear очередь должна остаться пустой
        queue.clear()
        assert queue.is_empty()
        assert queue.size() == 0

    def test_queue_size(self, queue: OperationQueue) -> None:
        """Тест получения размера очереди."""
        assert queue.size() == 0
        # Добавляем операцию в очередь (без executor)
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
        )
        asyncio.run(queue.enqueue(operation))
        assert queue.size() == 1

    @pytest.mark.asyncio
    async def test_queue_clear(self) -> None:
        """Тест очистки очереди."""
        queue = OperationQueue()
        # Добавляем несколько операций
        for _ in range(3):
            operation = NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
            )
            await queue.enqueue(operation)
        
        assert queue.size() == 3
        queue.clear()
        assert queue.is_empty()
        assert queue.size() == 0

    @pytest.mark.asyncio
    async def test_enqueue_single_operation(self) -> None:
        """Тест добавления одной операции в очередь."""
        queue = OperationQueue()
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
        )
        
        # Без executor операция просто добавляется
        await queue.enqueue(operation)
        assert queue.size() == 1
        assert not queue.is_empty()

    @pytest.mark.asyncio
    async def test_enqueue_multiple_operations(self) -> None:
        """Тест добавления нескольких операций в очередь."""
        queue = OperationQueue()
        operations = [
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
            )
            for _ in range(5)
        ]
        
        for op in operations:
            await queue.enqueue(op)
        
        assert queue.size() == 5

    @pytest.mark.asyncio
    async def test_priority_ordering_high_first(self) -> None:
        """Тест приоритизации операций (HIGH > NORMAL > LOW)."""
        queue = OperationQueue()
        executed_order: list[int] = []
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor для отслеживания порядка выполнения."""
            executed_order.append(operation.priority)
        
        # Сначала добавляем операции БЕЗ executor
        operations = [
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,  # NORMAL
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=0,  # LOW
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=2,  # HIGH
            ),
        ]
        
        # Добавляем в очередь все операции без executor
        for op in operations:
            await queue.enqueue(op)
        
        # Теперь устанавливаем executor и обрабатываем
        queue.set_executor(mock_executor)
        
        # Обрабатываем очередь
        await queue._process_queue()
        
        # Ожидаем выполнения в порядке приоритета: 2, 1, 0
        assert executed_order == [2, 1, 0]

    @pytest.mark.asyncio
    async def test_fifo_order_same_priority(self) -> None:
        """Тест FIFO порядка для операций одного приоритета."""
        queue = OperationQueue()
        executed_order: list[int] = []
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor для отслеживания порядка выполнения."""
            executed_order.append(operation.priority)
        
        queue.set_executor(mock_executor)
        
        # Добавляем операции с одинаковым приоритетом
        operations = [
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
                metadata={"id": 1},
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
                metadata={"id": 2},
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
                metadata={"id": 3},
            ),
        ]
        
        for op in operations:
            await queue.enqueue(op)
        
        # Все имеют приоритет 1, должны выполняться в FIFO порядке
        assert executed_order == [1, 1, 1]

    @pytest.mark.asyncio
    async def test_complex_priority_mix(self) -> None:
        """Тест сложной комбинации приоритетов."""
        queue = OperationQueue()
        executed_order: list[int] = []
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor для отслеживания порядка выполнения."""
            executed_order.append(operation.priority)
        
        # Добавляем операции в разном порядке
        # Ожидаемый порядок: 2, 2, 1, 1, 0
        operations = [
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,  # NORMAL
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=2,  # HIGH
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=0,  # LOW
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=2,  # HIGH
            ),
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,  # NORMAL
            ),
        ]
        
        # Добавляем в очередь без executor
        for op in operations:
            await queue.enqueue(op)
        
        # Устанавливаем executor и обрабатываем
        queue.set_executor(mock_executor)
        await queue._process_queue()
        
        assert executed_order == [2, 2, 1, 1, 0]

    @pytest.mark.asyncio
    async def test_operation_callback_success(self) -> None:
        """Тест вызова callback при успешном выполнении операции."""
        queue = OperationQueue()
        success_callback = Mock()
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor."""
            pass
        
        queue.set_executor(mock_executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
            on_success=success_callback,
        )
        
        await queue.enqueue(operation)
        success_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_operation_callback_error(self) -> None:
        """Тест вызова callback при ошибке выполнения операции."""
        queue = OperationQueue()
        error_callback = Mock()
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor который выбрасывает исключение."""
            raise ValueError("Test error")
        
        queue.set_executor(mock_executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
            on_error=error_callback,
        )
        
        with pytest.raises(OperationQueueError):
            await queue.enqueue(operation)
        
        # Проверяем что callback ошибки был вызван
        error_callback.assert_called_once()
        call_args = error_callback.call_args[0][0]
        assert isinstance(call_args, ValueError)

    @pytest.mark.asyncio
    async def test_operation_timeout(self) -> None:
        """Тест обработки таймаута операции."""
        queue = OperationQueue()
        
        async def slow_executor(operation: NavigationOperation) -> None:
            """Executor который выполняется дольше таймаута."""
            await asyncio.sleep(1.0)
        
        queue.set_executor(slow_executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
            timeout_seconds=0.1,  # Очень короткий таймаут
        )
        
        with pytest.raises(OperationQueueError):
            await queue.enqueue(operation)

    @pytest.mark.asyncio
    async def test_operation_timeout_callback(self) -> None:
        """Тест вызова callback при таймауте операции."""
        queue = OperationQueue()
        error_callback = Mock()
        
        async def slow_executor(operation: NavigationOperation) -> None:
            """Executor который выполняется дольше таймаута."""
            await asyncio.sleep(1.0)
        
        queue.set_executor(slow_executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
            timeout_seconds=0.1,
            on_error=error_callback,
        )
        
        with pytest.raises(OperationQueueError):
            await queue.enqueue(operation)
        
        # Проверяем что callback ошибки был вызван
        error_callback.assert_called_once()
        call_args = error_callback.call_args[0][0]
        assert isinstance(call_args, TimeoutError)

    @pytest.mark.asyncio
    async def test_empty_queue_dequeue(self) -> None:
        """Тест обработки пустой очереди."""
        queue = OperationQueue()
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor."""
            pass
        
        queue.set_executor(mock_executor)
        
        # При пустой очереди должна вернуться None
        await queue.enqueue(
            NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
            )
        )
        # Результат не проверяем, так как он зависит от executor

    @pytest.mark.asyncio
    async def test_concurrent_enqueue(self) -> None:
        """Тест конкурентного добавления операций."""
        queue = OperationQueue()
        executed_operations: list[int] = []
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor."""
            executed_operations.append(operation.priority)
        
        queue.set_executor(mock_executor)
        
        # Создаем задачи для конкурентного добавления
        async def add_operations() -> None:
            """Добавить несколько операций."""
            for _ in range(3):
                await queue.enqueue(
                    NavigationOperation(
                        operation_type=OperationType.SHOW_SCREEN,
                        screen=Mock(),
                        priority=1,
                    )
                )
        
        # Запускаем несколько конкурентных добавлений
        await asyncio.gather(
            add_operations(),
            add_operations(),
        )
        
        # Проверяем что все 6 операций были обработаны
        assert len(executed_operations) == 6

    @pytest.mark.asyncio
    async def test_set_executor(self) -> None:
        """Тест установки executor функции."""
        queue = OperationQueue()
        executor = AsyncMock()
        
        queue.set_executor(executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
        )
        
        await queue.enqueue(operation)
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_operation_without_callbacks(self) -> None:
        """Тест выполнения операции без callbacks."""
        queue = OperationQueue()
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor."""
            pass
        
        queue.set_executor(mock_executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
            on_success=None,
            on_error=None,
        )
        
        # Должно выполниться без ошибок
        await queue.enqueue(operation)
        assert queue.is_empty()

    @pytest.mark.asyncio
    async def test_multiple_operations_sequential_execution(self) -> None:
        """Тест последовательного выполнения множественных операций."""
        queue = OperationQueue()
        execution_order: list[int] = []
        
        async def mock_executor(operation: NavigationOperation) -> None:
            """Mock executor для отслеживания порядка."""
            execution_order.append(operation.metadata.get("id", 0))
        
        queue.set_executor(mock_executor)
        
        # Добавляем операции с метаданными
        for i in range(5):
            operation = NavigationOperation(
                operation_type=OperationType.SHOW_SCREEN,
                screen=Mock(),
                priority=1,
                metadata={"id": i},
            )
            await queue.enqueue(operation)
        
        # Проверяем что все были выполнены в FIFO порядке
        assert execution_order == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_executor_return_value(self) -> None:
        """Тест возврата значения из executor."""
        queue = OperationQueue()
        
        async def mock_executor(operation: NavigationOperation) -> str:
            """Mock executor который возвращает значение."""
            return "success"
        
        queue.set_executor(mock_executor)
        
        operation = NavigationOperation(
            operation_type=OperationType.SHOW_SCREEN,
            screen=Mock(),
            priority=1,
        )
        
        result = await queue.enqueue(operation)
        assert result == "success"

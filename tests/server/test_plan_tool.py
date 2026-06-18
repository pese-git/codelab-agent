"""Тесты для update_plan инструмента и PlanToolExecutor."""

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.definitions.plan import PlanToolDefinitions
from codelab.server.tools.executors.plan_executor import PlanToolExecutor


class TestPlanToolDefinitions:
    """Тесты для PlanToolDefinitions."""

    def test_update_plan_definition(self) -> None:
        """Проверить определение update_plan инструмента."""
        definition = PlanToolDefinitions.update_plan()
        
        assert definition.name == "update_plan"
        assert definition.kind == "think"
        assert definition.requires_permission is False
        
        # Проверить параметры
        params = definition.parameters
        assert params["type"] == "object"
        assert "entries" in params["properties"]
        assert params["required"] == ["entries"]

    def test_update_plan_entries_schema(self) -> None:
        """Проверить схему entries."""
        definition = PlanToolDefinitions.update_plan()
        entries_schema = definition.parameters["properties"]["entries"]
        
        assert entries_schema["type"] == "array"
        
        item_schema = entries_schema["items"]
        assert "content" in item_schema["properties"]
        assert "priority" in item_schema["properties"]
        assert "status" in item_schema["properties"]
        
        # Проверить enum для priority
        priority_enum = item_schema["properties"]["priority"]["enum"]
        assert set(priority_enum) == {"low", "medium", "high"}
        
        # Проверить enum для status
        status_enum = item_schema["properties"]["status"]["enum"]
        assert set(status_enum) == {"pending", "in_progress", "completed"}


class TestPlanToolExecutor:
    """Тесты для PlanToolExecutor."""

    @pytest.fixture
    def executor(self) -> PlanToolExecutor:
        """Создать executor."""
        return PlanToolExecutor()

    @pytest.fixture
    def session(self) -> SessionState:
        """Создать mock сессию."""
        return SessionState(
            session_id="test-session",
            cwd="/tmp",
            mcp_servers=[],
        )

    @pytest.mark.asyncio
    async def test_execute_success(
        self, executor: PlanToolExecutor, session: SessionState
    ) -> None:
        """Успешное выполнение с валидными entries."""
        arguments = {
            "entries": [
                {"content": "Task 1", "priority": "high", "status": "pending"},
                {"content": "Task 2", "priority": "medium", "status": "in_progress"},
            ]
        }
        
        result = await executor.execute(session, arguments)
        
        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["entries_count"] == 2
        assert "Plan updated with 2 entries" in (result.output or "")

    @pytest.mark.asyncio
    async def test_execute_empty_entries(
        self, executor: PlanToolExecutor, session: SessionState
    ) -> None:
        """Пустой список entries возвращает ошибку."""
        arguments = {"entries": []}
        
        result = await executor.execute(session, arguments)
        
        assert result.success is False
        assert "No valid plan entries provided" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_invalid_entries_type(
        self, executor: PlanToolExecutor, session: SessionState
    ) -> None:
        """Невалидный тип entries возвращает ошибку."""
        arguments = {"entries": "not a list"}
        
        result = await executor.execute(session, arguments)
        
        assert result.success is False
        assert "entries must be a list" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_normalization(
        self, executor: PlanToolExecutor, session: SessionState
    ) -> None:
        """Проверить нормализацию entries."""
        arguments = {
            "entries": [
                {"content": "  Task  ", "priority": "invalid", "status": "unknown"},
            ]
        }
        
        result = await executor.execute(session, arguments)
        
        assert result.success is True
        assert result.metadata is not None
        validated = result.metadata["validated_entries"]
        
        # Пробелы убраны, невалидные значения заменены
        assert validated[0]["content"] == "Task"
        assert validated[0]["priority"] == "medium"
        assert validated[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_execute_skip_invalid_entries(
        self, executor: PlanToolExecutor, session: SessionState
    ) -> None:
        """Пропустить entries без content."""
        arguments = {
            "entries": [
                {"priority": "high", "status": "pending"},  # Нет content
                {"content": "Valid", "priority": "low", "status": "completed"},
            ]
        }
        
        result = await executor.execute(session, arguments)
        
        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["entries_count"] == 1
        assert result.metadata["validated_entries"][0]["content"] == "Valid"

    @pytest.mark.asyncio
    async def test_execute_title_alias(
        self, executor: PlanToolExecutor, session: SessionState
    ) -> None:
        """Поле title как альтернатива content."""
        arguments = {
            "entries": [
                {"title": "Title Task", "priority": "high", "status": "pending"},
            ]
        }
        
        result = await executor.execute(session, arguments)
        
        assert result.success is True
        assert result.metadata is not None
        validated = result.metadata["validated_entries"]
        assert validated[0]["content"] == "Title Task"

"""Unit-тесты для SimpleToolRegistry."""

import pytest

from codelab.server.tools import SimpleToolRegistry, ToolDefinition


def simple_add(a: int, b: int) -> int:
    """Простой обработчик: сложение двух чисел."""
    return a + b


def simple_multiply(x: int, y: int) -> int:
    """Простой обработчик: умножение двух чисел."""
    return x * y


def handler_with_error() -> None:
    """Обработчик, вызывающий исключение."""
    raise RuntimeError("Тестовая ошибка")


def handler_returns_none() -> None:
    """Обработчик, возвращающий None."""
    return None


class TestSimpleToolRegistryRegistration:
    """Тесты регистрации инструментов."""

    def test_register_single_tool(self) -> None:
        """Тест регистрации одного инструмента."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="add",
            description="Сложение двух чисел",
            parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
            kind="math",
        )

        registry.register(tool, simple_add)

        # Проверка, что инструмент зарегистрирован
        retrieved = registry.get("add")
        assert retrieved is not None
        assert retrieved.name == "add"

    def test_register_multiple_tools(self) -> None:
        """Тест регистрации нескольких инструментов."""
        registry = SimpleToolRegistry()

        add_tool = ToolDefinition(
            name="add",
            description="Сложение",
            parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
            kind="math",
        )
        mul_tool = ToolDefinition(
            name="multiply",
            description="Умножение",
            parameters={"x": {"type": "integer"}, "y": {"type": "integer"}},
            kind="math",
        )

        registry.register(add_tool, simple_add)
        registry.register(mul_tool, simple_multiply)

        assert registry.get("add") is not None
        assert registry.get("multiply") is not None

    def test_register_tool_with_empty_name_raises_error(self) -> None:
        """Тест регистрации инструмента с пустым именем вызывает ошибку."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="",
            description="Инструмент с пустым именем",
            parameters={},
            kind="other",
        )

        with pytest.raises(ValueError, match="Имя инструмента не может быть пустым"):
            registry.register(tool, simple_add)

    def test_register_tool_with_whitespace_name_raises_error(self) -> None:
        """Тест регистрации инструмента с именем из пробелов вызывает ошибку."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="   ",
            description="Инструмент с пробельным именем",
            parameters={},
            kind="other",
        )

        with pytest.raises(ValueError, match="Имя инструмента не может быть пустым"):
            registry.register(tool, simple_add)

    def test_register_overwrites_existing_tool(self) -> None:
        """Тест перезаписи существующего инструмента."""
        registry = SimpleToolRegistry()

        tool1 = ToolDefinition(
            name="test",
            description="Первая версия",
            parameters={},
            kind="other",
        )
        tool2 = ToolDefinition(
            name="test",
            description="Вторая версия",
            parameters={"param": {"type": "string"}},
            kind="other",
        )

        registry.register(tool1, simple_add)
        registry.register(tool2, simple_multiply)

        # Должна быть вторая версия
        retrieved = registry.get("test")
        assert retrieved is not None
        assert retrieved.description == "Вторая версия"
        assert "param" in retrieved.parameters


class TestSimpleToolRegistryRetrieval:
    """Тесты получения инструментов."""

    def test_get_existing_tool(self) -> None:
        """Тест получения существующего инструмента."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="Тестовый инструмент",
            parameters={},
            kind="test",
        )
        registry.register(tool, simple_add)

        retrieved = registry.get("test_tool")
        assert retrieved is not None
        assert retrieved.name == "test_tool"
        assert retrieved.description == "Тестовый инструмент"

    def test_get_nonexistent_tool_returns_none(self) -> None:
        """Тест получения несуществующего инструмента возвращает None."""
        registry = SimpleToolRegistry()

        retrieved = registry.get("nonexistent")
        assert retrieved is None

    def test_get_tool_after_registration(self) -> None:
        """Тест получения инструмента сразу после регистрации."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="immediate",
            description="Тест получения",
            parameters={"x": {"type": "string"}},
            kind="test",
        )

        registry.register(tool, simple_add)
        retrieved = registry.get("immediate")

        assert retrieved is not None
        assert retrieved.name == "immediate"
        assert retrieved.parameters == {"x": {"type": "string"}}


class TestSimpleToolRegistryListing:
    """Тесты получения списка инструментов."""

    def test_list_tools_empty_registry(self) -> None:
        """Тест получения списка инструментов из пустого реестра."""
        registry = SimpleToolRegistry()

        tools = registry.list_tools()

        assert tools == []
        assert len(tools) == 0

    def test_list_tools_single_tool(self) -> None:
        """Тест получения списка с одним инструментом."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="single",
            description="Один инструмент",
            parameters={},
            kind="test",
        )
        registry.register(tool, simple_add)

        tools = registry.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "single"

    def test_list_tools_multiple_tools(self) -> None:
        """Тест получения списка нескольких инструментов."""
        registry = SimpleToolRegistry()

        tools_to_register = [
            ToolDefinition(
                name="tool1",
                description="Первый инструмент",
                parameters={},
                kind="test",
            ),
            ToolDefinition(
                name="tool2",
                description="Второй инструмент",
                parameters={},
                kind="test",
            ),
            ToolDefinition(
                name="tool3",
                description="Третий инструмент",
                parameters={},
                kind="test",
            ),
        ]

        for tool in tools_to_register:
            registry.register(tool, simple_add)

        tools = registry.list_tools()

        assert len(tools) == 3
        names = {tool.name for tool in tools}
        assert names == {"tool1", "tool2", "tool3"}


class TestSimpleToolRegistryExecution:
    """Тесты выполнения инструментов."""

    def test_execute_existing_tool_success(self) -> None:
        """Тест успешного выполнения существующего инструмента."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="add",
            description="Сложение",
            parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
            kind="math",
        )
        registry.register(tool, simple_add)

        result = registry.execute("add", {"a": 2, "b": 3})

        assert result.success is True
        assert result.output == "5"
        assert result.error is None

    def test_execute_nonexistent_tool_fails(self) -> None:
        """Тест выполнения несуществующего инструмента возвращает ошибку."""
        registry = SimpleToolRegistry()

        result = registry.execute("nonexistent", {})

        assert result.success is False
        assert result.error is not None
        assert "не найден" in result.error
        assert result.output is None

    def test_execute_tool_with_exception(self) -> None:
        """Тест выполнения инструмента, вызывающего исключение."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="error_tool",
            description="Инструмент с ошибкой",
            parameters={},
            kind="test",
        )
        registry.register(tool, handler_with_error)

        result = registry.execute("error_tool", {})

        assert result.success is False
        assert result.error is not None
        assert "Ошибка при выполнении" in result.error
        assert "Тестовая ошибка" in result.error

    def test_execute_tool_returns_none(self) -> None:
        """Тест выполнения инструмента, возвращающего None."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="none_tool",
            description="Инструмент, возвращающий None",
            parameters={},
            kind="test",
        )
        registry.register(tool, handler_returns_none)

        result = registry.execute("none_tool", {})

        assert result.success is True
        assert result.output is None
        assert result.error is None

    def test_execute_tool_with_multiple_arguments(self) -> None:
        """Тест выполнения инструмента с несколькими аргументами."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="multiply",
            description="Умножение",
            parameters={"x": {"type": "integer"}, "y": {"type": "integer"}},
            kind="math",
        )
        registry.register(tool, simple_multiply)

        result = registry.execute("multiply", {"x": 4, "y": 5})

        assert result.success is True
        assert result.output == "20"

    def test_execute_tool_with_wrong_arguments(self) -> None:
        """Тест выполнения инструмента с неправильными аргументами."""
        registry = SimpleToolRegistry()
        tool = ToolDefinition(
            name="add",
            description="Сложение",
            parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
            kind="math",
        )
        registry.register(tool, simple_add)

        # Передача неправильных типов или отсутствие аргументов
        result = registry.execute("add", {"a": "not_a_number", "b": 3})

        # Должна быть ошибка при выполнении
        assert result.success is False
        assert result.error is not None


class TestSimpleToolRegistryIntegration:
    """Интеграционные тесты."""

    def test_full_workflow(self) -> None:
        """Тест полного цикла: регистрация, получение, выполнение."""
        registry = SimpleToolRegistry()

        # Регистрация
        tool = ToolDefinition(
            name="workflow_tool",
            description="Инструмент для тестирования workflow",
            parameters={"a": {"type": "integer"}, "b": {"type": "integer"}},
            kind="math",
        )
        registry.register(tool, simple_add)

        # Получение
        retrieved = registry.get("workflow_tool")
        assert retrieved is not None
        assert retrieved.name == "workflow_tool"

        # Выполнение
        result = registry.execute("workflow_tool", {"a": 10, "b": 20})
        assert result.success is True
        assert result.output == "30"

    def test_multiple_tools_independent(self) -> None:
        """Тест независимости нескольких инструментов."""
        registry = SimpleToolRegistry()

        add_tool = ToolDefinition(
            name="add",
            description="Сложение",
            parameters={},
            kind="math",
        )
        mul_tool = ToolDefinition(
            name="mul",
            description="Умножение",
            parameters={},
            kind="math",
        )

        registry.register(add_tool, simple_add)
        registry.register(mul_tool, simple_multiply)

        # Проверка независимости
        add_result = registry.execute("add", {"a": 2, "b": 3})
        mul_result = registry.execute("mul", {"x": 2, "y": 3})

        assert add_result.success is True
        assert add_result.output == "5"
        assert mul_result.success is True
        assert mul_result.output == "6"

    def test_registry_isolation(self) -> None:
        """Тест изоляции отдельных реестров."""
        registry1 = SimpleToolRegistry()
        registry2 = SimpleToolRegistry()

        tool = ToolDefinition(
            name="test",
            description="Тестовый инструмент",
            parameters={},
            kind="test",
        )

        registry1.register(tool, simple_add)

        # Второй реестр не должен содержать инструмент
        assert registry1.get("test") is not None
        assert registry2.get("test") is None

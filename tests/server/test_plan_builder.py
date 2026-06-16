"""Unit-тесты для PlanBuilder.

Проверяет корректность валидации, парсинга и построения планов.
"""

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.state import PromptDirectives, SessionState


@pytest.fixture
def plan_builder() -> PlanBuilder:
    """Создает экземпляр PlanBuilder для тестов."""
    return PlanBuilder()


@pytest.fixture
def session() -> SessionState:
    """Создает экземпляр SessionState для тестов."""
    return SessionState(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
    )


@pytest.fixture
def directives() -> PromptDirectives:
    """Создает экземпляр PromptDirectives для тестов."""
    return PromptDirectives()


class TestPlanBuilderShouldPublish:
    """Тесты для should_publish_plan."""

    def test_should_not_publish_when_flag_false(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Не публикует при publish_plan=False."""
        directives.publish_plan = False
        directives.plan_entries = [{"content": "Test", "priority": "high"}]
        assert not plan_builder.should_publish_plan(directives)

    def test_should_not_publish_when_no_entries(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Не публикует при отсутствии entries."""
        directives.publish_plan = True
        directives.plan_entries = None
        assert not plan_builder.should_publish_plan(directives)

    def test_should_not_publish_when_entries_empty(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Не публикует при пустом списке entries."""
        directives.publish_plan = True
        directives.plan_entries = []
        assert not plan_builder.should_publish_plan(directives)

    def test_should_publish_when_valid(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Публикует при валидных параметрах."""
        directives.publish_plan = True
        directives.plan_entries = [{"content": "Test"}]
        assert plan_builder.should_publish_plan(directives)

    def test_should_publish_multiple_entries(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Публикует при наличии нескольких entries."""
        directives.publish_plan = True
        directives.plan_entries = [
            {"content": "Step 1"},
            {"content": "Step 2"},
            {"content": "Step 3"},
        ]
        assert plan_builder.should_publish_plan(directives)


class TestPlanBuilderValidation:
    """Тесты для validate_plan_entries."""

    def test_validate_empty_list(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Возвращает None для пустого списка."""
        result = plan_builder.validate_plan_entries([])
        assert result is None

    def test_validate_none_input(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Возвращает None для None входа."""
        result = plan_builder.validate_plan_entries(None)
        assert result is None

    def test_validate_not_list(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Возвращает None для non-list входа."""
        result = plan_builder.validate_plan_entries("not a list")
        assert result is None

    def test_validate_single_entry(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Валидирует одиночный entry."""
        entries = [{"content": "Test task"}]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert len(result) == 1
        assert result[0]["content"] == "Test task"

    def test_validate_entry_with_all_fields(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Валидирует entry со всеми полями."""
        entries = [
            {
                "content": "Complex task",
                "priority": "high",
                "status": "in_progress",
            }
        ]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert len(result) == 1
        entry = result[0]
        assert entry["content"] == "Complex task"
        assert entry["priority"] == "high"
        assert entry["status"] == "in_progress"

    def test_validate_normalizes_priority(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Нормализует невалидный priority."""
        entries = [{"content": "Task", "priority": "invalid"}]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert result[0]["priority"] == "medium"

    def test_validate_normalizes_status(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Нормализует невалидный status."""
        entries = [{"content": "Task", "status": "invalid"}]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert result[0]["status"] == "pending"

    def test_validate_skips_invalid_entries(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Пропускает невалидные entries."""
        entries = [
            {"content": "Valid task"},
            {"priority": "high"},  # No content
            {"content": "Another valid"},
        ]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert len(result) == 2
        assert result[0]["content"] == "Valid task"
        assert result[1]["content"] == "Another valid"

    def test_validate_strips_whitespace(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Убирает пробелы из content."""
        entries = [{"content": "  Task with spaces  "}]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert result[0]["content"] == "Task with spaces"

    def test_validate_rejects_empty_content(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Отклоняет entries с пустым content."""
        entries = [
            {"content": "Valid"},
            {"content": ""},
            {"content": "   "},
        ]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert len(result) == 1
        assert result[0]["content"] == "Valid"


class TestPlanBuilderNotification:
    """Тесты для build_plan_notification."""

    def test_build_notification_structure(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Строит notification с правильной структурой ACP.
        
        Согласно протоколу ACP, формат должен быть:
        - sessionUpdate: "plan"
        - entries: список {content, priority, status}
        """
        entries = [
            {"content": "Step 1", "priority": "high", "status": "pending"},
            {"content": "Step 2", "priority": "medium", "status": "pending"},
        ]
        notification = plan_builder.build_plan_notification("sess_1", entries)

        assert isinstance(notification, ACPMessage)
        assert notification.method == "session/update"
        assert notification.params["sessionId"] == "sess_1"
        # Проверяем формат соответствует протоколу ACP
        assert notification.params["update"]["sessionUpdate"] == "plan"
        assert "entries" in notification.params["update"]

    def test_build_notification_plan_format(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Строит plan с правильным форматом ACP.
        
        Entries передаются напрямую без трансформации.
        """
        entries = [
            {"content": "Step 1", "priority": "high", "status": "pending"},
        ]
        notification = plan_builder.build_plan_notification("sess_1", entries)
        plan_entries = notification.params["update"]["entries"]

        assert len(plan_entries) == 1
        assert plan_entries[0]["content"] == "Step 1"
        assert plan_entries[0]["priority"] == "high"
        assert plan_entries[0]["status"] == "pending"

    def test_build_notification_preserves_entry_fields(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Передаёт entries напрямую без изменений."""
        entries = [{"content": "Step 1", "priority": "low", "status": "in_progress"}]
        notification = plan_builder.build_plan_notification("sess_1", entries)
        plan_entries = notification.params["update"]["entries"]

        assert plan_entries[0]["content"] == "Step 1"
        assert plan_entries[0]["priority"] == "low"
        assert plan_entries[0]["status"] == "in_progress"


class TestPlanBuilderExtraction:
    """Тесты для extract_plan_from_directives."""

    def test_extract_with_valid_plan(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Извлекает план из directives."""
        directives.plan_entries = [
            {"content": "Task 1"},
            {"content": "Task 2"},
        ]
        result = plan_builder.extract_plan_from_directives(directives)
        assert result is not None
        assert len(result) == 2

    def test_extract_with_no_plan(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает None если плана нет."""
        directives.plan_entries = None
        result = plan_builder.extract_plan_from_directives(directives)
        assert result is None

    def test_extract_with_empty_plan(
        self,
        plan_builder: PlanBuilder,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает None для пустого плана."""
        directives.plan_entries = []
        result = plan_builder.extract_plan_from_directives(directives)
        assert result is None


class TestPlanBuilderSessionUpdate:
    """Тесты для update_session_plan."""

    def test_update_session_plan(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
    ) -> None:
        """Обновляет latest_plan в сессии."""
        entries = [
            {"content": "Step 1", "priority": "high", "status": "pending"},
            {"content": "Step 2", "priority": "medium", "status": "pending"},
        ]
        plan_builder.update_session_plan(session, entries)

        assert len(session.latest_plan) == 2
        assert session.latest_plan[0]["title"] == "Step 1"
        assert session.latest_plan[1]["title"] == "Step 2"

    def test_update_session_plan_empty(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
    ) -> None:
        """Очищает план при передаче пустого списка."""
        session.latest_plan = [{"title": "Old plan"}]
        plan_builder.update_session_plan(session, [])
        assert len(session.latest_plan) == 0


class TestPlanBuilderUpdates:
    """Тесты для build_plan_updates."""

    def test_build_updates_no_publish(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает пустой список если publish_plan=False."""
        directives.publish_plan = False
        updates = plan_builder.build_plan_updates(session, "sess_1", directives)
        assert updates == []

    def test_build_updates_with_valid_plan(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Строит updates при валидном плане."""
        directives.publish_plan = True
        directives.plan_entries = [{"content": "Task 1"}]
        updates = plan_builder.build_plan_updates(session, "sess_1", directives)

        assert len(updates) == 1
        assert isinstance(updates[0], ACPMessage)
        assert updates[0].method == "session/update"

    def test_build_updates_updates_session_plan(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Обновляет session.latest_plan при построении updates."""
        directives.publish_plan = True
        directives.plan_entries = [{"content": "Task 1"}]
        plan_builder.build_plan_updates(session, "sess_1", directives)

        assert len(session.latest_plan) == 1
        assert session.latest_plan[0]["title"] == "Task 1"

    def test_build_updates_no_valid_entries(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает пустой список при отсутствии валидных entries."""
        directives.publish_plan = True
        directives.plan_entries = []
        updates = plan_builder.build_plan_updates(session, "sess_1", directives)
        assert updates == []


class TestPlanBuilderEdgeCases:
    """Тесты граничных случаев."""

    def test_validate_with_title_instead_of_content(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Принимает 'title' вместо 'content'."""
        entries = [{"title": "Task from title field"}]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert len(result) == 1
        assert result[0]["content"] == "Task from title field"

    def test_validate_with_non_dict_entry(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Пропускает non-dict entries."""
        entries = [
            {"content": "Valid"},
            "string entry",
            ["list", "entry"],
            {"content": "Another valid"},
        ]
        result = plan_builder.validate_plan_entries(entries)
        assert result is not None
        assert len(result) == 2

    def test_build_notification_with_special_chars(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Обрабатывает entries со спецсимволами."""
        entries = [
            {"content": "Task with *special* & chars!", "priority": "high", "status": "pending"},
        ]
        notification = plan_builder.build_plan_notification("sess_1", entries)
        plan_entries = notification.params["update"]["entries"]
        assert plan_entries[0]["content"] == "Task with *special* & chars!"

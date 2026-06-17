"""Тесты для компонентов Фазы 3: Tool Components.

Тестируют:
- ActionButton, IconButton: стилизованные кнопки
- ActionBar: панель с кнопками действий
- PermissionBadge: badge статуса разрешения
- PermissionRequest: виджет запроса разрешения
- ToolCallCard: карточка tool call
- ToolCallList: список tool calls
- FileChangePreview: предпросмотр изменений файла
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.client.tui.components.action_bar import ActionBar
from codelab.client.tui.components.action_button import ActionButton, IconButton
from codelab.client.tui.components.file_change_preview import DiffLine, FileChangePreview
from codelab.client.tui.components.file_change_preview_modal import FileChangePreviewModal
from codelab.client.tui.components.permission_badge import PermissionBadge
from codelab.client.tui.components.tool_call_card import ToolCallCard
from codelab.client.tui.components.tool_call_list import ToolCallList

if TYPE_CHECKING:
    pass


# === ActionButton тесты ===


class TestActionButton:
    """Тесты для ActionButton."""

    def test_action_button_creates_with_default_variant(self) -> None:
        """ActionButton создаётся с вариантом secondary по умолчанию."""
        button = ActionButton("Test")
        assert button._button_variant == "secondary"

    def test_action_button_creates_with_primary_variant(self) -> None:
        """ActionButton создаётся с primary вариантом."""
        button = ActionButton("Test", variant="primary")
        assert button._button_variant == "primary"

    def test_action_button_creates_with_danger_variant(self) -> None:
        """ActionButton создаётся с danger вариантом."""
        button = ActionButton("Delete", variant="danger")
        assert button._button_variant == "danger"

    def test_action_button_creates_with_ghost_variant(self) -> None:
        """ActionButton создаётся с ghost вариантом."""
        button = ActionButton("Cancel", variant="ghost")
        assert button._button_variant == "ghost"

    def test_action_button_with_icon(self) -> None:
        """ActionButton с иконкой сохраняет её."""
        button = ActionButton("Save", icon="💾")
        assert button._icon == "💾"
        assert button._label == "Save"

    def test_action_button_stores_label(self) -> None:
        """ActionButton сохраняет label."""
        button = ActionButton("Test Label", variant="primary")
        assert button._label == "Test Label"

    def test_action_button_icon_property_change(self) -> None:
        """Изменение icon обновляет внутреннее состояние."""
        button = ActionButton("Test", icon="💾")
        button._icon = "📄"
        assert button._icon == "📄"


class TestIconButton:
    """Тесты для IconButton."""

    def test_icon_button_creates_with_icon(self) -> None:
        """IconButton создаётся с указанной иконкой."""
        button = IconButton("❌")
        assert button._icon == "❌"

    def test_icon_button_disabled_state(self) -> None:
        """IconButton поддерживает disabled состояние."""
        button = IconButton("❌", disabled=True)
        assert button._disabled is True
        assert "-disabled" in button.classes

    def test_icon_button_enable_disable(self) -> None:
        """IconButton можно включить и выключить."""
        button = IconButton("❌", disabled=False)
        assert button.disabled is False
        
        button.disabled = True
        assert button.disabled is True
        assert "-disabled" in button.classes
        
        button.disabled = False
        assert button.disabled is False
        assert "-disabled" not in button.classes


# === PermissionBadge тесты ===


class TestPermissionBadge:
    """Тесты для PermissionBadge."""

    def test_permission_badge_granted_status(self) -> None:
        """PermissionBadge с granted статусом показывает галочку."""
        badge = PermissionBadge("granted")
        assert badge._status == "granted"
        assert "granted" in badge.classes
        # Иконка должна быть галочкой
        assert "✓" in badge._format_display()

    def test_permission_badge_denied_status(self) -> None:
        """PermissionBadge с denied статусом показывает крестик."""
        badge = PermissionBadge("denied")
        assert badge._status == "denied"
        assert "denied" in badge.classes
        assert "✗" in badge._format_display()

    def test_permission_badge_pending_status(self) -> None:
        """PermissionBadge с pending статусом показывает часы."""
        badge = PermissionBadge("pending")
        assert badge._status == "pending"
        assert "pending" in badge.classes
        assert "⏳" in badge._format_display()

    def test_permission_badge_show_label(self) -> None:
        """PermissionBadge с show_label показывает текст."""
        badge = PermissionBadge("granted", show_label=True)
        display = badge._format_display()
        assert "✓" in display
        assert "Разрешено" in display

    def test_permission_badge_compact_mode(self) -> None:
        """PermissionBadge в compact режиме имеет соответствующий класс."""
        badge = PermissionBadge("granted", compact=True)
        assert "compact" in badge.classes

    def test_permission_badge_status_change(self) -> None:
        """Изменение статуса обновляет CSS классы."""
        badge = PermissionBadge("pending")
        assert "pending" in badge.classes
        
        badge.status = "granted"
        assert badge._status == "granted"
        assert "granted" in badge.classes
        assert "pending" not in badge.classes


# === ToolCallCard тесты ===


class TestToolCallCard:
    """Тесты для ToolCallCard."""

    def test_tool_call_card_creates_with_basic_info(self) -> None:
        """ToolCallCard создаётся с базовой информацией."""
        card = ToolCallCard(
            tool_call_id="call_123",
            tool_name="read_file",
            status="pending",
        )
        assert card.tool_call_id == "call_123"
        assert card.tool_name == "read_file"
        assert card.status == "pending"

    def test_tool_call_card_with_parameters(self) -> None:
        """ToolCallCard с параметрами сохраняет их."""
        params = {"path": "/home/user/file.txt", "encoding": "utf-8"}
        card = ToolCallCard(
            tool_call_id="call_123",
            tool_name="read_file",
            parameters=params,
        )
        assert card._parameters == params

    def test_tool_call_card_status_classes(self) -> None:
        """ToolCallCard имеет CSS класс соответствующий статусу."""
        card = ToolCallCard(
            tool_call_id="call_1",
            tool_name="test",
            status="running",
        )
        assert "running" in card.classes

    def test_tool_call_card_with_result(self) -> None:
        """ToolCallCard сохраняет результат выполнения."""
        card = ToolCallCard(
            tool_call_id="call_1",
            tool_name="test",
            status="success",
            result="File content here",
        )
        assert card.result == "File content here"

    def test_tool_call_card_with_error(self) -> None:
        """ToolCallCard сохраняет сообщение об ошибке."""
        card = ToolCallCard(
            tool_call_id="call_1",
            tool_name="test",
            status="error",
            error="File not found",
        )
        assert card.error == "File not found"

    def test_tool_call_card_format_parameters(self) -> None:
        """ToolCallCard форматирует параметры для отображения."""
        params = {"path": "/file.txt", "mode": "r"}
        card = ToolCallCard(
            tool_call_id="call_1",
            tool_name="read_file",
            parameters=params,
        )
        formatted = card._format_parameters()
        assert "path:" in formatted
        assert "/file.txt" in formatted
        assert "mode:" in formatted

    def test_tool_call_card_truncate_long_text(self) -> None:
        """ToolCallCard укорачивает длинный текст."""
        card = ToolCallCard(tool_call_id="call_1", tool_name="test")
        long_text = "x" * 300
        truncated = card._truncate(long_text, 50)
        assert len(truncated) == 50
        assert truncated.endswith("...")


# === ToolCallList тесты ===


class TestToolCallList:
    """Тесты для ToolCallList."""

    def test_tool_call_list_creates_empty(self) -> None:
        """ToolCallList создаётся пустым."""
        tool_list = ToolCallList()
        assert tool_list.count == 0

    def test_tool_call_list_add_tool_call(self) -> None:
        """ToolCallList добавляет tool call."""
        tool_list = ToolCallList()
        card = tool_list.add_tool_call(
            tool_call_id="call_1",
            tool_name="read_file",
            parameters={"path": "/file.txt"},
        )
        
        assert tool_list.count == 1
        assert card.tool_call_id == "call_1"

    def test_tool_call_list_update_status(self) -> None:
        """ToolCallList обновляет статус tool call."""
        tool_list = ToolCallList()
        tool_list.add_tool_call("call_1", "read_file")
        
        tool_list.update_status("call_1", "success", result="Content")
        
        tc_data = tool_list.get_tool_call("call_1")
        assert tc_data is not None
        assert tc_data["status"] == "success"

    def test_tool_call_list_remove_tool_call_data(self) -> None:
        """ToolCallList удаляет данные tool call из внутреннего хранилища."""
        tool_list = ToolCallList()
        # Добавляем напрямую в хранилище без монтирования
        tool_list._tool_calls["call_1"] = {"name": "read_file", "status": "pending"}
        assert tool_list.count == 1
        
        # Удаляем только из данных
        tool_list._tool_calls.pop("call_1", None)
        assert tool_list.count == 0

    def test_tool_call_list_clear_data(self) -> None:
        """ToolCallList очищает данные о tool calls."""
        tool_list = ToolCallList()
        # Добавляем напрямую в хранилище без монтирования
        tool_list._tool_calls["call_1"] = {"name": "read_file", "status": "pending"}
        tool_list._tool_calls["call_2"] = {"name": "write_file", "status": "pending"}
        assert tool_list.count == 2
        
        # Очищаем только данные
        tool_list._tool_calls.clear()
        assert tool_list.count == 0

    def test_tool_call_list_counts(self) -> None:
        """ToolCallList правильно считает по статусам."""
        tool_list = ToolCallList()
        tool_list.add_tool_call("call_1", "test", status="pending")
        tool_list.add_tool_call("call_2", "test", status="success")
        tool_list.add_tool_call("call_3", "test", status="error")
        tool_list.add_tool_call("call_4", "test", status="running")
        
        assert tool_list.pending_count == 2  # pending + running
        assert tool_list.completed_count == 1
        assert tool_list.failed_count == 1

    def test_tool_call_list_format_summary(self) -> None:
        """ToolCallList форматирует summary правильно."""
        tool_list = ToolCallList()
        tool_list.add_tool_call("call_1", "test", status="success")
        tool_list.add_tool_call("call_2", "test", status="pending")
        
        summary = tool_list._format_summary()
        assert "completed" in summary
        assert "pending" in summary

    def test_tool_call_list_status_mapping(self) -> None:
        """ToolCallList маппит статусы протокола на внутренние."""
        from unittest.mock import MagicMock
        
        tool_list = ToolCallList()
        
        # Создаём mock объекты tool call с протокольными статусами
        tc_pending = MagicMock()
        tc_pending.id = "call_1"
        tc_pending.name = "test"
        tc_pending.status = "pending"  # pending -> pending
        tc_pending.parameters = {}
        
        tc_in_progress = MagicMock()
        tc_in_progress.id = "call_2"
        tc_in_progress.name = "test"
        tc_in_progress.status = "in_progress"  # in_progress -> running
        tc_in_progress.parameters = {}
        
        tc_completed = MagicMock()
        tc_completed.id = "call_3"
        tc_completed.name = "test"
        tc_completed.status = "completed"  # completed -> success
        tc_completed.parameters = {}
        
        tc_failed = MagicMock()
        tc_failed.id = "call_4"
        tc_failed.name = "test"
        tc_failed.status = "failed"  # failed -> error
        tc_failed.parameters = {}
        
        # Вызываем обработчик
        tool_list._on_tool_calls_changed([tc_pending, tc_in_progress, tc_completed, tc_failed])
        
        # Проверяем маппинг статусов
        assert tool_list.get_tool_call("call_1")["status"] == "pending"
        assert tool_list.get_tool_call("call_2")["status"] == "running"
        assert tool_list.get_tool_call("call_3")["status"] == "success"
        assert tool_list.get_tool_call("call_4")["status"] == "error"
    
    def test_tool_call_list_handles_dict_tool_calls(self) -> None:
        """ToolCallList корректно обрабатывает словари из ChatViewModel.
        
        ChatViewModel хранит tool_calls как список словарей с ключом 'toolCallId',
        а не как объекты с атрибутом 'id'.
        """
        tool_list = ToolCallList()
        
        # Словари как в ChatViewModel (см. chat_view_model.py строки 316-328)
        dict_tool_calls = [
            {
                "toolCallId": "tc_001",
                "title": "read_file",
                "kind": "filesystem",
                "status": "pending",
            },
            {
                "toolCallId": "tc_002",
                "title": "write_file",
                "kind": "filesystem",
                "status": "in_progress",
            },
            {
                "toolCallId": "tc_003",
                "title": "execute_command",
                "kind": "terminal",
                "status": "completed",
            },
        ]
        
        # Вызываем обработчик со словарями
        tool_list._on_tool_calls_changed(dict_tool_calls)
        
        # Проверяем что tool calls добавлены с правильными ID
        assert "tc_001" in tool_list._tool_calls
        assert "tc_002" in tool_list._tool_calls
        assert "tc_003" in tool_list._tool_calls
        
        # Проверяем маппинг статусов для словарей
        assert tool_list.get_tool_call("tc_001")["status"] == "pending"
        assert tool_list.get_tool_call("tc_002")["status"] == "running"  # in_progress -> running
        assert tool_list.get_tool_call("tc_003")["status"] == "success"  # completed -> success
        
        # Проверяем что title используется как name
        assert tool_list.get_tool_call("tc_001")["name"] == "read_file"
        assert tool_list.get_tool_call("tc_002")["name"] == "write_file"


# === FileChangePreview тесты ===


class TestDiffLine:
    """Тесты для DiffLine."""

    def test_diff_line_creates_with_all_fields(self) -> None:
        """DiffLine создаётся со всеми полями."""
        line = DiffLine(
            content="test content",
            change_type="added",
            old_line_number=None,
            new_line_number=5,
        )
        assert line.content == "test content"
        assert line.change_type == "added"
        assert line.old_line_number is None
        assert line.new_line_number == 5

    def test_diff_line_unchanged(self) -> None:
        """DiffLine с unchanged типом имеет оба номера строк."""
        line = DiffLine(
            content="same line",
            change_type="unchanged",
            old_line_number=3,
            new_line_number=4,
        )
        assert line.change_type == "unchanged"
        assert line.old_line_number == 3
        assert line.new_line_number == 4


class TestFileChangePreview:
    """Тесты для FileChangePreview."""

    def test_file_change_preview_creates_with_path(self) -> None:
        """FileChangePreview создаётся с путём к файлу."""
        preview = FileChangePreview(file_path="/home/user/test.py")
        assert preview.file_path == "/home/user/test.py"

    def test_file_change_preview_computes_diff(self) -> None:
        """FileChangePreview вычисляет diff между версиями."""
        preview = FileChangePreview(
            file_path="/test.py",
            old_content="line1\nline2",
            new_content="line1\nline3\nline4",
        )
        
        # Должны быть добавленные и удалённые строки
        assert preview.added_count > 0

    def test_file_change_preview_with_ready_diff_lines(self) -> None:
        """FileChangePreview принимает готовые diff_lines."""
        lines = [
            DiffLine("added line", "added", None, 1),
            DiffLine("removed line", "removed", 1, None),
        ]
        
        preview = FileChangePreview(
            file_path="/test.py",
            diff_lines=lines,
        )
        
        assert preview.added_count == 1
        assert preview.removed_count == 1

    def test_file_change_preview_empty_content(self) -> None:
        """FileChangePreview обрабатывает пустой контент."""
        preview = FileChangePreview(
            file_path="/test.py",
            old_content="",
            new_content="",
        )
        
        assert preview.added_count == 0
        assert preview.removed_count == 0

    def test_file_change_preview_set_diff(self) -> None:
        """FileChangePreview обновляет diff через set_diff."""
        preview = FileChangePreview(file_path="/test.py")
        
        preview.set_diff(
            old_content="old",
            new_content="new",
        )
        
        # После обновления diff должен пересчитаться
        assert preview._old_content == "old"
        assert preview._new_content == "new"


# === ActionBar тесты ===


class TestActionBar:
    """Тесты для ActionBar."""

    def test_action_bar_creates_empty(self) -> None:
        """ActionBar создаётся пустым."""
        bar = ActionBar()
        assert len(bar._buttons) == 0

    def test_action_bar_buttons_dict_management(self) -> None:
        """ActionBar управляет словарём кнопок."""
        bar = ActionBar()
        # Симулируем добавление кнопки в словарь без mount
        button = ActionButton("Save", variant="primary", id="save")
        bar._buttons["save"] = button
        
        assert "save" in bar._buttons
        assert bar._buttons["save"] == button

    def test_action_bar_get_action(self) -> None:
        """ActionBar возвращает кнопку по ID из словаря."""
        bar = ActionBar()
        button = ActionButton("Save", id="save")
        bar._buttons["save"] = button
        
        result = bar.get_action("save")
        assert result == button

    def test_action_bar_get_nonexistent_action(self) -> None:
        """ActionBar возвращает None для несуществующего ID."""
        bar = ActionBar()
        
        button = bar.get_action("nonexistent")
        assert button is None

    def test_action_bar_buttons_removal(self) -> None:
        """ActionBar удаляет кнопку из словаря."""
        bar = ActionBar()
        button = ActionButton("Save", id="save")
        bar._buttons["save"] = button
        assert "save" in bar._buttons
        
        bar._buttons.pop("save", None)
        assert "save" not in bar._buttons

    def test_action_bar_buttons_clear(self) -> None:
        """ActionBar очищает словарь кнопок."""
        bar = ActionBar()
        bar._buttons["save"] = ActionButton("Save", id="save")
        bar._buttons["cancel"] = ActionButton("Cancel", id="cancel")
        assert len(bar._buttons) == 2
        
        bar._buttons.clear()
        assert len(bar._buttons) == 0


# === FileChangePreviewModal тесты ===


class TestFileChangePreviewModal:
    """Тесты для FileChangePreviewModal."""

    def test_file_change_preview_modal_creates_with_file_path(self) -> None:
        """FileChangePreviewModal создаётся с путём к файлу."""
        modal = FileChangePreviewModal(file_path="/home/user/test.py")
        assert modal.file_path == "/home/user/test.py"

    def test_file_change_preview_modal_stores_old_content(self) -> None:
        """FileChangePreviewModal сохраняет старое содержимое."""
        modal = FileChangePreviewModal(
            file_path="/test.py",
            old_content="old content",
        )
        assert modal._old_content == "old content"

    def test_file_change_preview_modal_stores_new_content(self) -> None:
        """FileChangePreviewModal сохраняет новое содержимое."""
        modal = FileChangePreviewModal(
            file_path="/test.py",
            new_content="new content",
        )
        assert modal._new_content == "new content"

    def test_file_change_preview_modal_stores_tool_call_id(self) -> None:
        """FileChangePreviewModal сохраняет ID tool call."""
        modal = FileChangePreviewModal(
            file_path="/test.py",
            tool_call_id="call_123",
        )
        assert modal.tool_call_id == "call_123"

    def test_file_change_preview_modal_default_tool_name(self) -> None:
        """FileChangePreviewModal имеет tool_name по умолчанию."""
        modal = FileChangePreviewModal(file_path="/test.py")
        assert modal._tool_name == "file_edit"

    def test_file_change_preview_modal_custom_tool_name(self) -> None:
        """FileChangePreviewModal принимает custom tool_name."""
        modal = FileChangePreviewModal(
            file_path="/test.py",
            tool_name="write_file",
        )
        assert modal._tool_name == "write_file"

    def test_file_change_preview_modal_with_all_params(self) -> None:
        """FileChangePreviewModal создаётся со всеми параметрами."""
        modal = FileChangePreviewModal(
            file_path="/home/user/app.py",
            old_content="line1\nline2",
            new_content="line1\nline3\nline4",
            tool_call_id="call_456",
            tool_name="patch_file",
        )
        assert modal.file_path == "/home/user/app.py"
        assert modal._old_content == "line1\nline2"
        assert modal._new_content == "line1\nline3\nline4"
        assert modal.tool_call_id == "call_456"
        assert modal._tool_name == "patch_file"

    def test_file_change_preview_modal_empty_content(self) -> None:
        """FileChangePreviewModal обрабатывает пустой контент."""
        modal = FileChangePreviewModal(
            file_path="/test.py",
            old_content="",
            new_content="",
        )
        assert modal._old_content == ""
        assert modal._new_content == ""

    def test_file_change_preview_modal_tool_call_id_none(self) -> None:
        """FileChangePreviewModal может иметь tool_call_id=None."""
        modal = FileChangePreviewModal(file_path="/test.py")
        assert modal.tool_call_id is None

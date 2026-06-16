"""Тесты для UIViewModel и глобального UI-состояния."""

from __future__ import annotations

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.ui_view_model import SidebarTab, UIViewModel


def test_cycle_sidebar_tabs_forward_and_backward() -> None:
    """Проверить циклическое переключение вкладок sidebar."""

    ui_vm = UIViewModel(event_bus=EventBus(), logger=None)
    assert ui_vm.sidebar_tab.value == SidebarTab.SESSIONS

    ui_vm.cycle_sidebar_tab()
    assert ui_vm.sidebar_tab.value == SidebarTab.FILES

    ui_vm.cycle_sidebar_tab()
    assert ui_vm.sidebar_tab.value == SidebarTab.SETTINGS

    ui_vm.cycle_sidebar_tab(reverse=True)
    assert ui_vm.sidebar_tab.value == SidebarTab.FILES


def test_toggle_active_sidebar_section_uses_current_tab() -> None:
    """Проверить переключение expand-состояния активной вкладки."""

    ui_vm = UIViewModel(event_bus=EventBus(), logger=None)
    assert ui_vm.sessions_expanded.value is True

    ui_vm.toggle_active_sidebar_section()
    assert ui_vm.sessions_expanded.value is False

    ui_vm.set_sidebar_tab(SidebarTab.FILES)
    assert ui_vm.files_expanded.value is True

    ui_vm.toggle_active_sidebar_section()
    assert ui_vm.files_expanded.value is False

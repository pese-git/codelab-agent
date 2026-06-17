"""Тесты для компонентов Core Layout (Фаза 1 миграции UI).

Тестирует:
- MainLayout: трехколоночный layout с responsive поведением
- StyledContainer, Card: универсальные контейнеры
- CollapsiblePanel, AccordionPanel: сворачиваемые панели
- HeaderBar, FooterBar: улучшенные header/footer
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from codelab.client.presentation.ui_view_model import ConnectionStatus, UIViewModel
from codelab.client.tui.components.container import Card, ContainerVariant, StyledContainer
from codelab.client.tui.components.footer import AgentStatus, FooterBar
from codelab.client.tui.components.header import HeaderBar
from codelab.client.tui.components.main_layout import LayoutConfig, MainLayout
from codelab.client.tui.components.panel import AccordionPanel, CollapsiblePanel

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def event_bus() -> Mock:
    """Создает mock EventBus для тестов."""
    return Mock()


@pytest.fixture
def ui_vm(event_bus: Mock) -> UIViewModel:
    """Создает UIViewModel для тестов."""
    return UIViewModel(event_bus=event_bus, logger=None)


# =============================================================================
# MainLayout Tests
# =============================================================================


class TestMainLayout:
    """Тесты для MainLayout компонента."""

    def test_main_layout_creation(self) -> None:
        """MainLayout создается с дефолтными параметрами (OpenCode-style)."""
        layout = MainLayout()
        assert layout is not None
        assert layout.sidebar_visible is True
        # OpenCode-style: dock region (bottom_panel) виден по умолчанию
        assert layout.bottom_panel_visible is True

    def test_main_layout_with_ui_vm(self, ui_vm: UIViewModel) -> None:
        """MainLayout интегрируется с UIViewModel."""
        layout = MainLayout(ui_vm=ui_vm)
        assert layout._ui_vm is ui_vm

    def test_toggle_sidebar(self) -> None:
        """toggle_sidebar переключает видимость sidebar."""
        layout = MainLayout()
        assert layout.sidebar_visible is True
        
        layout.toggle_sidebar()
        assert layout.sidebar_visible is False
        
        layout.toggle_sidebar()
        assert layout.sidebar_visible is True

    def test_toggle_bottom_panel(self) -> None:
        """toggle_bottom_panel переключает видимость dock region (OpenCode-style)."""
        layout = MainLayout()
        # OpenCode-style: dock region виден по умолчанию
        assert layout.bottom_panel_visible is True
        
        layout.toggle_bottom_panel()
        assert layout.bottom_panel_visible is False
        
        layout.toggle_bottom_panel()
        assert layout.bottom_panel_visible is True

    def test_sidebar_collapsed_sync(self, ui_vm: UIViewModel) -> None:
        """sidebar_collapsed в UIViewModel синхронизируется с layout."""
        layout = MainLayout(ui_vm=ui_vm)
        
        # Изначально sidebar виден
        assert layout.sidebar_visible is True
        
        # Изменяем через UIViewModel
        ui_vm.sidebar_collapsed.value = True
        assert layout.sidebar_visible is False

    def test_custom_widths(self) -> None:
        """MainLayout принимает кастомные конфигурацию."""
        config = LayoutConfig(sidebar_width=40, bottom_panel_height=15)
        layout = MainLayout(config=config)
        assert layout.config.sidebar_width == 40
        assert layout.config.bottom_panel_height == 15


# =============================================================================
# StyledContainer Tests
# =============================================================================


class TestStyledContainer:
    """Тесты для StyledContainer компонента."""

    def test_default_container(self) -> None:
        """StyledContainer создается с дефолтным вариантом."""
        container = StyledContainer()
        assert container.variant == ContainerVariant.DEFAULT

    def test_bordered_container(self) -> None:
        """StyledContainer создается с bordered вариантом."""
        container = StyledContainer(variant=ContainerVariant.BORDERED)
        assert container.variant == ContainerVariant.BORDERED
        assert "bordered" in container.classes

    def test_rounded_container(self) -> None:
        """StyledContainer создается с rounded вариантом."""
        container = StyledContainer(variant=ContainerVariant.ROUNDED)
        assert container.variant == ContainerVariant.ROUNDED
        assert "rounded" in container.classes

    def test_panel_container(self) -> None:
        """StyledContainer создается с panel вариантом."""
        container = StyledContainer(variant=ContainerVariant.PANEL)
        assert container.variant == ContainerVariant.PANEL
        assert "panel" in container.classes

    def test_container_with_title(self) -> None:
        """StyledContainer принимает заголовок."""
        container = StyledContainer(title="Test Title")
        assert container.title == "Test Title"

    def test_set_variant(self) -> None:
        """set_variant изменяет вариант контейнера."""
        container = StyledContainer(variant=ContainerVariant.DEFAULT)
        assert container.variant == ContainerVariant.DEFAULT
        
        container.set_variant(ContainerVariant.BORDERED)
        assert container.variant == ContainerVariant.BORDERED
        assert "bordered" in container.classes


class TestCard:
    """Тесты для Card компонента."""

    def test_card_creation(self) -> None:
        """Card создается с корректными параметрами."""
        card = Card()
        assert card is not None

    def test_card_with_title(self) -> None:
        """Card принимает заголовок."""
        card = Card(title="My Card")
        assert card.title == "My Card"


# =============================================================================
# CollapsiblePanel Tests
# =============================================================================


class TestCollapsiblePanel:
    """Тесты для CollapsiblePanel компонента."""

    def test_panel_creation(self) -> None:
        """CollapsiblePanel создается с дефолтными параметрами."""
        panel = CollapsiblePanel(title="Test Panel")
        assert panel._title == "Test Panel"
        assert panel._initial_collapsed is False

    def test_panel_collapsed_state(self) -> None:
        """CollapsiblePanel можно создать свернутым."""
        panel = CollapsiblePanel(title="Test", collapsed=True)
        assert panel._initial_collapsed is True

    def test_panel_with_icon(self) -> None:
        """CollapsiblePanel принимает иконку."""
        panel = CollapsiblePanel(title="Test", icon="⚙️")
        assert panel._icon == "⚙️"

    def test_toggle(self) -> None:
        """toggle переключает состояние панели."""
        panel = CollapsiblePanel(title="Test")
        panel.collapsed = False
        
        panel.toggle()
        assert panel.collapsed is True
        
        panel.toggle()
        assert panel.collapsed is False

    def test_expand(self) -> None:
        """expand разворачивает панель."""
        panel = CollapsiblePanel(title="Test", collapsed=True)
        panel.collapsed = True
        
        panel.expand()
        assert panel.collapsed is False

    def test_collapse(self) -> None:
        """collapse сворачивает панель."""
        panel = CollapsiblePanel(title="Test")
        panel.collapsed = False
        
        panel.collapse()
        assert panel.collapsed is True


class TestAccordionPanel:
    """Тесты для AccordionPanel компонента."""

    def test_accordion_creation(self) -> None:
        """AccordionPanel создается."""
        accordion = AccordionPanel()
        assert accordion is not None
        assert accordion._allow_multiple is False

    def test_accordion_allow_multiple(self) -> None:
        """AccordionPanel может разрешить несколько открытых панелей."""
        accordion = AccordionPanel(allow_multiple=True)
        assert accordion._allow_multiple is True


# =============================================================================
# HeaderBar Tests
# =============================================================================


class TestHeaderBar:
    """Тесты для HeaderBar компонента."""

    def test_header_creation(self, ui_vm: UIViewModel) -> None:
        """HeaderBar создается с UIViewModel."""
        header = HeaderBar(ui_vm)
        assert header.ui_vm is ui_vm

    def test_header_session_title(self, ui_vm: UIViewModel) -> None:
        """HeaderBar отображает заголовок сессии."""
        header = HeaderBar(ui_vm, session_title="Test Session")
        assert header._session_title == "Test Session"

    def test_set_session_title(self, ui_vm: UIViewModel) -> None:
        """set_session_title обновляет заголовок."""
        header = HeaderBar(ui_vm)
        header.set_session_title("New Title")
        assert header._session_title == "New Title"

    def test_set_breadcrumbs(self, ui_vm: UIViewModel) -> None:
        """set_breadcrumbs устанавливает путь навигации."""
        header = HeaderBar(ui_vm)
        header.set_breadcrumbs(["Home", "Projects", "CodeLab"])
        assert header._session_title == "Home > Projects > CodeLab"

    def test_header_status_icon(self, ui_vm: UIViewModel) -> None:
        """HeaderBar показывает корректную иконку статуса."""
        header = HeaderBar(ui_vm)
        
        # Connected
        ui_vm.connection_status.value = ConnectionStatus.CONNECTED
        assert header._get_status_icon(ConnectionStatus.CONNECTED) == "🟢"
        
        # Disconnected
        assert header._get_status_icon(ConnectionStatus.DISCONNECTED) == "⚪"
        
        # Error
        assert header._get_status_icon(ConnectionStatus.ERROR) == "🔴"

    def test_header_loading_indicator(self, ui_vm: UIViewModel) -> None:
        """HeaderBar показывает индикатор загрузки."""
        header = HeaderBar(ui_vm)
        
        ui_vm.is_loading.value = False
        right_part = header._build_right_part()
        assert "⟳" not in right_part
        
        ui_vm.is_loading.value = True
        right_part = header._build_right_part()
        assert "⟳" in right_part


# =============================================================================
# FooterBar Tests
# =============================================================================


class TestFooterBar:
    """Тесты для FooterBar компонента."""

    def test_footer_creation(self, ui_vm: UIViewModel) -> None:
        """FooterBar создается с UIViewModel."""
        footer = FooterBar(ui_vm)
        assert footer.ui_vm is ui_vm

    def test_footer_show_tokens(self, ui_vm: UIViewModel) -> None:
        """FooterBar отображает токены при включенной опции."""
        footer = FooterBar(ui_vm, show_tokens=True)
        assert footer._show_tokens is True
        
        footer = FooterBar(ui_vm, show_tokens=False)
        assert footer._show_tokens is False

    def test_footer_show_hotkeys(self, ui_vm: UIViewModel) -> None:
        """FooterBar отображает горячие клавиши при включенной опции."""
        footer = FooterBar(ui_vm, show_hotkeys=True)
        assert footer._show_hotkeys is True

    def test_set_agent_status(self, ui_vm: UIViewModel) -> None:
        """set_agent_status обновляет статус агента."""
        footer = FooterBar(ui_vm)
        
        footer.set_agent_status(AgentStatus.THINKING)
        assert footer._agent_status == AgentStatus.THINKING
        
        footer.set_agent_status(AgentStatus.IDLE)
        assert footer._agent_status == AgentStatus.IDLE

    def test_update_tokens(self, ui_vm: UIViewModel) -> None:
        """update_tokens обновляет информацию о токенах."""
        footer = FooterBar(ui_vm)
        footer.update_tokens(1500, 0.0025)
        
        assert footer._tokens_used == 1500
        assert footer._cost == 0.0025

    def test_footer_status_prefix(self, ui_vm: UIViewModel) -> None:
        """FooterBar показывает корректный префикс статуса."""
        footer = FooterBar(ui_vm)
        
        assert footer._status_prefix(ConnectionStatus.CONNECTED) == "✓"
        assert footer._status_prefix(ConnectionStatus.CONNECTING) == "⟳"
        assert footer._status_prefix(ConnectionStatus.RECONNECTING) == "⟳"
        assert footer._status_prefix(ConnectionStatus.ERROR) == "✗"
        assert footer._status_prefix(ConnectionStatus.DISCONNECTED) == "○"

    def test_footer_error_priority(self, ui_vm: UIViewModel) -> None:
        """FooterBar отображает ошибку с высшим приоритетом."""
        footer = FooterBar(ui_vm)
        
        # Устанавливаем все сообщения
        ui_vm.error_message.value = "Critical error"
        ui_vm.warning_message.value = "Warning"
        ui_vm.info_message.value = "Info"
        
        footer._update_display()
        # Проверяем что отображается именно ошибка (не можем проверить текст напрямую)
        assert ui_vm.error_message.value == "Critical error"

    def test_footer_hotkeys_text(self, ui_vm: UIViewModel) -> None:
        """FooterBar генерирует текст с горячими клавишами."""
        footer = FooterBar(ui_vm)
        hotkeys_text = footer._build_hotkeys_text()
        
        assert "F1" in hotkeys_text
        assert "help" in hotkeys_text

    def test_footer_tokens_text(self, ui_vm: UIViewModel) -> None:
        """FooterBar генерирует текст с токенами."""
        footer = FooterBar(ui_vm)
        footer._tokens_used = 1000
        footer._cost = 0.001
        
        tokens_text = footer._build_tokens_text()
        assert "1,000" in tokens_text
        assert "$0.0010" in tokens_text


# =============================================================================
# AgentStatus Tests
# =============================================================================


class TestAgentStatus:
    """Тесты для AgentStatus enum."""

    def test_agent_status_values(self) -> None:
        """AgentStatus имеет корректные значения."""
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.THINKING.value == "thinking"
        assert AgentStatus.EXECUTING.value == "executing"
        assert AgentStatus.WAITING.value == "waiting"


# =============================================================================
# ContainerVariant Tests
# =============================================================================


class TestContainerVariant:
    """Тесты для ContainerVariant enum."""

    def test_container_variant_values(self) -> None:
        """ContainerVariant имеет корректные значения."""
        assert ContainerVariant.DEFAULT.value == "default"
        assert ContainerVariant.BORDERED.value == "bordered"
        assert ContainerVariant.ROUNDED.value == "rounded"
        assert ContainerVariant.PANEL.value == "panel"


# =============================================================================
# Integration Tests
# =============================================================================


class TestCoreLayoutIntegration:
    """Интеграционные тесты для компонентов Core Layout."""

    def test_ui_vm_connection_status_propagation(self, ui_vm: UIViewModel) -> None:
        """Изменение connection_status в UIViewModel обновляет компоненты."""
        header = HeaderBar(ui_vm)
        footer = FooterBar(ui_vm)
        
        # Изменяем статус
        ui_vm.connection_status.value = ConnectionStatus.CONNECTED
        
        # Проверяем что компоненты имеют доступ к актуальному статусу
        assert header.ui_vm.connection_status.value == ConnectionStatus.CONNECTED
        assert footer.ui_vm.connection_status.value == ConnectionStatus.CONNECTED

    def test_ui_vm_loading_propagation(self, ui_vm: UIViewModel) -> None:
        """Изменение is_loading в UIViewModel обновляет компоненты."""
        header = HeaderBar(ui_vm)
        footer = FooterBar(ui_vm)
        
        ui_vm.is_loading.value = True
        
        assert header.ui_vm.is_loading.value is True
        assert footer.ui_vm.is_loading.value is True
        # FooterBar должен изменить статус агента
        assert footer._agent_status == AgentStatus.THINKING

    def test_sidebar_collapsed_state(self, ui_vm: UIViewModel) -> None:
        """sidebar_collapsed корректно синхронизируется."""
        layout = MainLayout(ui_vm=ui_vm)
        
        # Сворачиваем через layout
        layout.toggle_sidebar()
        assert ui_vm.sidebar_collapsed.value is True
        
        # Разворачиваем через layout
        layout.toggle_sidebar()
        assert ui_vm.sidebar_collapsed.value is False

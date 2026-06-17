"""Тесты покрытия для MainLayout компонента.

Проверяют непокрытые строки в:
- LayoutConfig
- MainLayout
"""

from __future__ import annotations

from unittest.mock import patch

from textual.app import App

from codelab.client.presentation.observable import Observable
from codelab.client.tui.components.main_layout import LayoutConfig, MainLayout


class FakeUIViewModel:
    """Фейковый UIViewModel для тестов MainLayout."""

    def __init__(self) -> None:
        self.sidebar_collapsed: Observable[bool] = Observable(False)


class TestLayoutConfig:
    """Тесты для LayoutConfig."""

    def test_default_values(self) -> None:
        """Конфигурация по умолчанию содержит ожидаемые значения."""
        config = LayoutConfig()

        assert config.sidebar_width == 30
        assert config.sidebar_visible is True
        assert config.right_panel_width == 30
        assert config.right_panel_visible is True
        assert config.bottom_panel_height == 10
        assert config.bottom_panel_visible is True
        assert config.min_width_for_sidebar == 80

    def test_custom_values(self) -> None:
        """Конфигурация сохраняет переданные значения."""
        config = LayoutConfig(
            sidebar_width=20,
            sidebar_visible=False,
            right_panel_width=25,
            right_panel_visible=False,
            bottom_panel_height=5,
            bottom_panel_visible=False,
            min_width_for_sidebar=100,
        )

        assert config.sidebar_width == 20
        assert config.sidebar_visible is False
        assert config.right_panel_width == 25
        assert config.right_panel_visible is False
        assert config.bottom_panel_height == 5
        assert config.bottom_panel_visible is False
        assert config.min_width_for_sidebar == 100


class TestMainLayout:
    """Тесты для MainLayout."""

    def test_init_default(self) -> None:
        """Инициализация с параметрами по умолчанию."""
        layout = MainLayout()

        assert isinstance(layout.config, LayoutConfig)
        assert layout.sidebar_visible is True
        assert layout.right_panel_visible is True
        assert layout.bottom_panel_visible is True
        assert layout._ui_vm is None

    def test_init_with_config(self) -> None:
        """Инициализация с пользовательской конфигурацией."""
        config = LayoutConfig(
            sidebar_visible=False,
            right_panel_visible=False,
            bottom_panel_visible=False,
        )
        layout = MainLayout(config=config)

        assert layout.config is config
        assert layout.sidebar_visible is False
        assert layout.right_panel_visible is False
        assert layout.bottom_panel_visible is False

    def test_init_subscribes_to_view_model(self) -> None:
        """При наличии UIViewModel подписываемся на изменения sidebar."""
        ui_vm = FakeUIViewModel()
        layout = MainLayout(ui_vm=ui_vm)

        ui_vm.sidebar_collapsed.value = True
        assert layout.sidebar_visible is False

        ui_vm.sidebar_collapsed.value = False
        assert layout.sidebar_visible is True

    async def test_compose_and_mount(self) -> None:
        """Компонент создает колонки layout после монтирования."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            config = LayoutConfig(
                sidebar_visible=True,
                right_panel_visible=True,
                bottom_panel_visible=True,
            )
            layout = MainLayout(config=config)
            await pilot.app.mount(layout)

            assert layout.sidebar_column is not None
            assert layout.sidebar_column.id == "sidebar-column"
            assert layout.content_area is not None
            assert layout.content_area.id == "content-area"
            assert layout.dock_region is not None
            assert layout.dock_region.id == "dock-region"
            assert layout.bottom_panel is layout.dock_region
            assert layout.right_panel_column is not None
            assert layout.right_panel_column.id == "right-panel-column"

    async def test_compose_hidden_panels(self) -> None:
        """Скрытые панели получают CSS-класс hidden."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            config = LayoutConfig(
                sidebar_visible=False,
                right_panel_visible=False,
                bottom_panel_visible=False,
            )
            layout = MainLayout(config=config)
            await pilot.app.mount(layout)

            assert "hidden" in layout.sidebar_column.classes
            assert "hidden" in layout.dock_region.classes
            assert "hidden" in layout.right_panel_column.classes

    async def test_watch_sidebar_visible(self) -> None:
        """Изменение видимости sidebar обновляет классы и отправляет событие."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            layout = MainLayout()
            await pilot.app.mount(layout)

            with patch.object(layout, "post_message") as mock_post:
                layout.sidebar_visible = False

            assert "hidden" in layout.sidebar_column.classes
            events = [call.args[0] for call in mock_post.call_args_list]
            toggled = [e for e in events if isinstance(e, MainLayout.SidebarToggled)]
            assert len(toggled) == 1
            assert toggled[0].visible is False

    async def test_watch_bottom_panel_visible(self) -> None:
        """Изменение видимости dock region обновляет классы и отправляет событие."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            layout = MainLayout(
                config=LayoutConfig(bottom_panel_visible=False)
            )
            await pilot.app.mount(layout)

            with patch.object(layout, "post_message") as mock_post:
                layout.bottom_panel_visible = True

            assert "hidden" not in layout.dock_region.classes
            events = [call.args[0] for call in mock_post.call_args_list]
            toggled = [e for e in events if isinstance(e, MainLayout.PanelToggled)]
            assert len(toggled) == 1
            assert toggled[0].panel_type == "dock"
            assert toggled[0].visible is True

    async def test_watch_right_panel_visible(self) -> None:
        """Изменение видимости правой панели обновляет классы и отправляет событие."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            layout = MainLayout(
                config=LayoutConfig(right_panel_visible=False)
            )
            await pilot.app.mount(layout)

            with patch.object(layout, "post_message") as mock_post:
                layout.right_panel_visible = True

            assert "hidden" not in layout.right_panel_column.classes
            events = [call.args[0] for call in mock_post.call_args_list]
            toggled = [e for e in events if isinstance(e, MainLayout.PanelToggled)]
            assert len(toggled) == 1
            assert toggled[0].panel_type == "right"
            assert toggled[0].visible is True

    async def test_watch_bottom_panel_hidden(self) -> None:
        """Скрытие dock region добавляет CSS-класс hidden."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            layout = MainLayout()
            await pilot.app.mount(layout)

            layout.bottom_panel_visible = False

            assert "hidden" in layout.dock_region.classes

    async def test_watch_right_panel_hidden(self) -> None:
        """Скрытие правой панели добавляет CSS-класс hidden."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            layout = MainLayout()
            await pilot.app.mount(layout)

            layout.right_panel_visible = False

            assert "hidden" in layout.right_panel_column.classes

    def test_toggle_sidebar_without_vm(self) -> None:
        """Переключение sidebar работает без ViewModel."""
        layout = MainLayout()
        layout.toggle_sidebar()

        assert layout.sidebar_visible is False

    def test_toggle_sidebar_with_vm(self) -> None:
        """Переключение sidebar синхронизируется с UIViewModel."""
        ui_vm = FakeUIViewModel()
        layout = MainLayout(ui_vm=ui_vm)

        layout.toggle_sidebar()
        assert layout.sidebar_visible is False
        assert ui_vm.sidebar_collapsed.value is True

        layout.toggle_sidebar()
        assert layout.sidebar_visible is True
        assert ui_vm.sidebar_collapsed.value is False

    def test_toggle_bottom_panel(self) -> None:
        """Переключение нижней панели меняет состояние."""
        layout = MainLayout()
        layout.toggle_bottom_panel()

        assert layout.bottom_panel_visible is False

    def test_toggle_right_panel(self) -> None:
        """Переключение правой панели меняет состояние."""
        layout = MainLayout()
        layout.toggle_right_panel()

        assert layout.right_panel_visible is False

    async def test_on_resize_hides_sidebar_on_small_width(self) -> None:
        """При малой ширине sidebar автоматически скрывается."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            layout = MainLayout()
            await pilot.app.mount(layout)

            await pilot.resize_terminal(70, 24)
            await pilot.pause()

            assert layout.sidebar_visible is False

    async def test_on_resize_restores_sidebar_when_enough_space(self) -> None:
        """При достаточной ширине sidebar восстанавливается, если не свернут в VM."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            ui_vm = FakeUIViewModel()
            layout = MainLayout(
                ui_vm=ui_vm,
                config=LayoutConfig(sidebar_visible=False),
            )
            await pilot.app.mount(layout)

            await pilot.resize_terminal(120, 24)
            await pilot.pause()

            assert layout.sidebar_visible is True

    async def test_on_resize_does_not_restore_when_collapsed_in_vm(self) -> None:
        """Если VM считает sidebar свернутым, ширина его не восстанавливает."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            ui_vm = FakeUIViewModel()
            ui_vm.sidebar_collapsed.value = True
            layout = MainLayout(
                ui_vm=ui_vm,
                config=LayoutConfig(sidebar_visible=False),
            )
            await pilot.app.mount(layout)

            await pilot.resize_terminal(120, 24)
            await pilot.pause()

            assert layout.sidebar_visible is False

    async def test_properties_return_containers(self) -> None:
        """Свойства возвращают созданные в compose контейнеры."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            layout = MainLayout()
            await pilot.app.mount(layout)

            assert layout.sidebar_column is not None
            assert layout.content_area is not None
            assert layout.dock_region is not None
            assert layout.bottom_panel is layout.dock_region
            assert layout.right_panel_column is not None

    def test_events_store_attributes(self) -> None:
        """События переключения панелей сохраняют переданные атрибуты."""
        sidebar_event = MainLayout.SidebarToggled(visible=False)
        assert sidebar_event.visible is False

        panel_event = MainLayout.PanelToggled(panel_type="dock", visible=True)
        assert panel_event.panel_type == "dock"
        assert panel_event.visible is True

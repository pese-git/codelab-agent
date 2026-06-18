"""Тесты для компонента HeaderBar с MVVM интеграцией."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import Mock

import pytest

from codelab.client.presentation.ui_view_model import ConnectionStatus, UIViewModel
from codelab.client.tui.components.header import HeaderBar


@pytest.fixture
def ui_view_model() -> UIViewModel:
    """Создать UIViewModel для тестов."""
    # EventBus требуется обязательно для подписки на события в __init__
    event_bus = Mock()
    return UIViewModel(event_bus=event_bus, logger=None)


@pytest.fixture
def header_bar(ui_view_model: UIViewModel) -> HeaderBar:
    """Создать HeaderBar с UIViewModel."""
    return HeaderBar(ui_view_model)


def test_header_bar_initializes_with_ui_view_model(ui_view_model: UIViewModel) -> None:
    """Проверить что HeaderBar инициализируется с UIViewModel."""
    header = HeaderBar(ui_view_model)
    
    assert header.ui_vm is ui_view_model
    assert header.id == "header"


def test_header_bar_displays_initial_status(header_bar: HeaderBar) -> None:
    """Проверить что HeaderBar отображает начальный статус (DISCONNECTED)."""
    # Начальный статус — DISCONNECTED, не загружается
    rendered = cast(Any, header_bar.render()).plain
    assert "CodeLab" in rendered
    assert "disconnected" in rendered


def test_header_bar_updates_on_connection_status_change(
    header_bar: HeaderBar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить что HeaderBar обновляется при изменении connection_status."""
    # Изменить статус на CONNECTING
    ui_view_model.connection_status.value = ConnectionStatus.CONNECTING
    
    rendered = cast(Any, header_bar.render()).plain
    assert "connecting" in rendered
    assert "CodeLab" in rendered


def test_header_bar_shows_loading_indicator_when_loading(
    header_bar: HeaderBar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить что HeaderBar показывает индикатор загрузки при is_loading=True."""
    # Включить загрузку
    ui_view_model.is_loading.value = True
    
    rendered = cast(Any, header_bar.render()).plain
    assert "⟳" in rendered
    assert "CodeLab" in rendered


def test_header_bar_hides_loading_indicator_when_not_loading(
    header_bar: HeaderBar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить что HeaderBar скрывает индикатор загрузки при is_loading=False."""
    # Сначала включить загрузку
    ui_view_model.is_loading.value = True
    
    # Потом отключить
    ui_view_model.is_loading.value = False
    
    rendered = cast(Any, header_bar.render()).plain
    assert "⟳" not in rendered


def test_header_bar_handles_multiple_status_changes(
    header_bar: HeaderBar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить что HeaderBar корректно обрабатывает несколько изменений статуса."""
    # Переходы: DISCONNECTED → CONNECTING → CONNECTED → RECONNECTING → CONNECTED
    statuses = [
        ConnectionStatus.CONNECTING,
        ConnectionStatus.CONNECTED,
        ConnectionStatus.RECONNECTING,
        ConnectionStatus.CONNECTED,
    ]
    
    for status in statuses:
        ui_view_model.connection_status.value = status
        rendered = cast(Any, header_bar.render()).plain
        assert status.value in rendered


def test_header_bar_displays_connected_status(
    header_bar: HeaderBar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить что HeaderBar отображает CONNECTED статус."""
    ui_view_model.connection_status.value = ConnectionStatus.CONNECTED
    
    rendered = cast(Any, header_bar.render()).plain
    assert "connected" in rendered


def test_header_bar_displays_error_status(
    header_bar: HeaderBar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить что HeaderBar отображает ERROR статус."""
    ui_view_model.connection_status.value = ConnectionStatus.ERROR
    
    rendered = cast(Any, header_bar.render()).plain
    assert "error" in rendered

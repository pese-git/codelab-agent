"""Тесты для компонента PlanPanel с MVVM интеграцией."""

from __future__ import annotations

from typing import Any, cast

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.messages import PlanEntry, PlanUpdate
from codelab.client.presentation.plan_view_model import PlanViewModel
from codelab.client.tui.components.plan_panel import PlanPanel


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def plan_view_model(event_bus: EventBus) -> PlanViewModel:
    """Создать PlanViewModel для тестов."""
    return PlanViewModel(event_bus=event_bus, logger=None)


@pytest.fixture
def plan_panel(plan_view_model: PlanViewModel) -> PlanPanel:
    """Создать PlanPanel с PlanViewModel."""
    return PlanPanel(plan_view_model)


# ===== Инициализация =====


def test_plan_panel_initializes_with_plan_vm(plan_view_model: PlanViewModel) -> None:
    """Проверить что PlanPanel инициализируется с PlanViewModel."""
    plan_panel = PlanPanel(plan_view_model)

    assert plan_panel.plan_vm is plan_view_model
    assert plan_panel.id == "plan-panel"


def test_plan_panel_requires_plan_vm() -> None:
    """Проверить что PlanPanel требует PlanViewModel в конструкторе."""
    # Попытаемся создать PlanPanel без параметра - должна быть ошибка
    # Так как конструктор сразу обращается к plan_vm.plan_text, получаем AttributeError
    invalid_plan_vm = cast(Any, None)
    with pytest.raises(AttributeError):
        PlanPanel(invalid_plan_vm)


# ===== Отображение =====


def test_plan_panel_displays_empty_state_initially(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что PlanPanel показывает пустое состояние по умолчанию."""
    # Начальное состояние - план не установлен
    assert plan_view_model.has_plan.value is False

    rendered = cast(Any, plan_panel.render()).plain
    assert "План: не получен" in rendered


# ===== Реактивное обновление =====


def test_plan_panel_updates_on_plan_change(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что PlanPanel обновляется при изменении плана в ViewModel."""
    test_plan = "1. Задача A\n2. Задача B"
    plan_view_model.set_plan(test_plan)

    # Проверяем что has_plan флаг установлен
    assert plan_view_model.has_plan.value is True

    # Проверяем что план отображается в UI
    rendered = cast(Any, plan_panel.render()).plain
    assert test_plan in rendered
    assert "План: не получен" not in rendered


def test_plan_panel_handles_whitespace_only_plan(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что план только из пробелов считается пустым."""
    plan_view_model.set_plan("   \n   \t   ")

    # has_plan должен быть False для плана только из пробелов
    assert plan_view_model.has_plan.value is False

    rendered = cast(Any, plan_panel.render()).plain
    assert "План: не получен" in rendered


def test_plan_panel_displays_multiline_plan(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что многострочный план отображается корректно."""
    multiline_plan = "1. Первая задача\n2. Вторая задача\n3. Третья задача"
    plan_view_model.set_plan(multiline_plan)

    rendered = cast(Any, plan_panel.render()).plain
    assert "1. Первая задача" in rendered
    assert "2. Вторая задача" in rendered
    assert "3. Третья задача" in rendered


# ===== Очистка плана =====


def test_plan_panel_clears_on_plan_clear(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что PlanPanel очищается при вызове clear_plan."""
    # Сначала установим план
    plan_view_model.set_plan("Какой-то план")
    assert plan_view_model.has_plan.value is True

    # Потом очистим его
    plan_view_model.clear_plan()
    assert plan_view_model.has_plan.value is False

    # Проверяем что UI вернулась к пустому состоянию
    rendered = cast(Any, plan_panel.render()).plain
    assert "План: не получен" in rendered


def test_plan_panel_clears_entries_on_reset(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что reset() полностью очищает панель и ViewModel."""
    # Сначала применим update с entries
    entry = PlanEntry(content="Задача", priority="high", status="pending")
    update = PlanUpdate(sessionUpdate="plan", entries=[entry])
    plan_panel.apply_update(update)
    assert plan_view_model.has_plan.value is True
    assert plan_panel._entries != []

    # Вызовем reset()
    plan_panel.reset()

    # Проверяем что план очищен
    assert plan_view_model.has_plan.value is False
    assert plan_panel._entries == []

    rendered = cast(Any, plan_panel.render()).plain
    assert "План: не получен" in rendered


# ===== Обновление по session/update =====


def test_plan_panel_apply_update(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что apply_update() обновляет панель и ViewModel."""
    # Создаем mock объект PlanUpdate с entries
    entry1 = PlanEntry(content="Задача 1", priority="high", status="pending")
    entry2 = PlanEntry(content="Задача 2", priority="medium", status="in_progress")
    update = PlanUpdate(sessionUpdate="plan", entries=[entry1, entry2])

    # Применяем update
    plan_panel.apply_update(update)

    # Проверяем что entries сохранились
    assert len(plan_panel._entries) == 2
    assert plan_panel._entries[0]["content"] == "Задача 1"
    assert plan_panel._entries[1]["content"] == "Задача 2"

    # Проверяем что план обновился в ViewModel
    assert plan_view_model.has_plan.value is True
    rendered = cast(Any, plan_panel.render()).plain
    assert "Задача 1" in rendered
    assert "Задача 2" in rendered


# ===== Реактивность между компонентами =====


def test_plan_panel_reacts_to_multiple_plan_changes(
    plan_panel: PlanPanel,
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что PlanPanel реагирует на множественные изменения плана."""
    plans = [
        "План 1",
        "План 2\nС двумя строками",
        "План 3\nС тремя\nстроками",
        "",  # Пустой план
    ]

    for plan in plans:
        plan_view_model.set_plan(plan)
        rendered = cast(Any, plan_panel.render()).plain

        if plan.strip():
            assert plan_view_model.has_plan.value is True
            assert plan in rendered
        else:
            assert plan_view_model.has_plan.value is False
            assert "План: не получен" in rendered


def test_plan_panel_subscription_works_correctly(
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что подписка на Observable работает корректно."""
    # Создаем PlanPanel
    plan_panel = PlanPanel(plan_view_model)

    # Изменяем ViewModel
    plan_view_model.set_plan("Новый план")

    # Проверяем что UI обновился
    rendered = cast(Any, plan_panel.render()).plain
    assert "Новый план" in rendered
    assert plan_view_model.has_plan.value is True


def test_plan_panel_observable_change_notifications(
    plan_view_model: PlanViewModel,
) -> None:
    """Проверить что Observable правильно уведомляет подписчиков."""
    callback_called = []

    def on_plan_changed(new_plan: str) -> None:
        callback_called.append(new_plan)

    # Подписываемся на план_текст
    plan_view_model.plan_text.subscribe(on_plan_changed)

    # Изменяем план несколько раз
    plan_view_model.set_plan("План 1")
    plan_view_model.set_plan("План 2")
    plan_view_model.set_plan("План 3")

    # Проверяем что callback вызывался для каждого изменения
    assert len(callback_called) >= 3  # >= потому что может быть notification от has_plan
    assert "План 1" in callback_called
    assert "План 2" in callback_called
    assert "План 3" in callback_called

from __future__ import annotations

from codelab.client.messages import PlanEntry, PlanUpdate
from codelab.client.presentation.plan_view_model import PlanViewModel
from codelab.client.tui.components.plan_panel import PlanPanel


def test_plan_panel_applies_plan_update_snapshot() -> None:
    # Создаем PlanViewModel для компонента
    plan_vm = PlanViewModel()
    panel = PlanPanel(plan_vm)
    panel.apply_update(
        PlanUpdate(
            sessionUpdate="plan",
            entries=[
                PlanEntry(content="Собрать контекст", priority="high", status="completed"),
                PlanEntry(content="Обновить тесты", priority="medium", status="in_progress"),
            ],
        )
    )

    rendered = panel._render_text()  # noqa: SLF001

    assert "[completed] (high) Собрать контекст" in rendered
    assert "[in_progress] (medium) Обновить тесты" in rendered


def test_plan_panel_reset_restores_placeholder() -> None:
    # Создаем PlanViewModel для компонента
    plan_vm = PlanViewModel()
    panel = PlanPanel(plan_vm)
    panel.apply_update(
        PlanUpdate(
            sessionUpdate="plan",
            entries=[
                PlanEntry(content="Проверить статус", priority="low", status="pending"),
            ],
        )
    )

    panel.reset()

    assert panel._render_text() == "План: не получен"  # noqa: SLF001

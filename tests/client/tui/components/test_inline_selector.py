"""Тесты для InlineSelector виджета."""

from __future__ import annotations

from unittest.mock import MagicMock

from codelab.client.presentation.observable import Observable
from codelab.client.tui.components.inline_selector import InlineSelector


def _make_selector(
    label: str = "Model",
    current_value: str = "gpt-4o",
    *,
    with_observable: bool = True,
    with_callback: bool = True,
) -> tuple[InlineSelector, Observable[str | None], MagicMock, MagicMock]:
    """Создаёт InlineSelector с тестовыми зависимостями."""
    observable: Observable[str | None] = Observable(current_value)
    get_label_fn = MagicMock(return_value=current_value)
    callback = MagicMock()

    selector = InlineSelector(
        label=label,
        get_label_fn=get_label_fn,
        observable=observable if with_observable else None,
        open_callback=callback if with_callback else None,
        hotkey="ctrl+m",
    )
    return selector, observable, get_label_fn, callback


class TestInlineSelectorInit:
    """Тесты инициализации InlineSelector."""

    def test_display_text_includes_label_and_value(self) -> None:
        """Отображаемый текст содержит label и значение."""
        selector, _, _, _ = _make_selector(label="Model", current_value="gpt-4o")
        rendered = str(selector.render())
        assert "Model" in rendered
        assert "gpt-4o" in rendered

    def test_display_text_includes_dropdown_indicator(self) -> None:
        """Отображаемый текст содержит индикатор dropdown."""
        selector, _, _, _ = _make_selector()
        rendered = str(selector.render())
        assert "▾" in rendered

    def test_init_without_observable(self) -> None:
        """Инициализация без Observable не вызывает ошибок."""
        selector, _, _, _ = _make_selector(with_observable=False)
        assert selector._observable is None

    def test_init_without_callback(self) -> None:
        """Инициализация без callback не вызывает ошибок."""
        selector, _, _, _ = _make_selector(with_callback=False)
        assert selector._open_callback is None


class TestInlineSelectorObservable:
    """Тесты подписки на Observable."""

    def test_updates_on_observable_change(self) -> None:
        """Виджет обновляется при изменении Observable значения."""
        selector, observable, get_label_fn, _ = _make_selector(
            current_value="gpt-4o",
        )
        # Подписка уже создана в __init__
        get_label_fn.return_value = "claude-sonnet"
        observable.value = "claude-sonnet"
        assert "claude-sonnet" in selector.content

    def test_no_update_when_value_unchanged(self) -> None:
        """Виджет не обновляется если значение не изменилось."""
        selector, observable, get_label_fn, _ = _make_selector(
            current_value="gpt-4o",
        )
        get_label_fn.reset_mock()
        observable.value = "gpt-4o"  # Same value
        get_label_fn.assert_not_called()


class TestInlineSelectorClick:
    """Тесты обработки клика."""

    def test_click_calls_callback(self) -> None:
        """Клик вызывает open_callback."""
        selector, _, _, callback = _make_selector()
        selector.on_click()
        callback.assert_called_once()

    def test_click_without_callback(self) -> None:
        """Клик без callback не вызывает ошибок."""
        selector, _, _, _ = _make_selector(with_callback=False)
        selector.on_click()  # Should not raise


class TestInlineSelectorOpenSelector:
    """Тесты программного открытия модала."""

    def test_open_selector_calls_callback(self) -> None:
        """open_selector вызывает open_callback."""
        selector, _, _, callback = _make_selector()
        selector.open_selector()
        callback.assert_called_once()

    def test_open_selector_without_callback(self) -> None:
        """open_selector без callback не вызывает ошибок."""
        selector, _, _, _ = _make_selector(with_callback=False)
        selector.open_selector()  # Should not raise


class TestInlineSelectorMountUnmount:
    """Тесты монтирования и размонтирования."""

    def test_init_subscribes_to_observable(self) -> None:
        """При инициализации виджет подписывается на Observable."""
        selector, observable, _, _ = _make_selector()
        assert selector._unsubscribe is not None

    def test_unmount_unsubscribes(self) -> None:
        """При размонтировании виджет отписывается от Observable."""
        selector, _, _, _ = _make_selector()
        assert selector._unsubscribe is not None
        selector.on_unmount()
        assert selector._unsubscribe is None

    def test_unmount_without_subscribe(self) -> None:
        """Размонтирование без подписки не вызывает ошибок."""
        selector, _, _, _ = _make_selector(with_observable=False)
        selector.on_unmount()  # Should not raise

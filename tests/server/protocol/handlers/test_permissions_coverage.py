"""Дополнительные тесты покрытия для обработчиков разрешений.

Покрывает ранее непокрытые ветки извлечения outcome/optionId
и разрешения kind опции.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from codelab.server.protocol.handlers.permissions import (
    extract_permission_option_id,
    extract_permission_outcome,
    resolve_permission_option_kind,
)


class TestExtractPermissionOutcome:
    """Тесты извлечения outcome."""

    def test_non_dict_result_returns_none(self) -> None:
        """При не-dict результате возвращается None."""
        assert extract_permission_outcome("allow") is None

    def test_legacy_string_outcome(self) -> None:
        """Поддерживается legacy-формат со строкой в outcome."""
        assert extract_permission_outcome({"outcome": "allow"}) == "allow"

    def test_no_outcome_returns_none(self) -> None:
        """Если outcome отсутствует или невалиден, возвращается None."""
        assert extract_permission_outcome({"other": "value"}) is None
        assert extract_permission_outcome({"outcome": 123}) is None


class TestExtractPermissionOptionId:
    """Тесты извлечения optionId."""

    def test_non_dict_result_returns_none(self) -> None:
        """При не-dict результате возвращается None."""
        assert extract_permission_option_id("allow_once") is None

    def test_legacy_option_id(self) -> None:
        """Поддерживается legacy-формат с optionId в корне."""
        assert extract_permission_option_id({"optionId": "allow_once"}) == "allow_once"


class TestResolvePermissionOptionKind:
    """Тесты разрешения kind опции."""

    def test_none_option_id(self) -> None:
        """При None optionId возвращается None."""
        assert resolve_permission_option_kind(None, []) is None

    def test_non_dict_option_skipped(self) -> None:
        """Опции не являющиеся dict пропускаются."""
        options = [MagicMock()]
        assert resolve_permission_option_kind("x", options) is None

    def test_non_string_kind_returns_none(self) -> None:
        """Если kind не строка, возвращается None."""
        options = [{"optionId": "x", "kind": 123}]
        assert resolve_permission_option_kind("x", options) is None

    def test_matching_kind_returned(self) -> None:
        """При совпадении optionId возвращается строковый kind."""
        options = [{"optionId": "allow_once", "kind": "allow_once"}]
        assert resolve_permission_option_kind("allow_once", options) == "allow_once"

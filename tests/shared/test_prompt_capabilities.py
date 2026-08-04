"""Тесты общего VO возможностей промпта (Shared Kernel).

По ACP `image`/`audio`/`embeddedContext` входят в `agentCapabilities.promptCapabilities`:
агент их объявляет, клиент читает. Тип общий, поэтому wire-форма проверяется здесь, а
не на каждой стороне отдельно (tech-debt P2-32 — свод дублей).
"""

from __future__ import annotations

import pytest

from codelab.shared.prompt_capabilities import PromptCapabilities


class TestDefaults:
    """Baseline: без явной поддержки всё выключено."""

    def test_all_disabled_by_default(self) -> None:
        caps = PromptCapabilities()
        assert caps.image is False
        assert caps.audio is False
        assert caps.embedded_context is False
        assert caps.supports_multimodal() is False

    def test_frozen(self) -> None:
        caps = PromptCapabilities()
        with pytest.raises(AttributeError, match="cannot assign to field"):
            caps.image = True  # type: ignore[misc]


class TestFromDict:
    """Разбор ACP-словаря `promptCapabilities`."""

    def test_reads_camel_case_embedded_context(self) -> None:
        """Ключ в wire — camelCase; snake_case здесь не ACP-форма."""
        caps = PromptCapabilities.from_dict({"embeddedContext": True})
        assert caps.embedded_context is True

    def test_snake_case_key_is_not_accepted(self) -> None:
        caps = PromptCapabilities.from_dict({"embedded_context": True})
        assert caps.embedded_context is False

    def test_none_gives_baseline(self) -> None:
        assert PromptCapabilities.from_dict(None) == PromptCapabilities()

    def test_full(self) -> None:
        caps = PromptCapabilities.from_dict(
            {"image": True, "audio": True, "embeddedContext": True}
        )
        assert caps == PromptCapabilities(image=True, audio=True, embedded_context=True)

    def test_ignores_unknown_keys(self) -> None:
        caps = PromptCapabilities.from_dict({"image": True, "video": True})
        assert caps == PromptCapabilities(image=True)


class TestFromAgentCapabilities:
    """Извлечение из `agentCapabilities` ответа `initialize`."""

    def test_extracts_nested_block(self) -> None:
        caps = PromptCapabilities.from_agent_capabilities(
            {"loadSession": True, "promptCapabilities": {"image": True}}
        )
        assert caps.image is True

    def test_missing_block_gives_baseline(self) -> None:
        assert PromptCapabilities.from_agent_capabilities({"loadSession": True}) == (
            PromptCapabilities()
        )

    def test_none_gives_baseline(self) -> None:
        assert PromptCapabilities.from_agent_capabilities(None) == PromptCapabilities()


class TestWireForm:
    """Форма на проводе задана спецификацией ACP, а не удобством сторон."""

    def test_to_dict_keys(self) -> None:
        caps = PromptCapabilities(image=True, audio=False, embedded_context=True)
        assert caps.to_dict() == {
            "image": True,
            "audio": False,
            "embeddedContext": True,
        }

    def test_round_trip_lossless(self) -> None:
        caps = PromptCapabilities(image=True, audio=True, embedded_context=True)
        assert PromptCapabilities.from_dict(caps.to_dict()) == caps


class TestPredicates:
    """Предикаты — то, чем пользуются вызывающие."""

    @pytest.mark.parametrize(
        ("caps", "expected"),
        [
            (PromptCapabilities(image=True), True),
            (PromptCapabilities(audio=True), True),
            (PromptCapabilities(embedded_context=True), True),
            (PromptCapabilities(), False),
        ],
    )
    def test_supports_multimodal(self, caps: PromptCapabilities, expected: bool) -> None:
        assert caps.supports_multimodal() is expected

    def test_individual_predicates(self) -> None:
        caps = PromptCapabilities(image=True, audio=False, embedded_context=True)
        assert caps.supports_image() is True
        assert caps.supports_audio() is False
        assert caps.supports_embedded_context() is True

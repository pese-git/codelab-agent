"""Юнит-тесты ToolLoopDetector (tech-debt #22) — без моков, прямой API."""

from __future__ import annotations

from dataclasses import dataclass

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.loop_detector import (
    ToolLoopDetector,
)


@dataclass
class _Result:
    success: bool
    output: str | None = None
    error: str | None = None


class TestSignature:
    def test_independent_of_arg_order(self) -> None:
        assert ToolLoopDetector.signature(
            "terminal/create", {"command": "fvm", "args": ["analyze"]}
        ) == ToolLoopDetector.signature(
            "terminal/create", {"args": ["analyze"], "command": "fvm"}
        )

    def test_differs_by_args(self) -> None:
        assert ToolLoopDetector.signature("terminal/create", {"command": "fvm"}) != (
            ToolLoopDetector.signature("terminal/create", {"command": "ls"})
        )

    def test_differs_by_tool_name(self) -> None:
        assert ToolLoopDetector.signature("a", {}) != ToolLoopDetector.signature("b", {})

    def test_non_serializable_args_do_not_raise(self) -> None:
        sig = ToolLoopDetector.signature("t", {"x": object()})
        assert isinstance(sig, str)


class TestLoopDetection:
    def test_blocks_after_limit_repeats(self) -> None:
        d = ToolLoopDetector(limit=3)
        args = {"command": "fvm", "args": ["analyze"]}
        assert d.register_attempt("terminal/create", args) is False  # 1
        assert d.register_attempt("terminal/create", args) is False  # 2
        assert d.register_attempt("terminal/create", args) is False  # 3
        assert d.register_attempt("terminal/create", args) is True  # 4 → блок

    def test_interleaving_does_not_reset_count(self) -> None:
        """Чередование create/wait (разные сигнатуры) не мешает детекции create."""
        d = ToolLoopDetector(limit=3)
        create = {"command": "fvm"}
        for i in range(1, 4):
            assert d.register_attempt("terminal/create", create) is False
            assert d.register_attempt("terminal/wait_for_exit", {"terminal_id": f"t{i}"}) is False
        assert d.register_attempt("terminal/create", create) is True

    def test_distinct_args_never_flagged(self) -> None:
        d = ToolLoopDetector(limit=3)
        for i in range(10):
            assert d.register_attempt("terminal/wait_for_exit", {"terminal_id": f"t{i}"}) is False

    def test_zero_limit_disables(self) -> None:
        d = ToolLoopDetector(limit=0)
        assert d.enabled is False
        for _ in range(20):
            assert d.register_attempt("terminal/create", {"command": "fvm"}) is False

    def test_repeat_count_and_last_output(self) -> None:
        d = ToolLoopDetector(limit=2)
        args = {"command": "fvm"}
        d.register_attempt("terminal/create", args)
        d.register_attempt("terminal/create", args)
        d.record_output("terminal/create", args, _Result(success=True, output="создан term_1"))
        assert d.repeat_count("terminal/create", args) == 2
        assert d.last_output("terminal/create", args) == "создан term_1"

    def test_record_output_uses_error_on_failure(self) -> None:
        d = ToolLoopDetector(limit=2)
        args = {"command": "fvm"}
        d.record_output("terminal/create", args, _Result(success=False, error="boom"))
        assert d.last_output("terminal/create", args) == "boom"

    def test_last_output_empty_when_unseen(self) -> None:
        d = ToolLoopDetector(limit=2)
        assert d.last_output("t", {}) == ""
        assert d.repeat_count("t", {}) == 0

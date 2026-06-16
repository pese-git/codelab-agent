"""Тесты CLI entrypoint-ов codelab connect."""

from __future__ import annotations


def test_tui_main_forwards_history_dir(monkeypatch, tmp_path) -> None:
    """codelab connect пробрасывает --history-dir в run_tui_app."""
    from codelab.client.tui import __main__ as tui_main

    captured: dict[str, dict[str, object]] = {}
    history_dir = tmp_path / "history"

    monkeypatch.setattr(
        "codelab.client.tui.__main__.setup_logging",
        lambda **kwargs: captured.setdefault("logging", kwargs),
    )
    monkeypatch.setattr(
        "codelab.client.tui.__main__.run_tui_app",
        lambda **kwargs: captured.setdefault("run", kwargs),
    )
    # __main__.py не использует подкоманды - аргументы передаются напрямую
    monkeypatch.setattr(
        "sys.argv",
        ["codelab-connect", "--history-dir", str(history_dir)],
    )

    tui_main.main()

    assert captured["run"]["history_dir"] == str(history_dir)


# Тест test_cli_forwards_history_dir удалён -
# после рефакторинга CLI находится в codelab.cli, а не codelab.client.cli

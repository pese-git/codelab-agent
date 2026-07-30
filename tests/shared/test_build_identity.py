"""Идентичность сборки пишется в лог при старте сервера.

Мотив практический: на разборе логов 2026-07-30 дважды сделали ложный вывод —
прогон считали проверкой свежей правки, хотя процесс работал с кодом, загруженным
до переустановки. По логу это было неразличимо: ни версии, ни пути.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from codelab.shared.logging import log_build_identity


class TestBuildIdentity:
    def test_logs_version_path_and_python(self) -> None:
        cap = structlog.testing.LogCapture()
        structlog.configure(processors=[cap])

        log_build_identity("stdio")

        assert len(cap.entries) == 1
        entry = cap.entries[0]
        assert entry["event"] == "build_identity"
        assert entry["transport"] == "stdio"
        assert entry["version"]
        assert entry["python"]
        # Путь должен указывать на пакет, из которого реально загружен код:
        # именно он отвечает на вопрос «рабочее дерево или установленная копия»
        assert Path(entry["package_path"]).name == "codelab"
        assert (Path(entry["package_path"]) / "shared" / "logging.py").exists()

    def test_path_matches_imported_module(self) -> None:
        """Путь берётся из загруженного модуля, а не из конфигурации."""
        import codelab

        cap = structlog.testing.LogCapture()
        structlog.configure(processors=[cap])

        log_build_identity("websocket")

        expected = Path(codelab.__file__).resolve().parent
        assert Path(cap.entries[0]["package_path"]) == expected

#!/usr/bin/env python3
"""Guardrail: не допускать появления новых God Objects.

Падает, если какой-либо .py файл в src/ превышает MAX_LINES строк и при этом
не входит в ALLOWLIST существующих крупных файлов. Задача — остановить рост
числа файлов > 1000 строк (см. doc/internals/tech-debt.md, P1-4), не требуя
немедленного рефакторинга уже существующих.

Файлы из ALLOWLIST по мере разбиения нужно из него удалять — тогда guardrail
не даст им снова разрастись.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 1000

# Существующие крупные файлы (baseline на 2026-07-10). Разбили файл —
# удали его отсюда, чтобы зафиксировать результат.
ALLOWLIST = {
    "src/codelab/server/mcp/transport.py",
    "src/codelab/server/protocol/handlers/prompt.py",
    "src/codelab/client/infrastructure/services/acp_transport_service.py",
    "src/codelab/server/di.py",
    "src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py",
    "src/codelab/client/messages.py",
    "src/codelab/client/tui/app.py",
    "src/codelab/client/presentation/chat_view_model.py",
    "src/codelab/server/mcp/manager.py",
    "src/codelab/server/mcp/client.py",
}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    violations: list[tuple[str, int]] = []

    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        lines = sum(1 for _ in path.open(encoding="utf-8"))
        if lines > MAX_LINES and rel not in ALLOWLIST:
            violations.append((rel, lines))

    if violations:
        print(f"❌ Новые файлы > {MAX_LINES} строк (разбейте или обоснуйте в ALLOWLIST):")
        for rel, lines in violations:
            print(f"   {lines:>5}  {rel}")
        return 1

    print(f"✅ Нет новых файлов > {MAX_LINES} строк ({len(ALLOWLIST)} в allowlist).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

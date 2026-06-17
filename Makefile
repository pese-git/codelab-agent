.PHONY: sync check check-client check-server check-tui lint typecheck test \
	serve connect

HOST ?= 127.0.0.1
PORT ?= 8765

# === Основные команды ===

sync:
	uv sync --extra dev

check: lint typecheck test

lint:
	uv run ruff check .

typecheck:
	uv run ty check

test:
	uv run python -m pytest

# === Частичные проверки ===

check-client:
	uv run python -m pytest tests/client/

check-server:
	uv run python -m pytest tests/server/

check-tui:
	uv run ruff check src/codelab/client/tui tests/client/test_tui_*.py
	uv run python -m pytest tests/client/test_tui_*.py

# === Запуск ===

serve:
	uv run codelab serve --host $(HOST) --port $(PORT)

connect:
	uv run codelab connect --host $(HOST) --port $(PORT)

# === Deprecated (для обратной совместимости, будут удалены) ===

server-sync:
	@echo "DEPRECATED: use 'make sync' instead"
	uv sync --extra dev

server-check:
	@echo "DEPRECATED: use 'make check-server' instead"
	uv run python -m pytest tests/server/

client-sync:
	@echo "DEPRECATED: use 'make sync' instead"
	uv sync --extra dev

client-check:
	@echo "DEPRECATED: use 'make check-client' instead"
	uv run python -m pytest tests/client/

run-server-ws:
	@echo "DEPRECATED: use 'make serve' instead"
	uv run codelab serve --host $(HOST) --port $(PORT)

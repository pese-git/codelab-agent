# Технический долг CodeLab Agent

> Дата аудита: 2026-06-16
> Ветка: `feature/agent`
> Коммит: `f03df77`

---

## Сводка

| Метрика | Значение | Цель |
|---------|----------|------|
| Покрытие тестами | 77% | >= 85% |
| Cyclomatic complexity (max) | 30 | <= 10 |
| Файлов > 1000 строк | 6 | 0 |
| Warnings в тестах | 62 | 0 |
| Нерешенных TODO | 2 | 0 |
| Тестов | 3974 | — |

---

## P0 — Критический (влияет на надежность)

### 1. Покрытие тестами: `stdio_runner.py` — 0%

**Файл:** `src/codelab/server/transport/stdio_runner.py` (209 строк)

Модуль не покрыт тестами вообще. Отвечает за запуск stdio-транспорта — критический путь.

**Задачи:**
- [ ] Написать unit-тесты на инициализацию runner
- [ ] Написать тесты на обработку stdin/stdout lifecycle
- [ ] Написать тесты на graceful shutdown
- [ ] Написать интеграционный тест с mock transport

**Оценка:** 1 день
**Критерий приемки:** покрытие модуля >= 90%

---

### 2. Рефакторинг `request_with_callbacks` — сложность 30

**Файл:** `src/codelab/client/infrastructure/services/acp_transport_service.py:506`

Функция имеет цикломатическую сложность 30 при пороге 10. Содержит множество ветвлений обработки callback'ов, notification и client-rpc.

**Задачи:**
- [ ] Выделить обработку notification в отдельный метод `_handle_notification`
- [ ] Выделить обработку client-rpc в отдельный метод `_handle_client_rpc`
- [ ] Выделить обработку response в отдельный метод `_handle_response`
- [ ] Извлечь валидацию в отдельный метод `_validate_request`
- [ ] Упростить основной метод до делегирования подметодам

**Оценка:** 1 день
**Критерий приемки:** сложность <= 10, все существующие тесты проходят

---

### 3. Исправление warnings в тестах (62 warnings)

#### 3a. RuntimeWarning: coroutine was never awaited (40+ случаев)

AsyncMock возвращает корутины, которые не awaited в коде. Проблема в тестах, где мокируются async-методы.

**Задачи:**
- [ ] Пройтись по всем тестам с `AsyncMock` и добавить `await` или использовать `return_value` вместо `side_effect`
- [ ] Проверить `use_cases.py:209,215` — `is_initialized()`, `is_connected()`
- [ ] Проверить `mcp/client.py:274,283` — `register_notification_handler`, `register_request_handler`
- [ ] Проверить `mcp/manager.py:445-459` — `register_handler`, `register_progress_callback`
- [ ] Проверить `protocol/core.py:1809,1827,1954` — `mcp_prompt_handlers`

**Оценка:** 0.5 дня

#### 3b. PytestWarning: incorrect `@pytest.mark.asyncio` (6 тестов)

**Файл:** `tests/client/test_session_coordinator_permissions.py`

Тесты помечены `@pytest.mark.asyncio`, но являются sync-функциями.

**Задачи:**
- [ ] Удалить `@pytest.mark.asyncio` из 6 тестов:
  - `test_resolve_permission_without_handler`
  - `test_resolve_permission_not_found`
  - `test_resolve_permission_error`
  - `test_cancel_permission_without_handler`
  - `test_cancel_permission_not_found`
  - `test_cancel_permission_error`

**Оценка:** 10 минут

#### 3c. PytestUnraisableExceptionWarning: event loop closed

**Файл:** `tests/client/test_terminal_executor.py`

Subprocess transport закрывается после закрытия event loop.

**Задачи:**
- [ ] Добавить корректный teardown subprocess в fixture
- [ ] Использовать `async with` или явный `await transport.close()` перед закрытием loop

**Оценка:** 0.5 дня

---

## P1 — Важный (влияет на поддерживаемость)

### 4. Разбить God Objects

| Файл | Строк | План разбиения |
|------|-------|----------------|
| `server/protocol/core.py` | 2030 | Выделить session management, message routing, middleware pipeline в отдельные модули |
| `server/mcp/transport.py` | 1799 | Выделить HTTP transport, SSE transport, transport factory |
| `server/protocol/handlers/prompt.py` | 1495 | Выделить prompt builder, prompt validator, directive processor |
| `client/infrastructure/services/acp_transport_service.py` | 1294 | Уже частично покрыт P0-2, выделить request/response handling |
| `client/presentation/chat_view_model.py` | 1229 | Выделить streaming handler, session update handler, tool call handler |
| `client/tui/app.py` | 1126 | Выделить keybindings, layout management, modal handling |

**Задачи:**
- [ ] `core.py` — выделить `session_manager.py`, `message_router.py`, `middleware_pipeline.py`
- [ ] `transport.py` — выделить `http_transport.py`, `sse_transport.py`, `transport_factory.py`
- [ ] `prompt.py` — выделить `prompt_builder.py`, `prompt_validator.py`, `directive_processor.py`
- [ ] `acp_transport_service.py` — завершить после P0-2
- [ ] `chat_view_model.py` — выделить `streaming_handler.py`, `session_update_handler.py`
- [ ] `app.py` — выделить `keybindings.py`, `layout.py`, `modals.py`

**Оценка:** 5 дней (по 1 дню на файл)
**Критерий приемки:** ни один файл < 500 строк, все тесты проходят, нет нарушения зависимостей между слоями

---

### 5. Обновить `textual` 0.43 → 8.x (мажорное обновление)

Текущая версия `textual==0.43.2`, последняя — `8.2.7`. Разница ~2 года.

**Задачи:**
- [ ] Изучить CHANGELOG textual на breaking changes
- [ ] Обновить `pyproject.toml`
- [ ] Исправить deprecated API в TUI компонентах
- [ ] Проверить все `DirectoryTree.watch_path` warnings (связаны с textual)
- [ ] Прогнать все TUI-тесты
- [ ] Ручное тестирование TUI

**Оценка:** 3 дня
**Риск:** высокое количество breaking changes, может потребоваться рефакторинг TUI-компонентов

---

### 6. Покрыть тестами transport layer

| Модуль | Покрытие | Строк без покрытия |
|--------|----------|--------------------|
| `server/transport/stdio.py` | 64% | 70 строк |
| `server/transport/websocket.py` | 71% | 64 строки |
| `server/web_app.py` | 42% | 14 строк |

**Задачи:**
- [ ] `stdio.py` — тесты на connection lifecycle, error handling, reconnection
- [ ] `websocket.py` — тесты на handshake, message framing, close handshake
- [ ] `web_app.py` — тесты на startup/shutdown, middleware chain

**Оценка:** 2 дня
**Критерий приемки:** покрытие transport layer >= 80%

---

### 7. Обновить зависимости (минорные/патч)

| Пакет | Текущая | Доступная | Тип |
|-------|---------|-----------|-----|
| `openai` | 2.8.1 | 2.41.1 | minor |
| `pydantic` | 2.4.2 | 2.13.4 | minor |
| `pydantic-settings` | 2.0.3 | 2.11.0 | minor |
| `aiohttp` | 3.12.15 | 3.13.5 | patch |
| `python-dotenv` | 1.0.0 | 1.2.1 | patch |

**Задачи:**
- [ ] Обновить `pyproject.toml`
- [ ] Запустить `uv lock --upgrade`
- [ ] Прогнать `make check`
- [ ] Исправить breaking changes в `pydantic` (если есть)

**Оценка:** 1 день

---

## P2 — Желательный (улучшение качества)

### 8. Устранить TODO

| Файл | Строка | Описание |
|------|--------|----------|
| `client/tui/components/terminal_panel.py` | 421 | Реализовать копирование через pyperclip |
| `server/llm/fallback/orchestrator.py` | 145 | Реализовать buffering и переключение |

**Задачи:**
- [ ] Реализовать копирование в буфер обмена в terminal_panel
- [ ] Реализовать buffering в fallback orchestrator
- [ ] Либо удалить TODO, если задача неактуальна

**Оценка:** 1 день

---

### 9. Исправить ruff warnings

| Правило | Количество | Описание |
|---------|-----------|----------|
| D212 | ~100 | Multi-line docstring summary at first line |
| TC005 | 1 | Empty TYPE_CHECKING block in `cli.py:27` |
| FBT001/FBT002 | ~20 | Boolean arguments in functions |
| RUF001/RUF002/RUF003 | ~50 | Ambiguous cyrillic characters |

**Задачи:**
- [ ] Удалить пустой `TYPE_CHECKING` блок в `cli.py:27`
- [ ] Настроить ruff: добавить `D212` в ignore или исправить все docstrings
- [ ] Решить: игнорировать RUF001-003 (кириллица в комментариях допустима по AGENTS.md) или добавить в ignore
- [ ] FBT001/FBT002 — оценить, стоит ли переводить boolean args в kwargs

**Оценка:** 0.5 дня

---

### 10. Добавить coverage threshold в CI

**Задачи:**
- [ ] Добавить `pytest-cov` в dev-зависимости
- [ ] Настроить `.coveragerc` или `pyproject.toml` с `fail_under = 80`
- [ ] Добавить stage в GitHub Actions: `pytest --cov=src/codelab --cov-fail-under=80`
- [ ] Добавить badge покрытия в README

**Оценка:** 0.5 дня

---

## Дорожная карта

```
Неделя 1: P0 (пункты 1-3)
  ├─ День 1: stdio_runner тесты + request_with_callbacks рефакторинг
  ├─ День 2: warnings (AsyncMock + asyncio marks + event loop)
  └─ День 3: буфер на непредвиденное

Неделя 2: P1 часть 1 (пункты 4-5)
  ├─ День 4: разбить core.py (2030 строк)
  ├─ День 5: разбить transport.py (1799 строк)
  └─ День 6-7: обновление textual

Неделя 3: P1 часть 2 (пункты 6-7)
  ├─ День 8: transport layer тесты
  ├─ День 9: обновление зависимостей
  └─ День 10: буфер

Неделя 4: P2 (пункты 8-10)
  ├─ День 11: TODO
  ├─ День 12: ruff warnings
  └─ День 13: CI coverage threshold
```

---

## Метрики успеха

После полного устранения долга:

| Метрика | Было | Станет |
|---------|------|--------|
| Покрытие тестами | 77% | >= 85% |
| Max cyclomatic complexity | 30 | <= 10 |
| Файлов > 1000 строк | 6 | 0 |
| Warnings в тестах | 62 | 0 |
| TODO | 2 | 0 |
| Coverage threshold в CI | нет | 80% |

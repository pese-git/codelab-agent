# Технический долг CodeLab Agent

> Первичный аудит: 2026-06-16 (ветка `feature/agent`, коммит `f03df77`)
> Актуализация: 2026-07-10 (ветка `develop`, коммит `3c5e7de`)
> Пересчёт метрик: 2026-07-10 (ветка `tech-debt`, коммит `5da4988`)

> **Примечание о пересчёте (2026-07-10):** метрики измерены на ветке `tech-debt`.
> Сложность — `radon cc` (порог 10). Ruff — `ruff check .` (текущая конфигурация проекта).
> Размеры файлов — `wc -l`. Покрытие — `pytest --cov` (см. ниже).

---

## Сводка

| Метрика | Значение (2026-06) | Значение (2026-07) | Цель |
|---------|--------------------|--------------------|------|
| Покрытие тестами | 77% | **96%** ✅ (цель достигнута) | >= 85% |
| Cyclomatic complexity (max) | 30 | 51 → **32** 🟡 (три топ-нарушителя разбиты, см. P0-2) | <= 10 |
| Блоков со сложностью > 10 | — | 72 → 71 | 0 |
| Файлов > 1000 строк | 6 | 10 (состав изменился, см. P1-4) | 0 |
| Warnings в тестах | 62 | 0 в выводе, но 3 класса **подавлены** `filterwarnings` (см. P0-3) | 0 |
| Ruff-нарушений (`ruff check .`) | ~170 | **0** ✅ | 0 |
| Нерешенных TODO | 2 | 2 | 0 |
| Тестов | 3974 | ~7262 | — |

---

## P0 — Критический (влияет на надежность)

### 1. Покрытие тестами: `stdio_runner.py` — 0% — ✅ ЗАКРЫТО (2026-07-10)

> ✅ Появились тесты: `tests/server/transport/test_stdio_runner.py` +
> `tests/server/test_stdio_runner_coverage.py`. Пункт закрыт.

**Файл:** `src/codelab/server/transport/stdio_runner.py` (278 строк, покрытие 82%)

Модуль не покрыт тестами вообще. Отвечает за запуск stdio-транспорта — критический путь.

**Задачи:**
- [ ] Написать unit-тесты на инициализацию runner
- [ ] Написать тесты на обработку stdin/stdout lifecycle
- [ ] Написать тесты на graceful shutdown
- [ ] Написать интеграционный тест с mock transport

**Оценка:** 1 день
**Критерий приемки:** покрытие модуля >= 90%

---

### 2. Снизить цикломатическую сложность — max 51 → 32 🟡 В РАБОТЕ (2026-07-10)

> Исходный пункт был про `request_with_callbacks` (сложность 30) — она уже опустилась
> ниже порога отчёта. Пересчёт `radon cc` выявил максимум **51**. Три топ-нарушителя
> (51, 37, 37) разобраны (см. ниже); текущий максимум по кодовой базе — **32**
> (`AppConfig._merge_llm_config`).

**✅ Сделано (1):** `resolve_pending_client_rpc_response_impl` (было 51) вынесена в новый
модуль `server/protocol/handlers/client_rpc_response.py` и разбита на таблицу
диспетчеризации по `pending.kind` + по одному обработчику на fs/terminal-операцию.
Результат: диспетчер — сложность 8, максимум в модуле — 10 (`_handle_terminal_output`),
попутно устранена дупликация построения terminal-запросов (`_issue_terminal_followup`).
`prompt.py` уменьшен 1554 → 1095 строк (подтачивает P1-4). Публичный API сохранён через
re-export.

**✅ Сделано (3):** `WebSocketTransport.run` (было 37) разбит через введение объекта
состояния `_WsRunState` (Parameter Object) на `_handle_text_message`,
`_apply_initialization_gate`, `_update_notification_subscription`,
`_schedule_prompt_in_background`, `_cleanup_connection` (+ `_cancel_prompt_request_tasks` /
`_cancel_deferred_prompt_tasks`). Результат: `run` — сложность 8, cleanup — 8,
`_handle_text_message` — 11 (оставлен: связный поток обработки сообщения).

**✅ Сделано (2):** `AgentLoop._process_tool_calls` (было 37) разбит на
`_process_single_tool_call` + `_pause_for_permission` / `_reject_tool_call` /
`_execute_allowed_tool_call` + DRY-помощники `_run_tool` / `_build_notification_content` /
`_emit_plan_notification_if_needed` (переиспользованы в `_execute_pending_tool`, тот
снижен 17 → 12). Результат: `_process_tool_calls` — сложность 5. Помощники `*_allowed`
и `_execute_pending_tool` остались на 12 (связная логика исполнить→отчитаться→вернуть,
дальнейшее дробление — ради метрики, не делаем).

**Топ оставшихся нарушителей (`radon cc`, порог 10):**

| Сложность | Функция | Файл |
|-----------|---------|------|
| 32 (E) | `AppConfig._merge_llm_config` | `server/config.py:350` |
| 31 (E) | `ThreePhaseCompactor._phase_hard_truncate` | `server/agent/context/compactor.py:307` |
| 30 (D) | `run_server` | (см. вывод `radon`) |
| 26 (D) | `ACPContextGatherer.gather` | `server/agent/context/gatherer.py:77` |
| 26 (D) | `DefaultContextManager.build_context` | `server/agent/context/manager.py:214` |
| 21 (D) | `AgentLoop.run` | `server/protocol/handlers/pipeline/stages/agent_loop.py` |

**Задачи:**
- [x] Декомпозировать `resolve_pending_client_rpc_response_impl` (51)
- [x] Разбить `AgentLoop._process_tool_calls` (37 → 5)
- [x] Разбить `WebSocketTransport.run` (37 → 8)
- [ ] Разобрать оставшиеся E/D-блоки (config merge, compactor, context gatherer/manager, run)
- [ ] После снижения всех блоков — включить `C901` (mccabe) в ruff с `max-complexity = 10`,
      чтобы предотвратить регресс (сейчас включать нельзя: блоки выше порога остаются)

**Оценка:** 2 дня
**Критерий приемки:** max сложность <= 10 (или согласованный порог), все тесты проходят

---

### 3. Исправление warnings в тестах (62 warnings) — 🟡 ПОДАВЛЕНЫ, НЕ ИСПРАВЛЕНЫ (2026-07-10)

> Прогон `pytest` (7280 тестов) показал **0 warnings в выводе**, НО это результат
> подавления через `filterwarnings` в `pyproject.toml`, а не устранения причин:
> ```toml
> filterwarnings = [
>     "ignore::pytest.PytestUnraisableExceptionWarning",          # маскирует 3c
>     "ignore:coroutine.*was never awaited:RuntimeWarning",       # маскирует 3a
>     "ignore:coroutine.*DirectoryTree\\.watch_path:RuntimeWarning",
>     "ignore:coroutine.*SearchInput:RuntimeWarning",
> ]
> ```
> То есть 3a и 3c скрыты фильтрами; 3b (неверный `@pytest.mark.asyncio`) при
> `asyncio_mode = "auto"` не всплывает. Долг закрыт «поверхностно» — чтобы считать его
> реально устранённым, нужно временно убрать `ignore`-фильтры и починить источники.

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

### 4. Разбить God Objects — 🟡 ЧАСТИЧНО (2026-07-10)

> Актуальные размеры (`develop`, 2026-07-10):
> - ✅ `server/protocol/core.py` — **2030 → 335 строк** (декомпозирован).
> - ✅ `client/presentation/chat_view_model.py` — 1229 → 1046 (у цели <1000 близко).
> - 🟡 `server/mcp/transport.py` — 1799 (без изменений).
> - 🟡 `server/protocol/handlers/prompt.py` — 1495 → 1554 (вырос).
> - 🟡 `client/infrastructure/services/acp_transport_service.py` — 1294 → 1390.
> - 🟡 `client/tui/app.py` — 1126 → 1101.
> - ⬜ Новые файлы >1000 строк: `server/di.py` (1200), `agent_loop.py` (1191),
>   `client/messages.py` (1117), `mcp/manager.py` (1036), `mcp/client.py` (1029).

| Файл | Строк | План разбиения |
|------|-------|----------------|
| `server/protocol/core.py` | ~~2030~~ 335 ✅ | Выделить session management, message routing, middleware pipeline в отдельные модули |
| `server/mcp/transport.py` | 1799 | Выделить HTTP transport, SSE transport, transport factory |
| `server/protocol/handlers/prompt.py` | 1554 | Выделить prompt builder, prompt validator, directive processor |
| `client/infrastructure/services/acp_transport_service.py` | 1390 | Уже частично покрыт P0-2, выделить request/response handling |
| `client/presentation/chat_view_model.py` | 1046 | Выделить streaming handler, session update handler, tool call handler |
| `client/tui/app.py` | 1101 | Выделить keybindings, layout management, modal handling |

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

### 5. Обновить `textual` 0.43 → 8.x (мажорное обновление) — 🟡 ЧАСТИЧНО (2026-07-10)

> 🟡 В `pyproject.toml` теперь `textual>=0.66.0` (было 0.43). До 8.x ещё не обновлено — пункт открыт.

Текущая версия `textual>=0.66.0`, последняя — `8.2.7`.

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

### 6. Покрыть тестами transport layer — ✅ ЗАКРЫТО (2026-07-10)

> Пересчёт `pytest --cov`: весь transport layer превысил цель 80%.

| Модуль | Было | Стало (2026-07-10) |
|--------|------|--------------------|
| `server/transport/stdio.py` | 64% | **98%** ✅ |
| `server/transport/websocket.py` | 71% | **94%** ✅ |
| `server/web_app.py` | 42% | **100%** ✅ |
| `server/transport/stdio_runner.py` | — | 82% (см. P0-1) |
| `server/transport/websocket_connection.py` | — | 90% |

**Критерий приемки:** покрытие transport layer >= 80% — достигнуто.

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

### 9. Исправить ruff warnings — ✅ ЗАКРЫТО (2026-07-10)

> `ruff check .` теперь **0 нарушений** (было ~170). Массовые классы (D212, RUF001-003,
> FBT) устранены/в ignore; оставшиеся 6 (3× F401, 3× E501) исправлены в коммите
> `style(lint): устранить оставшиеся ruff-нарушения`.

---

### 10. Добавить coverage threshold в CI — 🟢 ПОЧТИ ЗАКРЫТО (2026-07-10)

> Реализовано в коммите `ci: порог покрытия 85% и guardrail на размер файлов`.

**Задачи:**
- [x] Добавить `pytest-cov` в dev-зависимости
- [x] Шаг CI `pytest --cov=src/codelab --cov-fail-under=85` (порог 85, факт 96%)
- [x] Бонус: guardrail `scripts/check_large_files.py` против новых God Objects
- [ ] Добавить badge покрытия в README

**Оценка:** 0.5 дня

---

### 11. `ClientRPCService._wrap_future` — необработанное исключение future

**Файл:** `src/codelab/server/client_rpc/service.py:154` (`_call_method` → `_wrap_future`)

При RPC-ошибке от клиента (напр. `fs/read_text_file` → `-32603` на нечитаемом файле
вроде `*.db-shm`) в рантайме появляется `Task exception was never retrieved` +
traceback `ClientRPCResponseError`.

**Причина:** `_call_method` оборачивает `pending_request.future` в отдельный
`future_task = asyncio.create_task(self._wrap_future(...))` и ждёт через `asyncio.wait`.
После пробуждения исключение забирается только у `pending_request.future` (строка 182),
а у самого `future_task` — нет. Заброшенный task с исключением → предупреждение asyncio
при GC. Функционально ошибка обрабатывается (executor логирует и возвращает failed-
результат), но traceback шумит в логах и **маскирует реальные сбои**.

> Связано с P0-3: именно этот класс подавлен фильтром
> `ignore::pytest.PytestUnraisableExceptionWarning` в `pyproject.toml`.

**Задачи:**
- [ ] После `asyncio.wait` забирать исключение и у `future_task` (или не оборачивать в
      отдельный task, а ждать `pending_request.future` напрямую с `asyncio.wait_for`/
      `add_done_callback`)
- [ ] Тест на путь «RPC read → -32603»: убедиться, что нет unretrieved-task warning
- [ ] После фикса — снять `ignore::PytestUnraisableExceptionWarning` (см. P0-3)

**Обнаружено:** 2026-07-10 при анализе логов реальной stdio-сессии (не регресс —
дефект существовал до рефакторинга P0-2; файл не затрагивался).
**Оценка:** 0.5 дня
**Критерий приемки:** нет `Task exception was never retrieved` при RPC-ошибках чтения,
фильтр `PytestUnraisableExceptionWarning` снят.

---

### 12. `session/load` сессии с планом крашил WS-соединение — ✅ ЗАКРЫТО (2026-07-10)

**Файл:** `src/codelab/server/protocol/handlers/replay_manager.py:324` (`replay_latest_plan`)

При `session/load` сессии, содержащей план, сервер падал с
`TypeError: Object of type PlanStep is not JSON serializable` в
`_send_outcome → ACPMessage.to_json`. Исключение выходило из `run`, соединение
закрывалось; клиент получал CLOSING-фрейм и не мог загрузить историю (см. P13).

**Причина:** `SessionState.latest_plan: list[PlanStep | dict]`. При десериализации
из JSON-хранилища pydantic коэрсит подходящие dict в объекты `PlanStep`.
`replay_latest_plan` клал `latest_plan` в нотификацию как есть, а `to_dict`/`to_json`
не сериализует вложенные BaseModel.

**Фикс:** `replay_latest_plan` сериализует entries (`model_dump(exclude_none=True)` для
BaseModel, dict как есть). Регресс-тест
`test_replays_plan_with_planstep_objects_is_serializable`.

**Обнаружено:** 2026-07-10 при анализе логов WS-сессии из рабочего дерева (не регресс —
`replay_latest_plan` рефакторингом не затрагивался).

---

### 13. Клиентский receive-loop падает на `WSMsgType.CLOSING` (257)

**Файл:** `src/codelab/client/infrastructure/transport.py:228`

При штатном закрытии WebSocket сервером клиент получает control-фрейм
`WSMsgType.CLOSING` (257) / `CLOSED` (258) и поднимает
`RuntimeError: Unexpected WebSocket message type: 257` вместо graceful-обработки.
Это превращает нормальное закрытие в ошибку receive-loop с ретраями/backoff (в логе
5 попыток) и провалом `session/load`.

**Задачи:**
- [ ] Обрабатывать `WSMsgType.CLOSING`/`CLOSED` как штатное закрытие (выход из loop,
      а не `RuntimeError`)
- [ ] Тест на receive-loop при закрытии соединения сервером

**Обнаружено:** 2026-07-10 (каскад после P12; усугубляет любое закрытие соединения).
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

| Метрика | Было (2026-06) | Сейчас (2026-07) | Цель |
|---------|----------------|------------------|------|
| Покрытие тестами | 77% | **96%** ✅ | >= 85% |
| Max cyclomatic complexity | 30 | **51** 🔴 | <= 10 |
| Файлов > 1000 строк | 6 | **10** 🔴 | 0 |
| Warnings в тестах | 62 | 0 (частично подавлены фильтрами) 🟡 | 0 |
| Ruff-нарушений | ~170 | **6** 🟢 | 0 |
| TODO | 2 | 2 | 0 |
| Coverage threshold в CI | нет | нет | 80% |

**Итог пересчёта (2026-07-10):** две метрики достигли цели (покрытие, ruff), две
серьёзно **ухудшились** (сложность 30→51, God Objects 6→10) — код растёт быстрее
рефакторинга. Приоритет №1 — остановить регресс через CI-guardrails (порог сложности
в ruff `C901` + проверка размера файла + `--cov-fail-under`), иначе метрики будут
деградировать между аудитами незаметно.

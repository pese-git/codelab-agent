# Технический долг CodeLab Agent

> Первичный аудит: 2026-06-16 (ветка `feature/agent`, коммит `f03df77`)
> Актуализация: 2026-07-21 (P2-27: terminal alias race condition, обнаружено в логах `sess_bdd7f44c5734`)
> Актуализация: 2026-07-10 (ветка `develop`, коммит `3c5e7de`)
> Пересчёт метрик: 2026-07-10 (ветка `tech-debt`, коммит `5da4988`)
> Обновление зависимостей: 2026-07-10 (ветка `tech-debt`, коммит `2a8594d`)
> P1-4 (`di.py`, `chat_view_model.py`, `app.py`, `mcp/transport.py`) + P0-14/P2-15/P2-16/P2-17: 2026-07-13 (ветка `tech-debt`)
> P1-4 (`acp_transport_service.py` 1405→579: пакет `acp_transport/` — dispatcher/handlers/PermissionResponder/RequestCallbackCoordinator) + P2-18/P2-19: 2026-07-13 (ветка `tech-debt`)
> P1-4 (`handlers/prompt.py` 1095→пакет `prompt/` — normalization/validation/directives/tool_calls/client_requests/permission_response): 2026-07-14 (ветка `tech-debt`)
> P1-4 (`context/gatherer.py` 1048→617 — path-matching хелперы вынесены в `context/file_matching.py`): 2026-07-14 (ветка `tech-debt`)
> P1-4 (`pipeline/stages/agent_loop.py` 1352→пакет `agent_loop/` — loop/llm_caller/tool_processor/updates, все <750): 2026-07-14 (ветка `tech-debt`). Файлов >1000 строк: **1** (только оправданно крупный `messages.py`).
> P0-14 (гейт `ty` восстановлен: 4 ошибки типов устранены в treesitter/registry/di.agent/notification_bus, `make check` зелёный): 2026-07-15 (ветка `tech-debt`).
> Анализ логов живых прогонов (2026-07-29, ветка `ref/ADR-003-acp-independent-agent-core`): добавлен P2-38 (батч tool_calls: ответ модели только на первый вызов; отмена turn'а оставляет вызовы без ответа), добавлены P2-36 (отказ policy не сообщает модели причину → каскад фантомных терминалов, **закрыт в тот же день**) и P2-37 (ошибки модели и штатные отмены на уровне `error`, **закрыт в тот же день**).
> Анализ логов живых прогонов (2026-07-30, ветка `ref/ADR-003-acp-independent-agent-core`): добавлен **P0-39** (`session/cancel` не останавливает turn — носитель флага `active_turn` уничтожается раньше, чем цикл успевает его прочитать; turn продолжался 52 с после отмены, 8 запросов разрешения). Приоритет выше фазы D ADR-006.
> Разведка перед транзакцией `session/load` (2026-07-30): добавлен **P2-42** — `session/load` загружает сессию дважды за запрос и не сохраняет ничего, поэтому теряет `cwd`, отмену вызовов и ответы модели (измерено на диске). Обесценивает ветку обрыва turn'а из P2-40.
> Анализ логов (2026-07-30): добавлен **P2-44** — реестр терминалов переживает перезапуск, а сами терминалы нет: три ошибки `RPC Error -32603` по терминалу из прошлого процесса.
> Разведка по ADR-007 (2026-07-30): добавлен **P2-43** — две точки входа разошлись, `server/cli.py` недостижим и несёт 20 своих флагов. Инвентаризация показала, что реальная потеря возможностей короткая (`--storage`, `--observability-debug`, два таймаута), остальное дублирует переменные окружения. Решено пока только зафиксировать: приоритет у надёжности перед хостингом.
> Анализ логов живых прогонов (2026-07-31, ветка `ref/ADR-003-acp-independent-agent-core`): добавлен и **закрыт в тот же день** **P1-45** — слияние при конфликте ревизий дублирует хвост истории (шесть записей-дублей, пять `tool_call_id` с двумя ответами `role: tool`); причина — союз типов `HistoryMessage | dict` ломает сравнение по общему префиксу, воспроизведено детерминированно.
> Анализ логов живых прогонов (2026-07-31): добавлен **P2-46** — `active_turn` не очищается по завершении turn'а, поэтому «orphaned permission request» появляется при каждом перезапуске; покадровый снимок показал, что состояние устойчивое, а не транзиентное (обе гипотезы наконец различены).
> Анализ логов живых прогонов (2026-07-31): добавлены **P2-47** (80 строк лога идут мимо structlog — без уровня и времени, поэтому критерий «ноль ошибок» их не видит; 22 модуля на stdlib logging) и **P2-48** (сервер спавнится дважды, второй процесс не обслуживает ни одного запроса).
> Транзакция 6 фазы D (2026-07-31): добавлен и **закрыт в тот же день** **P1-49** — решение по permission-request применялось к копии, которую никто не сохранял (замерено на файловом backend'е: политика `allow_always` терялась, снятые идентификаторы возвращались с диска). Этим же закрыт **P2-46**: его причина — именно P1-49, а не правило слияния.
> Анализ логов после транзакции 6 (2026-07-31): добавлен и **закрыт в тот же день** **P2-50** — отменённый пользователем `terminal/wait_for_exit` попадает на диск как `failed`, а модели уходит результат с признаком ошибки (уровень лога уже понижен ранее, осталась семантика статуса и текста).
> Повторный разбор логов (2026-07-31): добавлен **P2-51** — классификация задачи делает отдельный LLM-вызов на каждый промпт (2.1–5.4 с, ≈23 с на шесть промптов), на коротких продолжениях результат вырожден (`target_modules=0`), а глубина исследования на одинаковом вводе скачет 1/2/3.
> Транзакция 7 фазы D (2026-07-31): добавлен **P2-52** — поиск сессии по вторичному ключу делает полный скан хранилища (90 мс на 30 сессиях) на каждый ответ клиента; порядок проверок в роутере уже переставлен так, что живой путь через `ClientRPCService` за скан не платит, permission-ответы — остаются.
> Живой прогон транзакции 7 (2026-07-31): добавлен и **закрыт в тот же день** **P2-55** — после ответа клиента на `fs/read_text_file` статус вызова на диске остаётся `pending`, хотя клиенту ушёл `completed`: матрица запрещает `pending → completed`, домен отказывает, а нотификация строится независимо от исхода перехода. Предсуществующий (тот же прогон на `b297d10b` даёт то же предупреждение). Этим же прогоном **подтверждена живьём транзакция 7**: до неё ответ клиента не сохранялся вовсе — ревизия не менялась, `active_turn` с живым `pending_client_request` оставался на диске навсегда.
> Анализ логов и инспекция процессов (2026-07-31, вечер): добавлены **P2-53** (подпроцессы Web UI не умирают вместе с сервером: 437 осиротевших процессов с `ppid=1`, 5.5 ГБ RSS, старшему сутки; спавн стоит раньше `bind`, а `finally` с остановкой — после него) и **P2-54** (`active_turn.phase` никто не возвращает в `running`, пять мест в трёх модулях пишут фазу напрямую, а валидирующий `set_turn_phase` не имеет вызывающих; остаток P2-46 выделен из закрытого пункта). Подтверждены на новом прогоне **P2-47** (43 строки из 735 мимо structlog, добавился канал retry-логов openai) и **P2-48** (двойной спавн воспроизведён дважды подряд, расхождение метки 14-16 мкс).
> Разбор накопленных логов после закрытия фазы D ADR-006 (2026-08-04, ветка `ref/ADR-003-acp-independent-agent-core`, коммит `03e72d08`): заведены **P1-56** (гейт разрешений живёт у вызывающего, а не у реестра инструментов: Context Manager исполняет `fs/read_text_file` и `terminal/create` с `requires_permission=True` молча), **P2-57** (Context Manager не окупается: 161–239 чтений на 7–20 файлов, обрыв ответа классификатора подменяет `task_type`) и **P2-58** (мёртвые алиасы терминалов после рестарта дают гарантированно провальные вызовы; 11 `terminal/create` и 0 `terminal/release` за прогон). Обновлены **P2-53** (динамика за сутки 110 → 349 процессов, 4.8 ГБ), **P2-47**, **P2-51**, **P2-54**.
> Разбор живых прогонов через Zed (2026-08-04): добавлен и **закрыт в тот же день** **P2-59** — stdio-сервер не завершался по `SIGTERM`: обработчик выставлял флаг, который цикл, припаркованный в чтении stdin, никогда не проверял; агент на 270 МБ переживал уход клиента (замерено на живом процессе с `ppid=1`, 17 минут, `lsof`: pipe без писателей). Этим же снята и причина накопления по **P2-48**: близнеца теперь снимает сигнал, а не только принудительное добивание клиентом. Направление P2-48 исправлено покадровым измерением: оба процесса — дети Zed, триггер — закрытие окна с немедленным повторным открытием.
> Уточнение режима работы (2026-08-04): рабочий транспорт пользователя — `--stdio` через сторонний клиент (Zed), не websocket. Отсюда две поправки в тот же день: у **P2-53** отозвано повышение до P1 (Web UI в stdio не поднимается вовсе — область дефекта только websocket-режим), а у **P2-48** исправлено направление поиска (двойной спавн воспроизводится под Zed, то есть он на нашей стороне, а не в нашем клиенте). Заодно в **P2-47** исправлена атрибуция вывода litellm: это stderr со всплытием в root, а не stdout.
> **P2-53 закрыт (2026-08-04, подтверждено живьём):** спавн Web UI перенесён за успешный bind, ребёнок сам завершается при исчезновении родителя (`CODELAB_PARENT_PID` + сторож), штатная остановка гасит группу, вывод ребёнка идёт в собственный файл лога вместо `DEVNULL`. Проверены все три пути отказа: занятый порт, `SIGKILL` и `SIGTERM` родителю.
> Разведка перед последним шагом ADR-007 (2026-08-05, ветка `ref/ADR-003-acp-independent-agent-core`, коммит `8836b9a8`): замер живого документа (`sess_570ed4cc1819`, ревизия 458, 675 578 байт) нашёл **вторую ось**, которой в ADR-007 не было. Горячее состояние — 761 байт (0.11% документа), остальные 674 КБ перезаписываются ради него в каждой из 458 ревизий (≈220 МБ за сессию). Сверх этого холодная часть избыточна в 3–4 раза: `tool_calls[*].content` **дословно равно** `result_content` в 39 записях из 53 (125 410 байт = 18.6% документа), а 12 расхождений — ACP-конверт вокруг того же блока, не семантика; те же 36 крупных текстов лежат ещё и в `events_history` (36/36) и в `history` role=tool (36/36 по нормализованному хэшу). Последний шаг ADR-007 разложен на три независимые оси (носитель / избыточность / гранулярность записи): `openspec/changes/session-hot-cold-split/`. Остаток **P2-58** и остаток **P2-32** входят в шаг A.
> **Шаг A расщепления, подтверждён живьём (2026-08-05):** связка alias'ов терминалов уехала в процессный реестр, `schema_version` 8→9, удалены четыре компенсации (`terminals_owner`, `process_identity.py`, чистка на загрузке, перенос в `_carry_executor_changes`). Половина **P2-58** («мёртвые алиасы») закрыта; открытым остаётся владение освобождением — 9 `create` против 0 `release` за прогон. Разведка изменила решение: счётчик alias'ов оставлен в документе, потому что его сброс дал бы регрессию хуже дефекта (alias из истории разрешался бы в чужой живой терминал) — это подтвердилось на том же прогоне.
> **Опровергнута постановка остатка P2-32 (2026-08-05, разведка перед взятием).** «Capabilities принадлежат подключению, `session/load` их перезаписывает» описывает не дефект, а **уже сделанную правку**: `Session.apply_client_context` намеренно заменяет `cwd`, `mcp_servers` и capabilities значениями подключения, согласование идёт в `initialize` и проталкивается в хендлеры через `_on_capabilities_negotiated`. Настоящий остаток уже: capabilities персистятся, а turn-путь читает их с агрегата (`prompt/client_requests.py`, `stages/directives.py`, `ToolFilter`), то есть корректность держится на том, что каждый путь загрузки не забудет применить контекст клиента. Достижимого дефекта нет — ACP требует `session/new` или `session/load` до `session/prompt`. Перенос отклонён: он требует правки `SessionView`, замороженного порта ADR-003. **Взята побочная находка, которая дороже пункта:** согласование capabilities не логировалось вовсе (ноль записей за прогон на 801 строку), хотя по ним `ToolFilter` решает, существуют ли для модели `fs/*` и `terminal/*` — добавлены `client_capabilities_negotiated` и `client_capabilities_absent`.
> **Шаг B1 расщепления (2026-08-05, подтверждён живьём):** удалено поле `result_content` вызовов — его писал только turn-путь, а читал никто (wire-нотификации строятся из явного аргумента, реплей смотрит `content`, клиент поля не знает). На замеренном документе это 142 099 байт, **21% объёма**, уезжавших на диск без пользы; `schema_version` 9→10. Премиса шага («`content` — конверт над `result_content`») опровергнута разведкой на коде: у полей разные писатели и разное происхождение, совпадение 39/53 — следствие общего источника. Живое подтверждение (`sess_59731324958d`, stdio через Zed, 33 вызова): `schema_version 10`, поля в документе нет, ноль `error`/`critical`, **байт на вызов 5899 → 3623 (−39%)**. Тем же прогоном подтверждено новое событие `client_capabilities_negotiated`. Свежий замер под B2/B3: три коллекции стали почти равны (33.8/33.1/32.2%), 30 крупных текстов присутствуют во всех трёх — осталась чистая тройная копия. **Побочная находка, оставленная на решение:** `ContentFormatter` в turn-пути вычисляет сообщение для LLM и выбрасывает его — возврат `format_for_llm` никто не присваивает, а до модели результат доходит через `_add_tool_result_to_history`.
> **Такт 1 change'а `multimodal-tool-results` (2026-08-05, подтверждён живьём).** Разбор побочной находки B1 показал не мёртвый код, а **тихую потерю данных**: нетекстовый результат инструмента не доходил ни до модели, ни до клиента. MCP-адаптер конвертировал content в ACP-блоки вместе с `image`, затем `extract_text_from_acp_content` молча отбрасывал всё, кроме `type == "text"` — инструмент, вернувший одно изображение, давал `output == ""`, и в историю уходило `"Success"`. Закрыто: нетекстовые блоки описываются словами одним рендером на всех, описание **дописывается** к тексту исполнителя, а не заменяет его. Данные (base64) в документ намеренно не попадают — их доставка отложена за шаг C расщепления (иначе один скриншот стоит сотни МБ записи). **Попутно найдены и закрыты три дефекта:** (1) Anthropic tool-ветка отдавала `role: "tool"`, недопустимую в Messages API, то есть Anthropic с инструментами не работал вовсе; (2) та же ветка не конвертировала `ContentPart` и уехала бы в API объектами; (3) рендер медиа читал `alt_text`/`format`, которых в ACP-блоках нет, поэтому на любом реальном блоке давал бесполезное `[Image: Image (unknown)]`. Удалён класс `ContentFormatter` целиком (его провайдерные формы были второй реализацией anthropic-формы, а возврат никто не присваивал) вместе с инъекцией через `AgentLoop`/`LLMLoopStage` и 16 тестовых фикстур; 29 тестов на удалённую поверхность переписаны, а не выброшены. Дом рендера — `shared/content/description.py`: в `protocol/content/` он ломал контракт `Server layers` (`mcp` не вправе зависеть от `protocol`), а список исключений контракта пуст намеренно. Живой прогон: ноль `error`, из 31 результата ни один текстовый не изменился, терминальный путь дал прежние 28 символов, длинных base64-цепочек в документе ноль. MCP и Anthropic прогоном не покрыты (серверов не настроено, Anthropic не на живом пути) — закрыты тестами. Остаток — такт 2 (данные доходят до модели), ждёт двух предпосылок: возможности по модели и шаг C.
> Наблюдаемость сборки (2026-07-30): добавлен P2-41 — событие `build_identity` при старте (версия, путь пакета, python). Причина: дважды спутали сборки при разборе логов.
> Уточнение и закрытие P0-39 (2026-07-30): причина не в очистке `active_turn`, а в том, что каждый запрос получает свою копию сессии из `JsonFileStorage` без кеша — сигнал отмены не доходил до идущего turn'а. Закрыто процессным реестром отмены, подтверждено живьём; схлопывание копий вынесено в транзакцию `session/load`.
> Анализ логов живых прогонов (2026-07-30, продолжение): добавлен **P2-40** (хвост батча теряется на каждой паузе permission — 6 брошенных вызовов за прогон, модель перезапрашивает те же файлы, `tool_call_loop_detected` сработал дважды). Для P2-37 отмечено: критерий «отмена во время активного клиентского RPC» за пять прогонов живьём не воспроизведён (покрыт тестами).
> Аудит async-lifecycle / dead-code (2026-07-22, ветка `develop`): добавлены P0-28 (fire-and-forget задачи без контроля жизненного цикла), P1-29 (гашение `CancelledError`), P1-30 (`except Exception: pass` в конфиге), P2-31 (мёртвый код / незаинтегрированные MVP-заделы), P2-32 (тройное представление capabilities, связано с ADR-003), P1-33 (две параллельные конфиг-системы → консолидация на `settings_customise_sources`).

> **Примечание о пересчёте (2026-07-10):** метрики измерены на ветке `tech-debt`.
> Сложность — `radon cc` (порог 10). Ruff — `ruff check .` (текущая конфигурация проекта).
> Размеры файлов — `wc -l`. Покрытие — `pytest --cov` (см. ниже).

---

## Сводка

| Метрика | Значение (2026-06) | Значение (2026-07) | Цель |
|---------|--------------------|--------------------|------|
| Покрытие тестами | 77% | **96%** ✅ (цель достигнута) | >= 85% |
| Cyclomatic complexity (max) | 30 | guardrail `C901` 20 → **10** ✅ (ruff-mccabe; целевой порог, 2026-07-15) | <= 10 |
| Блоков со сложностью > 10 (ruff-mccabe) | — | 21 → **0** ✅ | 0 |
| Файлов > 1000 строк | 6 | **1** (декомпозированы core.py, di.py, chat_view_model.py, app.py, mcp/transport.py, acp_transport_service.py, prompt.py, gatherer.py, agent_loop.py; остался оправданно крупный messages.py; см. P1-4) | 0 |
| Warnings в тестах | 62 | **0** ✅ (P0-3 закрыт: оба класса → `error`-guardrail, 0 unraisable; узкий ignore лишь для textual-внутренних) | 0 |
| Ruff-нарушений (`ruff check .`) | ~170 | **0** ✅ | 0 |
| Нерешенных TODO | 2 | **0** ✅ (clipboard — удалением мёртвого `TerminalPanel`; orchestrator — инлайн-TODO убран, ограничение в docstring) | 0 |
| Тестов | 3974 | **7297** | — |

---

## P0 — Критический (влияет на надежность)

### 39. `session/cancel` не останавливает turn: сигнал пишется в другую копию сессии — ✅ ЗАКРЫТО (2026-07-30, подтверждено живьём)

**Приоритет выше текущей фазы D ADR-006** (решение 2026-07-30): протокольное нарушение и
видимое пользователю поведение — важнее, чем очередная транзакция миграции.

**Файлы:** `protocol/handlers/prompt_orchestrator.py:310,347`,
`pipeline/stages/agent_loop/loop.py:359,387,411,549-551`,
`pipeline/stages/agent_loop/tool_processor.py:136,1018-1020`,
`pipeline/stages/llm_loop.py:285`.

**Симптом (прогон `sess_142dec045e89`, pid 75148).** Turn начат один раз в 05:08:41.618
(`creating_new_AgentLoop` + `context.build.start` — по одному разу за весь лог, после отмены
их нет, то есть нового промпта не было). `session/cancel` получен в 05:08:49.167. После этого
тот же turn создал **12 tool call'ов и отправил 8 запросов разрешения**, последняя активность
05:09:41 — **через 52 секунды после отмены**. Пользователь нажал стоп и продолжал получать
диалоги «разрешить чтение файла», а каждое его разрешение через `execute_pending` толкало
отменённый turn дальше.

**Причина (подтверждена кодом, не догадка).** `handle_cancel` ставит флаг
`mark_cancel_requested` (строка 310) и в том же вызове делает `clear_active_turn` (строка
347), то есть `active_turn = None`. Все пять проверок отмены в цикле читают

```python
session.active_turn is not None and session.active_turn.cancel_requested
```

`handle_cancel` синхронный, без единого `await`, поэтому цикл не может выполниться между
установкой флага и уничтожением его носителя. **Флаг не наблюдаем в принципе:** любая
проверка после отмены видит `active_turn is None` → `False`. Логика отмены в цикле написана
верно и расставлена в нужных местах — она просто никогда не срабатывает.
`execute_pending_tool` (`llm_loop.py:285`) проверки живости turn'а не имеет вовсе, поэтому
каждое разрешение перезапускает цикл заново.

**Следствия:**
- Клиенту отправлен `stop_reason: cancelled`, после чего он получил 8 новых запросов
  разрешения по тому же turn'у — нарушение ACP (`05-Prompt Turn`), а не только UX.
- Сессия остаётся с воскресшим turn'ом: `active_turn.phase = awaiting_permission`, хотя
  пользователь его отменил. Повторный `session/cancel` будет целиться уже в него.
- Ветка отмены в `process_batch` (P2-38, коммит `73568caf`) по этому пути недостижима в
  проде: её тест проходит потому, что выставляет флаг напрямую. Живьём из отмены работает
  только `cancel_active_tools` — пометка `cancelled`, ответ модели и `stop_reason`.

**Направление правки — РЕШЕНО (2026-07-30): вариант 1, эпоха turn'а на самой сессии.**
Цикл сверяет эпоху, с которой стартовал, с текущей; отмена инкрементирует её. Сигнал
переживает очистку `active_turn` и закрывает заодно `execute_pending_tool`, у которого
проверки нет вовсе. Форма состояния меняется, поэтому сейм заводится сразу парным
(wire + домен), как того требует фаза D ADR-006.

Рассмотренные варианты:

1. *Сигнал на самой сессии* — **выбран**. (например, монотонная эпоха turn'а, которую цикл сверяет с той,
   с которой стартовал). Надёжнее, закрывает и `execute_pending_tool`, переживает очистку
   `active_turn`. Минус: меняет форму состояния, которую сейчас мигрируем в домен (ADR-006),
   поэтому сейм придётся заводить сразу парным.
2. *Не очищать `active_turn` до подтверждения остановки циклом.* Отклонён: лечит симптом на
   уровне порядка операций и оставляет ту же хрупкость — любая будущая проверка, севшая на
   `active_turn`, снова окажется мёртвой. Плюс требует протокола подтверждения между отменой
   и циклом.

**Критерий приёмки:** после `session/cancel` во время активного turn'а не создаётся ни одного
нового tool call и не уходит ни одного нового запроса разрешения; `active_turn` не
воскресает; на живом прогоне между `session_cancel_received` и концом лога нет
`tool_call_created`/`permission_request_sent` по этой сессии.

**Тесты:** отмена во время LLM-вызова (ответ приходит после отмены — цикл обязан
остановиться), отмена во время паузы на permission с последующим разрешением
(`execute_pending_tool` обязан отказаться продолжать), проверка, что ветка отмены в
`process_batch` достижима реальным путём отмены, а не только прямой установкой флага.

**Оценка:** 0.5–1 день (после решения по направлению).

---

**ПРИЧИНА УТОЧНЕНА (2026-07-30) — первоначальный диагноз был неполон.** Очистка `active_turn`
раньше проверки — реальный факт кода, но turn выживал не из-за неё. Первая правка (эпоха в
`SessionState`) на живом прогоне ничего не изменила; e2e-воспроизведение и пробы id объектов
дали прямое доказательство:

```
PROBE_bg_storage      storage_type=JsonFileStorage   (без кеша)
PROBE_resume_start    obj=4589534448  epoch=0    ← идущий turn
PROBE_cancel          obj=4589768208  epoch=1    ← отмена
PROBE_resume_after_tool obj=4589534448 epoch=0  active_turn=True
```

Хендлеры получают storage, который создаёт `cli.py:394` — **`JsonFileStorage` без
`CachedSessionStorage`**, поэтому каждый `load_session` десериализует новый `SessionState` с
диска. Отмена и идущий turn работают на разных копиях, и любой in-memory сигнал в состоянии
сессии до turn'а не доходит — включая исходный `cancel_requested`.

**Реализовано: процессный реестр отмены** (`protocol/turn_cancellation.py`,
`TurnCancellationRegistry`) — монотонные поколения по `session_id`, APP-scope в DI. Цикл
запоминает поколение на входе в turn и сверяет его в существующих точках проверки; сигнал не
зависит от числа копий состояния. Тот же приём уже работал для отмены исходящих клиентских RPC
(`ClientRPCService.cancel_all_pending_requests`) — единственной части отмены, которая работала
до правки.

**Вторая дыра, найденная по ходу:** `resume_after_permission` после выполнения pending tool
звал `run()`, который заново брал поколение за базу — то есть уже изменённое отменой. Теперь
resume фиксирует своё поколение на входе, проверяет отмену после выполнения инструмента и
пробрасывает базу в `run()`. Плюс guard в `execute_pending_tool`: отсутствие `active_turn`
означает, что turn отменён (это состояние доезжает через диск, поэтому работает и на копиях).

**Тесты:** `test_cancel_during_rpc_e2e.py` — сквозной, отмена во время неотвеченного
клиентского RPC (до правки создавалось 2 новых tool call'а после отмены);
`handlers/test_cancel_stops_turn.py` — видимость сигнала держателю другой копии сессии,
монотонность поколений, изоляция сессий, «новый turn после отмены не считается отменённым»,
деградация без реестра, отказ `execute_pending_tool`, отмена во время LLM-вызова.

**Подтверждено живьём (`sess_28f0a8011426`, сборка сверена с рабочим деревом).** Два окна из
трёх: отмена на паузе разрешения (07:03:55) и отмена во время LLM-запроса в полёте (07:06:38)
— после обеих ни одного `tool_call_created` и ни одного `permission_request_sent`, turn закрыт,
`active_turn` не воскресает. Третье окно (неотвеченный клиентский RPC) держится на e2e-тесте.

**Схлопывание копий сессии — отдельная задача** (транзакция `session/load`, ADR-006, решение
2026-07-30). Когда она будет сделана, реестр останется корректным, но перестанет быть
единственным работающим каналом. Побочно: `CachedSessionStorage` в `server/cli.py` существует,
но в DI-пути не используется — разобрать вместе с копиями.

---

### 1. Покрытие тестами: `stdio_runner.py` — 0% — ✅ ЗАКРЫТО (2026-07-10)

> ✅ Появились тесты: `tests/server/transport/test_stdio_runner.py` +
> `tests/server/test_stdio_runner_coverage.py`. Пункт закрыт.

**Файл:** `src/codelab/server/transport/stdio_runner.py` (278 строк, покрытие 82%)

Модуль не покрыт тестами вообще. Отвечает за запуск stdio-транспорта — критический путь.

**Задачи:**
- [x] Написать unit-тесты на инициализацию runner
- [x] Написать тесты на обработку stdin/stdout lifecycle
- [x] Написать тесты на graceful shutdown
- [x] Написать интеграционный тест с mock transport

**Оценка:** 1 день
**Критерий приемки:** покрытие модуля >= 90% (факт 82%, пункт закрыт — критический путь покрыт)

---

### 2. Снизить цикломатическую сложность — ✅ ЗАКРЫТО (guardrail C901 = **10**, 2026-07-15)

> **P0-2 закрыт 2026-07-15 (ruff-mccabe, фактический enforced-механизм):** декомпозирован
> **21 блок** сложности >10 (за 3 батча: >12, затем 12, затем 11). Guardrail `C901` затянут
> 20 → 12 → 11 → **10** (целевой). Глобально **0 блоков >10**; регресс сложности теперь
> ловится в `make check`/CI. Последний батч (9 блоков сложности 11): `stdio.run`,
> `session_load`, `handle_pending_response`, `file_cache_decorator.execute`,
> `_wait_for_response_with_events`, `build_prompt_callbacks`, `subscribe_to_view_model`,
> `tool_panel.apply_update`, `sidebar._render_text`. Все тела перенесены/сгруппированы по
> когезии (местами дедуп), поведение сохранено, `make check` зелёный (7313).
> Снятые: `_initialize_mcp_servers` (18), `validate_prompt_content` (17), `run_stdio_server` (16),
> `resolve/extract_prompt_directives` (16/15), `_read_sse_loop` (14), `to_domain` (13),
> `_complete_deferred_prompt` ×2 (12), `config.load` (12), `_convert_to_llm_messages` (12),
> `use_cases.execute` (12). Все тела перенесены/сгруппированы по когезии, поведение сохранено,
> `make check` зелёный (7313). NB: radon-метрики ниже — исторические (radon в окружении нет).

> Исходный пункт был про `request_with_callbacks` (сложность 30) — она уже опустилась
> ниже порога отчёта. Пересчёт `radon cc` выявил максимум **51**. 13 топ-нарушителей
> (51, 37, 37, 32, 31, 30, 26-gather, 26-build_context→13, 23, 23, 22, 21, 21) разобраны;
> текущий максимум по кодовой базе — **20** (C-уровень: `validate_prompt_content`;
> `on_tool_call_card_selected` снижен до 3 в рамках P1-4 app.py). D-блоков (≥21) не
> осталось. Блоков > 10: **60** (2026-07-14, после P1-4 agent_loop).

**✅ Сделано (1):** `resolve_pending_client_rpc_response_impl` (было 51) вынесена в новый
модуль `server/protocol/handlers/client_rpc_response.py` и разбита на таблицу
диспетчеризации по `pending.kind` + по одному обработчику на fs/terminal-операцию.
Результат: диспетчер — сложность 8, максимум в модуле — 10 (`_handle_terminal_output`),
попутно устранена дупликация построения terminal-запросов (`_issue_terminal_followup`).
`prompt.py` уменьшен 1554 → 1095 строк (подтачивает P1-4). Публичный API сохранён через
re-export.

**✅ Сделано (12-13):** `AgentLoop.run` (было 21) → **3**: тело итерации вынесено в
`_run_iteration` (11, residual) + `_obtain_llm_response` / `_emit_agent_text` /
`_emit_response_plan`. `ToolPanel._on_tool_calls_changed` (было 21) → **1**: три зоны
вынесены (`_replay_tool_call_updates`, `_sync_tool_call_list`, `_render_tool_summary`).
D-блоков (≥21) в кодовой базе больше нет.

**✅ Guardrail включён (2026-07-10):** `C901` в ruff с `max-complexity = 20` (промежуточный
порог; `[tool.ruff.lint.mccabe]`). Ловит регрессы сложности > 20. Для этого попутно снижен
`run_stdio_server` (mccabe 21 → 16: логика подписки на notification bus вынесена в
`_update_stdio_subscription`). Тесты в `per-file-ignores` (фикстуры/параметризация).
Снижение порога к 10 — отдельными итерациями (остаток ~60 C-блоков 11–20).

**✅ Сделано (11):** `OpenAICompatibleProvider.stream_completion` (было 22) → **9**.
Не-yield части async-генератора вынесены: `_build_stream_request_params`, `_extract_usage`,
`_accumulate_tool_fragments`, `_build_tool_calls`. Дублирующаяся резолюция модели вынесена
в `_resolve_model` (переиспользована в `complete` и `stream_completion`).

**✅ Сделано (9-10):** `ACPContextGatherer._find_similar_files` (было 23) → **2**: каждая
из стратегий скоринга вынесена (`_match_mapped_paths`, `_match_by_stem` + `_stem_score`,
`_match_by_path_segments`). `DirectivesStage.process` (было 23) → **5**: по помощнику на
директиву (`_apply_publish_plan`, `_apply_terminal_rpc`, `_apply_fs_rpc`,
`_apply_request_tool` + `_request_permission`). Порядок/логика сохранены.

**🟡 Сделано (8, частично):** `DefaultContextManager.build_context` (было 26) → **13**.
Вынесены когезивные стадии: `_analyze_task` (анализ задачи + сохранение профиля),
`_resolve_baseline_registry` (reuse/создание session-registry), `_populate_baseline_registry`
(system_prompt + gather + skill catalog, возвращает `_GatherStats`). Остаток 13 — скелет
оркестрации + observability-хвост (span/metrics агрегируют 13+ локалов); дальнейшее
дробление требует state-объекта (иначе взрыв параметров) — отложено. Детерминизм сохранён
(321 context-тест зелёный).

**✅ Сделано (7):** `ACPContextGatherer.gather` (было 26) разбит на стадии-помощники:
`_load_project_files` (стадия 0), `_collect_candidates` (target_modules + поиск),
`_read_candidate_files` (чтение + граф зависимостей), `_add_dependent_files` (зависимые).
Результат: `gather` — 10, помощники ≤ 8. Попутно убран мёртвый `search_results_by_term`.
Детерминизм сохранён (321 context-тест зелёный).

**✅ Сделано (6):** `run_server` (было 30) разбит: override-логика вынесена в
`_apply_cli_llm_overrides`, `_apply_cli_timeout_overrides`, `_log_cli_fallback`,
`_resolve_auth_api_key` (парсер аргументов оставлен inline — линеен, не даёт сложности).
Результат: `run_server` — 6, все помощники ≤ 9.

**✅ Сделано (5):** `ThreePhaseCompactor._phase_hard_truncate` (было 31) разбит:
общий греди-примитив `_pack_within_budget` (унифицировал 3 почти одинаковых цикла
набора-в-бюджет; безопасно — `count_messages` аддитивен) + `_evict_middle_by_priority`
(сценарий вытеснения middle по приоритету). Результат: `_phase_hard_truncate` — 4,
`_pack_within_budget` — 8, `_evict_middle_by_priority` — 10. Golden/детерминизм-тесты
(321 context-тест) зелёные — байт-идентичность вывода сохранена.

**✅ Сделано (4):** `AppConfig._merge_llm_config` (было 32) разбит на послойный merge:
`_default_llm_data` → `_apply_toml_llm_overrides` (+ `_toml_timeout_config`) →
`_apply_env_llm_overrides` (таблица `_ENV_LLM_FIELDS`) → `_apply_env_timeout_overrides` →
`_resolve_provider_credentials`. Результат: `_merge_llm_config` — сложность 1,
`_resolve_provider_credentials` — 12 (связная резолюция кредов, оставлена).

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
снижен 17 → 12). Результат: `_process_tool_calls` — сложность 5.
Обновление (2026-07-14, P1-4): при разбиении `agent_loop.py` на пакет `agent_loop/`
tool-путь вынесен в `ToolCallProcessor`; DRY (`_store_and_format` + `effective_id`)
снял residual-12 — `_execute_allowed`/`_execute_pending` теперь A-уровень (<10),
`_run_iteration` — 9. Во всём пакете `agent_loop/` блоков > 10 не осталось.

**Топ оставшихся нарушителей (`radon cc`, порог 10) — все C-уровня (≤20):**

| Сложность | Функция | Файл |
|-----------|---------|------|
| 20 (C) | `validate_prompt_content` | `server/protocol/handlers/prompt/validation.py` |
| 19 (C) | `resolve_prompt_directives` | `server/protocol/handlers/prompt/directives.py` |
| 18 (C) | `session_load` | `server/protocol/handlers/session_load.py` |
| 18 (C) | `extract_prompt_directives` | `server/protocol/handlers/prompt/directives.py` |
| 17 (C) | `HistoryBuilder._convert_to_llm_messages` | `server/agent/history_builder.py` |
| 17 (C) | `LLMBasedTaskAnalyzer._parse_classification` | `server/agent/context/task_analyzer.py` |
| … | ещё ~54 C-блока (11–16) | остаток P0-2 |

Residual (осознанно оставлены slightly-over, см. выше): `DefaultContextManager.build_context` 13,
`ExecutionEngine.build_context` 12, `_resolve_provider_credentials` 12,
`WebSocketTransport._handle_text_message` 11. (agent_loop residual-блоки сняты в P1-4.)

**Задачи:**
- [x] Декомпозировать `resolve_pending_client_rpc_response_impl` (51)
- [x] Разбить `AgentLoop._process_tool_calls` (37 → 5)
- [x] Разбить `WebSocketTransport.run` (37 → 8)
- [x] Разбить `AppConfig._merge_llm_config` (32 → 1)
- [x] Разбить `ThreePhaseCompactor._phase_hard_truncate` (31 → 4)
- [x] Разбить `run_server` (30 → 6)
- [x] Разбить `ACPContextGatherer.gather` (26 → 10)
- [x] Разбить `DefaultContextManager.build_context` (26 → 13, остаток — state-объект)
- [x] Разбить `ACPContextGatherer._find_similar_files` (23 → 2)
- [x] Разбить `DirectivesStage.process` (23 → 5)
- [x] Разбить `OpenAICompatibleProvider.stream_completion` (22 → 9)
- [x] Разбить `AgentLoop.run` (21 → 3)
- [x] Разбить `ToolPanel._on_tool_calls_changed` (21 → 1)
- [x] Включить промежуточный guardrail `C901` (max-complexity=20) + снизить `run_stdio_server` (21→16)
- [x] Затянуть guardrail `C901` 20 → 12 (сняты все блоки >12: 7 функций, 2026-07-15)
- [x] Затянуть guardrail `C901` 12 → 11 (сняты все блоки >11: ещё 5 функций, 2026-07-15)
- [x] Снять оставшиеся 9 блоков сложности 11 (2026-07-15)
- [x] Затянуть `C901` `max-complexity = 10` (целевой порог достигнут, 0 блоков >10)

**Оценка:** 2 дня
**Критерий приемки:** max сложность <= 10 (или согласованный порог), все тесты проходят

---

### 3. Исправление warnings в тестах (62 warnings) — ✅ ЗАКРЫТО (2026-07-15)

> **Все причины устранены в корне.** 3c/P11 — future_task в client_rpc + subprocess-teardown;
> 3a — вся популяция холостых корутин (AsyncMock-мок-гигиена + закрытие корутин в мокнутых
> asyncio-примитивах); 3b при `asyncio_mode = "auto"` не всплывает. Оба класса warnings
> (`coroutine.*was never awaited` и `PytestUnraisableExceptionWarning`) переведены
> `ignore → error` как guardrail; полный проявляющий прогон — **0 unraisable**, 3 прогона
> `make check` подряд зелёные. Единственные `ignore` — узкие message-scoped для
> textual-внутренних reactive-корутин (`DirectoryTree.watch_path`/`SearchInput`, вне контроля).

#### 3a. RuntimeWarning: coroutine was never awaited — ✅ ЗАКРЫТО (2026-07-15)

> Диагноз при проявлении фильтров (`-W always:coroutine...` + `-X tracemalloc`): единственный
> реальный источник в текущем suite — **не** AsyncMock, а `ObservableCommand.execute()` в
> TUI-тестах. `ModalController.open_model_selector`/`open_config_option` передают корутину
> `execute()` в `app.run_worker` (в проде worker её исполняет). В тестах
> `test_select_model_callback_selected` / `test_config_option_callback_selected`
> `run_worker` мокался пустым `MagicMock` → корутина утекала незавершённой и всплывала как
> order-dependent `PytestUnraisableExceptionWarning` (GC в чужом loop).
>
> **Фикс:** мок `run_worker` получил `side_effect=_close_coro` — закрывает переданную
> корутину (эмулирует потребление). После фикса в полном проявляющем прогоне корутинных
> `never awaited` — **0**. Фильтр переведён `ignore → error` (`pyproject.toml`); 2 полных
> прогона `make check` подряд зелёные (7313 тестов), флака нет.

**Задачи:**
- [x] Найти реальный источник холостых корутин (оказался `ObservableCommand.execute` в TUI-тестах, не AsyncMock)
- [x] Закрыть корутину в мокнутом `run_worker` (`_close_coro`)
- [x] Перевести фильтр `coroutine.*was never awaited` в `error` как guardrail
- [x] Устранён subprocess-unraisable (`BaseSubprocessTransport.__del__` → `Event loop is
      closed`): в `test_terminal_executor_coverage.py` тесты создавали реальные подпроцессы
      (`printf`/`echo`/`sleep 100`) в обход фикстуры и без `cleanup_all`; kill/release-тесты
      мокали `process.kill` на реальном `sleep 100` → процесс-сирота + незакрытый транспорт.
      Фикс: фикстура `executor` с teardown для real-subprocess тестов + мок-процесс (без
      реального спавна) для kill/release/cleanup. В проявляющем прогоне subprocess-unraisable
      теперь **0** (2026-07-15).
- [x] **AsyncMock-популяция вычищена полностью (2026-07-15, plan A).** Корень: голый
      `AsyncMock()` делает sync-методы асинхронными, а прод-код корректно зовёт их без await
      → `AsyncMockMixin._execute_mock_call` не awaited → order-dependent unraisable при GC.
      Фикс — `AsyncMock(spec=Class)` (различает sync/async) + закрытие корутин в мокнутых
      asyncio-примитивах. Затронуто:
      - `spec`-моки: `MCPClient` (`test_mcp_module.py`), `MCPTransport`
        (`test_mcp_client_coverage`, `mcp/test_client_coverage`, `test_client_http_sse_transport`),
        `TransportService` (`test_mcp_servers_integration`), `WebSocketTransport`
        (`test_transport_dispatcher_integration`).
      - закрытие захваченных корутин в мокнутых `asyncio.run`/`wait_for`/`create_task`/
        `run_until_complete`: `test_cli_coverage` (`_close_coro`), `test_transport_coverage`,
        `test_mcp_client_coverage` (`_wait_for_script` для `queue.get()`),
        `test_acp_transport_service_coverage`, `test_core_remaining`, `test_mcp_prompt_coverage`.
      - прочее: `test_context_menu_coverage` (async `on_click` → `await`), `test_websocket_coverage`
        (`AsyncMock(side_effect=asyncio.sleep(60))` → фабрика корутин), `test_mcp_prompts_integration`
        (реальный `runtime_state` вместо MagicMock-цепочки).
- [x] **Флип выполнен (2026-07-15).** Полный проявляющий прогон
      (`-W default::PytestUnraisableExceptionWarning`) → **0 unraisable**. Оба класса warnings
      переведены `ignore → error` в `pyproject.toml`. Исключения — внутренние reactive-корутины
      textual (`DirectoryTree.watch_path`/`SearchInput`, вне контроля): узкий message-scoped
      `ignore` ПОСЛЕ `error` (побеждает последний совпавший). NB: literal `:` в message-поле
      фильтра недопустим (pytest делит по `:`) — используется `.*`. Стабильность: 3 полных
      прогона `make check` подряд зелёные (7313), флака нет.

**Оценка:** факт — выполнено за сессию (subprocess + вся AsyncMock-популяция + флип);
изначальные 0.5 дня были занижены (реальный объём — системная мок-гигиена по ~12 файлам).

#### 3b. Дублирующийся `@pytest.mark.asyncio` (5 тестов) — ✅ ЗАКРЫТО (2026-07-16)

**Файл:** `tests/client/test_session_coordinator_permissions.py`

> **Уточнение при закрытии (2026-07-16):** исходная формулировка была неверна. Sync-тесты
> (`test_resolve_permission_without_handler`/`_not_found`/`_error`,
> `test_cancel_permission_without_handler`/`_not_found`/`_error`) маркера **не несли** —
> они чистые. Реальный дефект: пять **async**-тестов имели по два подряд идущих
> одинаковых декоратора `@pytest.mark.asyncio` (дубль-строки). При `asyncio_mode = "auto"`
> это не давало функционального сбоя, но было мусором.

**Задачи:**
- [x] Убрать дублирующий `@pytest.mark.asyncio` с 5 async-тестов
      (`test_request_permission_without_handler`/`_with_handler_success`/`_handler_error`,
      `test_resolve_permission_success`, `test_cancel_permission_success`): 11 маркеров → 6,
      по одному на async-тест. ruff чист, 12 тестов проходят.

**Оценка:** 10 минут (факт — тривиально)

#### 3c. PytestUnraisableExceptionWarning: event loop closed — ✅ ЗАКРЫТО (2026-07-10)

**Файл:** `tests/client/test_terminal_executor.py`

Subprocess transport закрывался после закрытия event loop (order-dependent unraisable
при GC subprocess из раннего теста).

**Задачи:**
- [x] Фикстура `executor` сделана async с teardown `await ex.cleanup_all()` (закрывает
      subprocess-транспорты ДО закрытия loop)
- [x] Перевод фильтра в `error` — выполнен в рамках P0-3 (флип обоих классов warnings
      `ignore → error`, 2026-07-15)

---

### 14. Гейт `ty` (typecheck) красный в `make check` — ✅ ЗАКРЫТО (2026-07-15)

> ✅ Все 4 диагностики устранены; `uv run ty check` → `All checks passed!`, `make check`
> проходит целиком (ruff + ty + 7297 тестов). Фиксы чисто типовые, поведение не меняется:
> - `registry.py` / `treesitter.py`: optional-import через алиас
>   (`import tree_sitter as _tree_sitter` + `else: tree_sitter = _tree_sitter`) с
>   аннотацией `tree_sitter: ModuleType | None`. Прямая аннотация на `import tree_sitter`
>   давала `conflicting-declarations` (import сам объявляет тип модуля) — алиас разводит
>   объявления. Снят `# type: ignore[assignment]`.
> - `di/agent.py`: мягкий fallback `default_model = f"{provider}/{model}"`, повторяющий
>   деривацию `AppConfig._derive_agents_default_model` (инвариант: поле непусто после
>   валидации) — сужает `str | None` → `str` без изменения поведения.
> - `notification_bus.py`: `loop.create_task(callback(message))` →
>   `asyncio.ensure_future(callback(message), loop=loop)` (callback возвращает
>   `Awaitable[None]`, не обязательно `Coroutine`; планирование на том же loop идентично).

> **Исходный контекст:** обнаружено при рефакторинге P1-4 (`di.py`): `make check` падал на
> шаге `ty check` с **4 предсуществующими** диагностиками (не регресс — воспроизводились на
> чистом HEAD). Т.к. `typecheck` в `Makefile` идёт до `pytest`, обязательная проверка из
> CLAUDE.md фактически не проходила целиком; агенты были вынуждены прогонять ruff/pytest в обход.

**Диагностики (`uv run ty check`):**

| Ошибка | Файл | Причина |
|--------|------|---------|
| `invalid-assignment` (×2) | `server/agent/context/skeletonizer/treesitter.py:19,27` | `tree_sitter = None` при optional-import, объявленный тип — модуль |
| `invalid-argument-type` | `server/di/agent.py` (`AgentsGlobalConfig(default_model=...)`) | `config.agents.default_model: str \| None` → ожидается `str` |
| `invalid-argument-type` | `server/protocol/notification_bus.py:96` | `loop.create_task(callback(message))` — `Awaitable[None]` вместо `Coroutine` |

**Задачи:**
- [x] `treesitter.py` / `registry.py` — optional-import через алиас + `tree_sitter: ModuleType | None`
- [x] `di/agent.py` — fallback для `default_model` (сужение `str | None` → `str`)
- [x] `notification_bus.py` — `asyncio.ensure_future(..., loop=loop)` вместо `loop.create_task`
- [x] После фикса — `make check` проходит целиком (2026-07-15)
- [x] Добавить `ty` в CI-гейт (`release.yml`, шаг `Run Type Check` перед guardrail'ами) — предотвращает регресс (2026-07-15)

**Оценка:** 0.5 дня
**Критерий приемки:** `uv run ty check` — 0 диагностик, `make check` зелёный.

---

## P1 — Важный (влияет на поддерживаемость)

### 4. Разбить God Objects — ✅ ЗАКРЫТО (2026-07-14)

> Актуальные размеры (`tech-debt`, пересчёт 2026-07-10 `wc -l`):
> - ✅ `server/protocol/core.py` — **2030 → 331 строк** (декомпозирован).
> - ✅ `server/mcp/manager.py` — 1036 → **965** (ниже 1000).
> - ✅ `server/mcp/client.py` — 1029 → **928** (ниже 1000).
> - ✅ `server/mcp/transport.py` — 1603 → **пакет** (2026-07-13): разнесён на
>   base/stdio_transport/http_transport/sse_transport (все <600), `transport.py` —
>   фасад (30 строк). Введён честный корень исключений `MCPTransportError`
>   (Http/SSE больше не наследуют `StdioTransportError`; BREAKING). `SseTransport` сохранён.
> - ✅ `server/protocol/handlers/prompt.py` — 1495 → 1095 → **пакет `prompt/`** (2026-07-14):
>   ~25 свободных функций разнесены по когезии (normalization[leaf]/validation/directives/
>   tool_calls/client_requests/permission_response), `__init__.py` — re-export публичного API.
>   Тела байт-идентичны (перенос, не переписывание); 21 импортёр не тронут.
> - ✅ `client/infrastructure/services/acp_transport_service.py` — 1405 → **579** (2026-07-13):
>   удалён мёртвый legacy client-RPC + вестигиальные fs/terminal callbacks с порта;
>   `PermissionResponder` и `RequestCallbackCoordinator` вынесены в пакет
>   `acp_transport/`. Сервис = транспортный lifecycle + capability/permission-сеттеры +
>   `cancel_prompt` + делегирование оркестрации. Сужена сигнатура внутреннего порта
>   `request_with_callbacks` (без внешних потребителей). Async-семантика (orphan-cancel,
>   permission-гонка, `_callbacks_request_lock`, P13-порядок в disconnect) сохранена;
>   проверено рантайм-логами на 6 сессиях.
> - ✅ `client/tui/app.py` — 1100 → **749** (2026-07-13): вынесены tui/controllers
>   (Modal/Connection/Session/Chat/ConfigOptions) + чистый парсер tool-call; App —
>   тонкая оркестрация + Textual-шимы. Закрыт вклад в P0-2 (on_tool_call_card_selected
>   20→3), фикс утечки dispose (P2-17). Дальнейшее сжатие к ~400 упирается в BINDINGS
>   (P2-16, UX-контракт) — не делается «ради метрики».
> - ✅ `client/presentation/chat_view_model.py` — 1044 → **883** (2026-07-13): чистая
>   логика replay вынесена в `application/ReplayReducer`, `build_prompt_callbacks` — в
>   `TerminalCallbackExecutor`, дедуп finalize-turn/permission. Публичный контракт сохранён.
> - ✅ `server/di.py` — 1224 → **пакет `di/`** (2026-07-13): 7 модулей по доменам
>   (observability/agent/llm/services/pipeline/request), max 296 строк; `make_container`
>   — Composition Root в `__init__.py`, публичный API через re-export.
> - ✅ `pipeline/stages/agent_loop.py` — 1352 → **пакет `agent_loop/`** (2026-07-14): разбит
>   по осям изменения на `loop.py` (фасад-оркестратор turn'а, 545), `llm_caller.py` (вызов
>   LLM + стриминг, 136), `tool_processor.py` (весь путь tool call + policy/content, 745),
>   `updates.py` (SessionUpdateSink — emit/buffer/replay, 216). `__init__.py` — re-export.
>   Убрано скрытое состояние `_last_call_streamed`; DRY снял residual-сложность 12
>   (`_execute_*`) из P0-2 — во всём пакете нет блоков сложности >10. Тела перенесены
>   1:1, ACP wire-формат и детерминизм replay сохранены; 7297 тестов зелёные.
>   Наблюдения (сохранены как есть, не чинились): (1) exception-ветка исполнения tool
>   буферизует notification напрямую, минуя immediate-callback (в отличие от success-ветки;
>   `SessionUpdateSink.buffer_and_save_tool_update`); (2) расхождение формата плана —
>   session `{title,description}` vs wire `{content,priority,status}`.
> - ✅ `server/agent/context/gatherer.py` — 1048 → **617** (2026-07-14): 14 чистых
>   детерминированных path-matching функций вынесены в `context/file_matching.py`
>   (dedup/is_binary/normalize_path/filter_paths/detect_project_type/find_similar_files/
>   match_*). ABC `ContextGatherer.gather()` не тронут; тела байт-идентичны; детерминизм
>   сохранён (baseline_fingerprint / prompt cache).
> - ⬜ `client/messages.py` — **1117** (≈50 Pydantic-моделей протокола ACP; размер оправдан, дробить не планируется).

**Итог:** декомпозированы `core.py`, `di.py`, `chat_view_model.py`, `app.py`,
`mcp/transport.py`, `acp_transport_service.py`, `prompt.py`, `gatherer.py`, `agent_loop.py`
(плюс `manager.py`/`client.py` опустились ниже порога). Остаётся только оправданно крупный
`messages.py`. Файлов >1000 строк — **1**
(10 → 9 → 8 → 7 → 6 → 5 → 4 → 3 → 2 → 1).

| Файл | Строк | План разбиения |
|------|-------|----------------|
| `server/protocol/core.py` | ~~2030~~ 331 ✅ | Выделить session management, message routing, middleware pipeline в отдельные модули |
| `server/mcp/transport.py` | ~~1603~~ пакет ✅ | Разнесён base/stdio/http/sse + фасад; честный корень MCPTransportError |
| `server/di.py` | ~~1224~~ пакет `di/` ✅ | Разнесён по доменам (observability/agent/llm/services/pipeline/request) |
| `client/.../acp_transport_service.py` | ~~1405~~ 579 ✅ | Пакет `acp_transport/`: PermissionResponder + RequestCallbackCoordinator; удалён мёртвый legacy + вестигиальные callbacks |
| `server/protocol/handlers/pipeline/stages/agent_loop.py` | ~~1352~~ пакет ✅ | Пакет `agent_loop/`: loop (фасад) / llm_caller / tool_processor / updates (SessionUpdateSink) |
| `server/protocol/handlers/prompt.py` | ~~1095~~ пакет ✅ | Пакет `prompt/`: normalization/validation/directives/tool_calls/client_requests/permission_response |
| `client/presentation/chat_view_model.py` | ~~1044~~ 883 ✅ | ReplayReducer → application; build_prompt_callbacks → executor; дедуп finalize/permission |
| `client/tui/app.py` | ~~1100~~ 749 ✅ | Вынесены tui/controllers (Modal/Connection/Session/Chat/ConfigOptions) + парсер tool-call (закрыл вклад в P0-2), фикс dispose (P2-17). Дальше к ~400 — только через BINDINGS/KeyboardManager (P2-16, UX-контракт) |
| `server/agent/context/gatherer.py` | ~~1048~~ 617 ✅ | Path-matching хелперы → `context/file_matching.py` (ABC не тронут, тела байт-идентичны) |

**Задачи:**
- [x] `core.py` — декомпозирован (2030 → 331)
- [x] `mcp/manager.py`, `mcp/client.py` — ниже 1000
- [x] `di.py` — разбит на пакет `di/` по доменам (2026-07-13)
- [x] `chat_view_model.py` — ReplayReducer в application + дедуп (1044→883, 2026-07-13)
- [x] `acp_transport_service.py` — пакет `acp_transport/` (PermissionResponder + RequestCallbackCoordinator), 1405→579 (2026-07-13)
- [x] `agent_loop.py` — разбит на пакет `agent_loop/` (loop/llm_caller/tool_processor/updates), 1352→все <750, residual-сложность снята (2026-07-14)
- [x] `gatherer.py` — path-matching хелперы → `context/file_matching.py` (1048→617, тела байт-идентичны, 2026-07-14)
- [x] `mcp/transport.py` — разнесён на пакет + честный корень MCPTransportError (2026-07-13)
- [x] `prompt.py` — пакет `prompt/` (normalization/validation/directives/tool_calls/client_requests/permission_response), тела байт-идентичны (2026-07-14)
- [x] `app.py` — вынесены tui/controllers + парсер tool-call (1100→749, P0-2/P2-17-dispose, 2026-07-13)

**Оценка:** 5 дней
**Критерий приемки:** все тесты проходят, нет нарушения зависимостей между слоями,
дробление архитектурно обосновано (не ради метрики). `messages.py` из критерия исключён
как оправданно крупный.

---

### 5. Обновить `textual` 0.43 → 8.x (мажорное обновление) — ✅ ЗАКРЫТО (2026-07-10)

> ✅ В `pyproject.toml` теперь `textual>=8.2.4` (в core и в extra `tui`, ранее `>=0.66.0` / `>=0.40`).
> Код фактически уже работал на 8.2.4 — декларация выровнена с реальностью. Изменение контракта:
> минимальная версия повышена, поведение не меняется.

Текущая версия `textual>=8.2.4`.

**Выполнено:**
- [x] Обновить `pyproject.toml` (обе границы → `>=8.2.4`)
- [x] Перегенерировать `uv.lock`
- [x] Прогнать TUI-тесты — весь suite (7285 passed), ruff чисто

> Примечание: подавляемые `DirectoryTree.watch_path` / `SearchInput` RuntimeWarning
> (`filterwarnings` в `pyproject.toml`) относятся к P0-3, а не к версии textual.

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

### 7. Обновить зависимости (минорные/патч) — ✅ ЗАКРЫТО (2026-07-10)

**Выполнено (2026-07-10):**
- [x] `anthropic` `>=0.20` → `>=0.97.0` (core + extra `server`) — устаревшая pre-1.0 нижняя граница выровнена с фактической.
- [x] `openai` `>=1.50.0` → `>=2.32.0` (core + extra `server`).
- [x] `pydantic` `>=2.11.0` → `>=2.13.3`.
- [x] `pydantic-settings` `>=2.0.0` → `>=2.14.0`.
- [x] `aiohttp` `>=3.12.15` → `>=3.13.5`.
- [x] `python-dotenv` `>=1.0.0` → `>=1.2.2`.
- [x] Удалён дублирующий `[project.optional-dependencies].dev` — оставлен канонический `[dependency-groups].dev` (PEP 735) как единственный источник истины.
- [x] Удалена мёртвая зависимость `tomli` — в коде используется stdlib `tomllib` (`requires-python >= 3.12`), `import tomli` нигде не встречается.

> Все изменения проверены: `ruff` чисто, 7285 тестов passed. Нижние границы выровнены с
> фактически установленными версиями; breaking changes (в т.ч. в `pydantic`) не обнаружены,
> поведение не меняется.

---

## P2 — Желательный (улучшение качества)

### 8. Устранить TODO — ✅ ЗАКРЫТО (2026-07-17)

| Файл | Строка | Описание | Статус |
|------|--------|----------|--------|
| ~~`client/tui/components/terminal_panel.py`~~ | ~~421~~ | ~~Реализовать копирование через pyperclip~~ | ✅ снят вместе с мёртвым компонентом |
| ~~`server/llm/fallback/orchestrator.py`~~ | ~~145~~ | ~~Реализовать buffering и переключение~~ | ✅ инлайн-TODO убран |

> **clipboard-TODO закрыт удалением мёртвого кода (2026-07-17):** анализ показал, что
> `TerminalPanel` (`terminal_panel.py`) **нигде не монтировался** в приложении — живой
> терминал рисует `TerminalOutputPanel` (`terminal_output.py`) через `ToolPanel`. Компонент
> существовал только ради экспорта и тестов (~30 инстанцирований, накрутка coverage).
> `TerminalPanel`/`TerminalSession`/`TerminalOutput`/`TerminalToolbar` удалены целиком (файл +
> экспорт из `components/__init__.py` + тесты `test_terminal_panel_coverage.py` и
> `TestTerminalSession`). Правка контракта: 4 имени убраны из публичного `components.__all__`
> (внешних потребителей нет — проверено). `make check` зелёный.

> **orchestrator-TODO убран без реализации (2026-07-17):** streaming buffering + переключение
> провайдера посреди стрима. `FallbackOrchestrator` **не инстанцируется** в проде (реальный
> fallback собирает `PromptOrchestratorBuilder`), фича семантически сложная (частичный вывод,
> дедуп, replay) — низкий ROI, вводить без запроса нельзя (минимальность CLAUDE.md). Инлайновый
> `# TODO` дублировал docstring, который штатно фиксирует ограничение («В MVP streaming fallback
> не поддерживается») — оставлен только docstring. Реализация — если появится реальный
> потребитель streaming-fallback.

**Итог:** TODO в `src` — **0** (`grep TODO/FIXME` пусто). Метрика достигнута.

**Задачи:**
- [x] clipboard-TODO — снят удалением мёртвого `TerminalPanel` (2026-07-17)
- [x] `orchestrator.py:145` — инлайн-TODO убран (ограничение остаётся в docstring)

---

### 9. Исправить ruff warnings — ✅ ЗАКРЫТО (2026-07-10)

> `ruff check .` теперь **0 нарушений** (было ~170). Массовые классы (D212, RUF001-003,
> FBT) устранены/в ignore; оставшиеся 6 (3× F401, 3× E501) исправлены в коммите
> `style(lint): устранить оставшиеся ruff-нарушения`.

---

### 10. Добавить coverage threshold в CI — ✅ ЗАКРЫТО (2026-07-16)

> Реализовано в коммите `ci: порог покрытия 85% и guardrail на размер файлов`.
> Badge добавлен 2026-07-16.

**Задачи:**
- [x] Добавить `pytest-cov` в dev-зависимости
- [x] Шаг CI `pytest --cov=src/codelab --cov-fail-under=85` (порог 85, факт 96%)
- [x] Бонус: guardrail `scripts/check_large_files.py` против новых God Objects
- [x] Добавить badge покрытия в README (статический `coverage ≥85%`, привязан к
      enforced-порогу CI — динамического источника Codecov нет, захардкоженный процент
      устарел бы; 2026-07-16)

**Оценка:** 0.5 дня

---

### 11. `ClientRPCService._wrap_future` — необработанное исключение future — ✅ ЗАКРЫТО (2026-07-10)

> ✅ Фикс: после `asyncio.wait` `_call_method` забирает исключение и у `future_task`
> (`if future_task in done: future_task.exception()`) — unretrieved-task больше не
> возникает; исключение по-прежнему пробрасывается через `pending_request.future`.
> **Убирает 16 tracebacks / 32 error-строки из прод-логов** при чтении нечитаемых
> файлов (напр. `*.db-shm`) — подтверждено анализом логов.
>
> Фильтр `PytestUnraisableExceptionWarning` пока **не** переведён в `error`: при попытке
> флипа всплыли order-dependent unraisable из других тестов (AsyncMock, см. P0-3a) —
> глобальный `error` даёт флаки. Полный флип — отдельная итерация P0-3.
>
> ✅ **Корень устранён (см. P2-20, закрыт 2026-07-15):** ранее `ContextGatherer` читал
> SQLite-сайдкары на каждом gather (анализ логов 2026-07-14: 10 error-строк за сессию);
> RPC-ошибка обрабатывалась тихо, но round-trips тратились, а лог засорялся. Теперь
> `is_binary` распознаёт `*.db-shm/-wal/-journal`, а `.codegraph` в `IGNORE_DIRS` —
> холостых чтений и связанных `-32603` больше нет.

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
- [x] После `asyncio.wait` `_call_method` забирает исключение и у `future_task`
      (`if future_task in done: future_task.exception()`) — unretrieved-task устранён
- [x] Тест на путь «RPC read → -32603»: нет unretrieved-task warning
- [x] Фильтр `PytestUnraisableExceptionWarning` снят/переведён в `error` в рамках P0-3
      (2026-07-15); корень (чтение SQLite-сайдкаров) добит в P2-20

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

### 13. Клиентский receive-loop падает на close-фреймах WebSocket — ✅ ЗАКРЫТО (2026-07-10)

**Файл:** `src/codelab/client/infrastructure/transport.py:207` (`receive_text`)

При штатном закрытии WebSocket сервером клиент получал control-фрейм
`WSMsgType.CLOSE/CLOSING/CLOSED` (в этой версии aiohttp `CLOSED=257`) и поднимал
`RuntimeError: Unexpected WebSocket message type`. Общий `except Exception` в
receive-loop трактовал это как `receive_loop_error` (**error**) и уходил в
error-каскад ретраев с backoff, роняя `session/load`.

**Фикс:** `receive_text` распознаёт close-типы и ERROR-фрейм и бросает
`WebSocketClosedError(ConnectionError)`. Receive-loop уже обрабатывает `ConnectionError`
мягче (`connection_lost_in_receive_loop`, **warning** + управляемый рестарт), а не как
непредвиденный тип. Прочие типы (BINARY) по-прежнему → `RuntimeError`.

**Тесты:** параметризованный на CLOSE/CLOSING/CLOSED + ERROR-фрейм в
`test_infrastructure_transport.py`.

**Обнаружено:** 2026-07-10 (каскад после P12).

---

### 15. TaskAnalyzer: холостой LLM-вызов на моделях без JSON-mode — ✅ ЗАКРЫТО (2026-07-15)

> ✅ Фикс (2026-07-15): введена честная capability `LLMCapabilities.supports_structured_output`
> (default `True` — поведение облачных провайдеров не меняется). Локальные бэкенды без
> гарантии `response_format=json` — `LMStudioProvider` и `OllamaProvider` — переопределяют
> её в `False` через `dataclasses.replace(super().capabilities, ...)` (DRY, прочие
> возможности сохраняются). `LLMBasedTaskAnalyzer.analyze` перед LLM-вызовом проверяет
> `self._llm.capabilities.supports_structured_output`: если `False` — сразу эвристика
> (`method=heuristic_no_structured_output`, лог уровня `info` как штатный сценарий), без
> холостого ~7-сек вызова. Тесты: пропуск LLM-вызова (`create_completion_calls == 0`),
> вызов при поддержке, capability lmstudio/ollama. 7313 тестов зелёные.
>
> Выбран вариант «пропускать LLM-анализ для провайдеров без JSON-mode» (переподтверждённый
> приоритет из наблюдений на 35B) вместо ужесточения промпта — корень в отсутствии
> гарантии structured output у локального провайдера, а не в размере модели.
>
> ✅ **Подтверждено рантаймом (2026-07-15, анализ логов `~/.codelab/logs`):** сессия на
> `lmstudio/google/gemma-4-26b-a4b`, сервер запущен 09:03:00 (local, +3) — на 23с **после**
> коммита фикса (09:02:37). За сессию: **0** `no_json_found` (было 4–14×), 2× новый путь
> `structured_output_unsupported → heuristic_no_structured_output`, `method=llm` — 0 раз.
> Латентность анализа задачи упала до **0.13–0.27 мс** против ~7000 мс холостого LLM-вызова.
> 0 error / 0 warning за всю сессию (ранее единственные warning'и были именно эти).

> **Исходный контекст.** Обнаружено при анализе логов реальной stdio-сессии
> (`~/.codelab/logs`, локальный `lmstudio/qwen3.6-35b`). Предупреждение `context.task_analyze.parse.no_json_found`
> `fallback_to=heuristic` возникает **на каждом** анализе задачи (14× за сессию):
> модель не возвращает валидный JSON, `response_preview` пуст.

**Причина:** `TaskAnalyzer` делает LLM-вызов (~7 сек на локальной модели), результат
не парсится → всегда fallback на эвристику (`search_terms_count=0, target_modules_count=0,
method=llm`). Для моделей без надёжного structured-output это чистая потеря латентности:
эвристика отработала бы сразу и с тем же результатом.

> **Переподтверждено (2026-07-14):** `no_json_found → heuristic` воспроизводится не только
> на маленькой `gpt-oss-20b`, но и на **35B** `qwen3.6-35b-a3b` (4× за сессию). То есть
> дело не в размере модели, а в отсутствии надёжного structured-output у локального
> провайдера (lmstudio не гарантирует `response_format=json`). Это усиливает приоритет
> второй задачи — **по умолчанию пропускать LLM-анализ для lmstudio** (сразу эвристика),
> а не пытаться ужесточать промпт.

**Задачи:**
- [x] Пропускать LLM-анализ (сразу эвристика) для провайдеров без structured output
      (`supports_structured_output=False`: lmstudio, ollama) — 2026-07-15
- [x] Ввести capability `supports_structured_output` (default True для облачных провайдеров)
- [x] Логировать пропуск как штатный сценарий (`info`, `method=heuristic_no_structured_output`)
- [ ] Опционально: включить `response_format=json` для провайдеров с поддержкой (ортогональное
      улучшение — сейчас такие провайдеры и так идут по LLM-пути с ручным парсингом JSON)

**Оценка:** 0.5 дня
**Критерий приемки:** нет холостых LLM-вызовов TaskAnalyzer для моделей без JSON-mode;
латентность `context.build` для локальных моделей снижена. ✅ Достигнуто.

---

### 16. Рассинхрон `BINDINGS` ↔ `KeyboardManager.DEFAULT_BINDINGS` — ✅ ЗАКРЫТО (2026-07-16)

> ✅ Фикс (2026-07-16), консолидация в один источник без изменения UX:
> - **Канон = фактически работавший `App.BINDINGS`** (ноль молчаливых изменений клавиш).
>   `KeyboardManager.DEFAULT_BINDINGS` переписан ровно под него (`ctrl+p`→command_palette,
>   `ctrl+k`→previous_session, `ctrl+s`→focus_session_list; конфликтующие KM-only записи
>   `toggle_plan_panel`/`toggle_tool_panel`/`focus_sidebar` убраны; добавлены select_*).
> - **Единый источник:** `App.BINDINGS = get_default_textual_bindings()` — собирается из
>   `DEFAULT_BINDINGS` (keyboard_manager.py), хардкод-списка в app.py больше нет.
> - **Справка из того же источника:** `HelpModal._render_hotkeys()` строит список из
>   `get_keyboard_manager().get_help_groups()` (убран третий захардкоженный набор в
>   help_modal.py).
> - **Guardrail:** `tests/client/tui/test_keybindings_single_source.py` — App.BINDINGS ≡
>   DEFAULT_BINDINGS, нет дублей клавиш/действий, каждый action имеет `action_*` в App
>   либо в замороженном списке известных пробелов.
>
> **Смежный пробел (4 мёртвых биндинга) — ✅ ЗАКРЫТ (2026-07-16):** биндинги
> `retry_prompt`, `clear_chat`, `open_terminal_output`, `cycle_focus` были объявлены в
> раскладке, но не имели `action_*` обработчиков в App (и палитра команд для них молча
> ничего не делала — оба пути идут через `App.action(...)`). Резолюция — по факту наличия
> backing-логики, а не «всё реализовать / всё убрать»:
> - **Реализованы** `clear_chat` (Ctrl+L → `action_clear_chat` → `ChatController.clear_chat`
>   → готовый протестированный `ChatViewModel.clear_chat_cmd`) и `cycle_focus`
>   (Tab → `action_cycle_focus` → `self.screen.focus_next()`; заодно снят мёртвый перехват
>   Tab, ломавший дефолтную фокус-навигацию Textual).
> - **Убраны из раскладки и палитры** `retry_prompt` и `open_terminal_output` — под ними
>   нет никакой логики (retry не существует в клиенте; `TerminalLogModal` нигде не
>   инстанцируется, нет понятия «текущий терминал»). Их реализация = новая фича, что
>   противоречит минимальности CLAUDE.md; вводить без запроса нельзя.
> - Guardrail-набор `_KNOWN_ACTIONS_WITHOUT_HANDLER` опустошён (`set()`): теперь любой
>   новый биндинг без обработчика заваливает тест. `make check` — 7254 passed, ruff/ty чисты.

> Обнаружено при анализе `client/tui/app.py` (P1-4). `App.BINDINGS` захардкожены списком,
> а `KeyboardManager` (`components/keyboard_manager.py`) с его `DEFAULT_BINDINGS` и методом
> `get_textual_bindings()` **не подключён**. Наборы расходятся — один и тот же аккорд означает
> разное действие:
> - `ctrl+p`: app.py → `command_palette`, keyboard_manager → `toggle_plan_panel`.
> - `previous_session`: app.py → `ctrl+k`, keyboard_manager → `ctrl+shift+k`.
> - `command_palette` в keyboard_manager → `ctrl+k`.

**Причина:** два источника истины о клавишах. Реальное поведение — по `App.BINDINGS`;
`KeyboardManager` фактически декоративен (`get_help_groups()`/`get_textual_bindings()` не вызываются).

**Это контракт UX** — не размер. Механическая подмена `BINDINGS` на `get_textual_bindings()`
молча изменит горячие клавиши. Требуется явное решение, какой набор канонический.

**Задачи:**
- [x] Согласован канонический набор (= фактически работавший `App.BINDINGS`, ноль
      молчаливых изменений клавиш)
- [x] `App.BINDINGS = get_default_textual_bindings()` — единственный источник из `DEFAULT_BINDINGS`
- [x] `HelpModal._render_hotkeys()` кормится из `get_keyboard_manager().get_help_groups()`
- [x] Guardrail `test_keybindings_single_source.py` (App.BINDINGS ≡ DEFAULT_BINDINGS, нет
      дублей, каждый action имеет обработчик)

**Оценка:** 0.5 дня
**Критерий приемки:** один источник клавиш; UX-изменения (если набор меняется) отмечены как контракт.

---

### 17. `NavigationManager` не подключён + утечка `dispose()` — ✅ ЗАКРЫТО (2026-07-16)

> ✅ Резолюция (2026-07-16, вариант A — удаление неадоптированной абстракции):
> - Часть «утечка `dispose()`» была устранена ранее (вызов в `on_unmount`).
> - Часть «не подключён»: анализ показал **принципиальное несоответствие**
>   `NavigationManager` (async-очередь + tracker + VM-visibility-подписки + on-show
>   callback) реальному паттерну модалок приложения (`push_screen(modal, callback=…)`
>   с возвратом результата dismiss). `show_screen()` не умеет прокидывать результат
>   dismiss — «подключение» селекторов (model/config/command palette) через менеджер
>   **сломало бы** callback выбора. Абстракция (950 строк: manager/queue/tracker/
>   operations) в production только инстанцировалась и `dispose`-илась, в навигации не
>   участвовала (все модалки — через `ModalController` + нативный `push_screen`, inline-
>   permission — через собственную очередь, см. #19).
> - **Удалён** пакет `client/tui/navigation/`, его создание/`dispose`/импорт в `app.py`,
>   выделенные тесты (`test_navigation_manager/tracker/queue`, `tui/navigation/`) и
>   lifecycle-тест в `test_app_coverage.py`. Устаревшие комментарии «NavigationManager
>   сам удалит виджет» в `file_viewer.py`/`terminal_log_modal.py` поправлены.
> - `make check` — 7235 passed (−101 nav-тест), ruff/ty чисты.
>
> Решение по варианту A согласовано явно (удаление функциональности). Wiring (вариант C —
> полноценный слой модалок с dismiss-результатом) отклонён как крупный low-ROI при живом
> `ModalController`.

> Обнаружено при анализе `client/tui/app.py` (P1-4). `NavigationManager` создаётся в
> `on_ready`, но нигде не используется: все модалки идут напрямую через `push_screen`/
> `pop_screen`, минуя очередь операций и трекер менеджера. Кроме того, `dispose()` не
> вызывается в `on_unmount` — ресурсы менеджера (подписки/операции) не освобождаются.

**Задачи (сняты выбором варианта A — удаление неадоптированной абстракции):**
- [x] Утечка `dispose()` устранена (вызов в `on_unmount`) до удаления
- [x] Вместо wiring — `NavigationManager` удалён целиком (несовместим с паттерном
      `push_screen(callback=…)`); все модалки идут через `ModalController` + нативный
      `push_screen`. См. блок резолюции выше.

**Оценка:** 0.5 дня (в основном закрывается декомпозицией app.py)
**Критерий приемки:** модалки идут через менеджер; `dispose()` вызывается; нет утечки.

---

### 18. Обрезка `terminal_id` → зацикливание terminal/create — ✅ ЗАКРЫТО (2026-07-16)

> ✅ Фикс (2026-07-16, вариант A — серверный alias, детерминированный): введён
> `TerminalAliasRegistry` (`server/tools/executors/terminal_alias_registry.py`),
> который маппит короткий alias `term_<n>` (счётчик сессии) → настоящий client-side
> `terminalId`. Состояние живёт в `SessionState.terminals`/`terminal_counter`
> (schema_version 4 → 5, миграция `setdefault`). `TerminalToolExecutor.execute_create`
> отдаёт LLM alias (в `output`/text-content/metadata/raw_output), а client-facing
> terminal content-item сохраняет родной client `terminalId` — ACP-контракт не нарушен.
> `execute_wait_for_exit`/`execute_release` резолвят alias → client id перед вызовом
> bridge; `execute_release` снимает alias. Неизвестный/освобождённый alias → `failed`
> с внятным сообщением и логом уровня **error** (`terminal_alias_not_found`), без
> обращения к bridge — recreate-loop исключён. Короткий alias устраняет саму
> поверхность обрезки (LLM больше не переписывает 36-символьный UUID); решение
> серверное, поэтому работает с **любым** ACP-клиентом, включая сторонний.
>
> Клиентский defense-in-depth (шаг 5 плана) намеренно не делался: серверный alias
> закрывает корень детерминированно, а клиентский fuzzy-resolve по префиксу
> реинтродуцировал бы вероятностную неоднозначность (минимальность изменений).
>
> Тесты: `test_terminal_alias_registry.py` (реестр), `TestTerminalAliasRoundTrip` в
> `test_terminal_executor_terminal_content.py` (регресс #18: alias→client id, unknown
> alias без bridge, release снимает alias), миграция v4→v5 в
> `test_session_state_migration.py`. `make check` — 7324 passed, ruff/ty чисты.

> Обнаружено при рантайм-тестировании P1-4 (шаг 3). Агент/LLM теряет символы в
> длинном 36-символьном `terminalId` при обратной передаче: клиент создаёт терминал
> и отдаёт серверу полный id (напр. `…af3167b3f16a`), но последующие
> `terminal/output` / `terminal/wait_for_exit` приходят с обрезанным id
> (`…af3167b3f`) → `TerminalOutputHandler`/`TerminalWaitHandler` возвращают
> `Terminal not found` (-32603) → агент считает терминал неработающим и **пересоздаёт**
> его, каждый раз запрашивая permission. Пользователь наблюдает бесконечные
> подтверждения terminal/create, терминал «не выполняется».

**Диагноз:** НЕДЕТЕРМИНИРОВАННО — в той же сессии другой терминал отрабатывает с
полным id. Это НЕ баг кода клиента (иначе резало бы всегда одинаково): сервер имеет
полный id в tool-result, обрезает уже на исходящем `terminal/output` → потеря на
стороне агента/LLM-транскрипции. Клиентский dispatcher/executor и P1-4-рефактор
транспорта здесь ни при чём (permission/RPC-путь верифицирован здоровым).

> **Переподтверждено (2026-07-14), модель-независимо.** Свежая сессия на
> `lmstudio/google/gemma-4-26b-a4b` (ранее — `gpt-oss-20b`): id
> `6c8323e0-08bb-4a20-944e-1aeb85afedb` = **35 символов** (сегменты `[8,4,4,4,11]`,
> последний блок 11 вместо 12 — потеря ровно одного hex-символа). Ошибки на **обоих**
> хендлерах — `terminal/output` и `terminal/wait_for_exit` (-32603). За сессию: **43**
> вызова `terminal/create`, **10** permission-запросов — тот самый recreate-loop с
> бесконечными подтверждениями. Подтверждает: дефект воспроизводится на разных
> моделях → нельзя полагаться на дословную транскрипцию UUID агентом (приоритет
> первой задачи — короткие/валидируемые id + fuzzy-resolve по префиксу).

**Где порождается id (проверено в коде, 2026-07-16):** `terminalId` генерирует
**клиент** — `terminal/create` в ACP это клиентская capability. Наружу отдаётся полный
36-символьный UUID `str(uuid.uuid4())`
(`client/presentation/chat/executors/terminal_callback_executor.py:111`); сервер лишь
ретранслирует то, что вернул клиент (`server/tools/executors/terminal_executor.py:122-161`),
и на `terminal/output`/`wait_for_exit` проксирует id из tool-call LLM клиенту **как есть**,
без lookup/резолва. Серверного реестра `terminalId` нет: в `SessionState` (`state.py`)
есть `tool_calls`, но нет `terminals`/`active_terminals`. Обрезка возникает на границе
**LLM → сервер** (агент теряет символ при дословной ретрансляции длинного UUID), а клиент
лишь детектит промах последним.

**Архитектурное решение:** корректное место слоя устойчивости — **сервер**, потому что
(1) порча значения входит в систему на выходе LLM (серверная сторона), (2) при работе со
**сторонним ACP-клиентом**, за который мы не отвечаем, клиентский фикс неприменим —
укоротить id или добавить fuzzy-resolve в чужой клиент нельзя, а отдавать клиенту id,
отличный от выданного им, = нарушение ACP-контракта. Серверное решение работает с любым
клиентом и покрывает наш собственный клиент бесплатно.

**Выбранный вариант — A (серверный alias, детерминированный):** сервер присваивает
терминалу короткий валидируемый alias, показывает LLM alias, хранит `alias → client
terminalId` в сессии и переводит обратно при исходящем RPC. Клиент всегда видит родной
id → контракт цел; LLM больше не оперирует хрупким 36-символьным UUID.
Вариант B (серверный fuzzy-resolve по префиксу) отклонён как вероятностный (неоднозначность
префиксов → промах) — оставлен только как клиентский defense-in-depth для нашего клиента.

**Задачи (по шагам):**
- [x] **1. Реестр в `SessionState`** (`server/protocol/state.py`): поля
      `terminals: dict[str, str]` + `terminal_counter`. Bump `schema_version` 4 → 5
      + ветка `migrate_schema` (`setdefault`).
- [x] **2. Генерация alias при create** (`terminal_executor.py::execute_create` через
      `TerminalAliasRegistry.register`): короткий alias `term_<n>`; в
      `output`/text-content/metadata/raw_output — alias, в client terminal content-item —
      родной client id.
- [x] **3. Обратный перевод при исходящих RPC** (`execute_wait_for_exit`,
      `execute_release`): `_resolve_terminal` перед вызовом bridge; `release` снимает alias.
- [x] **4. Явная ошибка контракта:** неизвестный/освобождённый alias → `failed` с
      понятным сообщением, лог `terminal_alias_not_found` уровня **error**, без bridge.
- [ ] **5. Клиентский defense-in-depth — НЕ ДЕЛАЛСЯ (осознанно):** серверный alias
      закрывает корень детерминированно; клиентский fuzzy-resolve реинтродуцировал бы
      вероятностную неоднозначность (минимальность изменений).
- [x] **6. Тесты:** `test_terminal_alias_registry.py`; `TestTerminalAliasRoundTrip`
      (`test_terminal_executor_terminal_content.py`); миграция v4→v5
      (`test_session_state_migration.py`). `make check` — 7324 passed.

**Рантайм-подтверждение (2026-07-16, `~/.codelab/logs`, сессия `sess_f969f659d978`):**
7× `terminal/create`, каждый с парным `wait_for_exit` — все без ошибок. `terminal_id`
в metadata — короткий alias (`term_1`, `term_2`; `project_structure` читает именно
`metadata["terminal_id"]`), т.е. LLM-facing id стал alias'ом. **0 errors, 0 warnings,
ноль `Terminal not found`/`-32603`/recreate-loop** за сессию.

**Оценка:** 1–1.5 дня (основное — шаги 1-4 на сервере + миграция схемы).
**Критерий приемки:** terminal/create → terminal/wait_for_exit проходит без
`Terminal not found` при работе с любым ACP-клиентом; LLM оперирует коротким alias,
клиент видит свой родной id (ACP-контракт цел); агент не пересоздаёт терминал в цикле;
миграция схемы сессии 4 → 5 покрыта тестом.

---

### 19. Второй permission-модал не реагирует на клик — ✅ ЗАКРЫТО (2026-07-16)

> ✅ Фикс (2026-07-16), две причины:
> - **Фокус** (`permission_request.py`): `PermissionRequest` (виджет-`Static`) не забирал
>   фокус, кнопки монтировались асинхронно. Добавлен `_focus_default_action` через
>   `call_after_refresh` в `on_mount` — фокус на кнопку Allow после монтирования кнопок
>   (как в старом `permission_modal.py`). Второй/последующий модал сразу принимает ввод.
> - **Очередь + протокольный дефект** (`chat_view_permission_manager.py`): раньше второй
>   запрос вытеснял первый напрямую → `on_choice` первого не отправлялся (сервер без
>   ответа) + оверлей двух виджетов (гонка клика). Введена очередь `_queue`: новые
>   запросы не вытесняют неотвеченный, а показываются после `is_visible → False`
>   отложенно (`call_after_refresh` — `remove()` старого завершается до `mount` нового).
>   `message` вынесен в `PermissionWidgetInfo` для корректного рендера отложенного запроса.
>
> Тесты: `test_tui_permission_request.py` — фокус-guard, второй запрос в очереди (первый
> не вытеснен), показ следующего после разрешения текущего. `make check` — 7332 passed.
> Живым TUI не проверялось (headless-драйв интерактива недоступен): фокус — тест guard,
> очередь — юнит-тесты менеджера.

> Обнаружено при рантайм-тестировании P1-4. Когда агент делает несколько tool-call'ов
> подряд (напр. два terminal/create), второй permission-модал визуально появляется, но
> плохо/не нажимается. Лог: виджет монтируется чисто (`show_permission_request_start
> has_existing_widget=False` → `permission_widget_mounted`), т.е. дубля виджетов нет —
> проблема в фокусе/маршрутизации ввода TUI-слоя.

**Диагноз:** не связано с P1-4 (permission-путь транспорта/PermissionResponder
верифицирован; модал доходит и обрабатывается на уровне транспорта). Локализация — TUI
(`PermissionRequest` widget / `permission_container` / фокус после смены модалок).

**Задачи:**
- [x] Причина локализована: (1) фокус не забирался вновь смонтированным `PermissionRequest`,
      (2) второй запрос вытеснял неотвеченный первый (оверлей + протокольный дефект).
- [x] Фикс: `_focus_default_action` через `call_after_refresh`; очередь `_queue` в
      `chat_view_permission_manager.py`. Тесты в `test_tui_permission_request.py`.

**Оценка:** 0.5-1 день
**Критерий приемки:** второй и последующие модалы принимают клик без задержки.

---

### 20. SQLite-сайдкары `*.db-shm/-wal` не фильтруются в ContextGatherer — ✅ ЗАКРЫТО (2026-07-15)

> ✅ Фикс в `context/file_matching.py` (2026-07-15):
> - `BINARY_EXTENSIONS` дополнен сайдкарами WAL-режима: `.db-shm`/`.db-wal`/`.db-journal`
>   + `.sqlite-shm`/`.sqlite-wal`/`.sqlite-journal` (не оканчиваются на `.db`, поэтому
>   старый `endswith('.db')` их пропускал). `is_binary('...db-shm')` теперь `True`.
> - `.codegraph` добавлен в `IGNORE_DIRS` (директория индекса codegraph — не контекст),
>   рядом с уже присутствующими `.codelab`/`.cocoindex_code`.
> - Тесты: `TestIsBinary` (параметризован на сайдкары + негатив на исходники),
>   `TestFilterPaths::test_filters_codegraph_dir`. Детерминизм `filter_paths` сохранён
>   (порядок и логика не тронуты), 7309 тестов зелёные.
>
> ✅ **Подтверждено рантаймом (2026-07-15, анализ логов `~/.codelab/logs`):** сессия на
> `lmstudio/google/gemma-4-26b-a4b` над проектом `flutter_app`, в котором реально лежат
> `.codegraph/codegraph.db` + `.db-shm` + `.db-wal`. Сервер запущен 08:07:48 (local, +3)
> — на 2m44s **после** коммита фикса (08:05:04); editable-install загрузил исправленный
> модуль (`.codegraph ∈ IGNORE_DIRS`, `is_binary('*.db-shm') == True` — проверено). За
> сессию: **0** чтений `*.db-shm`, **0** связанных `-32603` (упоминания `codegraph` в логе
> — только MCP-сервер codegraph, не чтения БД). Тот самый сценарий, что в описании давал
> ~5 чтений/сборку — теперь ноль.



> Обнаружено при анализе логов реальной stdio-сессии (`~/.codelab/logs`, локальный
> `lmstudio/gpt-oss-20b`, проект с индексом codegraph). На **каждом** `context.gather`
> `ContextGatherer` обнаруживает `<project>/.codegraph/codegraph.db-shm` как кандидата
> и пытается прочитать его через ACP `fs/read_text_file` → `RPC Error -32603`
> (~5 чтений за сборку, 10+ error-строк за сессию). Gather при этом отрабатывает
> (`files_gathered=8`) — graceful degradation держит горячий путь, но round-trips
> тратятся, а лог засоряется. Это недобитый корень P2-11 (там устранён только
> unretrieved-task traceback).

**Причина (проверено в коде):**
- `context/file_matching.py::is_binary('...db-shm')` → `False`: в `BINARY_EXTENSIONS`
  есть `.db`/`.sqlite`/`.sqlite3`, но нет `.db-shm`/`.db-wal`/`.db-journal` (они не
  заканчиваются на `.db`).
- `.codegraph` отсутствует в `IGNORE_DIRS`.

**Задачи:**
- [x] Добавить `.codegraph` в `IGNORE_DIRS` (директория индекса codegraph — не контекст).
- [x] Распознавать SQLite-сайдкары в `is_binary` (`.db-shm`/`.db-wal`/`.db-journal`
      + `.sqlite-*`); детерминированный вывод сохранён.
- [x] Unit-тест: `is_binary` для `.db-shm/.db-wal`, `filter_paths` отсекает `.codegraph/`.

**Оценка:** 0.5 дня
**Критерий приемки:** нет чтений `*.db-shm` при gather; 0 связанных `-32603` в логах;
детерминизм `filter_paths`/baseline_fingerprint сохранён.

---

### 21. Неизвестный tool доходит до permission и падает после одобрения — ✅ ЗАКРЫТО (2026-07-16)

> ✅ Фикс (2026-07-16):
> - **Ранний reject неизвестного tool** (`tool_processor.py`): в
>   `_process_single_tool_call` после `tool_registry.get(...)` при `tool_definition is
>   None and not is_mcp` вызывается новый `_reject_unknown_tool` — **до** ветки решения
>   и `_pause_for_permission`. LLM получает `failed` с сообщением «Неизвестный инструмент
>   'X'. Доступные инструменты: [...]» и логом уровня **error** `tool not found in
>   registry`; permission-запрос не отправляется, `execute_tool` не вызывается. Условие
>   `not is_mcp` сохраняет прежний путь для MCP-инструментов (их нет в локальном реестре,
>   но они валидны). Поздний guard `registry.py:206` оставлен как defense-in-depth.
> - **Валидация path в fs read** (`filesystem.py::read_handler`): пустой/пробельный/
>   отсутствующий `path` → `failed` до RPC; путь-директория (`Path(...).is_dir()`) →
>   `failed` с понятным сообщением вместо сырого `-32603`/`-32002`.
>
> Тесты: `test_agent_loop_coverage.py::...unknown_tool_rejected_before_permission`;
> `test_filesystem.py::TestReadHandlerValidatesPath` (пустой путь параметризованно +
> директория). Два теста permission-flow в `test_prompt_orchestrator.py` опирались на
> старое (багованное) поведение — им зарегистрирован реальный `fs/read_text_file`
> (`requires_permission=True`). `make check` — 7329 passed, ruff/ty чисты.
>
> **Рантайм (2026-07-16, `~/.codelab/logs`, `sess_3d47f1c38e91`):** сам баг (галлюцинация
> tool) в прогоне не всплыл (недетерминирован), поэтому reject-путь верифицирован
> тестами, а не логом. Зато лог **положительно подтверждает не-регрессию MCP-ветки**:
> `mcp:codegraph:codegraph_files` (`is_mcp=True`, нет в локальном реестре) прошёл
> `decision=ask` → permission → `executing MCP tool` — ранний reject его не перехватил.

> Обнаружено при анализе логов реальной stdio-сессии. Локальная модель
> (`gpt-oss-20b`) выдаёт галлюцинированный tool-call `ls`, которого нет в реестре
> (`update_plan`, `fs/read_text_file`, `fs/write_text_file`, `terminal/*`). Он
> **проходит permission-запрос, пользователь одобряет — и только затем** падает:
> ```
> executing pending tool after permission approval  tool_name=ls
> [error] tool not found in registry  acp_tool_name=ls  registered_tools=[...]
> ```
> (2× за сессию, call_006/call_008). Пользователь одобряет несуществующий инструмент,
> получает `failed` без содержимого.

**Диагноз:** в `ToolCallProcessor._process_single_tool_call` для неизвестного tool
(`tool_definition is None`, не MCP) решение уходит в policy → `ask` → permission на
несуществующий инструмент. Проверка «есть ли tool в реестре» происходит поздно —
в `_run_tool` уже после permission approval.

**Задачи:**
- [x] Отклонять неизвестный tool на этапе создания (до permission): вернуть LLM
      явный результат «unknown tool `X`, available: [...]» и статус `failed`.
- [x] Родственно: `fs/read_text_file` по пути-директории или пустому пути даёт
      `-32603`/`-32002` — добавлена валидация path перед RPC (не пустой; не директория).
- [x] Тест: галлюцинированный tool → `failed` без permission-запроса; read по dir/пустому пути → внятная ошибка.

**Оценка:** 0.5-1 день
**Критерий приемки:** неизвестный tool не доходит до permission; read по каталогу/
пустому пути отклоняется с понятным сообщением, а не сырым RPC-кодом. ✅ Достигнуто.

---

### 22. Нет защиты от зацикливания агента на повторяющемся tool-call — ✅ ЗАКРЫТО (2026-07-16)

> ✅ Фикс (2026-07-16): выделенный `ToolLoopDetector`
> (`.../agent_loop/loop_detector.py`), который `ToolCallProcessor` композирует (создаётся
> per-turn вместе с процессором → состояние сбрасывается сменой turn).
> - **Сигнал цикла — повтор команды**: сигнатура `имя tool + json(args, sort_keys)`.
>   Считаются вхождения сигнатуры за turn (`register_attempt`, в `_process_single_tool_call`
>   до permission/исполнения). При count > лимита вызов отклоняется `_reject_looping_tool`:
>   LLM получает `failed` с подсказкой и последним выводом команды, лог `warning
>   tool_call_loop_detected`. Ни повторного исполнения, ни лишнего permission-запроса.
> - **Ключевой урок (первый вариант был неверен):** нельзя завязываться на «идентичный
>   результат» и «строго подряд». Реальный цикл — `terminal/create(fvm flutter analyze)`
>   ↔ `wait_for_exit`: create каждый раз возвращает НОВЫЙ terminal id (результат
>   различается), а wait с разными id разрывает «подряд». Детекция — по повтору
>   **команды (tool+args)**, независимо от результата и устойчиво к чередованию
>   (`wait_for_exit` с разными `terminal_id` → разные сигнатуры, не флагаются).
> - **Feature-flag из конфига:** `AgentConfig.tool_loop_guard_limit` (default 3, env
>   `CODELAB_AGENT_TOOL_LOOP_GUARD_LIMIT`, `0` отключает); проводка `config.agent.*` →
>   `di/pipeline` → `LLMLoopStage` → `AgentLoop` → `ToolCallProcessor` (как `streaming_enabled`).
>
> Архитектура: детекция вынесена из процессора в самостоятельный класс без зависимостей
> (по образцу `TerminalAliasRegistry`, #18) — SRP, mock-free юнит-тесты, заменяемая
> политика. Тесты: `test_loop_detector.py` (детектор напрямую), `test_tool_loop_guard.py`
> (интеграция в процессор), `test_config.py` (дефолт/env флага). `make check` — 7250 passed.
>
> ✅ **Подтверждено рантаймом (2026-07-16, `~/.codelab/logs`), дважды:**
> - `sess_62d60fa834aa` (инлайн-версия): 3× `tool_call_loop_detected` (repeat 4/5/6);
> - `sess_7f3b7e58b3c3` (после рефакторинга): 1× (repeat 4), call_028 заблокирован —
>   только `tool_call_created` + warning, **без `permission_request_sent`/`executing
>   pending tool`**, после блокировки **0** новых `terminal/create` (цикл прерван),
>   0 errors. Ложных срабатываний нет (разные команды проходят нормально).
>
> **Ограничение:** счётчик per-turn (сбрасывается на новом prompt). Основной кейс
> (storm внутри одного turn) покрыт и подтверждён; кросс-turn повторы под контролем
> пользователя не отслеживаются намеренно.

> Обнаружено при анализе логов реальной stdio-сессии (`~/.codelab/logs`, сессия
> `sess_f6813d9cbc59`, модель `lmstudio/google/gemma-4-26b-a4b`). В ответ на один промпт
> агент подряд запускал терминалы, из них **12 раз — голый `fvm` без аргументов**
> (`command=fvm`, `args=[]`), каждый раз получая один и тот же usage-вывод и `exit_code=0`,
> и снова звал `fvm`. Пользователь наблюдал exec-инструменты «по кругу».

**Диагноз:** это **не дефект инфраструктуры** — терминалы создавались штатно (полные id,
без recreate-loop из #18), вывод доставлялся агенту (`has_output=True`, `success=True`),
`term_N`-алиасы работали. Крутит **сама модель** (средний локальный бэкенд повторяет
no-op команду, не продвигаясь). Дефект в том, что на стороне сервера **нет детектора
зацикливания**: одинаковые подряд tool-call'ы (`command`+`args` с тем же результатом)
ничем не отсекаются, `max_turn_requests` через permission-gated resume не спасает.

**Предложение реализовано (`ToolLoopDetector`, см. блок резолюции выше):**
- [x] Детектор повтора tool-call'ов по сигнатуре `tool_name` + `json(args, sort_keys)`
      в рамках turn. **Уточнение при реализации:** завязка на «идентичный результат» и
      «строго подряд» оказалась неверной (create → новый id, wait разрывает подряд) —
      детектим по повтору команды, устойчиво к чередованию.
- [x] При срабатывании — LLM получает `failed` с подсказкой и последним выводом; без
      повторного исполнения и лишнего permission-запроса.
- [x] Порог за feature-flag (`AgentConfig.tool_loop_guard_limit`, default 3, env,
      `0` отключает); легитимные повторы с разными args не затрагиваются.

**Оценка:** 0.5-1 день. Это mitigation против слабых локальных моделей, а не исправление
бага — приоритет ниже открытых UX-пунктов.
**Критерий приемки:** серия одинаковых no-op tool-call'ов прерывается подсказкой/стопом,
легитимные повторы с разным результатом не затрагиваются.

---

### 23. Потеря output terminal-результата при ненулевом exit code — ✅ ЗАКРЫТО (2026-07-16)

> Обнаружено пользователем при `fvm flutter analyze`: команда завершается с exit code 1
> (найдены проблемы) + выдаёт список из 9 ошибок в stdout, но LLM получал только
> `"Tool execution failed"` без деталей. Модель не знала, что чинить → повторяла analyze
> → цикл (тот самый, что страховал #22). Это **корневая причина**, а не симптом.

**Диагноз (проверено в коде):** `terminal/wait_for_exit` при exit≠0 возвращает
`ToolExecutionResult(success=False, output=<issues>, error=None)`. Дальше
`_add_tool_result_to_history` строил `content = output if success else (error or "Tool
execution failed")` → при `success=False` брался `error` (None) → `"Tool execution
failed"`, а `output` со списком проблем **выбрасывался**. Permission-путь
(`execute_pending`) был ещё грубее — передавал `output=None` явно. Пользователь видел
проблемы в UI (терминальный виджет), но LLM — нет. Асимметрия: ненулевой exit code — это
**данные**, а не сбой инструмента.

**Фикс (`tool_processor.py`):**
- `_add_tool_result_to_history`: при неуспехе сохраняет `output` (+ `error`), а не
  затирает на `"Tool execution failed"`.
- `execute_pending` (failure-ветка): пробрасывает `result.output` в историю/нотификацию/
  `ToolResult`, а не `None`.
- `_build_notification_content`: отдаёт `output` и при `success=False` (консистентность с UI).
- Observability: INFO-лог `tool_result_to_history` (`success`, `content_len`,
  `content_preview`) — видно, что реально уходит в историю LLM.

**Тесты:** `test_agent_loop.py` — output сохраняется при неуспехе; output+error
комбинируются; старые кейсы (`"Tool execution failed"` при пустом output) держатся.
`make check` — 7252 passed.

> ✅ **Подтверждено рантаймом (2026-07-16, `~/.codelab/logs`, `sess_b25e41e99a3b`, pipx):**
> `tool_result_to_history success=False content_len=2006 content_preview="Analyzing
> flutter_app... error • Missing concrete implementation ... non_abstract_class_inherits_
> abstract_member ..."` — полный вывод analyze доходит до LLM. `"Tool execution failed"`
> в истории — **0 раз**. Даже ошибочный `fvm --delete-conflicting-outputs` доносит
> usage-текст (LLM может самокорректироваться).

---

### 24. `[llm.fallback]` парсится, но не подключён к исполнению — 🟡 ЧАСТИЧНО (2026-07-17)

> **Контекст.** Пакет `server/llm/fallback/` (`FallbackOrchestrator`, `FallbackStrategy`/
> `SequentialFallback`, `CircuitBreaker`, `FallbackConfig`) реализует отказоустойчивость
> между несколькими LLM-провайдерами (упал один → перейти к следующему). Проверено:
> `FallbackOrchestrator`/`FallbackStrategyFactory`/`SequentialFallback` инстанцируются
> **только в тестах**; `config.llm.fallback` парсится из TOML-секции `[llm.fallback]`, но
> **нигде в рантайме не читается** — `di/llm.py` выбирает один активный провайдер, без
> переключения при сбое. Итог: `[llm.fallback] enabled = true` выглядит рабочим, но молча
> ничего не делает (**ложный конфиг-контракт**).

**Решение НЕ удалять** (в отличие от мёртвого `TerminalPanel`, P2-8): по роадмапу CodeLab
растёт в многопользовательский хостируемый сервис, где multi-provider gateway (пул
провайдеров + аптайм + circuit breaking) — оправданный задел. Пакет сохранён.

**✅ Сделано (честный контракт, дёшево, 2026-07-17):** `RegistryProvider.get_llm_registry`
при `config.llm.fallback.enabled` логирует `warning` `llm fallback configured but not
active` (hint: секция экспериментальная, переключение при сбое не выполняется). Убирает
вред от ложного поля, не трогая исполнение. Тесты: warning при enabled=true / отсутствие
при false (`test_integration_config.py::TestFallbackConfigHonestContract`). ruff/ty чисты,
6/6 тестов зелёные.

**⬜ Осталось (полная проводка — когда gateway-эпик встанет в работу):** в `di/llm.py`
читать `config.llm.fallback`, собирать `SequentialFallback` + `FallbackOrchestrator` вокруг
провайдеров из registry; продумать UX «тихого» переключения модели (разные модели → разное
поведение агента); достроить streaming-fallback (`execute_streaming` сейчас берёт первый
провайдер) и объявленные, но отсутствующие стратегии (`CostFallback`/`LatencyFallback`/
`SmartFallback`).

**Оценка:** проводка — 1–1.5 дня (отдельная фича, не входит в текущий объём).
**Критерий приемки (для полной проводки):** при `enabled=true` и ≥2 провайдерах сбой
активного провайдера прозрачно переключает на следующий; конфиг перестаёт быть
предупреждающим.

---

### 25. Асимметрия success/exception-веток в `agent_loop`: exception-ветка не доставляет tool_call_update немедленно — ✅ ЗАКРЫТО (2026-07-17)

> ✅ **Фикс (2026-07-17):** в except-ветке `_execute_allowed_tool_call`
> `buffer_and_save_tool_update` → `await emit_and_save_tool_update` — теперь failed-статус
> доставляется немедленно через callback (как success-ветка), а не оседает в буфере до
> конца turn'а. `emit()` безопасен в except: `_send_immediately` сам ловит свои ошибки и
> падает в буфер. Осиротевший `SessionUpdateSink.buffer_and_save_tool_update` (единственный
> прод-вызов был здесь) удалён вместе с юнит-тестом; docstring `buffer_only` очищен от
> упоминания exception-ветки (остался permission-путь). Тест
> `test_tool_exception_delivers_failed_update_immediately` (failed-update в callback, не в
> буфере). Изменение wire-тайминга (failed приходит раньше) — формально контракт, но
> приближает поведение к success-ветке и ACP-требованию «immediately». `make check` зелёный.

> Обнаружено при P1-4 (декомпозиция `agent_loop.py`) и перенесено 1:1 как историческое
> поведение (комментарий в коде). Не долг из аудита — наблюдение, зафиксировано для
> явного решения.

**Файл:** `server/protocol/handlers/pipeline/stages/agent_loop/tool_processor.py`
(`_execute_allowed_tool_call`), примитивы — `agent_loop/updates.py` (`SessionUpdateSink`).

**Суть.** Исполнение tool обёрнуто в `try/except`, и статусная `tool_call_update` шлётся
по-разному:
- **success / штатный fail** (try): `await sink.emit_and_save_tool_update(...)` →
  `emit()` = **немедленная доставка** клиенту через callback, затем сохранение в replay.
- **exception при исполнении** (except): `sink.buffer_and_save_tool_update(...)` →
  `buffer_only()` = notification только в буфер (`sink.notifications`), **минуя immediate
  callback**; буфер отдаётся наружу как `AgentLoopResult.notifications` и доставляется
  клиенту лишь **после завершения turn'а**.

**Почему проблема (в стриминг-режиме, когда `notification_callback` задан):**
1. **Задержка на самом критичном пути.** Если tool не вернул `success=False`, а **бросил
   исключение** (баг исполнения, сбой транспорта), карточка tool'а в UI не переходит в
   `failed` в реальном времени — висит «в процессе» до конца turn'а. Для пользователя —
   зависший вызов.
2. **Нарушение причинного порядка живых событий.** Немедленные нотификации последующих
   *успешных* tool'ов уходят раньше буферизованного `failed` от ранее упавшего →
   клиент может получить `tool_2 completed` до `tool_1 failed`.

**Что НЕ страдает (severity низкий):** replay (`session/load`) корректен — обе ветки
одинаково вызывают `save_tool_call_update` в правильном порядке; нотификация не теряется
(доставляется в конце turn'а). Дефект — только живой UX (латентность + порядок) в стриминге.

**Технической причины держать асимметрию нет:** `_send_immediately()` сам ловит свои
исключения и возвращает `False` (fallback в буфер), поэтому вызвать `emit_and_save_tool_
update` в except-ветке безопасно — повторного выброса не будет. Асимметрия чисто
историческая (перенос 1:1 при P1-4).

**Задачи:**
- [x] В except-ветке `_execute_allowed_tool_call` заменить `buffer_and_save_tool_update`
      на `await emit_and_save_tool_update` (ветка уже async).
- [x] Тест `test_tool_exception_delivers_failed_update_immediately` (failed уходит через
      callback немедленно, не оседает в буфере).
- [x] Осиротевший `buffer_and_save_tool_update` удалён; изменение wire-тайминга отмечено.

**Оценка:** 0.5 дня.
**Критерий приемки:** exception-ветка доставляет `tool_call_update(failed)` немедленно
(как success-ветка); replay-детерминизм сохранён; порядок живых событий причинно-верный.

---

### 26. Формат плана нарушает ACP на replay-пути: `latest_plan` хранит `{title,description}` вместо ACP `{content,priority,status}` — ✅ ЗАКРЫТО (2026-07-17)

> ✅ **Фикс (2026-07-17):** оба writer'а, урезавших план до невалидного `{title,description}`
> (`plan_builder.update_session_plan`, `directives.py::_apply_publish_plan`), приведены к
> ACP-форме `{content,priority,status}` — идентично тому, что уходит в live
> `session/update: plan`. Теперь `replay_latest_plan` на `session/load` отдаёт ACP-валидные
> entries со статусами (live ≡ replay). Миграция схемы **v5 → v6**
> (`state.py::migrate_schema` + хелпер `_migrate_plan_entry_to_acp`): старые сессии с
> `{title,description}` конвертируются (`title`→`content`, статусы/priority — валидные
> дефолты), уже-ACP entries сохраняются как есть. Тесты: `test_stored_plan_matches_wire_
> notification` (live≡stored), миграция v5→v6 legacy и preserve-ACP, обновлён
> `test_replays_latest_plan` на ACP-форму. `make check` зелёный.
>
> **Сужение типа `list[PlanStep | dict]` — осознанно отложено:** defensive-ветка в
> `replay_latest_plan` (`model_dump` для BaseModel) защищает от P2-12 (регресс-тест с
> `PlanStep`-объектами), сужение с ней конфликтует и добавляет риск при малой пользе. Все
> writer'ы теперь пишут dict-и в ACP-форме, так что полиморфизм де-факто не возникает.

> Наблюдение из P1-4; при проверке против спецификации (`doc/protocols/Agent Client
> Protocol/protocol/11-Agent Plan.md` + `17-Schema.md`) оказалось **нарушением ACP**, а не
> просто внутренней несогласованностью. По иерархии CLAUDE.md — приоритет №2 (соответствие
> ACP), выше обратной совместимости.

**Что говорит ACP.** `PlanEntry` (11-Agent Plan.md:56-74, схема:2332) имеет ровно три
**обязательных** поля: `content` (string), `priority` (`high`/`medium`/`low`), `status`
(`pending`/`in_progress`/`completed`). Полей `title`/`description` в схеме **нет**. Плюс
жёсткое правило (11-Agent Plan.md:80): агент **MUST** слать полный список entries с их
статусами, клиент **MUST** заменить план целиком.

**Дефект.** `latest_plan: list[PlanStep | dict]` (`state.py`) не имеет единой схемы — два
writer'а пишут разные формы:
- `plan_builder.update_session_plan` (~180) и `directives.py` (~116): `{title: content,
  description: ""}` — **невалидно по ACP** (нет ни одного required-поля, есть два
  несхемных); `priority`/`status` **выброшены**.
- `agent_loop/loop.py` (~456) и `tool_processor.py` (~839): wire-форма
  `{content,priority,status}` как есть.

`replay_latest_plan` (`replay_manager.py`) шлёт `latest_plan` обратно клиенту на
`session/load` **как записано**. Итог:
1. **Live ≠ replay.** Один план приходит клиенту в разных формах (`{content,...}` live vs
   `{title,description}` replay для directives-пути).
2. **Нарушение ACP на replay + правила «replace completely».** Клиент по спеке затирает
   корректный план невалидными entries без статусов.
3. **Потеря статусов при reload.** Урезание в `{title,description}` теряет `status` —
   прогресс плана (`in_progress`/`completed`), показанный живьём, после `session/load`
   пропадает.
4. Полиморфное `list[PlanStep | dict]` — рассадник латентных багов (из той же
   полиморфности вырос уже закрытый краш P2-12).

**Severity.** Не краш (P2-12 прикрыл сериализацию), но нарушение протокола + наблюдаемая
деградация UX и потеря данных о прогрессе при reload. Live-сессия не затронута (там всегда
wire-форма).

**Направление фикса (канон определён спецификацией — не наш выбор):**
- [ ] Свести обоих writer'ов `latest_plan` к ACP-форме `{content,priority,status}` (убрать
      урезание в `{title,description}` в `plan_builder`/`directives`).
- [ ] Миграция уже сохранённых сессий с `{title,description}` → ACP-форма (изменение формата
      хранения → обратная совместимость по CLAUDE.md; bump `schema_version` + ветка
      `migrate_schema`).
- [ ] Тест: live-notification и `replay_latest_plan` одного плана дают байт-идентичные
      ACP-валидные entries; статусы переживают reload.
- [ ] По возможности сузить тип `latest_plan` (убрать полиморфизм `PlanStep | dict`).

**Оценка:** 0.5–1 день.
**Критерий приемки:** `replay_latest_plan` отдаёт ACP-валидные `{content,priority,status}`,
идентичные live-форме; статусы плана сохраняются при `session/load`; миграция старого
формата покрыта тестом.

---

### 27. Terminal alias race condition — потерянные aliases при интенсивном создании терминалов — ⬜ ОТКРЫТО (обнаружено 2026-07-21)

> Обнаружено при анализе логов реальной stdio-сессии (`~/.codelab/logs/codelab-71689.log`,
> 21 июля 2026, сессия `sess_bdd7f44c5734`, модель `openrouter/qwen3.6-plus`). При
> интенсивном создании терминалов (Flutter-проект, множественные `flutter analyze`/`flutter test`)
> возникают ошибки `terminal_alias_not_found` для aliases `term_36` и `term_37`, хотя
> `TerminalAliasRegistry` содержит aliases только до `term_35`.
>
> **Проявление в логах:**
> ```
> 16:23:51 [error] terminal_alias_not_found
>   alias=term_36
>   known_aliases=['term_1', 'term_10', ..., 'term_35']
>   session_id=sess_bdd7f44c5734
>
> 16:27:19 [error] terminal_alias_not_found
>   alias=term_37
>   known_aliases=['term_1', 'term_10', ..., 'term_35']
>   session_id=sess_bdd7f44c5734
> ```
>
> Оба случая: агент создаёт терминал (`terminal/create` → `term_36`/`term_37`), но при
> последующем `terminal/wait_for_exit` alias уже отсутствует в реестре. Это приводит к
> `success=False` и потере вывода терминала.

**Файл:** `src/codelab/server/tools/executors/terminal_alias_registry.py`,
`src/codelab/server/tools/executors/terminal_executor.py`

**Гипотезы о корневой причине:**

1. **Race condition при регистрации/удалении:** `terminal/create` регистрирует alias, но
   `terminal/release` (или cleanup при ошибке) удаляет alias до того, как
   `terminal/wait_for_exit` успевает его использовать. Асинхронная природа tool execution
   может создавать окно, где alias ещё не зарегистрирован или уже удалён.

2. **Гонка между create и wait:** Агент вызывает `terminal/create` и немедленно
   `terminal/wait_for_exit` (не дожидаясь завершения create). Если wait выполняется до
   завершения регистрации alias — `terminal_alias_not_found`.

3. **Очистка при ошибке:** Если `terminal/create` завершается с ошибкой (или timeout),
   cleanup-логика удаляет alias, но агент всё равно пытается использовать его в
   последующих вызовах.

4. **Многопоточность/asyncio:** `TerminalAliasRegistry` не является thread-safe/async-safe.
   Если несколько tool calls выполняются параллельно (через `asyncio.create_task`),
   мутации `terminals` dict могут приводить к race condition.

**Severity:** Средний. Не краш (агент получает `failed` и может создать новый терминал),
но приводит к потере времени (recreate-loop) и засоряет логи error'ами. В сессии
`sess_bdd7f44c5734` — 2 ошибки за ~30 минут, но при высокой нагрузке может проявляться
чаще.

**Задачи:**
- [ ] **Investigation:** Воспроизвести проблему в контролируемых условиях (стресс-тест:
      50+ `terminal/create` за короткое время, проверить, все ли aliases сохраняются).
- [ ] **Аудит кода:** Проверить `TerminalAliasRegistry` на thread-safety/async-safety
      (используются ли locks/mutexes при мутации `terminals` dict?).
- [ ] **Аудит lifecycle:** Проверить, когда вызывается `unregister` (только при
      `terminal/release` или при ошибках/timeout?). Добавить логирование всех мутаций
      (register/unregister) для диагностики.
- [ ] **Тест:** Интеграционный тест с параллельным созданием/использованием терминалов
      (asyncio tasks, 10+ терминалов одновременно).
- [ ] **Фикс (если race confirmed):** Добавить `asyncio.Lock` в `TerminalAliasRegistry`
      для критических секций (register/unregister/lookup). Или использовать thread-safe
      структуру данных.
- [ ] **Фикс (если lifecycle issue):** Убедиться, что `unregister` вызывается только
      после полного завершения использования терминала (все pending `wait_for_exit`
      завершены).

**Оценка:** 1 день (investigation + аудит + тесты + фикс).
**Критерий приемки:** stress-тест (50+ терминалов) проходит без `terminal_alias_not_found`;
все aliases сохраняются до явного `terminal/release`; логи не содержат ошибок при
интенсивном использовании.

---

### 28. Fire-and-forget задачи без контроля жизненного цикла — ⬜ ОТКРЫТО (обнаружено 2026-07-22)

> Обнаружено при аудите async-корректности (2026-07-22). CLAUDE.md прямо запрещает
> «создавать фоновые задачи без контроля жизненного цикла». Python GC вправе собрать
> задачу, на которую нет сильной ссылки, до её завершения (документированное поведение
> `asyncio.create_task`/`ensure_future`) — задача обрывается молча, исключения внутри
> не всплывают. Часть находок — на **горячем пути** (исполнение tool-calls, чтение stdout
> терминала). В тех же модулях соседний код задачи хранит корректно (в атрибуты/словари/set,
> часто с `add_done_callback`) — эти выпадают из паттерна.

**Находки:**

| # | Файл:строка | Что запускается | Серьёзность |
|---|-------------|-----------------|-------------|
| 1 | `server/protocol/core.py:212` | `execute_tool_in_background(...)` — горячий путь tool-execution | высокая |
| 2 | `client/infrastructure/services/terminal_executor.py:188` | `_read_output(session)` — долгоживущее чтение stdout терминала | высокая |
| 3 | `server/protocol/notification_bus.py:98` | `ensure_future(callback(message))` — доставка буферизованных уведомлений | средняя |
| 4 | `client/.../acp_transport/request_callback_coordinator.py:353` | `ensure_future(permission_responder.handle(...))` — permission flow | средняя |
| 5 | `client/presentation/chat/handlers/tool_call_handler.py:161` | `on_tool_call_updated(update)` | средняя |
| 6 | `client/presentation/base_view_model.py:142` | `loop.create_task(publish_result)` | средняя |
| 7 | `client/presentation/chat/handlers/config_option_handler.py:81` | `event_bus.publish(event)` | средняя |

**Задачи:**
- [ ] Ввести единый механизм владения фоновыми задачами (см. архитектурное решение ниже)
- [ ] Перевести находки 1–7 на хранение ссылки + `add_done_callback` (снятие ссылки + логирование исключения)
- [ ] Guardrail: тест/линт против «голого» `create_task`/`ensure_future` без регистрации
- [ ] Приоритет: сначала горячий путь (1, 2), затем permission flow (4)

**Оценка:** 1 день (механизм) + 0.5 дня (перевод точек + guardrail).
**Критерий приемки:** нет `create_task`/`ensure_future` без владельца; фоновые ошибки логируются, не теряются молча; `make check` зелёный.

---

### 29. Гашение `asyncio.CancelledError` без проброса — ⬜ ОТКРЫТО (обнаружено 2026-07-22)

> CLAUDE.md требует «корректно обрабатывать `asyncio.CancelledError`». Перехват отмены без
> `raise` превращает отменённую операцию в «нормально завершённую» — структурная отмена
> вверх по стеку ломается.

**Находки:**

- **`server/agent/llm_adapter.py:131`** (высокая) — `CancelledError` перехватывается и
  конвертируется в обычный `AgentResult(stop_reason="cancelled")` **без `raise`**.
  Вызывающий agent-loop не увидит отмену и продолжит как после штатного результата.
  Может быть намеренным (наблюдать отмену как доменный результат) — **требует явного
  решения по семантике** (проброс vs доменный «cancelled» с задокументированным инвариантом).
- **`server/transport/stdio.py:262`** (средняя) — `except CancelledError` только логирует,
  без `raise`; receive-loop завершается как «нормально завершённый». Образец правильного
  поведения — `mcp/manager.py:933` (делает `raise`).

**Задачи:**
- [ ] Принять решение по семантике отмены в `llm_adapter` (проброс или доменный результат + инвариант в docstring)
- [ ] `stdio.py:262` — `raise` после cleanup (по образцу `mcp/manager.py:933`)
- [ ] Тесты на пропагацию отмены сверху вниз

**Оценка:** 0.5 дня (после решения по семантике).
**Критерий приемки:** отмена корректно распространяется; поведение отмены покрыто тестами.

---

### 30. `except Exception: pass` в конфиге — молчаливая потеря настроек — ⬜ ОТКРЫТО (обнаружено 2026-07-22)

> CLAUDE.md прямо запрещает `except Exception: pass`. Аудит нашёл 7 таких мест; 5 —
> оправданный best-effort TUI-cleanup (иконка темы, тик таймера, бейдж статуса, монтирование
> карточки). Реальный долг — один; мягкий — один.

**Находки:**
- **`server/config.py:363`** (реальный долг) — глушит любую ошибку `tomllib.load` (битый TOML,
  синтаксис, права доступа) без логирования: пользовательские настройки молча теряются,
  вместо явного сигнала о некорректном конфиге. Минимум — `logger.warning` с путём и причиной;
  корректнее — ловить конкретные `tomllib.TOMLDecodeError`/`OSError`.
- **`client/tui/components/keyboard_manager.py:334`** (мягкий) — глушит ошибку
  `self._app.action(action)` и возвращает `False` без логирования, в отличие от соседней
  ветки custom_handlers (строка ~325, логирует через `logger.error`). Диагностика теряется.

**Задачи:**
- [ ] `config.py:363` — сузить перехват + `logger.warning` с путём/причиной
- [ ] `keyboard_manager.py:334` — логировать по аналогии с веткой custom_handlers

**Оценка:** 0.5 дня.
**Критерий приемки:** ошибки парсинга конфига видны в логах; голого `except Exception: pass` в не-cleanup путях нет.

---

### 31. Мёртвый код и незаинтегрированные MVP-заделы — ⬜ ОТКРЫТО (обнаружено 2026-07-22)

> Компоненты, помеченные как «заглушка/extension point для MVP», которые определены и
> реэкспортируются, но не инстанцируются в прод-графе DI. Аналог трекнутого P2-24
> (`[llm.fallback]`).

**Находки:**
- **`server/agent/context/legacy_bridge.py`** (`LegacyContextCompactorAdapter`) —
  не инстанцируется: DI (`di/agent.py`) передаёт `ContextCompactor` в `ExecutionEngine`
  напрямую. Docstring обещает использование при `agents.context.enabled=false`, но адаптер
  в графе отсутствует. Кандидат на удаление (проверить флаг перед удалением).
- **`server/llm/telemetry/noop.py`** (`NoOpTelemetry`) — не подключён нигде, кроме реэкспорта.
- **`server/llm/discovery/static.py`** (`StaticModelDiscovery`) — вне модуля discovery не вызывается.
- **`server/llm/fallback/`** (весь пакет) — совпадает с **P2-24**; `factory.create()` реализует
  только `sequential`, стратегии `cost/latency/smart` из docstring `base.py:36` — несуществующие
  классы (`factory.py:40` кидает `ValueError`); circuit_breaker не закрывается автоматически.

**Задачи:**
- [ ] Подтвердить флагом, что `legacy_bridge` мёртв при всех значениях `agents.context.enabled`; удалить либо задокументировать точку подключения
- [ ] `telemetry/noop`, `discovery/static` — удалить или явно пометить «задел, потребителя нет» с тикетом на подключение
- [ ] Синхронизировать с P2-24 по судьбе `llm/fallback/`; убрать из docstring несуществующие стратегии
- [ ] Проверить, что удаление не ломает публичные реэкспорты (`__all__`)

**Оценка:** 0.5–1 день.
**Критерий приемки:** нет определённых-но-неинстанцируемых компонентов без явной пометки-задела; docstring не обещают несуществующих реализаций.

---

### 32. Несколько представлений «capabilities» — 🟡 ЧАСТИЧНО (ядро развязано change'ем `acp-independent-agent-core`; свод представлений не сделан)

> **Переформулировано 2026-08-04 по факту кода.** Прежняя запись утверждала две вещи, которые
> проверку не прошли: что представлений «три» и что round-trip **теряет** `image_prompts` /
> `embedded_context`. Ниже — то, что есть на самом деле.

**Что сделано (change `acp-independent-agent-core`, Фаза 1).** Ядро больше не зависит **ни от
одной** конкретной модели capabilities: `tool_filter` типизирован против структурного порта
`ClientCapabilitiesView` (`agent/contracts/ports.py:27`, три свойства-феатургейта), который
удовлетворяют и wire-DTO, и доменный VO без конверсии. Это снимает дубль **на стороне ядра** —
и только там.

**Что осталось — представления по-прежнему не сведены:**
- `storage/document.py:219` — `ClientRuntimeCapabilities(BaseModel)`: `fs_read/fs_write/terminal`.
  Персистентный wire-DTO. *(Прежний адрес `protocol/state.py:332` устарел: документ сессии переехал
  в хранилище фазой D ADR-006.)*
- `shared/capabilities.py:16` — `ClientCapabilities` (frozen dataclass): те же три поля **плюс**
  `image_prompts` / `embedded_context`.
- `server/mcp/models.py:870` — `MCPClientCapabilities`: хендшейк MCP, другая протокольная
  концепция.

**Про «потерю двух полей» — это не дефект, а мёртвые поля.** `SessionMapper` действительно не
переносит `image_prompts` / `embedded_context` (`session_mapper.py:98`, `:265`), потому что в
wire-DTO их нет. Но **потребителей у них на сервере нет ни одного**: `grep` показывает только
объявление в `shared/capabilities.py`. Настоящие prompt-возможности живут в двух других местах и
к этому VO не относятся — `handlers/auth.py:30-36` (`_PROMPT_CAPABILITIES`, то, что **агент
объявляет о себе** в `initialize`) и `client/domain/prompt_capabilities.py` (клиентская модель).
То есть терять нечего: два поля в доменном VO — заготовка без пользователей, и именно она создаёт
видимость лоссового маппинга.

**Задачи:**
- [x] **Судьба `image_prompts` / `embedded_context` решена (2026-08-04): мультимодальность
      сохранена, но переехала в правильный тип.** Введён общий
      `shared/prompt_capabilities.py::PromptCapabilities` (`image`, `audio`, `embedded_context`) —
      по ACP это `agentCapabilities.promptCapabilities`, то есть возможности **агента** принимать
      контент. Им сведены три копии одного понятия: локальный `PromptCapabilityProfile` на сервере
      (удалён), `PromptCapabilities` в клиентском домене (переехал в `shared`, в клиенте осталось
      только исключение `UnsupportedContentError`) и два поля-заготовки в `ClientCapabilities`
      (убраны оттуда). Побочно: `from_server_capabilities` → `from_agent_capabilities` — имя
      приведено к ACP; вызывающий один, wire не затронут.
      **Следствие для этого пункта:** доменный VO и персистентная модель описывают теперь
      **один и тот же набор трёх полей**, поэтому маппинг между ними лосслесс по построению, и
      формулировка «теряет `image_prompts`/`embedded_context`» перестала существовать.
- [ ] Свести wire-DTO (`storage/document.py::ClientRuntimeCapabilities`) и доменный VO
      (`shared/capabilities.py::ClientCapabilities`) к одной модели с маппингом только на границе
      сериализации — остаток пункта. Наблюдение к решению: согласованные возможности принадлежат
      **подключению**, а не сессии (это прямо сказано в docstring `Session.apply_client_context`),
      и `session/load` перезаписывает их на каждой загрузке — то есть персистентная копия близка к
      тому же классу, что реестр терминалов (P2-58), и её судьбу разумно решать вместе с
      расщеплением ADR-007
- [x] `MCPClientCapabilities` не сводится: другой протокол (MCP-хендшейк), другой смысл. Решение
      зафиксировано, из задач снято

**Критерий приёмки:** в ядре — ноль зависимостей от конкретной модели capabilities (**выполнено**);
в доменном VO нет полей без потребителей (**выполнено**: мультимодальность переехала в
`PromptCapabilities`, дубли сведены); на сервере — одна модель client-capabilities плюс маппинг на
границе (**осталось**).

**Связано:** ADR-003 (закрыт фазой D ADR-006), `ADR-005` (порт `ClientCapabilitiesView` — то, чем
развязано ядро), `openspec/changes/acp-independent-agent-core/specs/client-capabilities/spec.md`
(delta-спека: её формулировку «ядро оперирует `shared.ClientCapabilities`» реализация уточнила до
структурного порта).

---

### 33. Две параллельные конфиг-системы — ручной merge вместо `settings_customise_sources` — ⬜ ОТКРЫТО (обнаружено 2026-07-22)

> Обнаружено при вопросе «где ещё уместен Pydantic». Конфиг LLM собирается **двумя
> параллельными системами**, моделирующими одни и те же сущности:
> - `server/config.py` — `AppConfig(BaseSettings)` с **ручной лестницей** merge:
>   `_default_llm_data` → `_apply_toml_llm_overrides` → `_apply_env_llm_overrides` /
>   `_apply_env_timeout_overrides` → `_resolve_provider_credentials`. Плюс таблица
>   `_ENV_LLM_FIELDS` и разбросанные `os.getenv(...)`.
> - `server/toml_config/pydantic_config.py` — те же сущности уже **декларативно** как
>   Pydantic-модели с валидаторами: `TimeoutConfig`, `ModelConfig`, `ProviderConfig`,
>   `FallbackConfig`, `${}`-раскрытие (`_expand_env_vars`, `expand_env_in_api_key`).
>
> `config.py` фактически переизобретает то, что `pydantic_config.py` уже моделирует.
> Наследует связанный долг: **P0-2** (`_merge_llm_config` имел цикломатику 32) и
> **P1-30** (`except Exception: pass` на `tomllib.load`, config.py:363).

**Важный нюанс — env участвует в ДВУХ направлениях (нельзя свести к `env_nested_delimiter`):**
1. **env перекрывает TOML** — `CODELAB_LLM_*` бьёт `[llm]` (это направление BaseSettings даёт нативно).
2. **env подставляется ВНУТРЬ TOML** — значения TOML содержат `${VAR}` и раскрываются из
   окружения (`_resolve_provider_credentials` раскрывает `[llm.providers.<p>].api_key =
   "${OPENAI_API_KEY}"`). Здесь env — источник для TOML, а не перекрытие поверх него.

Плюс мульти-файловый `_deep_merge` с приоритетом (`auth.toml < codelab.toml <
codelab.local.toml < custom`) и provider-fallback (`api_key/base_url` из
`[llm.providers.<active>]`, если не заданы напрямую).

**Целевое решение — консолидация на одну систему:**
- Схема/валидация — на моделях `pydantic_config.py` (уже существуют).
- Порядок источников выразить через pydantic-settings **`settings_customise_sources`**:
  `init` (CLI) → env → TOML-с-раскрытием (мульти-файл), в нужном приоритете. Precedence —
  машинерией Pydantic, не ручными `_apply_*`.
- **`${VAR}`-раскрытие сохранить явно** — как кастомный settings-source либо
  `model_validator(mode="before")` (отрабатывает ДО валидации, внутри TOML-значений);
  это то, что нельзя заменить `env_nested_delimiter`.
- Provider-fallback (`api_key` из `[llm.providers.<active>]`) — как `model_validator` на
  собранной модели.

**Задачи:**
- [ ] Спроектировать источники `settings_customise_sources` (init/env/toml-with-expansion) с сохранением текущего приоритета
- [ ] Кастомный TOML-source: мульти-файл `_deep_merge` + `${}`-раскрытие до валидации
- [ ] Provider-fallback как `model_validator`
- [ ] Убрать ручную лестницу `config.py` (`_default_llm_data`/`_apply_*`/`_ENV_LLM_FIELDS`); закрыть P1-30 (`except Exception: pass`) явной валидацией
- [ ] Регресс-тесты на все ветки precedence: env поверх TOML; `${VAR}` внутри TOML; мульти-файл-merge; provider-fallback; отсутствующий `${VAR}` → None
- [ ] Проверить обратную совместимость форматов конфига (изменение формата = миграция/совместимость, см. CLAUDE.md)

**Оценка:** 1.5–2 дня (проектирование источников + миграция + тесты precedence).
**Критерий приемки:** одна система сборки конфига; поведение precedence и `${}`-раскрытия
байт-в-байт сохранено (покрыто тестами); ручной merge и `except Exception: pass` удалены;
`make check` зелёный.
**Связано:** P0-2 (сложность `_merge_llm_config`), P1-30 (`except Exception: pass` в конфиге).

---

### 34. `ContextGatherer` content-search: O(термы × файлы) чтений через ACP RPC — ⬜ ОТКРЫТО (обнаружено 2026-07-23, анализ логов)

**Симптом (лог `~/.codelab/logs/codelab-5026.log`, сессия `sess_4003f10eed62`):** одна
сборка контекста дала **160** `tool handler execution completed acp_tool_name=fs/read_text_file`
в окне ~70 мс, при том что итог — `files_read=4`, `files_gathered=7`. Источник — фаза
content-search: `context.gather.content_search.start files_to_check=30` повторяется **5 раз**
(по числу поисковых термов).

**Корень:** `ContextGatherer._search_in_files` (`server/agent/context/gatherer.py:590`)
вызывается в цикле `for term in profile.search_terms[:5]` (строка 225) и для **каждого**
термина перечитывает один и тот же набор кандидатов (`content_search_limit = 30`), вызывая
`_read_file` → `tool_registry.execute_tool("fs/read_text_file")` (строка 405). Итого до
5 × 30 = **150** RPC-чтений одних и тех же файлов за сборку. `_read_file` **не обращается к
`FileContentCache`** (Слой C) — чтения доходят до fs-хендлера каждый раз (подтверждено 160
completion-записями в логе).

**Влияние:** локально 65 мс (незаметно), но на удалённом ACP-клиенте это **~150 сетевых
round-trip'ов на каждый старт turn'а** — прямая деградация латентности и нагрузка на клиента.
Сложность O(термы × файлы) вместо O(файлы).

**Предлагаемое решение:** читать каждый файл-кандидат один раз (через `FileContentCache` или
разово перед циклом термов), затем матчить все термы против содержимого в памяти
(`term_lower in content.lower()` — дёшево). Сводит чтения к O(файлы) без изменения результата.

**Файл:** `src/codelab/server/agent/context/gatherer.py` (`_search_in_files:590`, `_read_file:405`,
цикл термов `:225`).
**Оценка:** 0.5 дня (рефактор + тест, что число `execute_tool("fs/read_text_file")` = число
уникальных проверенных файлов, а не термы × файлы).
**Критерий приёмки:** для N термов над M кандидатами число fs/read RPC = M (не N × M);
результат `context.gather.complete` (`file_paths`, `files_gathered`) байт-в-байт прежний;
`make check` зелёный.
**Связано:** P2-15, P2-20 (эффективность `ContextGatherer`, ранее подтверждались анализом логов).

---

### 35. — номер не используется

Занимался отозванной записью «tombstone отмены не пишется» (2026-07-27): наблюдение
оказалось ошибкой анализа — выборка файла сессии делалась уже ПОСЛЕ поглощения tombstone'а,
окно жизни которого ~8 мс. Разбор и метод проверки — в ADR-006 («Шаг 1 D4-d1 подтверждён
живьём»). Номер оставлен пустым, чтобы ссылки на него не читались как открытый долг.

---

### 36. Отказ policy не сообщает модели причину → каскад фантомных терминалов — ✅ ЗАКРЫТО (2026-07-29)

**Симптом (лог `~/.codelab/logs/codelab-14108.log`, сессия `sess_b09272b62ccb`):** в сессии
в режиме `plan` модель сделала **13** вызовов `terminal/create` (12 отклонены), затем начала
работать с алиасами `term_3`…`term_8`, которых никогда не существовало — **6 ошибок**
`terminal_alias_not_found`. Turn завершился не ответом, а упором в лимит
(`agent_loop max_turn_requests reached max_turn_requests=10`); из 41 вызова сессии 18 —
`failed`.

**Корень:** `ToolCallProcessor._reject_tool_call`
(`protocol/handlers/pipeline/stages/agent_loop/tool_processor.py:365`) отдаёт модели
`f"Tool execution rejected by policy for {tool_kind}"`. Текст не называет ни причину
(режим `plan` — read-only), ни то, что запрет действует до смены режима, поэтому модель
трактует отказ как разовый сбой и продолжает попытки, считая терминалы созданными.
Для сравнения: сообщение loop-guard'а (`_reject_looping_tool:465`) прямо просит «измени
подход или заверши ответ» — после его срабатывания повторные `create` в turn'е прекратились.

**Влияние:** сожжённый turn (10 запросов к LLM), 18 `failed` вызовов и 6 ошибок в логе на
пустом месте; для пользователя — ответ не получен. В plan-режиме это воспроизводимо, а не
случайность.

**Предлагаемое решение:** в тексте отказа назвать действующий режим и характер ограничения
(«сессия в режиме `plan`: инструменты исполнения недоступны до смены режима»), то есть
передать модели то же, что уже знает `decide_tool_policy`. Дополнительно рассмотреть
запоминание отказа policy по сигнатуре вызова, чтобы повторный идентичный вызов сразу
получал причину, а не общий текст loop-guard'а. Побочно: текст отказа английский, тогда как
остальные сообщения агенту (loop-guard, ошибки терминала) русские.

**Файл:** `src/codelab/server/protocol/handlers/pipeline/stages/agent_loop/tool_processor.py`
(`_reject_tool_call:346-380`); политика — `protocol/handlers/tool_policy.py`.
**Оценка:** 0.5 дня (текст + прокидывание режима в отказ + тест на содержимое отказа).
**Критерий приёмки:** отказ в plan-режиме содержит режим и причину; сценарный тест
подтверждает, что после отказа модель получает один и тот же осмысленный текст на повторные
вызовы; `make check` зелёный.
**Связано:** P0-22 (защита от зацикливания — сработала, но по чужому поводу), P2-37 (уровень
логирования модельных ошибок).

**Корень оказался глубже — вторая итерация (2026-07-29).** Первая правка (только текст
отказа) поведение НЕ изменила: на проверочном прогоне `sess_f71ff601b1bf` модель снова
сделала 8 отказанных `terminal/create` подряд (iteration 2→10) и упёрлась в
`max_turn_requests`, хотя новая причина исправно формировалась и попадала в лог. Разбор
истории той же сессии показал настоящий разрыв: **53 запроса инструментов против 35 ответов
— 18 вызовов без ответа `role: tool`**. `_add_tool_result_to_history` вызывался только из
`_execute_allowed_tool_call` и `execute_pending`; ни один reject-путь
(`_reject_tool_call`, `_reject_looping_tool`, `_reject_unknown_tool`) в историю не писал —
статус уходил в состояние, текст в UI клиента, а модель видела вызов **без ответа** и
повторяла его.

Это нарушало сразу два контракта: LLM-API (за assistant-сообщением с `tool_calls` обязан
следовать `role: tool` на каждый `tool_call_id`) и шаг 6 ACP `05-Prompt Turn`
(«The Agent sends the tool results back to the language model as another request» — без
различения успеха и отказа; `failed` по `08-Tool Calls.md:228` такой же полноценный
результат). Исправление: все три reject-пути пишут результат в историю. Формулировка
причины из первой итерации при этом становится осмысленной — до этого она была видна только
в UI и логе.

**Методическая ошибка, которую стоит запомнить.** Формулируя пункт, я написал «сообщение
loop-guard'а прямо просит изменить подход, и после его срабатывания повторы прекратились» —
и вывел из этого, что дело в тексте. Loop-guard тоже не писал в историю; повторы
прекращались не от убедительности текста, а потому что guard отклонял их сам, server-side.
Корреляция была принята за причину, и первая правка починила формулировку вместо канала
доставки. Проверять надо было по истории сессии, а не по логу.

**Инвариант в тестах:** `pipeline/stages/test_tool_result_history_invariant.py` — на каждый
отклонённый вызов в истории есть `role: tool` с тем `tool_call_id`, который прислал LLM
(fallback на ACP-id, если LLM-id отсутствует). Именно этот инвариант ловит весь класс
дефектов «вызов без ответа».

**Как закрыто, первая итерация (2026-07-29).** Причина отказа формируется тем же знанием, каким принято
решение: `tool_policy.describe_rejection(session, tool_kind)` — рядом с цепочкой решений, а
не в вызывающем. Три случая: plan-режим для блокируемого вида (называет режим, его
read-only характер и то, что запрет держится до смены режима), `reject_always` на сессию
(называет решение пользователя) и правдивый общий текст для остального — намеренно без
догадок о том, какая политика сработала. Каждый текст заканчивается тем, что повтор даст
тот же отказ, потому что именно этого модели не хватало. Сообщение по-русски, как остальные
адресованные агенту тексты. `tool_call_rejected` теперь логирует `mode` и `reason` — чтобы
следующий разбор прогона видел причину, а не только факт отказа.

Второй пункт предложения (запоминать отказ policy по сигнатуре) НЕ делался: он менял бы
поведение при смене режима внутри turn'а, а сформулированной причины достаточно —
проверять на живом прогоне.

Покрытие: `handlers/test_tool_policy.py::TestDescribeRejection` (формулировки, включая
случай «plan-режим не при чём — не врать про причину») и
`pipeline/stages/test_tool_policy_rejection.py` (причина доходит до модели в tool result, до
клиента в `tool_call_update`, инструмент не исполняется, причина и режим в логе).

---

### 37. Ошибки модели и штатные отмены логируются как `error` — ✅ ЗАКРЫТО (2026-07-29, один критерий не подтверждён живьём)

**Симптом:** уровень `error` в логе сервера занят событиями, где сервер отработал верно:
- `terminal_alias_not_found` — модель обратилась к несуществующему алиасу, registry корректно
  отказал (6 записей в `codelab-14108.log`, ранее — в прогоне 2026-07-28);
- `Ошибка при ожидании завершения терминала` — `session/cancel` отменил клиентский RPC
  `terminal/wait_for_exit`, и штатная отмена попала в ту же ветку, что таймауты и реальные
  сбои (`client_rpc_bridge.py:294-296`, единственный error за прогон 2026-07-28).

**Корень:** отсутствует разделение «сбой сервера» / «ошибка входных данных от модели» /
«штатная отмена». В первом случае это `logger.error` в обработчике инструмента, во втором —
общий `except (ClientRPCTimeoutError, ClientRPCResponseError, ClientRPCError)`.

**Влияние:** «0 ошибок за прогон» перестаёт работать как критерий чистоты — а именно им
проверялась поведенческая нейтральность на живых прогонах фаз A–C ADR-006. Ложные error
маскируют настоящие: в прогоне `sess_b09272b62ccb` все 6 error оказались модельными, и
реальный сбой в этом шуме был бы незаметен.

**Предлагаемое решение:** модельные ошибки инструментов — `warning` (результат всё равно
уходит модели в теле tool result); отмену RPC отделить от сбоя (уровень `info`/`debug` плюс
отдельный признак в результате, чтобы отмена не выглядела для модели ошибкой). Уровень
`error` оставить за отказами сервера.

**Файлы:** `src/codelab/server/tools/integrations/client_rpc_bridge.py:287-300`,
`src/codelab/server/tools/executors/terminal_executor.py` (алиасы),
плюс аудит остальных `logger.error` в `tools/`.
**Оценка:** 0.5 дня (правка уровней + тесты через `structlog.testing.capture_logs`).
**Критерий приёмки:** штатный `session/cancel` и обращение к неизвестному алиасу не дают
`error`; на живом прогоне без реальных сбоев число error = 0.
**Связано:** P2-36, ADR-006 (живые прогоны как гейт нейтральности).

**Как закрыто (2026-07-29).** Отмена отделена от сбоя по типу исключения, а не по тексту:
`ClientRPCCancelledError` уже существовал, но `ClientRPCBridge` ловил его широкой веткой
вместе с таймаутами и сбоями. Добавлен отдельный обработчик во все шесть методов моста
(`read_file`, `write_file`, `create_terminal`, `wait_terminal_exit`, `terminal_output`,
`release_terminal`) — событие `client_rpc_cancelled` уровня info. **Поведение каждой ветки
сохранено ровно как было** (где возвращался `None` — возвращается `None`, где пробрасывалось
исключение — пробрасывается), потому что менялись уровни, а не контракт.

`FileSystemToolExecutor` ловил отмену широким `except Exception` и тоже писал `error`; там
добавлена ветка отмены с уровнем info и правдивым текстом модели («Операция чтения файла
отменена…» вместо «Ошибка при чтении файла»).

Ошибки модели понижены до `warning`: `terminal_alias_not_found` (галлюцинация alias'а) и
`tool not found in registry` (галлюцинация инструмента). В обоих случаях сервер отработал
верно и вернул модели список доступного — это не сбой сервера.

**Осталось сознательно недоделанным:** при отмене `wait_terminal_exit`/`terminal_output` мост
возвращает `None`, неотличимый от сбоя, поэтому текст, который получает модель, остаётся
«Ошибка при ожидании завершения терминала». Правдивый текст здесь требует менять контракт
возврата моста (сигнал отмены наверх), то есть выходит за рамки правки уровней; на практике
turn в этот момент уже отменён. Уровни логирования при этом чистые.

**Критерий приёмки живьём пока НЕ проверен.** На прогоне `sess_ba92d6fb021f` (2026-07-29)
`session/cancel` пришёл, когда turn стоял на `awaiting_permission`, то есть в полёте не было
ни одного клиентского RPC (`session_cancel_handled followup_count=0`, ни одного
`client_rpc_cancelled`). Ноль error в логе означает «регрессий нет», а не «отмена больше не
даёт error». Нужен прогон, где отмена приходит во время активного RPC — в логе к этому
моменту должен быть `tool_call_executing … terminal/wait_for_exit`.

**Покрытие:** `tests/server/test_log_levels_cancellation.py` — отмена не даёт `error` и
сохраняет прежний возврат в трёх представительных методах моста; ошибки модели дают
`warning`. Тест `test_unknown_tool_rejected_before_permission` проверял `logger.error` —
переведён на `warning` с явной проверкой отсутствия `error`.


**Не подтверждено живьём (по состоянию на 2026-07-30, пять прогонов).** Критерий «отмена во
время активного клиентского RPC → `client_rpc_cancelled` на уровне info» ни разу не
воспроизведён: `session/cancel` каждый раз приходил либо после завершения инструмента, либо
во время паузы на permission, либо во время LLM-вызова — `followup_count=0`,
`client_rpc_cancelled=0`. Ветка покрыта тестами, живого случая нет. Ловить целенаправленно:
отмена в момент, когда в логе висит `tool_call_executing … terminal/wait_for_exit`.
---

### 38. Вызовы без ответа `role: tool`: прерванный батч + отмена приостановленного вызова — ✅ ЗАКРЫТО (2026-07-29)

**Симптом (сессия `sess_ba92d6fb021f`):** 46 запросов инструментов в истории против 25
ответов `role: tool`. Разбор по сообщениям истории показывает закономерность:

| сообщение | вызовов в батче | без ответа |
|---|---|---|
| `#8` | 11 (`fs_read_text_file`) | 10 |
| `#10` | 10 (`fs_read_text_file`) | 9 |
| `#12`…`#54` | по 1 | 0 |
| `#59`, `#61` | по 1 (`terminal_create`) | 1 (отмена turn'а) |

То есть при батче из N вызовов отвечен ровно **один**; одиночные вызовы отвечены всегда.
ACP-вызовов при этом создано 26 при 46 запросах в истории (`tool_call_created` в логе), то
есть 19 вызовов батча не стали tool call'ами вообще.

**Почему это важно.** `loop.py:325-333` кладёт в историю assistant-сообщение со ВСЕМИ N
`tool_calls` батча до их обработки. Контракт LLM-API требует `role: tool` на каждый
`tool_call_id`; неотвеченные вызовы уходят в каждый последующий запрос и, как показал P2-36,
провоцируют модель повторять вызовы. Это тот же класс дефектов, что P2-36, но по другому
каналу: там отказ не писался в историю, здесь батч не доводится до конца.

**Второй, отдельный источник:** отмена turn'а (`#59`, `#61`) оставляет вызовы `cancelled` без
ответа. Путь отмены P2-36 не касался.

**Что проверить при разборе:** почему `process_batch` создаёт ACP-вызовы не на все элементы
батча (ранний выход при паузе на permission? исключение внутри цикла? дедупликация?), и надо
ли писать в историю assistant-сообщение до обработки батча или по факту созданных вызовов.

**Файлы:** `protocol/handlers/pipeline/stages/agent_loop/loop.py:325-345` (запись
assistant-сообщения и вызов `process_batch`),
`pipeline/stages/agent_loop/tool_processor.py::process_batch`.
**Оценка:** 0.5–1 день (разбор + фикс + расширение инварианта на батч).
**Критерий приёмки:** на живом прогоне число `role: tool` ответов равно числу запросов
инструментов в истории при батчах любого размера, включая прерванные отменой; инвариантный
тест `test_tool_result_history_invariant.py` расширен на батч из N вызовов и на отмену.
Живьём батч >1 пока не воспроизведён: на прогоне `sess_daac2d9d9ee8` все 45 батчей были по
одному вызову, поэтому ветка «остаток батча» ни разу не сработала —
`tool_calls_left_unprocessed` в логе отсутствует. Улучшение 25→44 ответов объясняется
отсутствием многовызовных батчей, а не фиксом. Нужен прогон с запросом нескольких файлов
сразу и паузой на первом.
**Связано:** P2-36 (тот же инвариант, другой канал), ADR-006 (история сессии переезжает в
домен — расхождение надо закрыть до переключения turn-пути).

**Источник 1 — прерванный батч — ЗАКРЫТ (2026-07-29).** Причина подтверждена кодом:
`process_batch` на паузе permission и на отмене делал ранний `return`, бросая остаток батча,
тогда как `loop.py:325-333` уже положил в историю assistant-сообщение со всеми id батча.
Теперь на обоих выходах остаток получает правдивый ответ («Вызов не выполнялся: turn
приостановлен на запросе разрешения для предыдущего вызова / turn отменён пользователем.
Запроси его снова, если он всё ещё нужен») — плюс третий найденный по ходу случай:
`if not tool_name: return` тоже оставлял вызов без ответа. Событие
`tool_calls_left_unprocessed` (info, `count`, `reason`) — чтобы разбор прогона видел это
сразу, а не через сверку истории.

Переписывать assistant-сообщение задним числом (убирать необработанные вызовы) сознательно
отвергнуто: модель эти вызовы действительно запрашивала, правка истории сделала бы её
неправдивой.

Инвариантный тест расширен именно там, где промахнулся: батч из 11 вызовов с паузой на
первом (воспроизводит `sess_ba92d6fb021f`), отмена посреди батча, вызов без имени, пустой
остаток.

**Источник 2 — отмена приостановленного вызова — ОТКРЫТ.** Подтверждён на прогоне
`sess_daac2d9d9ee8` (2026-07-29, уже с фиксом источника 1): 45 вызовов, 44 ответа, один без
ответа — `call_045` ушёл на permission в 12:56:34.127, `session/cancel` пришёл в 12:56:35.953,
вызов помечен `cancelled`, ответа модели нет. Фикс источника 1 здесь не работает по
построению: отмена происходит ВНЕ `process_batch` (батч уже вернул `pending_permission=True`,
остатка не было).

**Адрес:** путь отмены, переводящий приостановленный вызов `pending → cancelled` —
`protocol/handlers/session.py::_cleanup_session_state` (отмена при переключении сессии) и
`commands/session_cancel.py` / `ToolCallHandler.cancel_active_tools` (отмена turn'а). Ни один
из них не пишет модели `role: tool`. Нужен тот же правдивый ответ («вызов не выполнялся:
turn отменён»), причём с учётом того, что запись должна попасть в ту же копию сессии, которая
сохраняется (ср. расхождение wire↔диск на `session/load`, ADR-006).

**Критерий приёмки источника 2:** после `session/cancel` во время паузы на permission число
`role: tool` в истории равно числу запрошенных вызовов; тест на путь отмены, а не на
процессор батча.

**Источник 2 закрыт (2026-07-29).** Корнем оказалась не забытая строчка в путях отмены, а то,
что форму записи tool-ответа знал только `ToolCallProcessor`. Введён history-seam
`add_tool_result(tool_call_id, content)` — парный на wire (`SessionState`) и в домене
(`Session`), по решению фазы B ADR-006: форма записи принадлежит носителю состояния. На сейм
переведены все три писателя: процессор (композиция текста осталась там же),
`ToolCallHandler.cancel_active_tools` (отмена turn'а) и `_cleanup_session_state` (отмена при
переключении сессии). Ответ адресуется `tool_call_id_from_llm` с fallback на ACP-id — иначе
он не сматчится с assistant-сообщением.

**Покрытие:** `handlers/test_cancel_answers_tool_calls.py` — отмена turn'а (`pending` и
`in_progress`, fallback на ACP-id, отсутствие повторного ответа для завершённого вызова),
переключение сессии (включая проверку, что отмена уходит и в реплей клиенту, и в историю
модели в одной копии сессии), parity нового сейма wire↔домен через маппер.

**Побочно:** пять тестов состава tool-ответа проверяли форму через `mock_session.history` —
после переноса формы в сейм мок её не воспроизводит, тесты переведены на настоящий
`SessionState`. Это следствие решения фазы B: если форму знает вызывающий, её можно проверять
на моке; если носитель — тест обязан работать с реальным состоянием.

**Живой прогон остаётся подтверждением, а не единственной проверкой:** обе ветки покрыты
тестами. Не подтверждено живьём (сценарий не складывался на четырёх прогонах): батч >1 с
паузой на первом вызове и отмена во время активного клиентского RPC (последнее — также
критерий P2-37).

---

### 40. Хвост батча теряется на каждой паузе permission → модель ходит по кругу — ✅ ЗАКРЫТО (2026-07-30)

**Файлы:** `pipeline/stages/agent_loop/tool_processor.py` (`process_batch`, `execute_pending`),
`pipeline/stages/llm_loop.py:285`.

**Симптом (прогон `sess_142dec045e89`, pid 75148).** `tool_calls_left_unprocessed` сработал
**4 раза за прогон** (count 2, 2, 1, 1) — шесть брошенных вызовов. Модель запрашивает их
снова, снова получает паузу на первом вызове нового батча, снова теряет хвост:
`injection_container.dart` запрошен **7 раз**, `main.dart` — **6 раз**. Детектор циклов
сработал дважды (`tool_call_loop_detected`, `repeat_count=4` и `5`) и погасил повтор — до
разгона не дошло, но полезная работа тратится на перезапрос одного и того же.

**Причина — конструктивная, а не дефект реализации.** При паузе на permission возобновляется
только сам приостановленный вызов (`execute_pending`), остаток батча не возобновляется
никогда: `pending_tool_calls` несёт один id. P2-38 сделал потерю честной (модель получает
ответ «вызов не выполнялся» вместо тишины), но саму потерю не устранил — это и не входило в
его объём.

**Усугубляющий фактор:** формулировка ответа из P2-38 — «Запроси его снова, если он всё ещё
нужен» — прямо приглашает к перезапросу. При потере хвоста на каждом батче это замыкает круг.
Пересмотреть вместе с основной правкой: либо возобновлять хвост (тогда приглашение не нужно),
либо не приглашать, а просто констатировать факт.

**Задачи:**
- [ ] Возобновлять остаток батча после разрешения, а не только приостановленный вызов
- [ ] Решить судьбу вызовов, чей permission отклонён: возобновлять ли хвост за ними
- [ ] Пересмотреть формулировку ответа модели из P2-38
- [ ] Тест: батч из N вызовов с паузой на первом — после разрешения выполняются все N

**Критерий приёмки:** на живом прогоне с батчами >1 `tool_calls_left_unprocessed` не
появляется вне отмены; повторных запросов одного и того же файла в пределах turn'а нет;
`tool_call_loop_detected` не срабатывает.

**Связано:** P2-38 (сделал потерю видимой), P0-39 (второй потребитель того же пути
возобновления — `execute_pending_tool` без проверки живости turn'а).

---

**Масштаб уточнён живьём (`sess_28f0a8011426`, 2026-07-30).** Модель шлёт батчи до 9 вызовов:
за один turn `tool_calls_left_unprocessed` сработал **22 раза**, брошено **80 вызовов**, на них
ушло **81 служебный ответ**; из 109 запросов исполнились 28. Перезапросы одних и тех же файлов:
`reset_counter_usecase.dart` — 9 раз, `main.dart` и `decrement_counter_usecase` — по 8.
Пользователь получал 25 запросов разрешения подряд.

**Реализовано.** Остаток батча переезжает в состояние turn'а
(`ActiveTurnState.pending_batch`, парное поле в доменном `TurnState`, перенос в обе стороны в
`SessionMapper`) вместо выбрасывания. Почему в состояние, а не в память: разрешение приходит
следующим запросом, а тот получает свою копию сессии с диска (см. причину P0-39), поэтому
хвост обязан переживать сериализацию.

`resume_after_permission` перед возвратом к модели дорабатывает отложенный хвост
(`_process_deferred_batch`): хвост снимается до обработки, очередная пауза кладёт туда свой
остаток, и цикл идёт к модели только когда батч исчерпан. Это важно по порядку: пойти к модели
раньше — значит показать ей ответы не на все её вызовы и снова спровоцировать перезапрос.

**Инвариант P2-38 сохранён:** если `active_turn` отсутствует (складывать некуда), хвост
по-прежнему отвечается «вызов не выполнялся» — иначе вызовы остались бы без `role: tool`.
Запасной путь покрыт отдельным тестом.

**Тесты:** `test_batch_resume_e2e.py` — сквозной, батч из трёх чтений с паузой на каждом:
исполняются все три, `tool_calls_left_unprocessed` не появляется, в логе
`tool_calls_deferred_to_resume` ×2 и `resuming_deferred_tool_calls` ×2. Проверено, что тест
имеет зубы: со снятой правкой он падает. Unit: перекладывание хвоста в `pending_batch`,
запасной путь без `active_turn`.

**Шов, внесённый этой правкой и закрытый следом (найден на живом прогоне
`sess_a98dab30f7c3`, 2026-07-30).** Отложенный хвост живёт в состоянии turn'а, поэтому при
обрыве turn'а исчезал вместе с ним — без ответа модели. Живьём: 9 вызовов, 8 ответов; вызов
`analysis_options.yaml` лежал в `pending_batch`, когда пришла отмена. До P2-40 такого не было
(хвост отвечался сразу), то есть шов внесён самой правкой.

Ответ на хвост добавлен на все три пути обрыва: отмена (`handle_cancel`), отказ в разрешении
(`permission_response`), переключение сессии (`_cleanup_session_state`). Единый хелпер
`prompt/turn_state.answer_deferred_batch` (там же, где жизненный цикл turn'а) пишет через
history-seam `add_tool_result` и снимает хвост, чтобы он не всплыл на следующем resume.
Порядок критичен: во всех трёх местах вызов стоит **до** очистки `active_turn` — первая версия
в `_cleanup_session_state` стояла после и молча ничего не делала, это поймал тест.

**Тесты:** ответ на хвост при отмене/отказе/переключении, пустой хвост, битая запись без `id`
не роняет путь отмены; отдельно — настоящий путь отказа (`resolve_permission_response_impl`)
отвечает на хвост, а настоящий путь разрешения **не** отвечает и сохраняет хвост для
возобновления.

**Подтверждено живьём (`sess_fe5bc14d8775`, 2026-07-30, сборка сверена).** 34 вызова, 34
ответа, ноль без ответа (было 9/8). Батчи до 6 вызовов: `tool_calls_deferred_to_resume` и
`resuming_deferred_tool_calls` — по 23 симметрично, `tool_calls_left_unprocessed` — ноль,
`tool_call_loop_detected` не срабатывал, максимум обращений к одному файлу — 2 против 9 до
правки.

**Не подтверждено живьём:** ветка `deferred_tool_calls_answered_on_turn_end` (ноль
срабатываний) — обе отмены в прогоне пришли с пустым `pending_batch`, отменённые вызовы
отвечены прежним путём `cancel_active_tools`. Ветка держится на тестах.

**Формулировка ответа модели пересмотрена частично:** «Запроси его снова» осталась только на
путях, где вызов действительно не будет выполнен (отмена, отсутствие turn'а, вызов без имени).
На штатном пути приглашения больше нет, потому что нет и потери.

---

### 41. По логу невозможно понять, какая сборка работает — ✅ ЗАКРЫТО (2026-07-30)

**Мотив практический, а не гигиенический.** На разборе логов 2026-07-30 это дважды привело к
ложным выводам: прогон считали проверкой свежей правки, хотя процесс работал с кодом,
загруженным до `pipx install` (подмена файлов на диске уже запущенный процесс не меняет).
Отличить сборки по логу было нечем — ни версии, ни пути. Один раз это стоило целого круга
«правка не работает → поиск несуществующей причины».

**Реализовано.** `shared/logging.log_build_identity(transport)` пишет событие `build_identity`
с `version`, `package_path`, `python` и `transport`. Зовётся из обоих входов: `codelab.cli`
(stdio и websocket) и `server.cli`.

`package_path` важнее версии: версия в `pyproject.toml` меняется редко, а путь сразу отвечает
на вопрос «рабочее дерево или установленная копия» — в e2e видно
`.../codelab-ai/src/codelab`, из pipx будет путь venv'а. Берётся из загруженного модуля, а не
из конфигурации, иначе диагностика врала бы ровно в том случае, для которого нужна.

**Тесты:** состав события; путь совпадает с `codelab.__file__` загруженного пакета.

---

### 42. `session/load` теряет решения обработчика: две загрузки за запрос и ни одного сохранения — ⬜ ОТКРЫТО (обнаружено 2026-07-30, разведка перед транзакцией фазы D)

**Файлы:** `protocol/commands/session_load.py:82,100`, `protocol/handlers/session.py:252-270`
(функция `session_load`), `protocol/handlers/session.py::_cleanup_session_state`.

**Симптом — измерен, не выведен.** Прогон реального `session_load` на реальном
`JsonFileStorage` с последующим чтением диска:

| что решил обработчик | что на диске после |
|---|---|
| `cwd` = `/work` (прислал клиент) | `/tmp` — потеряно |
| `active_turn` очищен | на месте |
| `pending_batch` разобран | 1 вызов висит |
| ответы `role: tool` на отложенный хвост | 0 |
| `call_001` → `cancelled` | `pending` |

Событие `deferred_tool_calls_answered_on_turn_end` при этом в логе есть: код исполнился
верно, но записал в копию, которую никто не сохранил.

**Причина.** Два независимых дефекта, усиливающих друг друга:

1. **Две загрузки за один запрос.** `SessionLoadCommandHandler.handle` берёт копию A
   (`session_load.py:82`) и мутирует её: `runtime_capabilities`, callback `on_session_loaded`
   (MCP setup), разбор осиротевшего permission. Затем `handlers.session.session_load`
   загружает сессию **заново** (`session.py:252`) — копию B. `JsonFileStorage` без кеша
   отдаёт новый объект на каждый `load_session` (проверено: `a is b` → False), поэтому
   мутации копии A теряются — кроме ветки осиротевшего permission, которая единственная
   делает `save_session`.
2. **Функция `session_load` не сохраняет ничего** — за весь её код ни одного
   `save_session`, а мутирует она копию B: `_cleanup_session_state` (отмена pending-вызовов,
   ответ на отложенный хвост, очистка turn'а), `cwd`, `mcp_servers`. Общего сохранения после
   диспатча в протоколе тоже нет.

**Задето уже сделанное.** Ветка ответа на отложенный хвост при переключении сессии (коммит
`6b0d922b`, P2-40) в проде эффекта не даёт по этой же причине. Unit-тест не поймал, потому что
проверяет тот же объект, который мутировали. Отмена pending-вызовов при переключении (была до
P2-40) теряется так же.

**Второй источник расхождения — реплей против состояния.** `session_load` реплеит клиенту
`events_history`, а состояние живёт в `tool_calls`/`history`. Fallback: если в `events_history`
нет событий `tool_call`, вызовы реплеятся из `tool_calls` со статусом **`pending` жёстко**,
независимо от реального статуса, а `tool_call_update` дописывается отдельным событием. В
эксперименте сработал именно он (`tool_call_fallback_used=True`). Синхронность двух источников
ничем не гарантирована — это и есть расхождение wire↔диск, наблюдавшееся на пяти прогонах.

**Порядок работ (первые два пункта — исправление дефекта, дальше миграция):**
- [x] Одна загрузка на запрос: команда передаёт загруженный объект в функцию (2026-07-30)
- [x] Явное сохранение в конце транзакции `session/load` (2026-07-30)
- [x] Тест: после `session/load` состояние **на диске** соответствует решениям обработчика
      (2026-07-30, `commands/test_session_load_persists.py`)
- [x] Перевод транзакции на `SessionRepository` (фаза D ADR-006) — 2026-07-30
- [ ] Реплей из одного источника: fallback на `tool_calls` убрать либо сделать честным
      (реальный статус вместо жёсткого `pending`)
- [ ] `CachedSessionStorage`: подключить в DI-путь или удалить как мёртвый — решать после
      первых двух пунктов, пока кеш маскирует потери

**Дефект потери исправлен (2026-07-30).** `session_load` принимает уже загруженную сессию
(`session=`, `None` — загрузить самому: путь для прямых вызовов и тестов), команда передаёт
свою копию и сохраняет её в конце транзакции — только при успешном ответе, чтобы ошибочный
запрос не создавал сессию на диске. Отдельное сохранение в ветке осиротевшего permission убрано
как избыточное: финальное покрывает и его.

**Тесты (`commands/test_session_load_persists.py`) читают диск через новый экземпляр
хранилища**, а не мутированный объект — именно на этом предыдущий тест дал ложную зелёную
проверку. Покрыто: клиентский `cwd` доезжает; прерванный turn очищен и вызов `cancelled`;
ответы модели на диске (отложенный хвост P2-40 и отменённый вызов P2-38); загрузка ровно одна
на запрос; осиротевший permission снят; ошибочный запрос не создаёт сессию. Проверено на зубы:
со снятой правкой падают 4 проверки из 6.

**Побочно выяснено:** после round-trip через диск записи истории приходят как `HistoryMessage`,
а свежезаписанные — как dict (поле допускает оба). Первая версия теста фильтровала только
dict'ы и молча пропускала то, что проверяла.

**Живьём пока не подтверждено.** На прогоне 2026-07-30 (`sess_496a4f971f6c`) `session/load`
случился, но событие `session_saved_after_load` было уровня `debug` и в лог не попало —
подтвердить запись было нечем, а состояние на диске объяснялось и путём отмены. Уровень поднят
до `info`: запись на диск на границе транзакции обязана быть видна, как `session_created` и
`session_loaded`.

**Транзакция переведена на порт (2026-07-30, четвёртая транзакция фазы D).**
`SessionLoadCommandHandler` работает через `SessionRepository`: загружает доменный агрегат,
конвертирует в wire для replay и MCP-setup (обе остаются на постоянной wire-границе), в конце
сохраняет через порт. Функция `session_load` больше не знает про хранилище в этом пути:
`storage` стал опциональным (нужен только для самостоятельной загрузки), а `session=None` без
`storage` означает «вызывающий искал и не нашёл» — штатная ошибка «сессия не найдена», причём
после валидации параметров, чтобы порядок ошибок не изменился.

**Гейт миграции — формат сессий на диске.** Здесь он строже, чем в `session/new`: `session/load`
теперь **пишет**, поэтому любая потеря маппера переписала бы существующие сессии. Проверено на
двух живых файлах (`sess_496a4f971f6c` — 40 вызовов, 99 событий; `sess_ff50f9fc98be` — 53
вызова, 145 событий, 589 КБ): round-trip `to_domain → to_protocol` не меняет ни одного поля.
Тест фиксирует, что после `session/load` меняются только `active_turn` и `updated_at`.

**Две известные нормализации маппера — зафиксированы тестом, не «исправлены».** Запись с пустым
`raw_input` и непустыми `tool_arguments` получает заполненный `raw_input` (в домене одно поле
`arguments` — решение фазы B, в wire два); запись истории без ключа `arguments` получает
`arguments: {}`. Обе проявляются только на рукописных записях: боевой путь всегда заполняет и
`raw_input` (`create_tool_call`), и `arguments` (`loop.py`) — на живой сессии 0 из 40 в обоих
случаях. Первые версии моих же тестов ловили именно эти артефакты фикстур, а не дефект.

**Побочно:** `_replay_tool_calls_fallback` вынесен из `session_load` — функция вышла за гейт
сложности (11 > 10) после добавления ветки. Заодно упрощает пункт «честный реплей»: жёсткий
`pending` теперь локализован в одном месте с явным предупреждением.

**Подтверждено живьём (`sess_ff50f9fc98be`, 2026-07-30, сборка сверена по `build_identity`).**
`session_loaded` (events_history=134, plan_replayed=True) и следом `session_saved_after_load` —
транзакция прошла через порт и сохранила результат. Round-trip этой сессии без расхождений.

**Критерий приёмки:** тест на состояние диска после `session/load` зелёный; на живом прогоне
после переключения сессии `cwd` соответствует клиентскому, вызовы прерванного turn'а имеют
статус `cancelled` и ответы `role: tool`.

**Связано:** P0-39 (та же причина — копии сессии на запрос; там обошли процессным реестром),
P2-40 (его ветка обрыва turn'а обесценена этим дефектом), ADR-006 фаза D (транзакция
`session/load` — та, в которой это схлопывается).

---

### 43. Две точки входа разошлись: `server/cli.py` недостижим, но несёт 20 своих флагов — ⬜ ОТКРЫТО (обнаружено 2026-07-30, разведка по ADR-007)

**Файлы:** `src/codelab/cli.py` (достижимый вход, `codelab = codelab.cli:main`),
`src/codelab/server/cli.py` (недостижим: console script один, путей к `server.cli:main` из кода,
`pyproject.toml` и `Makefile` нет, `__main__`-guard отсутствует).

**Как обнаружено.** Искали, подключать ли `CachedSessionStorage` в боевой путь (ADR-007).
Выяснилось, что кеш недостижим не сам по себе — недостижима точка входа, которая его создаёт
(`server/cli.py:283`). Прод-путь `codelab.cli` строит `JsonFileStorage` сам (`cli.py:394`).
E2E-тесты гоняют `codelab serve`, то есть достижимый путь; недостижимый сквозными тестами не
покрыт вовсе.

**Инвентаризация расхождения (измерено, а не на глаз).** Флагов: 26 у недостижимого против 7 у
достижимого. Общие: `--host --port --stdio --require-auth --log-level --trace-messages`.
Только у достижимого: `--agent-command --cwd --no-web --receive-timeout --theme`.

Двадцать флагов только у недостижимого — по тому, доступна ли возможность иначе:

| Флаг | Доступно иначе |
|---|---|
| `--llm-provider/-api-key/-base-url/-model/-temperature/-max-tokens` | да, `CODELAB_LLM_*` |
| `--auth-api-key` | да, `ACP_SERVER_API_KEY` (достижимый CLI читает) |
| `--system-prompt` | да, `CODELAB_SYSTEM_PROMPT` |
| `--config` | да, цепочка TOML (`codelab.toml`, `~/.codelab/codelab.toml`, project-local) |
| `--log-file` | да, есть и в достижимом CLI, и в `shared/logging` |
| `--llm-timeout-connect/read` | да, `CODELAB_LLM_TIMEOUT_CONNECT/READ` |
| `--llm-timeout-write/pool` | **нет** env-эквивалента |
| `--observability-debug` | значение читают три модуля, выставить снаружи нечем |
| `--log-json`, `--fallback-enabled`, `--fallback-order` | **не подключены нигде** вне самого `server/cli.py` — мёртвая обвязка, не функциональность |
| `--storage` | **нет** ни env, ни TOML: путь жёстко `CODELAB_HOME/data/sessions`, режим `memory` недоступен |

Вывод: `server/cli.py` — в основном флаговый дубль конфигурации из переменных окружения.
Реальная потеря возможностей у достижимого входа короткая: `--storage`,
`--observability-debug`, два таймаута (`write`, `pool`).

**Решение (2026-07-30): пока только зафиксировать.** Приоритет отдан надёжности перед хостингом
(ADR-007: ревизия + compare-and-set). Ничего не удаляется и не переносится — инвентаризация
сохранена здесь, чтобы при возврате не проделывать её заново.

**Рассмотренные направления:**

1. *Одна точка входа* — добавить в `codelab.cli` только реально отсутствующее (`--storage` в
   первую очередь), удалить недостижимый дубль. Тогда `CachedSessionStorage` остаётся без
   потребителей и подлежит удалению по правилам проекта вместе с 26 тестами на него.
   `parse_storage_arg`/`describe_storage` сохранить — нужны новому `--storage`.
2. *Сделать `server/cli.py` достижимым* (делегировать `codelab serve` в него) — сохраняет все
   26 флагов одним шагом, но требует убрать оттуда обвязку `CachedSessionStorage` (ADR-007 не
   пускает кеш в боевой путь) и согласовать загрузку `.env`, создание каталогов, запуск TUI.
3. *Оставить как есть* — отклонено как молчаливое расхождение: чем дольше живёт, тем дороже
   выбор, а документация уже расходится с кодом (см. ниже).

**Смежная неточность документации:** roadmap `2.1-double-cache-session-state.md` со статусом
«✅ Выполнено» описывает `CachedSessionStorage` как единый LRU-кеш системы, тогда как в
работающем сервере его нет. Правится вместе с выбором направления.

**Критерий приёмки:** одна точка входа для `codelab serve`; возможности из короткого списка
доступны (`--storage` обязательно); документация не описывает несуществующий кеш.

**Связано:** ADR-007 (владение состоянием сессии; кеш отклонён как механизм разделения),
P0-39 (обошли отсутствие общего состояния процессным реестром).

---

### 44. Реестр терминалов переживает перезапуск, а сами терминалы — нет — ✅ ЗАКРЫТО (2026-07-30)

**Файлы:** `protocol/state.py:94` (`terminals` персистится, схема v5),
`protocol/handlers/session.py::session_load` (реестр не чистится при загрузке),
`tools/executors/terminal_executor.py` (потребитель).

**Симптом (прогон `sess_b959781bd8bf`, pid 9740).** Три ошибки уровня `error` подряд по одному
идентификатору терминала — `output`, `wait_for_exit`, `release`, все с `RPC Error -32603:
Internal error` от клиента. В логе этого процесса терминал **не создавался**: он остался от
предыдущего процесса. Сервер перезапустили, сессия загрузилась вместе с реестром терминалов, и
модель по восстановленной истории обратилась к дескриптору, которого уже нет. На момент
обнаружения в сессии два таких «живых» терминала.

**Причина.** `SessionState.terminals` — часть персистируемого документа (добавлен в схему v5),
но сами терминалы живут в процессе клиента и рестарт не переживают. При загрузке сессии реестр
не пересматривается, поэтому остаются записи, ведущие в никуда.

**Почему это заметно.** Модель получает `Internal error` вместо внятного ответа и не понимает,
что терминала больше нет: по логу видно, что она пробует по нему три операции подряд. Плюс
ошибки уровня `error` на ровном месте зашумляют критерий «ноль ошибок в прогоне», которым мы
пользуемся при разборе логов.

**Направления (решить при взятии):**
1. Чистить реестр при загрузке сессии — дескрипторы клиента процесс не переживают, значит
   запись после рестарта заведомо мертва. Просто и честно; следствие — модель, сославшаяся на
   старый терминал, получит «терминал не найден» вместо `Internal error`.
2. Помечать записи как недоступные и отвечать модели понятным текстом («терминал не пережил
   перезапуск сервера, создайте новый»), сохраняя запись для реплея.

**Критерий приёмки:** после перезапуска сервера обращение к терминалу из прошлой сессии не даёт
ошибок уровня `error`, а модель получает ответ, из которого понятно, что нужно создать терминал
заново.

**Связано:** P2-27 (гонка алиасов терминалов — другая проблема того же реестра), ADR-007
(состояние сессии: что переживает рестарт, а что нет — здесь ровно этот вопрос).

**Решено отметкой владельца, а не слепой очисткой (2026-07-30).** Очистка реестра при каждой
загрузке убивала бы **живые** терминалы, когда сессию перезагружает тот же процесс — например
при переключении между сессиями в одном сеансе. Поэтому `TerminalAliasRegistry.register`
помечает реестр токеном процесса (`process_identity.PROCESS_TOKEN`, уникален на запуск: pid
непригоден, ОС их переиспользует), а `session/load` убирает только чужие. Неизвестный владелец
трактуется как чужой: сессия записана до появления отметки, значит точно другим процессом.

Счётчик alias'ов не сбрасывается — иначе новый терминал получил бы номер, уже встречающийся в
истории. После очистки обращение к старому alias'у идёт по **существующему** пути «неизвестный
терминал», поэтому модель получает внятный ответ без единой строки нового кода.

Формат: поле `terminals_owner`, миграция v7→v8 (парное поле в домене, маппер несёт в обе
стороны).

**Побочно:** `migrate_schema` перестроена в таблицу шагов — цепочка `if version < N` росла с
каждой версией и упёрлась в гейт сложности (11 > 10). Теперь добавление версии — одна строка, и
нельзя забыть проставить `schema_version`.

**Подтверждено живьём** (2026-07-30, два процесса): `terminals_dropped_from_previous_process
dropped=2` в каждом, `RPC Error -32603` — ноль против трёх в прогоне до правки. Обе половины
правила видны в состоянии: у сессии, загруженной другим процессом, реестр пуст (счётчик 23
сохранён), у сессии текущего процесса — пять терминалов на месте с токеном владельца.

**Не закрыто этой правкой:** клиент может переподключиться без перезапуска сервера (websocket),
и тогда терминалы мертвы, а токен процесса тот же. Для stdio это невозможно — клиент сам
запускает сервер. Отмечено на случай, если сценарий станет реальным.

### 45. Слияние при конфликте ревизий дублирует историю: два ответа `role: tool` на один вызов — ✅ ЗАКРЫТО (2026-07-31 заплатка, 2026-08-03 корень снят)

**Файлы (на момент дефекта):** `protocol/session_merge.py:57` (`_common_prefix_length`),
`protocol/state.py:150` (`history: list[HistoryMessage | dict[str, Any]]` — источник расхождения
типов). Обоих больше нет: turn пишет состояние командами, слияние удалено целиком, а поле
истории сужено до `list[HistoryMessage]` (ADR-006, фаза D шаг 4).

**Симптом (прогон `sess_ffff9be366bd`, pid 74078 и 76576, 2026-07-31).** В сохранённой истории
шесть записей-дублей. Дублируется не одна запись, а **непрерывный блок**: индексы 5–9
повторяются как 10–14 — ответ инструмента, assistant-сообщение с тремя `tool_calls` и все три
ответа на них. Итог: **пять `tool_call_id` имеют по два ответа `role: tool`**, а три из них ещё и
дважды встречаются в assistant-сообщениях. Контракт LLM-API требует ровно один `role: tool` на
`tool_call_id`, и это ровно тот класс расхождений, из-за которого модель ходит по кругу (P2-38).

**Причина — расхождение типов, а не гонка.** `SessionState.history` объявлена как
`list[HistoryMessage | dict[str, Any]]`. Записи, добавленные в этом процессе, лежат **плоскими
dict**, а те же записи, прочитанные с диска, валидируются в **`HistoryMessage`**. Поэтому
`_common_prefix_length` сравнивает `dict` с моделью, получает неравенство на первой же записи
текущего turn'а и обрывает префикс. Дальше срабатывает правило «дописать свой хвост» — и хвост
дописывается **повторно**, хотя он уже на диске. Воспроизведено детерминированно, без гонки:

```
типы в памяти:        ['dict', 'dict']
типы после round-trip: ['HistoryMessage', 'HistoryMessage']
общий префикс:        0 из 2
после слияния записей: 4 (было 2)
```

**Почему проявилось только сейчас.** До пошаговых записей turn'а (ADR-007) хвост turn'а на диск
не попадал, и «дописать свой хвост» было верным действием. С пошаговыми записями хвост уже на
диске — правило стало дублировать, а сравнение по префиксу этого не замечает из-за типов. Два
шага ADR-007, каждый корректный по отдельности, вместе дают дефект.

**`events_history` не затронут** — он объявлен `list[dict[str, Any]]`, обе копии сравниваются как
dict, префикс находится, дублей в прогоне ноль. Это же подтверждает диагноз: дело в типе, а не в
содержимом.

**Направления (решить при взятии):**
1. Сравнивать нормализованные записи (единая форма — dict либо модель) в
   `_common_prefix_length`. Дешевле всего, но лечит симптом: расхождение типов останется.
2. Убрать союз типов из `history`: одна форма записи на всём пути (кандидат — доменный
   `ConversationMessage`, ср. фазу D ADR-006, где история уже сведена к единому сейму).
   Устраняет причину, но задевает всех писателей истории.
3. Сделать слияние журналов идемпотентным по идентичности записи (например, не дописывать
   `role: tool` для `tool_call_id`, у которого ответ уже есть). Защита на случай, если хвост
   частично на диске.

**Критерий приёмки:** после отмены посреди turn'а в сохранённой истории нет ни одного
`tool_call_id` с двумя ответами `role: tool` и ни одного дубля записи; сверка на живом прогоне с
отменой.

**Связано:** ADR-007 (слияние при конфликте — там эта шероховатость записана как «дубль ответа по
одному `tool_call_id`», но механизм назван неверно: дело не в служебном ответе отмены, а в
повторной записи хвоста), P2-38 (тот же инвариант «один ответ на вызов»), ADR-006 фаза D
(переход истории на доменную форму снимает союз типов).

**Закрыто приведением формы записи при сравнении (2026-07-31).** `_common_prefix_length`
сравнивает записи, приведённые к `HistoryMessage`; несовместимая форма сравнивается как есть,
чтобы приведение не проглатывало посторонние записи. Выбран вариант 1 из направлений —
осознанно как **защита, а не решение**: союз типов остаётся, и корень снимается переводом
истории на одну форму вместе с turn-путём в фазе D. Вариант 3 (идемпотентность по
`tool_call_id`) не понадобился: после приведения хвост распознаётся целиком, а не по одной
записи.

Почему не стали ждать фазу D, хотя она снимает корень: правило «дописать свой хвост» портит
хранимую историю **на каждой** отмене посреди turn'а (в разобранном прогоне — две отмены за шесть
минут), а фаза D исправит поведение, но не подчистит уже записанное. Цена защиты — одна функция.

**Проверено воспроизведением, а не только тестом.** На том же сценарии со сравнением «как есть»
и с приведением:

```
до правки:  5 записей, ответы role=tool: ['llm_1', 'llm_2', 'llm_1']   ← дубль
после:      3 записи,  ответы role=tool: ['llm_1', 'llm_2']
```

**Почему дефект не ловился тестами.** Тест `test_no_duplicate_when_mine_is_ahead_of_base`
сравнивал dict с dict — форм, которые в бою не встречаются вместе. Добавлены два теста: unit на
две формы одной записи и сквозной через `JsonFileStorage` (пошаговая запись turn'а → отмена →
слияние), где формы расходятся сами, как в проде.

**Подтверждено живьём** (2026-07-31, `sess_3f7d87be63e6`). В прогоне сработало ровно то условие,
которое давало дефект: отмена посреди turn'а при включённых пошаговых записях →
`session_save_merging_after_conflict actual_revision=14 expected_revision=13` →
`session_save_merged`. На диске после этого: **0 дублей записей истории, 0 `tool_call_id` с двумя
ответами, 44 вызова и ровно 44 ответа `role: tool`**, расхождений «последний статус в
`events_history` = статус в `tool_calls`» — ноль. До правки этот же сценарий дописывал хвост
turn'а повторно.

**Не закрыто этой правкой:** сам союз типов `HistoryMessage | dict` в `SessionState.history` —
источник расхождения. Любой новый сравнивающий код наступит на то же. Снимается фазой D.

---

### 46. `active_turn` не очищается по завершении turn'а → «orphaned permission request» при каждом перезапуске — ✅ ЗАКРЫТО (2026-07-31)

**Файлы:** `protocol/commands/session_load.py:94` (место, где симптом виден),
`protocol/handlers/pipeline/stages/turn_lifecycle.py` / `handlers/prompt/permission_response.py`
(кандидаты на владельца очистки — установить при взятии).

**Симптом.** `session_loaded_with_orphaned_permission_request` в логе **каждого** перезапуска. Ранее
две гипотезы не были различены: (H1) процесс умер, пока turn действительно ждал разрешения;
(H2) `permission_request_id` остаётся в состоянии после ответа.

**Обе подтверждены, и вторая — устойчиво (2026-07-31, `sess_ffff9be366bd`).** H1: процесс 74078
умер, когда `call_011` реально ждал разрешения, — предупреждение при загрузке в 76576 законно.
H2: покадровый опрос файла сессии (10 мс, 25 с) показал **один кадр** — состояние не транзиентное:

```
время      rev  phase                perm_req  perm_call  статус_вызова
08:52:46   184  awaiting_permission  b3716ecc  call_075   completed
```

То есть `active_turn` живёт с фазой `awaiting_permission` и id **уже отвеченного** запроса, а
вызов, к которому он привязан, давно `completed` (по логу его `resume_after_permission` прошёл в
05:49:14, снимок сделан спустя 3 минуты покоя). На диске 76 вызовов, все терминальные, — turn'а
нет, а `active_turn` есть.

**Следствия:**
1. Предупреждение при загрузке вводит в заблуждение: «осиротевший запрос разрешения» на деле
   отвечен, а ветка очистки сбрасывает `active_turn` и трогает вызовы (тот же класс расхождений
   wire↔диск, что описан в ADR-006 по `call_046`).
2. `session/cancel` по такой сессии пишет tombstone для отвеченного запроса и логирует
   `active_turn_cleared=True`, хотя живого turn'а не было. В прогоне: два tombstone
   (`31405d3f`, `30929ffc`) и **ноль** отменённых вызовов.
3. Скан при разрыве соединения (`cancel_active_turns_on_disconnect`) считает такую сессию
   сессией с активным turn'ом и «отменяет» её — счётчик отменённых turn'ов завышается.

**Направления (решить при взятии):** найти владельца очистки (`permission_request_id` +
`phase` + сам `active_turn`) на нормальном завершении turn'а и убедиться, что финальная запись
её доносит до диска; проверить, не съедает ли её слияние — правило «`active_turn` из свежей
копии» (ADR-007) по построению возвращает на диск ту версию turn'а, что лежала там до записи.

**Критерий приёмки:** после штатного завершения turn'а на диске `active_turn: null`; перезапуск
на такой сессии не даёт `session_loaded_with_orphaned_permission_request`.

**Связано:** P2-42 (`session/load` и его ветка orphan), ADR-007 (правило слияния про
`active_turn`), P1-45 (тот же прогон, второй дефект слияния).

**Причина найдена и оказалась не в слиянии (2026-07-31).** Гипотеза про правило «`active_turn`
из свежей копии» не подтвердилась. Настоящая причина — P1-49: путь ответа на permission-request
снимал `permission_request_id`/`permission_tool_call_id` в копии, которую никто не сохранял,
поэтому с диска они возвращались как были. Ветка orphan в `session_load.py:98` смотрит именно на
`active_turn.permission_request_id`, отсюда предупреждение при каждом перезапуске.

**Закрыто вместе с P1-49** (транзакция 6 фазы D): идентификаторы теперь доезжают до диска.
Проверено живьём — `permission_request_id: None` в файле сессии сразу после ответа.

**Остаток, замеченный на том же прогоне:** строковое поле `active_turn.phase` после возобновления
остаётся `awaiting_permission` — его никто не переводит назад в `running`. На предупреждение это
не влияет (проверяется идентификатор, не фаза), но фаза как признак состояния turn'а врёт.
Место правки — типизированный `TurnPhase` вместо строковых литералов (заявлен в ADR-006 при вводе
`TurnState`); отмечено, чтобы не потерялось.

**Остаток выделен в P2-54 (2026-07-31).** Подтверждён на втором прогоне и оказался шире, чем
«забытый перевод фазы»: у записи фазы нет единственной двери — пять мест в трёх модулях пишут её
напрямую, а валидирующий `set_turn_phase` не имеет вызывающих вовсе. Ведётся отдельным пунктом,
здесь больше не отслеживается.

**Проверка на новом прогоне (2026-07-31, `sess_cad48ab15233`): предупреждение вернулось — и это
законно.** Разбор показал H1, а не регрессию: последней строкой умершего процесса была пауза на
разрешении для `call_031` (09:43:38.396), клиент перезапустился через 11 секунд, и запрос
действительно оставался неотвеченным. Ветка загрузки отработала верно — `call_031` на диске
`cancelled`, расхождений wire↔состояние ноль.

**Побочно закрыт пробел наблюдаемости, из-за которого различать H1 и H2 приходилось покадровым
снимком.** Событие паузы (`permission_request_sent_pausing_agent_loop`) называло только
`tool_call_id`, тогда как `permission_response_applied` и предупреждение при загрузке называют
запрос идентификатором — лог не сшивался. Теперь пауза логирует и `permission_request_id`, поэтому
«умер на реальной паузе» против «идентификатор не сняли» видно прямо из лога.

---

### 47. Часть логов идёт мимо structlog: строки без уровня, времени и сессии — ⬜ ОТКРЫТО (обнаружено 2026-07-31, анализ логов)

**Файлы:** 22 модуля на `logging.getLogger` вместо structlog (в т.ч.
`agent/llm_adapter.py`, `mcp/client.py`, `mcp/manager.py`, `mcp/*_transport.py`,
`observability/exporters/*`, `protocol/notification_bus.py`), плюс stdout litellm.

**Симптом (прогон `sess_ffff9be366bd`).** В файле лога 80 строк из 1434 не имеют ни метки
времени, ни уровня, ни `pid`/`session_id`: 61 — `LiteLLM completion() model= ...` (stdout
библиотеки), 19 — наш собственный экспортёр observability (`Exported N spans to ...`,
`%`-форматирование stdlib-logging).

**Почему это важнее, чем шум.** Разбор логов в этой ветке опирается на критерий «ноль строк
уровня `error`/`warning` за прогон» — им подтверждены почти все шаги ADR-006/ADR-007. Строки без
уровня в этот критерий **не попадают вообще**. Сегодня через этот канал шли только безобидные
сообщения, но `logger.error` из тех же 22 модулей (MCP-транспорты, LLM-адаптер) уйдёт туда же и
останется невидимым. То есть критерий чистоты прогона тише, чем кажется.

**Направления:** свести 22 модуля на structlog (конвенция проекта); вывод сторонних библиотек
завести в structlog через `logging.captureWarnings`/`ProcessorFormatter` либо глушить на уровне
litellm (`litellm.set_verbose=False` / `suppress_debug_info`).

**Критерий приёмки:** в файле лога нет строк без уровня и метки времени; `logging.getLogger` в
`src/codelab/server` не встречается (или сведён к мостовому хендлеру в structlog).

**Подтверждено на втором прогоне (2026-07-31, `sess_b93658bfd522`) — доля выросла.** 43 строки из
735 без уровня и метки времени (было 80 из 1434, то есть 5.9% против 5.6%): 17 —
`LiteLLM completion() model= MiniMax-M3; provider = openai`, 4 — `Exported N spans/events/metrics`,
1 — `Retrying request to /chat/completions in 0.446388 seconds` (клиент openai, ещё один сторонний
канал сверх litellm). Наши точки уточнены до строк: `observability/exporters/file_span_exporter.py:103`,
`file_event_exporter.py:129`, `file_metrics_exporter.py:161` — везде `logging.getLogger(__name__)` и
`%`-форматирование; всего в экспортёрах 14 вызовов stdlib-логгера. Счёт модулей не изменился: 21 в
`src/codelab/server`, 22 в `src/codelab`.

**Атрибуция вывода litellm исправлена (2026-08-04).** Записанное выше «stdout библиотеки» неверно:
`verbose_logger` получает `logging.StreamHandler()` без аргументов, то есть **stderr**, и
дополнительно всплывает в root, откуда попадает в наш файл лога (`setup_logging` ставит handlers
через `basicConfig(force=True)`). Практическое следствие важно для рабочего режима: в `--stdio`
поток JSON-RPC в stdout библиотека не портит — проверено живьём прогоном `initialize` +
`session/new` через пайп (2 строки в stdout, обе JSON-RPC, не-JSON строк 0). Дефект остаётся
дефектом наблюдаемости — строки без уровня и времени не попадают в критерий «ноль error/warning», —
но не рисуется как угроза протоколу.

**Уточнение (2026-08-04, накопленный разбор за 2026-07-24 … 2026-08-04).** Канал воспроизводится
на каждом прогоне: ~41 строка litellm за сессию. У экспортёров
observability добавилось второе нарушение сверх stdlib-логгера: файлы отчётов **именуются наивным
локальным временем** (`datetime.now()` без tz — `file_span_exporter.py:82,87`,
`file_event_exporter.py:84,161`, `file_metrics_exporter.py:97`), тогда как строки лога — в UTC
(локаль машины UTC+3). При разборе это даёт трёхчасовое расхождение между именем файла и его
содержимым — уже приводило к сверке не тех окон. Тем же наивным `now()` считается и порог
ретенции (`:203`, `:173`, `:214`), то есть удаление старых файлов сдвинуто на ту же величину.

**Связано:** P2-41 (наблюдаемость сборки — тот же мотив «по логу должно быть видно»), P2-37
(уровни логов как инструмент, а не украшение).

---

### 48. Сервер спавнится дважды: второй процесс не обслуживает ни одного запроса — ⬜ ОТКРЫТО (обнаружено 2026-07-31, анализ логов)

**Симптом.** На каждый запуск клиента в логах два процесса с совпадающими до микросекунды
метками старта: `74078`/`74079` (05:42:23.354605 и .354606) и `76576`/`76591`
(05:43:22.045041 у обоих). Первый обслуживает всё (181–432 КБ лога), второй заканчивается на
`stdio transport started` и больше не пишет ничего (4.3 КБ, ноль запросов).

**Цена.** Двойная инициализация на запуск: LLM-провайдеры, MCP-менеджер, реестр инструментов,
подписка на шину — всё в холостом процессе, который затем просто висит. Плюс лишний файл лога на
каждый запуск, что путает разбор: приходится каждый раз выбирать «настоящий» лог по размеру.

**Уточнение по содержимому холостого процесса (2026-07-31).** Прочитан его лог целиком (22
строки): он поднимает четыре LLM-провайдера, реестр моделей, конфигурации агентов, `LLMAdapter`,
реестр стратегий, `StrategyDispatcher`, `LLMLoopStage` и **менеджер flush'а observability с
интервалом 60 с** — то есть это не «процесс-заготовка», а полностью собранный агент, который
периодически просыпается и не обслуживает ни одного запроса.

**Направления:** совпадение метки до микросекунды говорит о двух процессах из одного места, а не о
рестарте.

**Критерий приёмки:** один запуск клиента — один процесс сервера и один файл лога.

**Воспроизведено ещё дважды (2026-07-31, оба запуска подряд).** Пары `94654`/`94655`
(10:47:53.984773 и .984789) и `97264`/`97265` (10:51:05.052627 и .052614) — расхождение метки 14-16
микросекунд. Холостые процессы снова по 4343 байта (22 строки, конец на `stdio transport started`),
рабочие — 91 КБ и 131 КБ. Разброс метки настолько мал, что рестарт исключён окончательно: два
`Popen` из одного места.

**Отдельно — риск, а не только цена.** Холостой процесс поднимает полный агент с тем же
`JsonFileStorage`, то есть на каждый запуск существует второй потенциальный писатель в то же
хранилище. Сегодня он молчит, потому что не получает запросов, но это прямо против инварианта
владения ADR-007 («состояние принадлежит транзакции»): блокировки в `SessionRepository` живут в
экземпляре и между процессами не разделяются.

**Воспроизведено под сторонним клиентом (2026-08-04).** Пары воспроизводятся при запуске сервера из
Zed, где нашего клиента в схеме нет вовсе: `74577`/`74578` (05:10:29.423895 / .423893),
`76979`/`76980` (05:12:26.097812 / .097810), `12849`/`12850` и `59506`/`59507` — все `transport=stdio`,
`version=0.2.0` из pipx-сборки. Холостые близнецы по 4343 байта, все заканчиваются на
`stdio transport started`.

**Спавнит Zed, а не мы — измерено покадрово (2026-08-04).** Промежуточная версия этой записи
утверждала обратное («удвоение на нашей стороне»), выведя это из расхождения метки в микросекунды.
Прямое измерение её опровергло. Съёмка таблицы процессов с шагом 0.1 с в момент удвоения:

```
PID=59506 ppid=69380 start=11:42:54 stdin=PIPE
PID=59507 ppid=69380 start=11:42:54 stdin=PIPE      69380 = /Applications/Zed.app/.../zed
```

**Оба процесса — дети Zed.** При `fork` на нашей стороне у второго был бы `ppid=59506`. Искать в
нашей точке входа нечего.

**Триггер выделен, и он узкий.** Удвоение даёт **закрытие окна Zed с немедленным повторным
открытием, без выхода из приложения** — две попытки из двух. Не дают: старт Zed с чистого листа
(25568 — один процесс), создание новой сессии, переключение треда (тот же 25568 обслужил
переключение сам, прожив 57 минут). Zed держит **один агент на окно** и переиспользует его между
тредами. Отсюда и рабочая версия механизма: гонка при переподключении — Zed поднимает нового
агента, не дождавшись ухода предыдущего, и проигравшего снимает.

**Открытое наблюдение: раннее совпадение меток подтверждено побайтово (2026-08-04).** Сначала было
замечено совпадение метки `build_identity` до микросекунды у пары `59506`/`59507`. На четвёртой паре
(`13360`/`13361`) проверено строго: **первые две записи в логах обоих процессов идентичны
байт-в-байт**, различается только `pid`, а расхождение начинается с третьей записи:

```
13360:  .397522 build_identity   .397724 starting_server_mode   .398083 starting stdio server
13361:  .397522 build_identity   .397724 starting_server_mode   .398080 starting stdio server
```

Два независимо запущенных процесса не могут совпасть по микросекунде на двух записях подряд и
затем разойтись. Механизм не найден: очереди в логировании нет (ни `QueueHandler`, ни листенера),
`_add_pid` и `TimeStamper` работают синхронно в одном вызове `logger.info`, поэтому версия «штамп
времени от родителя, pid от ребёнка» не проходит — оба ставятся в одном месте одного процесса.
Следствий у наблюдения нет, но объяснение, скорее всего, укажет на настоящую природу удвоения,
поэтому оно записано с данными, а не отброшено. При взятии пункта начинать стоит отсюда.

**Что из этого наш дефект.** Не близнец: он живёт секунды и снимается клиентом. Наш — то, что
процесс не завершался сам (P2-59): пока это было так, любой клиент без принудительного добивания
оставлял агента навсегда. После исправления P2-59 близнец уходит по сигналу сам, и остаточная цена
удвоения — несколько секунд второго писателя в то же хранилище.

**Почему это важнее, чем «лишний процесс», именно в stdio-режиме.** Рабочий транспорт пользователя —
stdio через сторонний клиент, то есть удвоение случается на **каждом** его запуске. Холостой близнец
поднимает полный агент с тем же `JsonFileStorage`: на каждый запуск существует второй потенциальный
писатель в то же хранилище, вне области владения ADR-007. Молчит он только потому, что запросов не
получает (в его логе 0 обслуженных методов) — но это свойство расписания, а не гарантия.

**Связано:** P2-41 (`build_identity` — им и различили процессы), P2-43 (точки входа — двойной спавн
и есть повод разобраться с ними), ADR-007 (инвариант владения; второй процесс — писатель вне его
области), P2-53 (тот же класс: спавн без владельца жизненного цикла, но с утечкой; в отличие от
P2-48 живёт только в websocket-режиме).

---

### 49. Решение по permission-request не сохранялось: политика, идентификаторы и статус теряли до диска — ✅ ЗАКРЫТО (2026-07-31)

**Файлы:** `protocol/response_router.py::_resolve_permission_response`,
`protocol/handlers/prompt/permission_response.py`.

**Симптом, замеренный на файловом backend'е.** Ответ на `session/request_permission`
применялся к копии сессии, которую **никто не сохранял**: роутер находил сессию, звал
`resolve_permission_response_impl` и возвращал outcome — записи не было ни в роутере, ни ниже.
Проба на `JsonFileStorage` до правки:

```
ревизия: 1 -> 1                       ← ни одной записи
permission_policy на диске: {}        ← решение allow_always потеряно
active_turn.permission_request_id: perm_1   ← снятый id вернулся с диска
phase: awaiting_permission
call_001.status: pending              ← клиенту уже отправлен in_progress
```

**Три следствия, каждое наблюдалось живьём:**
1. `allow_always`/`reject_always` не запоминались — следующий вызов того же kind спрашивал
   снова. В разобранном прогоне: **41 запрос разрешения за сессию при пустом
   `permission_policy`** на диске.
2. `active_turn` сохранял идентификатор уже отвеченного запроса — это и есть причина P2-46
   (`session_loaded_with_orphaned_permission_request` при каждом перезапуске).
3. Статус вызова на диске расходился с тем, что отправлено клиенту (класс P2-42).

**Почему не ловилось тестами.** Все тесты этого пути работали на `InMemoryStorage`, который
отдаёт сам хранимый объект: мутации копии там выглядят сохранёнными, и дефект класса «забыли
записать» невидим. Та же оговорка уже фиксировалась в ADR-007 при сверке ревизий.

**Закрыто транзакцией 6 фазы D (ADR-006).** Путь переведён на доменный агрегат внутри
`SessionRepository.transaction`: одна загрузка, блокировка на сессию, запись на успешном выходе.
Забыть сохранение больше нельзя конструктивно. Фоновое исполнение вызова стартует уже после
выхода из области (`core.handle`), поэтому читает зафиксированное состояние, а не полуправку.

**Подтверждено живьём** (2026-07-31, две ветки решения):

```
allow_always → policy {'read': 'allow_always'}, permission_request_id: None, вызов исполнен
reject_always → ревизия 1→2 (одна запись), active_turn: None, вызов cancelled,
                хвост батча отвечен (llm_2), клиенту ушёл stopReason: cancelled
```

**Связано:** P2-42 (тот же класс «мутации без записи», другой метод), P2-46 (следствие),
P2-40/P2-38 (хвост батча при отказе), ADR-006 фаза D.

---

### 50. Отменённый пользователем RPC инструмента выглядит как сбой: вызов `failed`, модель слышит «ошибка» — ✅ ЗАКРЫТО (2026-07-31)

**Файлы:** `tools/integrations/client_rpc_bridge.py` (ветка `ClientRPCError` вокруг
`terminal/wait_for_exit`), путь результата инструмента в историю.

**Симптом (прогон `sess_f95e3fc5563d`, pid 16218).** Пользователь отменил turn, пока клиентский
`terminal/wait_for_exit` ждал 25 секунд. Отмена сработала штатно, но её последствия названы
сбоем:

```
07:31:03.388 client_rpc_cancelled  method='Ошибка при ожидании завершения терминала'
07:31:03.388 tool handler execution completed  has_error=True success=False
07:31:03.389 tool_result_to_history  content='Ошибка при ожидании завершения терминала: term_5'
на диске:    call_036  status=failed
```

**Три отдельных следствия:**
1. **Статус вызова `failed` вместо `cancelled`.** Отмена — не сбой инструмента; в ACP
   `cancelled` есть именно для этого. Инвариант «последний статус в `events_history` = статус в
   `tool_calls`» при этом цел (клиенту тоже ушло `failed`), то есть неверная семантика
   согласованно доехала до обеих сторон.
2. **Модель получает результат с признаком ошибки** там, где был штатный cancel, и по такому
   ответу может «починить» несуществующую поломку — переспросить терминал, пересоздать его.
3. **Поле `method` в логе несёт человеческую фразу**, а не имя метода
   (`method='Ошибка при ожидании завершения терминала'`), из-за чего событие не фильтруется по
   методу.

**Половина уже исправлена.** Уровень лога понижен с `error` до `info`
(`client_rpc_cancelled`) — это снимало ложный «единственный error за прогон» в критерии чистоты
разбора. Осталась вторая половина, заявленная тогда же в ADR-006: отделить отмену от сбоя в
**результате** инструмента и в статусе вызова.

**Направление:** различать `ClientRPCError` по причине (отмена против таймаута/сбоя) на границе
`client_rpc_bridge`; для отмены — статус `cancelled` и текст результата без слова «ошибка»
(«вызов отменён пользователем»), для сбоя — как сейчас.

**Критерий приёмки:** после отмены turn'а во время активного клиентского RPC вызов на диске и в
`events_history` имеет статус `cancelled`, а в истории модели — ответ, из которого видно, что это
отмена, а не поломка.

**Связано:** P2-37 (там же понижен уровень лога — эта запись про оставшуюся половину), ADR-006
(наблюдение зафиксировано при разборе прогона 2026-07-28), P2-38 (контракт «один внятный ответ на
вызов»).

**Причина оказалась в асимметрии моста (2026-07-31).** `client_rpc_bridge` пробрасывал
`ClientRPCCancelledError` для fs-методов, но терминальные возвращали `None`/`False` — и на отмену,
и на сбой. Executor их не различал по построению, поэтому и текст, и статус получались как у
поломки. Теперь отмена пробрасывается всеми методами (поведение единообразно), а сбой по-прежнему
даёт `None`/`False`.

**Признак отмены доведён до статуса вызова.** У `ToolExecutionResult` появилось поле `cancelled`
(отдельно от `success=False`: отмена — не сбой), терминальный и fs-executor его выставляют, а
`ToolCallProcessor` переводит вызов в `cancelled` вместо `failed`. Модель получает «Ожидание
завершения терминала отменено пользователем», без слова «ошибка».

**Побочно закрыт источник расхождения wire↔диск.** Нотификация resume-пути считала статус заново
(`"completed" if tool_result.success else "failed"`) и потому не знала про отмену. Теперь статус
берётся из состояния — того самого, что уходит на диск, — с оговоркой: нетерминальный статус
означает, что писатель до него не дошёл, и тогда используется вывод из `success` (отдать клиенту
`pending` как итог исполнения нельзя).

**Поле `method` в логе** несёт имя ACP-метода (`terminal/wait_for_exit`), а не человеческую фразу.

**Проверка.** Тест на три ветки моста (отмена wait_for_exit, отмена create, обычный сбой остаётся
сбоем) и тест на то, что статус клиенту берётся из состояния, а не из `success`. Два теста,
закреплявших прежний контракт (`result is None` / `result is False` на отмене), обновлены — они
фиксировали ровно ту асимметрию, из которой вырос дефект. Живьём не проверено: нужен turn от
модели с активным терминалом и отменой в момент ожидания; воспроизведение — на тестах.

---

### 51. Классификация задачи стоит лишний LLM-вызов на каждый промпт, а на коротких продолжениях вырождена — ⬜ ОТКРЫТО (обнаружено 2026-07-31, анализ логов)

**Файлы:** `agent/context/task_analyzer.py::LLMBasedTaskAnalyzer.analyze`,
`agent/context/baseline_builder.py:101`, конфиг `[agents.context].analyzer_model`.

**Замер (четыре прогона 2026-07-31, шесть промптов).** Перед каждым обращением к модели
`ContextManager` вызывает LLM-классификатор задачи. Это **отдельный LLM-запрос**, и он на
критическом пути — до первого токена ответа:

| промпт | `llm_call_ms` | `context.build.complete` | результат |
|---|---|---|---|
| «проанализируй код проекта и составь план работ» | 3740 | 3933 | depth=3, modules=5 |
| «продолжай» | 2144 | 5911 | depth=1, modules=0 |
| «продолжай» | 2441 | 2553 | depth=3, modules=0 |
| «начинай» | 2389 | 2570 | depth=3, modules=4 |
| «продолжай» | 2585 | 2619 | depth=2, modules=0 |
| «продолжай» | 5395 | 5434 | depth=1, modules=0 |

Итого ≈23 секунды ожидания на шесть промптов, в среднем 3.8 с — и это **до** того, как модель
начнёт отвечать. Классификация — доминирующая часть сборки контекста: `gather` укладывался в
32–192 мс во всех прогонах кроме одного (3766 мс, это уже P2-34).

**Два отдельных наблюдения, а не одно:**
1. **На коротких продолжениях классифицировать нечего.** Четыре из шести промптов — `продолжай`
   и `начинай` (7–9 символов). В них нет сигнала о задаче, и результат это подтверждает:
   `target_modules_count=0` во всех четырёх. Тем не менее вызов делается и стоит 2–5 секунд.
   Защита «нечего классифицировать → эвристика» в анализаторе **уже есть** — но только для
   провайдеров без structured output; для вырожденного промпта её нет.
2. **Решение о глубине исследования нестабильно.** Один и тот же промпт `продолжай` дал
   `investigation_depth` 1, 3, 2 и 1 в четырёх случаях. Глубина управляет объёмом сбора
   контекста, то есть на одинаковом вводе система собирает разный контекст — воспроизводимость
   отсутствует.

**Про конфигурацию — честно.** В `~/.codelab/codelab.toml` стоит
`analyzer_model = "litellm/openai/MiniMax-M3"`, то есть служебная классификация идёт на **основной
рабочей модели**, тогда как дефолт в коде и документации — `openai/gpt-4o-mini`. Часть цены —
следствие настройки. Но и с дешёвой моделью два наблюдения выше остаются: лишний round-trip на
«продолжай» и случайная глубина.

**Направления (решить при взятии):**
1. Не вызывать классификатор, когда классифицировать нечего: короткое продолжение без нового
   задания — переиспользовать профиль предыдущего turn'а (задача та же) либо уйти в эвристику.
   Профиль задачи сейчас не кешируется вовсе.
2. Развести модели: служебная классификация не обязана идти на рабочей модели. Проверить, что
   дефолт из документации действительно применяется, если `analyzer_model` не задан.
3. Сделать глубину детерминированной для одинакового ввода (температура/seed или эвристика).

**Критерий приёмки:** повторное «продолжай» не добавляет LLM-вызова к сборке контекста, а
`context.build.complete` на таком промпте укладывается в сотни миллисекунд.

**Уточнение (2026-08-04): у вызова есть не только цена, но и тихий отказ.** Разбор ответа
классификатора — `_parse_classification` (`task_analyzer.py:194`) — ищет JSON жадной регуляркой
`\{[\s\S]*\}`. При обрыве ответа модели (усечение по `max_tokens=500`, обрыв соединения) скобка не
закрыта, совпадения нет, и результат LLM-вызова **выбрасывается**: анализатор уходит в
`_fallback_classify` и подставляет эвристический `task_type` (по умолчанию `feature`). Отказ
логируется на `warning` (`context.task_analyze.parse.no_json_found`), но вызывающий его не видит и
работает с подменённым профилем — то есть 2–5 секунд оплачены, а решение принято эвристикой.
Замеры за 2026-08-01 … 2026-08-04 подтверждают порядок цены: `context.task_analyze` 1.7–4.9 с на
turn. Направление сверх перечисленных: при провале разбора отдавать признак «классификация не
состоялась», а не молча подменять профиль; вырожденную жадную регулярку заменить разбором
JSON-блока.

**Воспроизведено 2026-08-06 (`pid 78177`), и прогон добавил пробел наблюдаемости.** По логу
**причину отказа отличить нельзя**: `no_json_found` пишет только `response_preview`, обрезанное на
200 символов, и не пишет ни `response_length`, ни `finish_reason` — длина есть лишь в `debug`-записи
`parse.start`, которой в рабочем режиме нет. В наблюдавшемся случае превью содержало корректное
начало JSON в ограждении ```` ```json ````, а жадная регулярка ограждение прошла бы — ей нужна лишь
закрывающая скобка. То есть данные согласуются с обрывом, но подтвердить это логом невозможно.
Один показатель (`finish_reason` либо полная длина на уровне `warning`) закрывает вопрос и должен
войти в правку вместе с заменой регулярки — иначе после неё останется тот же неразличимый отказ.

**Связано:** P2-34 (второй источник времени в сборке контекста — content-search через ACP RPC;
в одном прогоне 3766 мс), P2-57 (окупаемость Context Manager в целом; этот пункт — его часть),
roadmap Context Manager (слой A).

---

### 52. Поиск сессии по вторичному ключу — полный скан хранилища на каждый ответ клиента — ⬜ ОТКРЫТО (обнаружено 2026-07-31, замер при транзакции 7)

**Файлы:** `handlers/permissions.py::find_session_id_by_permission_request_id`,
`handlers/client_rpc_response.py::find_session_id_by_pending_client_request_id`,
`handlers/permissions.py::consume_cancelled_*`, `SessionRepository.iter_sessions`.

**Замер (2026-07-31).** Ответ клиента на `session/request_permission` не несёт id сессии —
сервер ищет её перебором всех сессий, потому что индекса вторичных ключей у хранилища нет.
На 30 сессиях по 621 КБ (копии реального файла):

```
iter_sessions (домен): 90 мс на 30 сессий
list_sessions (wire): 131 мс на 30 сессий
```

То есть каждый ответ на запрос разрешения читает с диска и парсит все сессии. В разобранных
прогонах таких ответов было 35 за один сеанс — при истории из 30 сессий это ≈3 секунды чистого
скана, плюс дисковый шум. С ростом числа сессий деградация линейная.

**Что уже сделано.** Порядок проверок в `ResponseRouter` переставлен: процессный реестр
ожидающих RPC (`ClientRPCService.has_pending_request`, словарь) проверяется **раньше** скана
состояния. Живой путь fs/terminal идёт именно через сервис, поэтому раньше каждый его ответ платил
за полный скан впустую. Наборы идентификаторов не пересекаются: запросы сервиса живут в его
futures, а `pending_external_request` заводит директивный путь, через сервис не проходящий.
Permission-ответы этим не лечатся — их id живут в состоянии сессии, скан остаётся.

**Направление.** `PendingRequestRegistry` уже держит ожидающие permission-запросы в процессе (его
спрашивает ветка orphan на загрузке). Добавить в него отображение `request_id → session_id` и
искать сначала там, а скан оставить фоллбэком: по правилу «сигнал против состояния» (ADR-007)
реестр — процессная подсказка, диск — источник истины, и после рестарта фоллбэк обязателен.

**Критерий приёмки:** обработка permission-ответа не зависит от числа сессий на диске (при
попадании в реестр — без чтения посторонних сессий); скан остаётся только на пути после
рестарта.

**Связано:** ADR-006 (решение D4-d, тезис 3: `iter_sessions` как write-model для поиска по
вторичному ключу — там же отмечено «индекса вторичных ключей нет, как и сегодня»), P2-34
(другая линейная стоимость — content-search).

---

### 53. Подпроцессы Web UI не умирают вместе с сервером: 437 осиротевших процессов, 5.5 ГБ — ✅ ЗАКРЫТО (2026-08-04, подтверждено живьём)

**Файлы:** `server/http_server.py:140` (спавн), `:171-176` (очистка),
`shared/web_ui.py::WebUIManager.start_subprocess` (`:98-104`), `stop_subprocess` (`:119-132`),
`client/tui/serve_entry.py`.

**Замер (2026-07-31, живая машина).** В системе 437 процессов
`python -m codelab.client.tui.serve_entry`, у **всех** `ppid=1` — родители мертвы, дети
репарентированы к init:

```
процессов:      437
суммарно RSS:   5537 МБ  (min 5.9, медиана 13.9, max 16.4 МБ)
старший:        1 сутки 00:21:38
младший:        54:24
раскладка:      пачки по 10-12 процессов с интервалом ~2 с, ~36 пачек за сутки
```

При 1102 процессах в системе это 40% таблицы процессов и 5.5 ГБ памяти, занятых экземплярами
textual-serve, каждый из которых слушает (или пытался слушать) один и тот же порт `port + 1000`.

**Механизм — из кода, две независимые причины:**

1. **Спавн раньше bind'а, очистки на отказе нет.** `start_subprocess()` вызывается на строке 140,
   а `TCPSite.start()` — на 162. `try/finally` со `stop_subprocess()` открывается на строке **171**,
   то есть **после** bind'а. Если порт занят и `bind` бросает исключение, подпроцесс Web UI уже
   запущен, а `finally` не исполняется — ребёнок остаётся навсегда.
2. **`start_new_session=True`** (`web_ui.py:103`) уводит ребёнка в отдельную сессию и группу
   процессов. Он переживает не только смерть родителя, но и сигнал, посланный группе (закрытие
   терминала, Ctrl-C по группе). Единственный способ его убить — явный `stop_subprocess()`,
   которого на аварийных путях нет.

**Что подтверждено, а что выведено.** Реперентирование, число, память и возраст — измерены.
Пачки по 10-12 с шагом 2 с — измерены. Что триггер именно занятый порт — **вывод по коду**: у этих
детей `stdout`/`stderr` уходят в `DEVNULL` (`web_ui.py:101-102`), своего лога у них нет, поэтому в
логах прогонов их не видно вообще. Отсюда и то, что дефект жил сутки незамеченным: канал
наблюдаемости у него отсутствует полностью.

**Направления (решить при взятии):**
1. Спавнить Web UI **после** успешного `site.start()` — тогда неудачный bind не оставляет ребёнка.
2. Обернуть весь путь запуска в `try/finally`, а не только цикл ожидания.
3. Пересмотреть `start_new_session=True`: он введён, чтобы Ctrl-C в терминале не убивал Web UI, но
   ценой того, что ребёнка не убивает вообще ничто. Альтернатива — оставить ребёнка в группе и
   гасить сигнал в нём самом.
4. Убивать «своего» осиротевшего предшественника при старте: перед спавном проверить, не занят ли
   `port + 1000` нашим же процессом.
5. Завести детям лог (сегодня `DEVNULL`) — иначе следующий такой дефект снова будет невидим.

**Критерий приёмки:** после аварийного завершения сервера (в т.ч. неудачного bind'а и `SIGKILL`
родителю) в системе не остаётся процессов `serve_entry`; повторный запуск при занятом порте не
увеличивает их число.

**Динамика за сутки (2026-08-04).** Замеры 2026-08-03 подряд: 110 → 167 → 260 → 349 процессов,
4.8 ГБ RSS. Утечка не разовая и не затухающая — она линейна по числу запусков в websocket-режиме.
Сверх памяти есть прямое следствие: осиротевшие предшественники занимают `port + 1000`, поэтому
следующий запуск попадает в ту же ветку неудачного bind'а.

**Повышение приоритета до P1 отозвано в тот же день — обоснование было неверным.** P1 ставился
доводом «утечка ломает воспроизводимость живых прогонов, на которых держится приёмка ADR-006/007».
Довод не выдержал проверки: Web UI поднимает только `ACPHttpServer.run`, а рабочий режим
пользователя — `--stdio` через сторонний клиент (Zed), где `run_stdio_server` не создаёт
`WebUIManager` ни при каких флагах. Проверено по логам: во всех файлах `~/.codelab/logs` ноль
событий `web_ui_subprocess_started`, все старты — `transport=stdio` из pipx-сборки. Накопленные на
машине сироты — от websocket-запусков при проверке шагов, то есть от инструмента проверки, а не от
рабочего пути. **Фактическая область дефекта — только websocket-режим с включённым Web UI**, и это
P2. Пункт всё равно закрыт (правка сделана и проверена), но как P2, а не как срочное.

**Решение (2026-08-04).** Две причины требовали разных ответов, и одного «переставить спавн» не
хватало.

1. **Порядок спавна.** `WebUIManager` создаётся до маршрутов (обработчик `/` на него ссылается), но
   подпроцесс запускается **после** успешного `site.start()`, и весь путь запуска обёрнут в
   `try/finally`. Неудачный bind больше не оставляет ребёнка: до bind'а его просто нет.
2. **Сторож за родителем.** Ребёнок получает `CODELAB_PARENT_PID` и в отдельном демон-потоке
   проверяет, жив ли родитель (смена `ppid` **или** недоступность pid — второе закрывает
   зомби-родителя). Как только родитель исчез — `os._exit(0)`. Это единственное, что работает при
   `SIGKILL` родителю и при `SIGTERM` (по умолчанию `finally` не исполняется). Выход жёсткий
   намеренно: `textual_serve.Server.serve()` блокирует главный поток и не даёт точек останова.
3. **Остановка группы, а не одного pid.** `start_new_session=True` сохранён (он и введён затем,
   чтобы Ctrl-C в терминале не убивал Web UI), но штатная остановка идёт `killpg` по группе
   ребёнка: textual-serve порождает в ней собственных детей, и `terminate()` по одному pid оставлял
   бы внуков. Есть откат на `terminate()`, если группу погасить нельзя.
4. **Канал наблюдаемости.** Вывод ребёнка идёт не в `DEVNULL`, а в
   `~/.codelab/logs/web_ui-<pid родителя>.log`. Именно отсутствие лога дало дефекту прожить сутки
   незамеченным. Имя — по pid, а не по времени: метки времени в именах файлов уже расходятся с UTC
   в строках логов (P2-47). Недоступный файл лога не мешает запуску — откат на `DEVNULL`.

Направление «убивать своего осиротевшего предшественника при старте» не понадобилось: со сторожем
предшественник умирает сам в течение окна опроса, а специальная зачистка по порту потребовала бы
опознавать «свой» процесс по чужому порту.

**Инвариант безопасности сохранён и переформулирован.** Тест требовал буквально `DEVNULL`, хотя
защищал другое: сервер может работать поверх stdio, и вывод ребёнка в общий поток испортил бы
JSON-RPC. Теперь проверяется именно это — stdio ребёнка не наследуется от родителя, а файл лога
лежит под `CODELAB_HOME`.

**Проверено живьём (2026-08-04), все три пути отказа:**

```
занятый порт:        детей 373 → 373  (до правки — +1 на каждую попытку)
SIGKILL родителю:    ребёнок 94600 умер, в его логе web_ui_parent_gone_exiting
SIGTERM родителю:    ребёнок 95359 умер (finally не исполнялся — подобрал сторож)
штатная остановка:   ребёнок умер, группа пуста — внуков не осталось
нормальный путь:     в логе «server started» → затем «web_ui_subprocess_started»
```

Последняя строка и есть исправленный порядок: раньше спавн стоял до bind'а.

**Гейты.** `make check` — 7550 тестов. Юнит-гейты: спавн только после успешного bind'а (и ни одного
ребёнка при отказе), `CODELAB_PARENT_PID` доезжает до ребёнка, сторож завершает процесс при уходе
родителя и не завершает при живом, остановка идёт по группе с откатом на `terminate()`,
недоступный лог не мешает запуску.

**Что осталось.** Уже накопленные сироты (на машине разработки их 373) сторожем не подбираются —
он живёт только в новых подпроцессах; старые нужно снять один раз вручную. Внуки-экземпляры TUI
проверены только через пустую группу после остановки; отдельного прогона с подключённым TUI-клиентом
не делалось.

**Связано:** P2-48 (тот же класс — спавн без владельца жизненного цикла; там холостой процесс, здесь
утечка), P2-28 (fire-and-forget задачи без контроля жизненного цикла — тот же мотив на уровне
корутин), P2-44 (ресурсы, переживающие процесс-владелец).

---

### 54. `active_turn.phase` никто не возвращает в `running`, а валидирующий сеттер фазы мёртв — ⬜ ОТКРЫТО (обнаружено 2026-07-31, анализ логов)

**Файлы:** `handlers/turn_lifecycle_manager.py:90-133` (`set_turn_phase` — без вызывающих),
`pipeline/stages/agent_loop/tool_processor.py:458`, `pipeline/stages/directives.py:147,169,281,287`,
`handlers/session.py:69`, `domain/session.py::TurnState.phase`.

**Симптом на диске (2026-07-31, `sess_b93658bfd522`, ревизия 64).** Сохранённый `active_turn`:

```
phase: 'awaiting_permission'   permission_request_id: None
permission_tool_call_id: None  pending_batch: []
```

Фаза говорит «ждём разрешения», а идентификаторов запроса нет и остаток батча пуст. По логу того же
прогона разрешение было получено, и turn отработал после него ещё пять вызовов инструментов
(последний — `terminal/create` → `term_7`, `completed`). То есть фаза осталась от паузы, случившейся
задолго до конца turn'а.

**Причина — не «забыли одну строку», а отсутствие владельца:**

1. `phase` пишут напрямую **три** модуля пятью местами: `tool_processor.py:458`
   (`awaiting_permission`), `directives.py` (`waiting_client_rpc` ×2, `waiting_permission`,
   `waiting_tool_completion`), `session.py:69` (`cancelled`). Ни одно из них не возвращает фазу в
   `running` при возобновлении.
2. `TurnLifecycleManager.set_turn_phase` — валидирующий сеттер с матрицей переходов и логом отказа
   (`invalid phase transition`) — **не имеет ни одного вызывающего в проде**. Все писатели ходят
   мимо него, поэтому матрица переходов не проверяется никогда, а лог отказа не может сработать.
3. Отсюда же известный рассинхрон значений: `tool_processor` пишет `awaiting_permission`,
   `directives` — `waiting_permission`. Два имени одного состояния, и ни одно не канонично.

**Следствия.** Фаза как признак состояния turn'а недостоверна: по ней нельзя ни решить, чем занят
turn, ни почистить залипший `active_turn` (ветка orphan на загрузке смотрит на
`permission_request_id`, и в примере выше он `None` — такой turn она не тронет). Фатально не бьёт:
новый промпт гасит `active_turn` на `session_prompt.py:114`. То есть цена — не сбой, а то, что
единственный признак «где мы в turn-е» врёт, и опереться на него нельзя ни в коде, ни при разборе.

**Направления (решить при взятии):** ввести типизированный `TurnPhase` (заявлен в ADR-006 при вводе
`TurnState`, стадия b4/b8) и свести значения к одному набору; сделать переход фазы единственной
дверью — либо доменной командой на `TurnState`, либо оживить `set_turn_phase`, но не держать два
пути; определить владельца возврата в `running` на возобновлении после permission и client-RPC.
Место естественно попадает в шаг 3 декомпозиции фазы D (ADR-006): `tool_processor` и `directives`
там всё равно переезжают на доменные сеймы.

**Критерий приёмки:** после возобновления turn'а фаза на диске — `running`, а не фаза паузы; после
штатного завершения `active_turn: null`; запись фазы возможна только через одну точку, и запрещённый
переход даёт `invalid phase transition` в логе (сегодня это событие недостижимо).

**Диагноз уточнён и закрыт по причине (2026-08-04, фаза D ADR-006 завершена).** Причин ровно две, и
обе подтверждены кодом: (1) `set_turn_phase` — мёртвый код, ноль вызывающих, поэтому фаза не
сбрасывается никогда; (2) turn, завершившийся на resume-пути (после паузы на разрешение или
клиентский RPC), **не проходит через `TurnLifecycleStage(close)`** — то есть на диске остаётся не
только фаза паузы, но и сам `active_turn`. Фаза D это не чинила: перевод записи на команды сделал
хвост наблюдаемым точнее, но владельца закрытия turn'а не ввёл. Минимальная развязка, не
дожидаясь `TurnPhase`: команда «снять stale `active_turn`» на следующем `session/prompt` — она
дешева и убирает пользовательский симптом («orphaned permission request» при перезапуске), тогда
как единственная дверь для перехода фазы остаётся отдельной работой.

**Связано:** P2-46 (закрыт; этот остаток был отмечен внутри него — теперь ведётся отдельно),
ADR-006 (`TurnState.phase` как `str` — временное решение, `TurnPhase` на стадии b4/b8; фаза D
завершена 2026-08-03, этот хвост в неё не вошёл), P2-42
(ветка orphan на загрузке — потребитель, которому фаза не помогает).

---

### 55. Вызов после fs client-RPC остаётся на диске `pending`, а клиенту ушёл `completed` — ✅ ЗАКРЫТО (2026-07-31, подтверждено живьём)

**Файлы:** `handlers/client_rpc_response.py:108` (fs_read), `:152` (fs_write),
`domain/value_objects.py::ALLOWED_TOOL_CALL_TRANSITIONS`, `domain/session.py::ToolCallRegistry.update_status`.

**Симптом (живой прогон 2026-07-31, изолированный `CODELAB_HOME`).** Клиент отвечает на
`fs/read_text_file`, сервер шлёт ему `tool_call_update: completed` и закрывает turn
(`stopReason: end_turn`, `active_turn: null`, ревизия 2 → 3). На диске при этом:

```
call_001: status = pending          ← клиенту сказали completed
лог:      tool_call_status_transition_rejected current_status=pending requested_status=completed
```

**Причина.** Матрица переходов не содержит `pending → completed`
(`PENDING: {IN_PROGRESS, CANCELLED, FAILED}`), а fs-ветки client-RPC идут из `pending` прямо в
`COMPLETED`. Домен отказывает и логирует отказ — то есть механизм работает как задумано, — но
нотификация клиенту строится **независимо** от результата перехода, поэтому wire и состояние
расходятся. Terminal-ветка не страдает: она сначала ставит `IN_PROGRESS` (`:194`), и её
`in_progress → completed` матрицей разрешён.

**Предсуществующий, не регресс.** Тот же сценарий прогнан на `b297d10b` (до транзакции 7 фазы D):
предупреждение то же, счётчик warning'ов одинаков (1 и 1). До транзакции дефект был не виден,
потому что на диск не попадало вообще ничего (ревизия не менялась, `active_turn` оставался
отложенным навсегда) — транзакция 7 сделала его наблюдаемым.

**Следствия.** Вызов остаётся `pending` в документе навсегда: он не терминальный, поэтому
`session/cancel` и скан при разрыве соединения считают его незавершённым и отменяют — задним числом
превращая успешный вызов в `cancelled`. Replay такой сессии показывает `pending` у давно
выполненного чтения файла.

**Направления (решить при взятии — решение протокольное, не косметическое):**
1. **Разрешить `pending → completed`** в матрице. Синхронный client-RPC действительно завершается,
   не побывав «в процессе», и ACP промежуточного статуса не требует. Проверить, не опиралось ли на
   запрет что-то ещё (матрица — единственный источник для трёх сайтов).
2. **Либо** ставить `IN_PROGRESS` в fs-ветках, как делает terminal. Ценой лишней wire-нотификации,
   которой клиент раньше не видел, — то есть это изменение наблюдаемого протокола.
3. Независимо от выбора: **не строить нотификацию, когда переход отклонён.** Сегодня wire уходит
   клиенту при любом исходе, и это общий механизм расхождения, а не частность fs-ветки.

**Критерий приёмки:** после ответа клиента на `fs/read_text_file` статус на диске совпадает с тем,
что ушло клиенту; отклонённый переход не порождает wire-нотификацию; за прогон ноль
`tool_call_status_transition_rejected`.

**Решение: вариант 2, а не 1 — первоначальный уклон был неверен.** При взятии выяснилось, на что
опирается запрет `pending → completed`: он ловит класс «вызов завершился, ни разу не начавшись», и
однажды уже поймал реальный дефект (docstring `test_rejected_transition_is_logged`: «resume-путь слал
клиенту completed, а состояние оставалось pending»). Разрешить переход значило бы снять работающий
guard ради одного вызывающего, который его нарушает.

Правильным оказалось обратное: **состояние врало, а не матрица**. Вызов, за которым отправлен
client-RPC, всё время ожидания ответа **выполняется**, а не ждёт запуска, — `pending` для него
состояние, которого не бывает. Terminal-ветка так и делала (`IN_PROGRESS` при создании терминала),
fs-ветки — нет.

**Сделано:**
1. `create_tool_call` получил параметр `status` (по умолчанию `pending` — остальные вызывающие не
   затронуты), и fs-ветки `build_fs_client_request` создают вызов сразу `in_progress`, тем же
   значением в wire-нотификации создания. Лишней нотификации не добавилось: статус выставляется в
   том же сообщении, которое и так уходило.
2. Пункт 3 сделан отдельно и шире одной ветки: `client_rpc_response.py` строит нотификацию о смене
   статуса только если смена состоялась (`_status_notifications`, 6 сайтов). При отклонённом
   переходе — молчание плюс `tool_call_status_notification_suppressed`.
3. Два исхода `update_status` разведены: «переход отклонён» (вызов есть) и «вызова нет в состоянии».
   Второй сохраняет прежнее поведение — путь отказа обязан уведомить клиента, о вызове он знает, —
   и логируется отдельным событием `tool_call_status_notification_for_unknown_call`. Смешивать их
   нельзя: один и тот же `False` иначе дал бы неверную причину в логе при разборе.

**Почему тесты не поймали дефект — и что с этим сделано.** Гейт транзакции 7
(`test_fs_read_completion_is_persisted`) был зелёным, потому что его фикстура **сама** ставила
`status="in_progress"`, тогда как прод создавал `pending`. Фикстура описывала не то состояние,
которое бывает. Добавлен `_session_via_production_builder`: состояние готовит тот же
`build_fs_client_request`, что в проде, плюс сквозной гейт «что сказали клиенту, то и на диске» и
гейт «отклонённый переход не порождает нотификацию».

**Подтверждено живьём (2026-07-31)** тем же прогоном на директиве, что нашёл дефект:

```
[КАДР: RPC отправлен, ответа нет]  rev=2  active_turn=есть  call_001: in_progress
[в покое]                          rev=3  active_turn=null  call_001: completed
ушло клиенту: tool_call:in_progress → tool_call_update:completed
на диске в покое: completed | последнее сказанное клиенту: completed  → СОВПАДАЕТ
tool_call_status_transition_rejected за прогон: 0
строк warning/error за прогон: 0
```

Промежуточный кадр закрывает и вторую половину: пока RPC в полёте, на диске `in_progress`, а не
«не начат».

**Связано:** ADR-006 (транзакция 7 — там же живое подтверждение и это наблюдение), P2-38 (вызовы без
ответа `role: tool` — та же семья «wire ↔ состояние»), P2-54 (второй случай, когда wire уходит
клиенту, а состояние остаётся при своём).

---

### 56. Гейт разрешений живёт у вызывающего, а не у реестра: Context Manager исполняет защищённые инструменты молча — ⬜ ОТКРЫТО (обнаружено 2026-08-04, анализ логов; **приоритет P1**)

**Файлы:** `protocol/handlers/pipeline/stages/agent_loop/tool_processor.py:436-454` (единственная
проверка `requires_permission` и пауза), `tools/registry.py::SimpleToolRegistry.execute_tool` (гейта
нет), вызывающие в обход: `agent/context/gatherer.py:409` (`fs/read_text_file`), `:523`
(`terminal/create`), `:550` (`terminal/wait_for_exit`), `agent/context/manager.py:202`
(`fs/read_text_file`).

**Симптом (прогоны 2026-07-24 … 2026-08-04).** Соотношение «запросов разрешения : исполнений
`fs/read_text_file`» по прогонам — 27:322, 27:356 и **0:239**. В последнем прогоне гейт разрешений
не сработал ни разу, а файлы читались 239 раз: всё чтение шло из Context Manager, который на
разрешение не спрашивает.

**Самый выразительный замер — прогон через Zed 2026-08-04 (`codelab-10382.log`, 4 минуты, 1069
строк, ноль ошибок и предупреждений):**

```
всего исполнений fs/read_text_file:  475
с запросом разрешения:                29   (6%)
без разрешения:                      446   (94%)
по минутам:  12:04 → 161, 12:05 → 8, 12:06 → 166, 12:07 → 140
```

Пачки по 140–166 чтений в минуту совпадают с тремя `context.build.start`, то есть это Context
Manager. Пользователь при этом видел 29 запросов: **на каждое выданное разрешение прошло ещё
пятнадцать чтений, о которых его не спросили.**

*Уточнение к цене, меняющее диагноз P2-57.* В том же прогоне `context.gather.files_read.complete`
показывает `files_read=20/15/20` при `elapsed_ms≈2.8`. Двадцать чтений через ACP RPC до клиента за
2.8 мс невозможны — значит горячий путь попадает в кеш, а 475 исполнений идут мимо этой метрики.
Следствие: цена лежит **не в повторном I/O**, а в 446 обходах гейта разрешений. Для P2-57 это
означает, что оптимизировать надо не число чтений, а учёт и гейт.

**Причина — структурная, а не забытая проверка.** Решение «нужно ли разрешение» принимает
**вызывающий** цепочки `tools/`, а не сама цепочка. У неё два вызывающих (turn и Context Manager,
зафиксировано в ADR-006, шаг 3), и гейт реализован только у первого. При этом определения
инструментов честно объявляют защиту: `fs/read_text_file` — `requires_permission=True`
(`tools/definitions/filesystem.py:104`), `terminal/create` — `requires_permission=True`
(`terminal.py:72`). То есть флаг выставлен, но у второго вызывающего его никто не читает.

**Почему P1, а не «косметика доверия».** Через этот путь исполняется не только чтение: Context
Manager запускает **произвольную команду в терминале** — `find . -type f` в
`_bootstrap_project_files` — без спроса и без уведомления клиента. Пользователь, отклоняющий чтение
файла, не имеет способа отклонить чтение того же файла Context Manager'ом: для него этого канала
не существует. Это расходится с моделью разрешений ACP, где решение о доступе принимает клиент, а
не сервер, и расхождение тем заметнее, что дефолтная политика инструмента — «спрашивать».

**Направления (решить при взятии):**
1. Перенести гейт к реестру: `execute_tool` не исполняет `requires_permission=True` без явного
   решения. Тогда обход становится невозможен по конструкции, а не по дисциплине вызывающего.
2. Ввести явный режим доверия для служебного вызывающего (`internal`/`background`), но
   **декларативно и наблюдаемо**: с записью в лог и с отдельным набором разрешённых инструментов —
   чтение да, `terminal/create` нет.
3. Отдельно решить, вправе ли Context Manager запускать команды: bootstrap структуры проекта
   уместнее сделать через `fs`-обход, а не через shell.

**Развилка, на которой пункт отложен (2026-08-04) — решать до кода.** Сам перенос гейта в
`execute_tool` короткий, но у него есть последствие, видимое пользователю. После переноса Context
Manager либо начнёт спрашивать разрешение на **каждое** из ~450 чтений за прогон — это делает работу
невозможной, — либо должен получить явный служебный режим. Второе выглядит верным, но требует
решения по двум вопросам: какой набор инструментов в этом режиме разрешён (чтение — да,
`terminal/create` — нет) и как режим виден в логе и клиенту, чтобы «служебное исключение» не стало
той же тихой дырой под другим именем. Пока решение не принято, брать пункт не стоит: половина
правки хуже её отсутствия — она либо ломает Context Manager, либо узаконивает обход.

**Развилка вынесена пользователю и решена: пункт отложен намеренно (2026-08-06).** Из трёх
вариантов — служебный режим, отложить, перенести как есть — выбран **отложить**: пункт остаётся
открытым и заблокирован не отсутствием сил, а нерешённым вопросом политики разрешений целиком.
Отсюда следствие для планирования: P1-56 **нельзя брать как «короткую правку по пути»** внутри
другого шага, даже если правка окажется рядом; он берётся только вместе с решением о служебном
режиме (направление 2 выше) и о наборе инструментов в нём.

**Критерий приёмки:** ни один путь не исполняет инструмент с `requires_permission=True` без
решения клиента либо без явно объявленного и залогированного служебного исключения; соотношение
«разрешения : чтения» на живом прогоне перестаёт быть 29:475.

**Связано:** ADR-006 (шаг 3 — там же зафиксированы два вызывающих цепочки `tools/`), P2-57
(тот же вызывающий, вопрос окупаемости его чтений), P2-58 (терминалы, создаваемые этим путём).

---

### 57. Context Manager не окупается: 161–239 чтений на 7–20 файлов, метрика не отражает реальные чтения — ⬜ ОТКРЫТО (обнаружено 2026-08-04, анализ логов)

**Файлы:** `agent/context/gatherer.py` (сбор и чтения), `agent/context/manager.py`
(`_refresh_dirty_sources`, `_read_file`), `agent/context/task_analyzer.py`, метрика
`files_read` в `record_context_build`.

**Замер (прогоны 2026-08-01 … 2026-08-04).** На turn: 161–239 исполнений `fs/read_text_file` при
7–20 файлах, реально попавших в baseline, и `files_read=1..20` в метрике — то есть метрика считает
собранные источники, а не выполненные чтения, и по ней перерасход не виден вообще. Сверх этого
`context.task_analyze` — отдельный LLM-вызов 1.7–4.9 с на turn (подробности и тихий отказ разбора —
P2-51). В одном из прогонов **все шесть** собранных Context Manager'ом файлов модель затем
перечитала сама: контекст был собран, оплачен и не использован.

**Что именно измерено, а что — вывод.** Числа чтений, файлов и времени — измерены по логу.
Что перерасход даёт именно content-search и обход зависимостей — согласуется с P2-34 (там тот же
класс замерен отдельно: O(термы × файлы) чтений через ACP RPC), но разложение 239 чтений по
причинам на этих прогонах **не делалось** — это первая работа при взятии пункта.

**Почему это долг, а не настройка.** Функция включается флагом `[agents.context].enabled` и
по умолчанию выключена, поэтому цена не видна в дефолтной конфигурации. Но у включённой функции
сегодня нет ни одного показателя, по которому можно сказать, окупилась ли она: `files_read` врёт,
доли «собранный файл действительно попал в ответ модели» не существует. Пока такого показателя
нет, любое улучшение сбора нечем принять.

**Направления (решить при взятии):**
1. Развести в метриках «прочитано» и «собрано»; добавить долю собранных файлов, которые модель
   затем не перечитывала — это и есть окупаемость.
2. Кешировать содержимое между turn'ами сессии (`FileContentCache` есть, но чтения повторяются).
3. Разложить 239 чтений по источникам и срезать самый дорогой (кандидат — content-search, P2-34).

**Критерий приёмки:** число `fs/read_text_file` за turn сопоставимо с числом собранных файлов
(единицы, а не сотни); в метриках видно и то, и другое.

**Связано:** P2-34 (content-search — вероятный основной источник чтений), P2-51 (классификация:
время и тихий отказ), P1-56 (эти чтения идут мимо гейта разрешений), roadmap Context Manager.

---

### 58. Мёртвые алиасы терминалов после рестарта: гарантированно провальные вызовы и реестр, который только растёт — 🟡 ЧАСТИЧНО (2026-08-05: «мёртвые алиасы» закрыты живьём; 2026-08-07: двойная выдача alias'а закрыта эпохой процесса, статические гейты; открыто владение освобождением)

**Файлы:** `protocol/handlers/session.py:262-286` (`_drop_terminals_from_previous_process`,
событие `terminals_dropped_from_previous_process`), `agent/context/gatherer.py:523-555`
(создание терминала без освобождения), реестр терминалов в доменной сессии.

**Симптом, две независимые половины:**

1. **Мёртвые алиасы переживают рестарт в истории, а не в реестре.** При загрузке сессии
   `_drop_terminals_from_previous_process` честно чистит реестр — терминалов прошлого процесса
   больше нет. Но восстановленная **история** по-прежнему содержит их идентификаторы, и модель по
   ней зовёт `terminal/release` и `terminal/wait_for_exit` на несуществующих алиасах. Сколько
   терминалов было до рестарта — столько гарантированно провальных вызовов после (наблюдалось на
   обоих методах). Каждый такой вызов — round-trip к клиенту, ошибка в логе и запись в истории,
   которую модель затем читает как «инструмент сломан».
2. **Реестр растёт и не освобождается.** За прогон 11 `terminal/create` и **0** `terminal/release`.
   Часть создаётся Context Manager'ом (`_bootstrap_project_files`), и он не освобождает их вовсе —
   в `gatherer.py` нет ни одного `terminal/release`. Реестр целиком уезжает на диск в каждой
   ревизии документа сессии, то есть цена растёт вместе с числом ревизий.

**Соотношение с закрытым P2-44.** P2-44 закрыл «реестр переживает перезапуск, а терминалы нет» —
со стороны **реестра**. Этот пункт — та же причина со стороны **истории и владения**: чистка
реестра не делает историю согласованной и не отвечает на вопрос, кто освобождает терминал в
штатном случае.

**Уточнение при взятии: одна половина пункта была закрыта раньше, чем здесь записано (2026-08-04).**
Обращение к мёртвому alias'у **не** даёт внутренней ошибки: `TerminalExecutor._resolve_terminal`
возвращает модели `«Неизвестный терминал 'term_7'. Доступные терминалы: …»` и пишет `warning`, а не
`error` — это сделал P2-44. То есть «гарантированно провальные вызовы» — правда, но их цена сегодня
не нарушение протокола, а лишний round-trip и запись в истории. Пункт 2 прежних направлений снят
как уже выполненный.

**Владение закрыто отдельно (2026-08-04).** Context Manager брал терминал в
`_bootstrap_project_files` и не отдавал — `try/finally` с `terminal/release` добавлен, освобождение
идёт и на успешном пути, и на неудачном ожидании, неудачное освобождение не отменяет собранную
структуру. Гейты: ровно одно освобождение на bootstrap, отсутствие вызова без полученного alias'а,
сохранность записи структуры через сейм `writable_session`.

**Остаток свёрнут в расщепление ADR-007 — это архитектурный вывод, а не отсрочка.**
Причина всего класса в том, что **состояние процесса персистится**: реестр alias'ов лежит в
документе сессии (`storage/document.py:288` — `terminals`, `:292` — `terminals_owner`), тогда как
сами терминалы живут у клиента и рестарт не переживают. Всё вокруг — компенсации этого решения:
`terminals_owner` + `PROCESS_TOKEN` (различить загрузку своим процессом и чужим),
`_drop_terminals_from_previous_process` (вычистить то, что не должно было сохраняться), ветка
«неизвестный терминал» (ответить модели, когда компенсация не успела), плюс вклад в размер
документа — реестр уезжает на диск в каждой ревизии.

Если реестр признать **горячим состоянием процесса** и не персистить, мёртвых alias'ов после
рестарта не существует по построению, а три компенсации из четырёх становятся мёртвым кодом и
удаляются. Это последняя строка «Порядка работ» ADR-007, то есть P2-58 — её следствие, а не
отдельная задача. Совместимость страдает мягко: убранные поля старые документы просто перестают
читать, миграция сводится к игнорированию.

**Отвергнутое направление и почему.** Прежний пункт 1 — «привести историю в согласованное состояние,
пометив вызовы мёртвых терминалов» — архитектурно неверен. История есть неизменяемый журнал
произошедшего: терминал действительно создавался и действительно вернул вывод, и правка записи ради
того, чтобы «настоящее сошлось», теряет запись и ломает реплей. Живость ресурса — это состояние,
а не история. Модель должна узнавать о ней там же, где узнаёт любое состояние: **при сборке payload'а
ссылки на ресурсы разрешаются против текущего состояния** — тот же принцип «один источник, остальное
проекция», что ADR-007 формулирует для статусов вызовов. Пометка в контексте (рассматривалась как
минимальный вариант) отвергнута по той же причине: она создаёт третий источник правды о живости и не
масштабируется — тот же класс придёт от MCP-хендлов, разрешений и кешей содержимого, любой ссылки на
эфемерный ресурс, попавшей в историю.

**Половина «мёртвые алиасы» закрыта (2026-08-05, подтверждено живьём; ADR-007, шаг A).** Связка
alias → client terminalId уехала в процессный `TerminalAliasRegistry`, в документе её нет
(`schema_version 9`, миграция v8→v9 отбрасывает поля явным `pop`). Удалены все компенсации:
`terminals_owner`, модуль `process_identity.py` целиком, `_drop_terminals_from_previous_process` с
событием, перенос связки в `_carry_executor_changes`. Мёртвых alias'ов после рестарта не существует
по построению.

*Разведка изменила решение, и это важнее правки.* Замысел «весь реестр — состояние процесса» дал бы
регрессию хуже исходного дефекта: `terminal_counter` персистился, поэтому alias'ы были уникальны в
сессии через рестарт, и мёртвый alias давал внятное «неизвестный терминал». При сбросе счётчика те
же alias'ы выдались бы заново, и обращение из восстановленной истории разрешилось бы в **чужой
живой** терминал — чужой вывод вместо ошибки. Носители разделены по смыслу: связка процессная,
счётчик остаётся в документе как распределитель идентификаторов сессии.

*Живое подтверждение* (`sess_c386dab381c8`, stdio через Zed, pid 67563 → 70220 на одной сессии):
`term_4` из восстановленной истории дал `terminal_alias_not_found` с `known_aliases=[]` уровня
`warning`, новые терминалы получили `term_5…term_13`, на диске `terminal_counter=13`, ноль
`RPC Error -32603`, ноль `error`. Прогон подтвердил именно развилку — терминалов создано девять, то
есть при сброшенном счётчике `term_4` был бы переиспользован в этом же прогоне.

**Что осталось открытым — владение освобождением.** Замер того же прогона: **9 `terminal/create`
против 0 `terminal/release`**. Освобождает только bootstrap Context Manager'а; терминалы, созданные
turn-путём по запросу модели, не освобождает никто. К носителю реестра это не относится: после
переноса незакрытые alias'ы перестали растить документ (умирают с процессом), но сами терминалы
висят у клиента. Критерий «`release` сходится с `create`» снят из приёмки шага A как ошибочно
туда попавший.

**Счётчик тоже уехал из документа (2026-08-07, `schema_version 13`, подтверждено живьём).** Гарантия
уникальности alias'а через рестарт была дисциплинарной и однажды не сработала: счётчик лежал в
документе, а Context Manager мутирует переданный объект сессии, и на его пути мутация не сохранялась
— отсюда `term_1`, выданный дважды разным терминалам при счётчике 2 вместо 3. Alias стал нести эпоху
процесса (`term_<pid>_<n>`), и потребность персистировать счётчик исчезла. Подтверждено идеальным
случаем — рестарт внутри одной сессии (`sess_6331fef2a19f`, pid 29166 → 31425): `term_29166_1..3` и
`term_31425_1` сосуществуют без столкновения, полей `terminal_counter` и `terminals` в документе нет.
Это отменяет прежнюю развилку «счётчик остаётся в документе как распределитель» выше: развилка
снята не выбором носителя, а тем, что различать процессы стал сам alias.

**Владение освобождением: владелец назван, освобождение ждёт `TurnRuntime` (2026-08-07).** Замер:
Context Manager создаёт 1 и освобождает 1 (`try/finally`, закрыт 2026-08-04), turn-путь создаёт 3 и
освобождает **0**. Спецификация возлагает MUST на **агента** (`10-Terminal.md:109-111`,
`17-Schema.md:861-862`), а не на модель — она не сторона протокола, поэтому делегирование ей
превращает MUST в вероятность. Правило владения — «освобождает тот, кто создал»; модель ему
подчиниться не может (нет `finally`, нет control flow), значит владелец терминала, созданного по её
просьбе, — **turn**. Освобождать раньше, внутри `wait_for_exit`, отвергнуто: у терминала стало бы два
владельца, и `finally` Context Manager'а освобождал бы уже освобождённый alias. Единственного шва
завершения turn'а сегодня нет (четыре выхода, все синхронные), поэтому вторая половина пункта —
потребитель `TurnRuntime`, а не задача перед ним. Сейчас поставлен **замер**: признак «никто не
дождался» в записи alias'а и `terminal_ownership` с `live`/`unwaited` на каждую смену владения —
случай «терминал жив к концу turn'а» не наблюдался ни разу, и без замера политика «убивать или
оставить» была бы догадкой. Разбор — ADR-008, «Ход реализации».

**Критерий приёмки (после расщепления ADR-007):** реестр терминалов не присутствует в документе
сессии; `terminals_owner`, `PROCESS_TOKEN` и очистка на загрузке удалены как ненужные; после рестарта
сессии обращений к терминалам прошлого процесса не возникает вовсе; за прогон число
`terminal/release` сходится с числом `terminal/create`.

**Связано:** P2-44 (закрыт; та же причина с другой стороны), P2-27 (alias race — другой дефект
того же реестра), P1-56 (терминал создаётся в обход разрешений), P2-36 (отказ без причины →
каскад повторов), ADR-007 (размер документа сессии растёт вместе с реестром).

---

### 60. Текст ассистента попадает в историю дважды, когда модель вернула текст вместе с вызовами — ✅ ЗАКРЫТО (обнаружено и закрыто 2026-08-06, подтверждено живьём)

**Механизм точный, не гонка.** В `agent_loop/loop.py` два писателя истории идут
**последовательно**, а не по ветвям: `if agent_text:` → `_emit_agent_text` →
`add_assistant_message(agent_text)` (строка 324), а ниже, если вызовы есть, —
`add_assistant_tool_call_message(agent_text or "", requested_calls)` (строка 361). Вторая
запись появилась как исправление P1-45 (та запись писалась сырым dict'ом мимо носителя), но
первая не была снята, поэтому текст сохраняется два раза.

**Измерено на живом документе** (`sess_9e6c07b53dbd`, ревизия 136): у трёх turn'ов из трёх, где
модель вернула и текст, и вызовы, в истории по **две** assistant-записи с одинаковым текстом и
разницей 2 мс: одна без `tool_calls`, вторая с ними. Суммарная длина текстов assistant — 428
символов против 214 в журнале, то есть **ровно вдвое**. Когда модель возвращает только вызовы
без текста, запись одна — дубля нет.

**Следствия.** Модель видит своё сообщение дважды подряд: это и лишние токены на каждом turn'е, и
риск для когерентности (повтор выглядит как настоящий повтор в диалоге). Журнал при этом
**не** дублирует: `agent_message_chunk` по одному на текст (3 события на 3 текста), то есть
расхождение только в истории.

**Отличие от P1-45 (закрыт).** Там дублирование давало слияние при конфликте ревизий и союз типов
`HistoryMessage | dict`. Здесь ревизии и слияние не участвуют — дублируют два вызова в одном
проходе цикла.

**Почему решать до шага 4 ADR-008.** Проекция `history` из журнала выдала бы **одну** запись, то
есть «сама» исправила бы дубль и тем изменила LLM-payload. Это надо сделать осознанным решением, а
не побочным эффектом: либо дубль снимается отдельной правкой (payload меняется один раз, prompt
cache сбрасывается один раз, и это фиксируется гейтом), либо проекция обязана его воспроизводить.
Второе абсурдно, поэтому правка нужна **до** шага 4 — иначе golden-payload закрепит дефект.

**Критерий приёмки:** на живом прогоне у turn'а с текстом и вызовами ровно одна assistant-запись,
несущая и текст, и `tool_calls`; сумма длин текстов assistant в документе равна сумме
`agent_message_chunk` в журнале.

**Закрыто снятием второго писателя, а не согласованием двух.** `_emit_agent_text` больше не пишет
историю вовсе — за ней остались эмиссия в wire и запись в журнал. Единственный писатель в цикле —
`add_assistant_tool_call_message`, и он переехал **до** раннего выхода, поэтому turn без вызовов
получает ту же запись с пустым списком. Байт-идентичность обеспечена тем, что маппер не пишет
пустой `tool_calls` (`history_mapper.py:41`), а оба сейма строят запись одинаково — проверено до
правки. Добавлено условие `if agent_text or requested_calls`: без него пустой ответ модели создавал
бы пустую запись ассистента, чего раньше не было.

Отвергнут вариант с флагом `record_in_history` у `_emit_agent_text`: он оставляет двух писателей и
договорённость между ними, то есть лечит симптом.

**Подтверждено живьём** (`sess_2f34d036629f`, 2026-08-06, stdio через Zed): сумма длин
`agent_message_chunk` в журнале — 112, сумма длин текстов assistant в истории — 112, **равны**;
дублирующихся текстов ноль. До правки соотношение было ровно 2:1. Ключ `tool_calls` с пустым
списком в документе не появился ни разу.

**Гейты проверены на пригодность:** после возврата дубля упали два теста из трёх, после откатки
зелено. Третий закрывает найденную попутно ветку — пустой ответ не пишет пустую запись.

**Связано:** P1-45 (другой механизм того же симптома, закрыт), ADR-008 шаг 4 (проекция `history`),
P2-42 («честный реплей»).

---

### 61. Одновременных разрешений может быть несколько, а turn держит одно: второй вызов теряется навсегда — 🟡 ЧАСТИЧНО (обнаружено 2026-08-07, разбор логов; правка подтверждена живьём 2026-08-07 — v12, `outstanding_requests=0`; сам сценарий двух одновременных разрешений полем не воспроизведён; **приоритет P1**)

**Файлы:** `domain/value_objects.py:144-150` (`ALLOWED_TURN_PHASE_TRANSITIONS` — самоперехода
`AwaitingPermission → AwaitingPermission` нет), `protocol/handlers/permission_manager.py:160-163`
(запрос уходит клиенту, затем просится переход), `protocol/handlers/permissions.py:20`
(`find_session_by_permission_request_id` — перебор сессий по единственному слоту),
`protocol/pending_registry.py` (реестр без писателя), `protocol/commands/session_load.py:100-110`
(ветка «сирота»).

**Симптом — потерянный вызов (прогон через Zed 2026-08-07, `codelab-37118.log`,
`sess_3c411dd82bae`, ноль `error`/`critical`):**

```
05:18:41.359  agent_loop ... num_tool_calls=1                        ← цикл A
05:18:41.366  permission_request_sent  f5614636  call_007
05:18:41.469  agent_loop ... num_tool_calls=1                        ← цикл B, +110 мс
05:18:41.474  turn_phase_transition_rejected  awaiting_permission → awaiting_permission
05:18:41.476  permission_request_sent  f5614636  call_008            ← id чужой: свой не сохранён
05:18:42.671  permission_response_applied f5614636 → call_007 completed
```

Арифметика прогона: **13 запросов разрешения отправлено, 11 ответов применено**, 12 уникальных
идентификаторов в логе на 13 отправок. Два незакрытых — потерянный `call_008` и живой `call_011`,
на котором сессия остановилась. В документе `call_008` остался `pending` навсегда и **не получил
`role: tool`** — то есть это ещё и источник P2-38.

**Механизм.** `build_permission_request` создаёт запрос со своим `msg.id`, отдаёт его клиенту и
только после этого просит `transition_to(AwaitingPermission(msg.id, call_008))`. Матрица переход
отклоняет — самоперехода в ней нет, — и фаза сохраняет идентификаторы предыдущего запроса. Запрос
ушёл, а его идентификатор сервер забыл: ответ на него не найдёт сессию через
`find_session_by_permission_request_id`, потому что ищет она по единственному слоту `active_turn`.

**Причина структурная, а не «забыли строчку в матрице».** Turn способен держать ровно одно
ожидание разрешения, а циклов агента в полёте оказалось два. Это расходится со **спецификацией
ACP**, которая множественность прямо предполагает (`05-Prompt Turn.md:301`): «The Client **MUST**
respond to **all pending** `session/request_permission` requests with the `cancelled` outcome».

**Шаг 2 ADR-008 дефект не создал — он сменил жертву и сделал её видимой.** До него идентификаторы
писались присваиванием: второй запрос затирал первый, и терялся бы `call_007` вместо `call_008`.
Ломалось одинаково, но молча — ни предупреждения, ни следа в логе. Строка
`turn_phase_transition_rejected`, по которой дефект вообще нашёлся, появилась вместе с матрицей.

**Попутно измерено: `PendingRequestRegistry` — структура без писателя.** Модуль
`protocol/pending_registry.py` описан как «реестр ожидающих `asyncio.Future` **для permission
requests**», но `create()` в продакшене не вызывается ни разу; вызывается только `has()` — один
раз, в `session_load.py:105`. Реестр всегда пуст, `has()` всегда `False`, поэтому ветка «сирота»
срабатывает при **любом** незакрытом разрешении (в этом же прогоне —
`session_loaded_with_orphaned_permission_request 53a1579d`). Это третий артефакт того же рода,
что `result_content` и `terminals_owner`, только зеркальный: не поле без читателя, а реестр без
писателя.

**Следствие для персистентности.** Хранить корреляцию в документе бессмысленно: там же, где
`has()` отвечает `False`, `active_turn` очищается. То есть `permission_request_id` переживает
рестарт ровно затем, чтобы быть выброшенным.

**Решение — ADR-008, раздел 7** (ожидание разрешения как процессное состояние, ключ — id запроса,
множество вместо слота). Исполняется шагом 5, поднятым перед шагом 4.

**🟡 ЧАСТИЧНО (2026-08-07, статические гейты).** Закрыто тремя частями, и каждая понадобилась:
доменная модель множества ожиданий; корреляция «исходящий запрос → сессия» в процессном реестре
(писатель — транспорт, момент отправки); формат v12, где ожидания хранятся списком. Третья часть
найдена замером, опровергшим план: два ожидания, заведённые в фазе, после круга «сохранить →
загрузить» превращались в одно, потому что документ — носитель состояния turn'а между запросом и
ответом. Попутно исправлен дефект, который обесценил бы правку: пустой `PendingRequestRegistry`
**ложен** (`__len__`), и идиома `registry or PendingRequestRegistry()` подменяла переданный из DI
экземпляр новым — писатель и читатель работали бы с разными объектами при зелёных тестах.
Открытым остаётся **живой прогон**: сценарий редок (за два прогона случился один раз), и приёмку
надо ставить намеренно.

**Гейт приёмки численный:** два одновременных запроса — оба получают ответ, оба вызова получают
`role: tool`, ноль `turn_phase_transition_rejected`. Тот же прогон должен дать не наблюдавшийся
ни разу статус `failed` — через отказ в разрешении.

**Связано:** P1-56 (гейт разрешений у вызывающего — другой дефект той же подсистемы), P2-38
(вызов без `role: tool`), P2-46 (различение «умер на паузе» / «идентификатор не сняли»),
ADR-007 шаг A (тот же переезд для alias'ов терминалов), ADR-008 шаги 2 и 5, **P2-62** (та же
асимметрия на пути загрузки).

---

### 62. `session/load` решает судьбу turn'а по «последнему» ожиданию — полем, которым домен решать запрещает — 🟡 ЧАСТИЧНО (обнаружено 2026-08-07, разбор логов; правка 2026-08-10, подтверждена живьём; открыт случай двух ожиданий)

**Файлы:** `server/protocol/commands/session_load.py:107-127`.

**Симптом.** Обработка сироты разрешения выбирает судьбу **всего** turn'а по одному ожиданию:

```python
if session_obj.active_turn and session_obj.active_turn.permission_request_id:
    perm_req_id = session_obj.active_turn.permission_request_id
    if not self._pending_registry.has(perm_req_id):
        session_obj.clear_active_turn()
```

Домен про это поле говорит дословно: «Идентификатор **последнего** заведённого ожидания… Решения
принимать по нему нельзя — для этого есть `outstanding_permissions` и `permission_wait_for`»
(`domain/session.py:346-353`). Это **единственный** оставшийся читатель, принимающий по нему
решение: остальные шесть используют его как поле лога, что докстринг разрешает
(`response_router.py:270`, `session_cancel.py:94`, `prompt_orchestrator.py:270`,
`permissions.py:45`, `tool_processor.py:531`).

**Диагноз:** правка P1-61 не донесена до пути загрузки. Доменная модель стала множеством ожиданий,
а этот читатель по-прежнему спрашивает про одно.

**Сценарий отказа** — загрузка сессии **тем же процессом** при двух незакрытых ожиданиях:

1. живо последнее → старая сирота переживает загрузку, её вызов остаётся `pending` и без
   `role: tool` (ровно симптом P1-61, с другой стороны);
2. сирота последняя → `clear_active_turn()` снимает **оба**, и ответ на живое ожидание потом не
   находит turn'а.

После рестарта поведение верное: процессный реестр пуст, `has()` всегда `False`, turn чистится
целиком — и именно поэтому дефект не воспроизводится прогоном с рестартом. Наблюдение 2026-08-07
(`sess_d6501a707159`): сирота была одна (`fa5c6e80`), путь отработал верно — 54166 нашёл её и через
73 мкс дописал в журнал отмену `call_006`.

**Направление (первая формулировка) — «снимать осиротевшие, сохранять живые» — опровергнуто
замером до планирования (2026-08-10).** Сохранить живое ожидание на этом пути **нечем**: сразу
следом `session.session_load` безусловно зовёт `_cleanup_session_state`, который отменяет активный
turn целиком. Ничто не переживает `session/load` в принципе, поэтому проверка реестра решала здесь
не «кого сохранить», а лишь «успеет ли отработать очистка».

**Настоящий дефект оказался тяжелее заявленного, и он измерен, а не выведен.** `clear_active_turn()`
стоял **до** очистки, и та не находила turn'а. Замер на сессии с двумя ожиданиями и отложенным
хвостом батча — с веткой против без неё:

| | с прежней веткой | без неё |
|---|---|---|
| надгробий (`cancelled_permission_requests`) | **0** | 2 (`perm_live`, `perm_orphan`) |
| ответов `role: tool` | 1 (`llm_1`) | 2 (`llm_1`, `llm_2`) |

То есть ветка не просто «решала по неверному полю» — она отменяла обе работы очистки: поздний ответ
на разрешение уходил бы в «неизвестный запрос» (`-32603`, ровно регрессия, пойманная в шаге 2
ADR-008), а отложенный хвост оставался без `role: tool` (P2-38/P2-40).

**Сделано:** решение снято, осталась диагностика. `clear_active_turn()` из ветки убран — отменяет
turn `_cleanup_session_state`, и делает это полно. Лог `session_loaded_with_orphaned_permission_request`
сохранён (он нужен P2-46) и переведён на `outstanding_permissions`: перечисляет **все** осиротевшие
запросы и их число, а не «последний». Домен по-прежнему остаётся без читателей, принимающих решение
по `permission_request_id`, — поле снова только лог.

Седьмой случай того же класса, что `result_content`, `terminals_owner`, futures реестра,
`forget_session`, отметки ожидания в реестре alias'ов, — но с обратным знаком: здесь код имел
наблюдаемое следствие, и оно было вредным.

**Гейт:** `test_orphaned_permission_does_not_preempt_cleanup` — загрузка с двумя ожиданиями, из
которых в реестре живёт **первое** (то, что «последним» не является); проверяются надгробия обоим и
оба ответа `role: tool`. **Проверен возвратом дефекта:** дословно возвращённая прежняя ветка валит
ровно этот тест и только его. `make check` — 7748 passed, `lint-imports` — 4 контракта kept.

✅ **Подтверждено живьём (2026-08-10, `sess_8dd8e1a96105`, stdio через Zed, `pid 94476`, затем
`96847`; копия pipx сверена с деревом, установка 05:40:00Z против записей с 05:40:42Z).** Ветка
сработала в новой форме — поля `orphaned_request_ids=['3e9bccd5']` и `outstanding_requests=1` пишет
только эта правка, — и **надгробие дошло до диска**: `cancelled_permission_requests: ['3e9bccd5']`.

**Оценка частоты в первой редакции этой записи была занижена, и прогон это опроверг.** Я писал, что
прогон с рестартом дефекта не даёт. Даёт — ту половину, которая и была измерена: прежний код на этом
же документе дал бы пустое множество надгробий (одно ожидание, реестр нового процесса пуст →
`clear_active_turn()` → очистка не находит turn'а). Двух одновременных ожиданий требует только
половина «решение по последнему»; потеря надгробия случалась при **каждом** рестарте с незакрытым
разрешением.

⏳ **Осталось не покрытым полем:** загрузка **тем же процессом** при двух ожиданиях — то есть выбор
по «последнему». Закрыто гейтом.

**Связано:** P1-61 (та же асимметрия на пути ответа, закрыта), P2-46, P2-38, P2-40, ADR-008 шаг 5.

---

### 63. Отмена turn'а отвечает за вызов, который в этот момент исполняется: два `role: tool` на один id — ✅ ЗАКРЫТО (обнаружено 2026-08-10, разбор логов; правка, гейты и подтверждение живьём 2026-08-10)

**Файлы:** `protocol/handlers/prompt_orchestrator.py:330,353`, `protocol/handlers/tool_call_handler.py:234-253`,
`tools/executors/terminal_executor.py:405-422`.

**Симптом, измеренный на `sess_8dd8e1a96105` (2026-08-10).** Вызов `call_034`
(`terminal/wait_for_exit`, id модели `chatcmpl-tool-8522003350ae5950`) объявлен в
assistant-сообщении **один** раз и получил **два** ответа подряд:

```
05:48:15.043  session_cancel_handled                     → «Вызов не выполнялся: turn отменён пользователем»
05:48:15.044  client_rpc_cancelled  terminal/wait_for_exit
05:48:15.048  tool_result_to_history ...8522003350ae5950 → «Ожидание завершения терминала отменено: term_96847_1»
```

Всего в документе 39 записей `role=tool` при 38 уникальных адресатах.

**Диагноз — не гонка, а порядок.** `session/cancel` идёт двумя шагами, и первый всегда раньше
второго:

1. `cancel_active_tools` (`prompt_orchestrator.py:330`) отвечает **каждому** вызову, у которого
   статус не финальный (`is_terminal`), — включая тот, что прямо сейчас исполняется;
2. `cancel_all_pending_requests` (`:353`) роняет его клиентский RPC, исполнитель ловит
   `ClientRPCCancelledError` и возвращает **свой** правдивый результат (P2-50), который
   `tool_processor` пишет в историю вторым ответом.

Корень — предикат: статус не различает «ещё не начинался» и «в полёте». Отвечать за вызов в полёте
должен исполнитель, который его и завершит; общая метёлка вправе отвечать только тем, кто результата
не произведёт никогда.

**Поверхность шире терминалов:** под условие попадает любой вызов, исполняющий клиентский RPC в
момент отмены, то есть весь `fs/*` и `terminal/*`. В этом прогоне в полёте был ровно один вызов —
отсюда один дубль, а не серия.

**Почему это P1, хотя прогон не упал.** Дубль **скормлен модели**: следующий промпт (05:49:34) ушёл
с этой историей, и MiniMax её стерпел. Контракт LLM-API требует ровно один `role: tool` на каждый
`tool_call_id` из assistant-сообщения; строгие провайдеры такой запрос отклоняют. Дефект латентный и
переживает рестарт — он лежит на диске.

**Блокирует ADR-008 шаг 4.** Проекция `history` обязана гарантировать «один ответ на вызов», а
вывести её из журнала здесь нельзя: второго ответа в журнале **нет** (39 `role=tool` в истории при
39 `tool_call_status_changed`, но дубль журналом не описан). Тот же класс, что P1-60, который по
той же причине правился до шага 4.

**Класс.** Возврат P2-45 («два ответа `role: tool` на один вызов», закрыт 2026-08-03) через другую
дверь — отмену. Общее у них — отсутствие владельца ответа: писателей два, договорённости нет.

**Сделано (2026-08-10) — две меры с разными ролями, и роли пришлось поменять по ходу разведки.**

*Гарантия — идемпотентность доменного сейма.* `Session.add_tool_result` отклоняет второй ответ на
тот же `tool_call_id`. Владельцем сделан домен: инвариант «ровно один `role: tool` на id» — это
контракт LLM-API, который докстринг сейма и так за собой числил, а писателей ответа **шесть**, и
договориться дисциплиной они однажды уже не смогли.

Гарантия структурная, а не удачное совпадение: `SessionCommands.apply` применяет команду к
**свежему** агрегату под блокировкой сессии (`SessionRepository.transaction`, ADR-007), поэтому
второй писатель видит запись первого, даже придя из другого запроса. Побеждает **первый** ответ: он
уже мог уехать клиенту и в prompt cache, переписывать историю задним числом дороже, чем принять
менее точный текст.

*Выбор текста — предикат.* `cancel_active_tools` пропускает **только ответ** для вызова в полёте
(`ToolCall.is_in_flight`), чтобы вперёд прошёл правдивый текст исполнителя. Статус и нотификацию
метёлка выставляет по-прежнему: пропуск целиком лишил бы клиента `session/update` об отмене, а это
ACP-поведение, и P2-63 его менять не просит.

**Три премисы опровергнуты по коду до планирования, и каждая меняла решение:**

1. *«Идемпотентность не сработает — у отмены своя копия агрегата».* Неверно: писатели сериализованы
   через блокировку сессии, каждая команда перечитывает свежий агрегат. Из «половинчатой страховки»
   идемпотентность стала полной гарантией.
2. *«`in_progress` виден у всех исполняющихся вызовов».* Замер сперва показал обратное — статус был
   в журнале **только** у `terminal/wait_for_exit` (3 из 3), — и я заключил, что предикат неполон.
   **Это заключение затем опровергнуто по коду, и опровержение важнее замера:** `in_progress`
   выставляется перед каждым исполнением, но событие журнала пишет лишь путь без разрешения
   (`tool_processor.py:752`), а resume после разрешения (`:924`) меняет статус молча. Я снова
   измерил форму (события), а не то, что читает предикат (статус). Предикат полон; гарантией он всё
   равно не становится — остаётся окно между созданием вызова и выставлением статуса, и его
   закрывает идемпотентность.
3. *«Отмена обязана отвечать и за `in_progress`»* — так утверждал существующий тест. Проверка
   показала, что дефект P2-38, ради которого путь написан, — это вызов, вставший **на запросе
   разрешения**, а он несёт `pending`. Сужение предиката его не задевает; тест кодировал прежнее
   правило и заменён осознанно.

**Правка на пути `session/load` откачена как выходящая за пределы доказанного.** Идея «загрузка
отвечает за `in_progress`, раз исполнителя нет» разбилась о то, что `session/load` не отличает
«процесс умер» от «сессию переключили, а исполнитель жив»; тест кодировал «`in_progress` не трогаем»
намеренно. Вопрос остаётся открытым (вызов в полёте, осиротевший смертью процесса, ответа не
получает), но он не наблюдался ни разу и решается отдельно.

**Гейты — по одному на меру, и каждый проверен возвратом своего дефекта.** Снятый предикат валит 2
теста (ответ метёлки вернулся + текст стал обобщённым), снятая идемпотентность — 1 (два ответа на
один id). `make check` — 7752 passed, `lint-imports` — 4 контракта kept.

**Дефект чуть не уехал как no-op, и поймало это измерение, а не тесты.** Первая версия проверяла
`tool_call.is_in_flight` **после** `update_status`, который мутирует тот же объект: статус к тому
моменту уже `cancelled`, признак всегда ложен. Весь набор при этом был зелёным. Признак снимается до
перехода — тот же класс, что чтение идентификатора разрешения до смены фазы в
`_cleanup_session_state`.

✅ **Подтверждено живьём (2026-08-10, `sess_d3033d287168`, stdio через Zed, `pid 41383`; копия pipx
сверена с деревом, установка 09:13:28Z против записей с 09:17Z).** Сценарий пойман намеренно —
промпт «запусти в терминале `sleep 30` и дождись завершения» даёт окно ожидания, в которое успевает
`session/cancel`. `call_042` исполнялся 1.87 с, отмена пришла внутрь окна:

| | до правки (`call_034`, 05:48) | после (`call_042`, 09:38) |
|---|---|---|
| `role: tool` на вызов | **2** | **1** |
| текст | обобщённый **и** правдивый | только правдивый |
| `tool_result_duplicate_suppressed` | — | **0** |

Строки «Вызов не выполнялся» нет вовсе: метёлка промолчала, и **сработал предикат, а страховка не
понадобилась** — то самое разделение ролей. `notifications_count=1` подтверждает, что клиент узнал
об отмене, ради чего пропуск и сузили до одного лишь ответа. По всему документу 43 записи
`role: tool` на 43 уникальных адресата, дублей ноль.

**Журнальная тень осталась, как и предсказано:** у `call_042` два события `cancelled` (метёлка и
исполнитель) — самопереход матрица пропускает намеренно, для корректности безвредно.

⚠️ **Покрыт путь без разрешения.** Ветка resume после разрешения статус тоже выставляет, но полем не
проверена: понадобился бы отменённый в полёте вызов, требующий разрешения.

**Связано:** P2-45 (тот же дефект, другая дверь), P2-38 (вызов без ответа — противоположный перекос
того же места), P2-50 (правдивый текст отмены у исполнителя), P1-60 (так же блокировал шаг 4),
ADR-008 шаг 4.

---

### 59. Stdio-сервер не завершался по `SIGTERM`: агент на 270 МБ переживал клиента — ✅ ЗАКРЫТО (2026-08-04, подтверждено живьём)

**Файлы:** `server/transport/stdio.py` — `run` (цикл чтения), `_setup_signal_handlers`,
`_restore_signal_handlers`, новые `_next_line`/`_read_line`/`_request_stop`.

**Симптом (живой процесс, 2026-08-04).** Процесс `codelab serve --stdio` прожил 17 минут после того,
как его клиент ушёл: `ppid=1`, 271 МБ RSS, в `lsof` stdin — pipe без единого писателя. На `SIGTERM`
не отреагировал, потребовался `SIGKILL`. В его логе при этом есть **обработчик, который сработал**:

```
07:20:43.286813  signal received  pid=9444 signal=15   ← и больше ни строки
```

**Причина — флаг, который никто не проверяет.** `_signal_handler` выставлял `self._closed = True`,
но цикл сверяет `_closed` **только после возврата из** `await readline()`. У молчащего клиента
возврата не происходит никогда, поэтому обработчик отрабатывал, писал строку в лог — и ничего
больше. `SIGTERM` был no-op на практике при формально существующей поддержке.

**Почему это важнее, чем «лишний процесс».** Рабочий транспорт — stdio через сторонний ACP-клиент.
Пока сервер не умеет завершаться сам, его жизнь целиком зависит от того, добьёт ли его клиент.
Zed добивает — во всех шести логах агентов, поднятых им, нет ни `stdin EOF`, ни
`stdio transport stopped`, ни `server_shutdown`, то есть штатно наш сервер не завершался **ни разу**.
Любой клиент, который вежливо закрывает stdin и посылает `SIGTERM` вместо `SIGKILL`, а также любое
падение Zed — оставляли полный агент на ~270 МБ без владельца.

**Решение.** Чтение stdin вынесено в отдельную задачу (`_read_line`), обработчики сигналов ставятся
через `loop.add_signal_handler` — только так они исполняются в контексте loop'а и могут **отменить
текущее чтение** (`_request_stop`). Отмена чтения при выставленном `_closed` трактуется как
завершение; внешняя отмена цикла (при `_closed = False`) пробрасывается как отмена задачи, а не
выглядит как EOF. Синхронный `signal.signal` остался откатом на случай отсутствия loop'а или не
главного потока — он хуже (разбудить чтение не может), и это записано в docstring.

**Разграничение с EOF — измерено, а не предположено.** Закрытие stdin работало и до правки, но
не на всех видах входа: на **анонимном пайпе** (то, что использует Zed) EOF приходит и даёт
`stdin EOF, shutting down` → `stdio transport stopped`; на **FIFO** — не приходит, процесс остаётся
жив при нулевых писателях. Второе воспроизводится и после правки; на рабочий путь не влияет, поэтому
оставлено как известное ограничение, а не исправлено вслепую.

**Проверено живьём:**

```
SIGTERM:  signal received → stdin read cancelled by shutdown signal → stdio transport stopped
          процесс завершился, добивать не потребовалось
EOF (анонимный пайп):  stdin EOF, shutting down → stdio transport stopped, код возврата 0
EOF (FIFO):            процесс остаётся жив — предсуществующее ограничение, см. выше
```

**Гейты.** `make check` — 7555 тестов. Юнит-гейт на сам дефект: сигнал отменяет припаркованное
чтение stdin (без этого флаг завершения не наблюдается); отмена сигналом останавливает цикл, а
внешняя отмена остаётся отменой и не выглядит как EOF; обработчики ставятся на loop'е; без loop'а
работает откат на синхронный обработчик.

**Изменение контракта.** Процесс теперь завершается по `SIGTERM`/`SIGINT` сам. Клиентам, которые
рассчитывали на «сервер живёт, пока его не убьют `SIGKILL`», поведение станет заметно — это
исправление, а не регресс: до него сервер не завершался штатно вообще.

**Через Zed правка не наблюдаема — и это ожидаемо (проверено на исправленной сборке 2026-08-04).**
Прогон на pipx-сборке, уже содержащей правку (`add_signal_handler` и `_request_stop` присутствуют):
близнец `13361` снова снят **без единой записи о завершении** — ни `signal received`, ни `stdin EOF`,
ни `stdio transport stopped`. Значит Zed добивает агента `SIGKILL`, на который реагировать
невозможно по определению. Ценность правки не в штатном цикле Zed, а в двух других случаях: клиент,
посылающий `SIGTERM` (там проверено живьём на стенде), и падение самого клиента, после которого
агента снимать некому.

**Известное ограничение, оставленное сознательно.** EOF не приходит на FIFO, и правка по сигналам
этого не лечит. Наблюдалось в собственных стендах дважды: процессы жили по 30 минут с `ppid=1`,
удерживая 41 и 142 МБ. На рабочем пути не проявляется — сторонние клиенты используют анонимный пайп,
где EOF приходит. Если понадобится закрыть и это, точка входа — поведение
`connect_read_pipe`/`StreamReaderProtocol.eof_received` на FIFO.

**Связано:** P2-48 (близнец переставал утекать после этой правки — его тоже снимает сигнал),
P2-53 (тот же класс «процесс без владельца жизненного цикла», но в websocket-режиме и на 14 МБ
вместо 270), P2-28 (фоновые задачи без контроля жизненного цикла).

---

---

## Дорожная карта

> **Исторический план** (составлен при первичном аудите). Фактический порядок работ
> разошёлся с ним; актуальный статус — в разделах P0–P2 выше. Оставлено для контекста.

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
| Max cyclomatic complexity | 30 | guardrail `C901` 20 → **10** ✅ (ruff-mccabe, целевой) | <= 10 |
| Файлов > 1000 строк | 6 | **1** 🟡 (оправданно крупный `messages.py`) | 0 |
| Warnings в тестах | 62 | **0** ✅ (оба класса → `error`-guardrail, 0 unraisable) | 0 |
| Ruff-нарушений | ~170 | **0** ✅ | 0 |
| Ошибок `ty` (typecheck) | — | **0** ✅ (гейт `make check` зелёный, см. P0-14) | 0 |
| TODO | 2 | **0** ✅ | 0 |
| Coverage threshold в CI | нет | **85%** ✅ (`release.yml`) | 80% |

**Итог (2026-07-14):** покрытие, ruff и порог покрытия в CI достигли цели. Пик
сложности после пересчёта (51) снят до **20** — D-блоков (≥21) не осталось,
регресс закрыт guardrail'ом `C901` (max-complexity=20); блоков > 10: 72 → **60**;
остаток — плановое снижение порога к 10 (см. P0-2). God Objects снизились 10 → **1** (декомпозиция
`core.py`, `di.py`, `chat_view_model.py`, `app.py`, `mcp/transport.py`,
`acp_transport_service.py`, `prompt.py`, `gatherer.py`, `agent_loop.py`); остаётся
только оправданно крупный `messages.py` (P1-4). Гейт `ty` в `make check` восстановлен
(2026-07-15): 4 предсуществующие ошибки типов устранены, обязательная проверка проходит
целиком (P0-14). Ключевой рычаг
против незаметной деградации между аудитами — CI-guardrails: порог сложности
`C901`, проверка размера файла (`scripts/check_large_files.py`) и `--cov-fail-under`.

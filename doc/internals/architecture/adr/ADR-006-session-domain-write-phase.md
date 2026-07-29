# ADR-006: Write-фаза доменной миграции сессии (вариант B ADR-003)

**Дата:** 23 июля 2026
**Статус:** Предложено
**Контекст:** Завершение доменной миграции сессии — `domain.Session` как рабочий агрегат сервера
**Авторы:** —
**Связанные документы:**
- ADR-003 — протечка `SessionState` в agent; выбран **вариант B** (доменный агрегат), выполняется отдельным эпиком
- ADR-005 — ACP-независимое ядро агента; **read-фаза** варианта B (порты `SessionView`/`ContentCodec`/…)
- `src/codelab/server/domain/session.py` — доменный агрегат `Session`
- `src/codelab/server/protocol/state.py` — `SessionState` (Pydantic-модель сериализации)
- `src/codelab/server/mapping/session_mapper.py` — `SessionMapper` (domain ↔ protocol)
- `src/codelab/server/storage/base.py` — `SessionStorage` (типизирован против `SessionState`)
- openspec change `session-domain-write-phase`
- `doc/internals/architecture/server-target-state.md` — целевая (post-refactor) схема серверной части

---

## Контекст

ADR-005 (read-фаза) развязал **ядро** (`agent.core.*`) от `protocol` через driven-порты:
на сегодня `agent.core.*` имеет **ноль** рёбер к `protocol` (подтверждено `import-linter` и
приёмочным smoke-тестом `CoreAgentRunner` на фейках). Но **корень** долга ADR-003 (вариант B)
не устранён — устранена лишь его read-поверхность:

1. **Рабочая модель сервера — по-прежнему `SessionState`** (Pydantic). Хендлеры turn-а
   **мутируют** её по ходу (`active_turn`, `history`, `tool_calls`, `plan`). `domain.Session`
   существует, но используется в основном как промежуточная модель, а не как агрегат,
   которым оперирует система.
2. **Тройное представление сессии** — `domain.Session` / `protocol.SessionState` / порты
   (`SessionView`) — точка рассинхрона (ср. P2-32 по capabilities).
3. **Остаточные рёбра `→ protocol.state`** в `ignore_imports` не снимаются read-фазой:
   - `agent.context.file_cache_decorator` — форвардит `session` в tools-executor;
   - `storage.base` — **рантайм**-импорт `SessionState`, сериализует/грузит её (не type-only);
   - `tools.executors.decorators.base` — executor'ы принимают `SessionState`.
   Все три требуют развязки `storage`/`tools` от `SessionState`, что read-фаза не делает.

Итог: цель ADR-003 «`Server layers` зелёный **без исключений для agent**» read-фазой
**недостижима** — упирается в write-путь и сериализацию/хранение.

## Решение

Выполнить **вариант B ADR-003** как эпик write-фазы:

1. **`domain.Session` — рабочий агрегат сервера end-to-end.** Turn-путь оперирует агрегатом
   (мутации сессии — доменные операции агрегата), а не Pydantic-моделью.
2. **`SessionState` низводится до сериализационного DTO** на границе wire/storage. Единственная
   точка конвертации — `SessionMapper` (domain ↔ protocol), симметричность которого доводится
   (устранить асимметрию роли `tool`, потерю полей).
3. **`SessionStorage` работает с `domain.Session`.** Формат хранения — **versioned schema с
   миграцией** существующих `~/.codelab/.../sessions` (изменение формата = миграция по CLAUDE.md).
4. **Tool-executor'ы получают доменный контекст.** Executor'ам нужна богатая поверхность
   (`cwd`, permission-контекст, `active_turn`, client-RPC) — вводится доменный `ToolContext`
   (или агрегат отдаёт нужное), `ToolExecutorProtocol` ретайпится с него.
5. **`file_cache_decorator`** после развязки tools-цепочки теряет ребро `→ protocol.state`.
6. **Унификация capabilities** (`ClientRuntimeCapabilities` ↔ `shared.ClientCapabilities`) —
   в рамках того же эпика (закрывает сторону P2-32).

## Гейты (одобрены владельцем, 2026-07-23)

- **Fake driver** — второй (не-ACP) driving-адаптер как тест-харнесс; диктует форму доменных
  портов (`AgentRunner`/`UpdateSink`) consumer-driven, а не спекулятивно.
- **Смена формата сериализации сессий допустима** — при условии миграции/совместимости.
- **Golden-тесты `session/update` wire** — обязательный гейт байт-идентичности.

## Последствия

- **Закрывает ADR-003 целиком:** `Server layers` зелёный без исключений для `agent`; снимаются
  строки `ignore_imports` `file_cache_decorator`/`storage.base`/`tools.executors.decorators.base`.
- Устраняет тройное представление сессии; `SessionState` — только сериализация.
- **Изменение публичного контракта:** формат хранения сессий → миграция обязательна;
  wire `session/update` — байт-в-байт (golden-гейт).
- Крупный рискованный рефактор горячего пути (мутации по ходу turn-а, маппинг на границе).
- Разблокирует прод turn-loop через `AgentRunner` (ADR-005, 4.3) и доменную эмиссию `UpdateSink`.

## Рассмотренные альтернативы

- **Оставить read-фазу как финал** (порты + `ignore_imports` для storage/tools). Отвергнуто как
  постоянное решение: ADR-003 явно требует устранить корень; тройное представление и
  рантайм-протечка `storage.base` остаются.
- **Не менять формат хранения** (маппинг только в памяти, на диск — по-старому). Возможно как
  interim, но не устраняет связку storage↔`SessionState` и усложняет инварианты.

## Порядок работ

Эпик — **Workstream D** плана ADR-005; после него разблокируются **B** (доменная эмиссия
`UpdateSink`, ADR-005 3.3/3.4), **C** (прод turn-loop через `AgentRunner`, 4.3), **E** (fake driver).
Детализация — в openspec change `session-domain-write-phase`.

### Переупорядочивание внутри эпика (2026-07-23)

**Finding:** 81 сайт (`protocol/` handlers/commands) держит `SessionState` как **рабочую
модель** (load→mutate→save); все реализации `SessionStorage` сериализуют через
`SessionState.model_dump/model_validate`. Ребро `storage.base → protocol.state` — **симптом
рабочей модели**, а не независимая вещь: тип `storage`/`tools` следует за рабочей моделью.

**Решение:** внутри эпика D2 (storage-on-domain) и D3 (tools) идут **после** D4 (рабочая
модель → `domain.Session`), иначе D2 создаёт throwaway-конверсии `SessionState↔domain` на
81 сайте. Порядок: **D0 → D1 → D4 → D2 → D3 → D5**. D4 ведётся strangler-стадиями по
под-стейтам (по возрастанию связности), каждая — за golden-wire + round-trip + `make check`.

### Дом состояния сессии: доменные VO, а не protocol-компаньон (2026-07-23)

**Finding:** «протокольный runtime-остаток» `SessionState` (`active_turn`, `terminals`,
`events_history`, `session_metrics`, `cancelled_client_rpc_requests`, …) — по проверке `state.py`
это **плоские данные** (`str`/`int`/`bool`/`dict`) без wire-логики ACP. Это **состояние сессии**,
чей ТИП случайно объявлен в `protocol/state.py`, а не протокол.

**Решение:** различать по СЕМАНТИКЕ. Состояние сессии переезжает в `domain` как plain VO
(`TurnState`, `SessionRuntime`); `domain.Session` становится **полной** рабочей+персистируемой
моделью. `storage.base` типизируется на `domain.Session` → ребро `storage.base → protocol.state`
**снимается** (D2.5 достижим). `SessionState` низводится до тонкого wire-DTO для ACP-подмножества
(replay/init) в `protocol`. Wire-framing (кодирование ACP-запросов/нотификаций) остаётся в `protocol`.

**Отклонено:** slim runtime-компаньон в `protocol` (`SessionRuntime`/`SessionContext`) — он не снял
бы ребро (`storage.base → …компаньон… → protocol`), а лишь переместил; и относил бы состояние сессии
к протоколу вопреки семантике. Инвариант «протокол в домен не течёт» не нарушается: переезжают
данные, не wire-семантика (`active_turn` = доменное «ждём внешний запрос X»; id — опаковый
resume-токен; переотправление после рестарта — протокол). Это устраняет корень (вариант B) целиком.

### Карта чтений/мутаций `SessionState` (D4.1, 2026-07-24)

Построена детерминированная карта обращений к `SessionState` по под-стейтам
(`openspec/changes/session-domain-write-phase/d4.1-mutation-map.md`). Threaded-объект —
`PromptContext.session`; границы транзакции `load→mutate→save` — в командах
(`session_prompt`/`session_load`/`session_cancel`/…). Находки:

- **`SessionMapper` в проде не вызывается** (только тесты) — расширение маппера безопасно для
  горячего пути; гейт — round-trip baseline (D0.2).
- **Оценки объёма в design.md устарели.** Реальная поверхность больше: `active_turn` 72R/31W через
  ~13 файлов; config-чтения (`cwd`/`config_values`/`runtime_capabilities`/`mcp_servers`) ~73R.
- **Рантайм-мёртвые под-стейты** (обращений на объекте сессии нет / только в маппере):
  `latest_plan` (0 сайтов), multi-agent поля (только `SessionMapper`). Их стадии — тривиальны.
- **Мёртвые поля:** `task_result`, `sliced_summary` (0 сайтов вне `state.py`); `session_metrics`,
  `correlation_id` (0 рантайм-сайтов — проверить наполнение при сериализации, кандидаты на удаление).
- **Дублирование стратегии:** `SessionState.active_strategy` дублирует `config_values["_active_strategy"]`
  (рантайм читает config-ключ, а не поле). Решить при флипе multi-agent под-стейта.
- **Дублирование tool_call-мутатора:** `protocol/handlers/tool_call_handler.py` и
  `protocol/handlers/prompt/tool_calls.py` — структурно идентичны (increment counter + insert).
- **Рассинхрон фаз turn:** `directives.py` пишет `phase="waiting_permission"`, а
  `pipeline/.../tool_processor.py` — `"awaiting_permission"` для похожего состояния (строковые
  литералы без enum). Устранить типизированным `TurnPhase` при вводе `TurnState` VO.
- **Duck-typing из agent-слоя:** `getattr(session, "cwd"/"config_values", …)` в `gatherer`/
  `child_session`/`dispatcher` — учесть нестрогие чтения при флипе типа threaded-объекта.

Уточнённый порядок стадий D4-b (по возрастанию связности):
`plan → multi_agent → terminals → tool_calls → history → permissions → runtime → config →
active_turn (последним)`.

### D4-a выполнен (2026-07-24)

`domain.Session` дополнен доменными VO `TurnState` (из `ActiveTurnState`) и `SessionRuntime`
(`terminals`/`terminal_counter`/`events_history`/`cancelled_client_rpc_requests`/
`pending_prompt_response`/`session_metrics`/`correlation_id`). `SessionMapper` доведён до
round-trip без потерь turn/runtime-состояния (опаковые снимки — plain dict, домен остаётся
чистым). `PromptContext.domain_session` — аддитивный scaffold, строится через
`SessionMapper.to_domain` на входе turn'а; `SessionState` остаётся source-of-truth, потребителей
нет. `mcp_prompt_handlers` (`exclude=True`, transient) и `available_commands` (ACP wire-DTO) в
домен не переезжают. Гейт: round-trip + golden-wire + `make check` (7359 passed, 1 xfail→D2).

### Ре-секвенирование: prep → D2 → D4-d (пивот, 2026-07-24, одобрено владельцем)

**Finding.** Per-sub-state write-flip (D4-c-стиль) трижды подряд упёрся в одно: `domain_session` не
проброшен на путь X. plan (b1) потребовал E-resume; tool_calls создаётся на ~8 сайтах/4 путях
(agent_loop, directives, **client-RPC, client-requests** — два последних `domain_session` не несут),
а `tool_call_counter` общий → флип обязан быть атомарным; history вдобавок блокирован multimodal (D2).
При этом чтения всё равно остаются на `SessionState` до D4-d, а durable-ценность дал **b3a**
(доменные поля + lossless-маппер): `SessionMapper.to_domain` уже отработал на проде 33× без потерь.

**Решение.** Прекратить дальнейшие per-sub-state write-flip'ы. Порядок остатка:
1. **Prep (lossless round-trip)** — довести/подтвердить `domain.Session ↔ SessionState` без потерь для
   ВСЕХ полей (уже: turn/runtime — D4-a, tool_calls — b3a, plan — PlanMapper, permissions/multi_agent/
   config — тривиальны). Гейт — сквозной round-trip тест; риск нулевой (аддитивно к мапперам).
2. **D2** — формат хранения + миграция + multimodal history (единственный незакрытый round-trip).
3. **D4-d** — ОДИН флип threaded-объекта (`context.session` → `domain.Session`); `SessionState`
   пересобирается на границе wire/storage через lossless `SessionMapper`. Риск сконцентрирован в одном
   хорошо-гейтнутом шаге (golden-wire + round-trip + live-smoke), совпадает с механизмом M2 design.md.

Сделанные b1 (plan) и E-resume — не выброшены: b1 доказал sink как domain-носитель, E-resume даёт
`domain_session` на resume-пути (нужен и для D4-d). b3b (tool_calls write-flip) — **снят** в пользу
D4-d (флип на границе). `terminals` — по-прежнему после D3.

**Коллизия имён (follow-up):** новый доменный VO `domain.session.SessionRuntime` (персистируемое
рантайм-состояние сессии: terminals/events/…) тёзка существующего
`protocol.session_runtime.SessionRuntime` (live-реестр per-session: notification bus,
`mcp_prompt_handlers`) — разные концепции. Пока в разных пакетах; при флипе runtime под-стейта
(D4-b «runtime») развести имена во избежание путаницы (ср. память «naming-semantics-over-compat»).

### Prep закрыт: 8 полей punch-list lossless (2026-07-24)

**Finding (D4-prep диагностика).** Round-trip `SessionState → domain → SessionState` (критичное для
D4-d направление — `SessionState` пересобирается из домена на границе) терял 8 полей. Все фиксы
аддитивны к домену+мапперам, риск нулевой.

**Сверка с ACP (снимает развилку по `timestamp`).** Протокол **не моделирует** per-message время;
единственное понятие времени — session-level `updatedAt: string | null`, «Set to null to clear»
(`17-Schema.md:2824,2852`). Значит: (1) `ConversationMessage.timestamp` — наше storage-расширение, не
ACP-контракт → смена доменного дефолта не является изменением протокола; (2) nullable — протокол-
санкционированная семантика → `timestamp: datetime | None = None`, null **не синтезируется** при
пересборке; (3) `updated_at` нести как есть — регенерация = ложная «last activity».

**Сделано (аддитивно):**
- `ConversationMessage.timestamp` → `datetime | None = None`; мапперы (`history_mapper`,
  `session_mapper._build_history`) несут `None → None`.
- `SessionConfig.mcp_servers`; `Session.{title, updated_at, schema_version, available_commands}`
  (storage-мета, `updated_at` не регенерируется); `MultiAgentState.{task_result, sliced_summary}`
  (opaque, для миграции).
- `raw_input` — оставлен derive. Инвариант реальных данных `raw_input == tool_arguments` (54/54 на
  дампе `sess_c3a315689e80`) → отдельный доменный дом не нужен; регрессия `{}→{...}` была артефактом
  синтетической фикстуры.

**Гейт:** `TestProtocolRoundtripLossless::test_protocol_roundtrip_lossless` +
`TestRoundtripPrepFields` (`test_session_mapper_roundtrip_baseline.py`). `make check`: 7367 passed,
1 xfail. Проверено на реальном дампе: все 8 полей lossless, 108 None-timestamp сохранены.

**Осталось за скопом prep → D2.** Полный `model_dump()` реального дампа ещё не байт-идентичен —
расходится **тело history-сообщений**: `content` (блоки vs `.text`), embedded `text`, embedded LLM
`tool_calls`. Это не punch-list, а fidelity истории; зафиксировано как
`xfail test_multimodal_history_preserved`. Чинится в **D2** (versioned schema + миграция формата) —
единственный незакрытый round-trip перед D4-d.

### План D2 — history-body fidelity (диагностика 2026-07-24, реализация — отдельной сессией)

**Finding (карта путей истории).** Сериализация истории идёт ДВУМЯ путями, второй lossy:
1. `HistoryMapper.to_protocol/to_domain` — богатый: разворачивает `content`-блоки, `resources`,
   `images` (`history_mapper.py:24-41`).
2. `SessionMapper` (`to_protocol` inline + `_build_history`) — **lossy**: строит
   `HistoryMessage(content=msg.content.text)`, только текст, **не делегирует** в `HistoryMapper`.

**Почему прод сегодня не теряет историю.** Живой путь записи пишет `SessionState` напрямую
(`JsonFileStorage.model_dump(mode="json")`); `HistoryMessage` с `extra="allow"` несёт всё
(`content`-блоки, отдельный `text`, embedded LLM `tool_calls`). Доменная конверсия ПОКА не на пути
записи. **Капкан:** wire `HistoryMessage` богаче домена `ConversationMessage` (=`MessageContent`
{text,resources,images} + `tool_call_id`) — у домена НЕТ полей под отдельный LLM-`text`, embedded
LLM-`tool_calls`, блочный `content`. **D4-d флипнет запись через домен → без обогащения домена
потеряет тело истории.** Это подтверждает порядок D2 → D4-d фактами (не только throwaway-конверсиями).

**Декомпозиция (одобрен ПЛАН; реализация отдельной сессией — фаза меняет on-disk формат):**
- **D2-a** — обогатить домен `ConversationMessage`: нести embedded `text` + LLM `tool_calls` +
  блочный `content` (аддитивно, не ослабляя типы). Риск низкий.
- **D2-b** — `SessionMapper` (`to_protocol` + `_build_history`) делегирует в lossless `HistoryMapper`
  оба направления; убрать text-only путь. Риск средний (единый путь сериализации истории).
- **D2-c** — гейт: full-dump round-trip `d0 == d1` на реальном дампе (флип
  `xfail test_multimodal_history_preserved` → pass; ср. prep-гейт `test_protocol_roundtrip_lossless`).
- **D2-d** — миграция: `HistoryMessage` уже несёт всё → структурная смена формата может НЕ
  потребоваться (тогда no-op version bump `v6→v7` в `SessionState.migrate_schema`); если домен
  начнёт диктовать иную форму — полноценное звено миграции + прогон на `~/.codelab/.../sessions`.

**Гейт фазы:** full-dump round-trip + golden-wire (ADR-005 гейт #3) + `make check` + live-smoke.
После D2 незакрытых round-trip не остаётся → D4-d (один флип `context.session → domain.Session`).

#### Решение по D2-a (реализация 2026-07-24): дуальные слоты — концерн маппера, не домена

Диагностика на реальном дампе (`sess_cc54a1f6c4d3.json`, 116 сообщений) уточнила форму wire
`HistoryMessage`: `text` (top-level str, assistant), `content` = str (tool result) | list[block]
(user) | null, embedded `tool_calls` = `[{id,name,arguments}]`. Выбор слота `content` **не** строго
определяется ролью — `state_manager.add_assistant_message` пишет `text` для str-входа и `content`
для dict-входа.

**Развилка моделирования** (как домену нести дуальные слоты для byte-lossless D4-d):
1. `text` + form-дискриминатор в домене;
2. `text`-слот как транспортный концерн → политика слотов в маппере (роль-driven, тотальная);
3. сырой wire-`content` рядом с семантическим `MessageContent`.

**Выбрано №2.** Дуальные слоты `text`/`content` — артефакт LLM-транспорта, не доменная семантика;
у всех ролей одно понятие «содержимое», уже смоделированное `MessageContent`. Выбор слота при
сериализации — политика маппера (его единственная задача — мост домен↔wire). №1 протаскивает
сериализационное состояние в доменную сущность (протечка слоя); №3 держит две репрезентации одного
факта (дрейф). «Хрупкость» №2 снимается тотальной детерминированной политикой в маппере: реальный
слот однозначен по роли (assistant→`text`/null, tool→str, user→blocks; 0 dict-content assistant,
0 `data!=null`), а теоретический assistant-со-structured-content закрывается явной веткой + assert,
не хранимым дискриминатором.

**Следствие — D2-a переопределён по факту: no-op на доменной модели.** Домен уже достаточен:
- `ConversationMessage.tool_calls: list[ToolCall]` — поле уже заведено (дормантное, мапперы его не
  заполняют); embedded LLM `{id,name,arguments}` ложится один-в-один (`id→id`, `name→tool_name`,
  `arguments→arguments`), прочие поля `ToolCall` остаются дефолтами и в embedded-слот не эмитятся;
- `MessageContent{text,resources,images}` покрывает все реальные формы блоков; `data: null` на
  text-блоке — дефолт wire-`MessageContent`, восстанавливается маппером;
- отдельное доменное поле под `text`-слот не заводится (по №2 это тот же `content.text`).

Разрыв fidelity — исключительно в lossy-мапперах, не в домене. Весь объём D2 смещается в **D2-b**
(тотальная роль-driven политика слотов + делегирование `SessionMapper` ↔ lossless `HistoryMapper`
в обоих направлениях; удаление text-only пути).

#### Реализация D2-b/c/d (2026-07-24)

- **D2-a — no-op** (домен уже достаточен, см. решение выше).
- **D2-b — сделано.** `HistoryMapper` переписан тотальным и двунаправленным: роль-driven политика
  слотов (`_content_to_wire`), чтение плоского `text`-слота и embedded LLM `tool_calls`
  (`_parse_embedded_tool_calls` → доменное поле `ConversationMessage.tool_calls`), сохранение роли
  `tool` (без схлопывания в `assistant`). `SessionMapper.to_protocol` (inline) и `_build_history`
  делегируют в `HistoryMapper`; text-only путь удалён. Единый путь сериализации истории.
- **D2-c — гейт зелёный.** Флип `xfail test_multimodal_history_preserved` → pass; добавлен
  `test_history_body_roundtrip_lossless` (все реальные wire-формы: assistant `text`+tool_calls,
  tool строковый content, user блочный content + image). Проверено на реальном дампе
  (`sess_cc54a1f6c4d3.json`, 116 сообщений): `d0['history'] == d1['history']`, 0 расхождений.
  Обновлены ожидаемо-изменившиеся тесты (`test_session_mapper`, `test_history_mapper`).
- **D2-d — no-op.** Структурной смены on-disk формата не произошло: round-trip через домен
  байт-идентичен входу на v6-дампе, живой путь записи (`JsonFileStorage`) не менялся. Version bump
  `v6→v7` и звено миграции не требуются.

**Итог:** незакрытых round-trip перед D4-d не осталось. `make check` зелёный (7372 passed).
Замечание: `SessionMapper.to_protocol` в проде пока не на пути записи (флип — D4-d), поэтому смена
формы сериализации истории регрессий на живом пути не даёт; `to_domain` (вход turn'а) стал богаче —
assistant-текст и embedded tool_calls больше не теряются при пересборке домена.

### Аудит D4-d — карта write-сайтов (диагностика 2026-07-24, только чтение)

**Цель.** Перед флипом убедиться, что «один флип threaded-объекта» реализуем. Аудит покрыл три оси:
жизненный цикл `SessionState`, write-сайты `tool_calls`, write-сайты остальных под-стейтов.

**Жизненный цикл (граница persist).** `SessionState` — единственный source-of-truth и на wire, и
in-memory, и на диске: мутируется **in-place**, весь пайплайн держит **тот же объект**. Резидентный
экземпляр живёт в LRU-кэше `CachedSessionStorage` (`storage/cached.py:49`); каждый turn: `load`
(тот же объект) → in-place мутации → `save`. `SessionMapper.to_protocol` в живом пути записи **не
участвует вообще** (только тесты). `to_domain` вызывается в двух точках (`prompt_orchestrator.py:217`,
`background_executor.py:177`) — аддитивный доменный снимок для чтения, «сгорает» в конце turn'а.
Физическая граница сериализации — `storage/json_file.py:69` (`model_dump`) и `:103` (`model_validate`
+ `migrate_schema`).

**Ключевой вывод — D4-d НЕ «один флип».** `domain_session` — эфемерный per-`PromptContext` снимок,
построенный в ОДНОЙ точке (вход turn'а). Множество write-путей `PromptContext` не получают вовсе:
1. **`response_router` path** (client-RPC responses `client_rpc_response.py`, permission-resume
   `prompt/permission_response.py`) — `PromptContext`/`domain_session` не создаётся никогда.
2. **Pre-pipeline turn-setup** — `state_manager.add_user_message`/`title`/`updated_at`
   (`prompt_orchestrator.py:196-206`) исполняется ДО построения `domain_session` (`:217`).
3. **Прямые писатели вне пайплайна** — slash-команды, `mcp_session_manager`, context-`gatherer`,
   tool-executor-декораторы, storage-граница — работают с `SessionState` напрямую.

**Гапы по под-стейтам (`domain_session` недоступен на сайте мутации):**
- **tool_calls** — крупнейший. 5 низкоуровневых примитивов (`tool_call_handler.py:111-114,159`;
  `prompt/tool_calls.py:21-23,61`; `session.py:78`) принимают только `SessionState`. `domain_session`
  доходит до `AgentLoop.run()` и `SessionUpdateSink`/`ToolCallUpdateBuilder`, но **не** до
  `ToolCallProcessor` (гап «на один хоп»: ctor `tool_processor.py:80`, вызовы `loop.py:337,493`).
  Пути без `domain_session`: agent_loop/tool_processor (~11 сайтов), client-RPC handler
  (`client_rpc_handler.py:143,215,284,363,384`), client-request builders
  (`client_requests.py:98,142,209`), client-RPC response (`client_rpc_response.py:93..581`),
  permission-resume, cancel-примитивы (`tool_call_handler.py:407`, `session.py:78`,
  `prompt/tool_calls.py:236`). В scope на самом сайте create — только `directives.py:208`.
- **history** — 6 сайтов, ни один не флипнут: `agent_loop/loop.py:328,432`,
  `tool_processor.py:877`, `llm_loop.py:259`, `state_manager.py:75,109`.
- **permissions** — весь под-стейт гап (policy: `permission_manager.py:324`,
  `prompt/permission_response.py:64`; cancelled: `session.py:65`, `prompt_orchestrator.py:330`,
  `permissions.py:241`, `commands/permission_response.py:87`).
- **config_values** — весь гап (`config.py:101`, slash-`{strategy,mode,context}`,
  `project_structure.py:159`, `gatherer.py:572`).
- **available_commands** — весь гап (`mcp_session_manager.py:180,374,566`).
- **multi_agent** — прямой write один (`child_session.py:89-90` через `config_values`); прочие поля
  пишутся только через маппер (round-trip).
- **title/updated_at** — turn-setup (pre-pipeline) + storage/client-RPC граница.

**Флипнут только plan** (`directives.py:118+135`, `updates.py:_apply_plan:185`) — единый писатель
`latest_plan` через `domain_session.plan` + dual-carry.

**Следствие — переформулировка D4-d.** «Флип одного threaded-объекта» недостижим, пока
`domain_session` — эфемерный снимок per-`PromptContext`. Настоящий D4-d = **релокация резидентного
source-of-truth**: доменный `Session` становится объектом в LRU-кэше и нитью, прошитой везде, а
`SessionState` пересобирается только на границе сериализации (`json_file.py:69`) через доменный
storage-порт (обёртка над `SessionStorage`: `to_protocol` на `save`, `to_domain` на `load`). Это
покрывает `response_router` и pre-pipeline пути одним махом (у них появляется доступ к резидентному
домену), но затрагивает ВСЕ write-сайты, а не один. Альтернатива (прошить `domain_session` в каждый
примитив) не закрывает пути, где `PromptContext` не строится, — поэтому storage-порт предпочтителен.

### Решение D4-d — резидентный домен + `SessionRepository`-порт (одобрено владельцем 2026-07-24)

**Стратегия.** Настоящий D4-d = релокация резидентного source-of-truth: доменный `Session`
становится рабочим объектом в памяти, `SessionState` — чистый DTO на границе сериализации. Отвергнута
прошивка эфемерного снимка `domain_session` в сайты (не закрывает пути без `PromptContext`, размазывает
шов конверсии) и хаки коэкзистенции (dual-write, duck-typed общий интерфейс — плодят долг, размывают
источник истины).

**Тезис 1 — кэш держит домен (необходимость, не развилка).** In-place-мутационный контракт turn'а
держится на идентичности резидента: `CachedSessionStorage.load_session` (`cached.py:76`) отдаёт ТОТ ЖЕ
объект на cache-hit. Конверсия `to_domain` на каждый `load` дала бы два разных `domain.Session` за turn
→ split-brain. Поэтому кэш ре-типизируется на `domain.Session`: `to_domain` только на cache-miss,
`to_protocol` только на `save`. `JsonFileStorage` собственного кэша не имеет → доменный кэш поглощает
роль `CachedSessionStorage` без double-caching.

**Тезис 2 — switch резидента атомарен, готовится аддитивным facade-pre-step (branch-by-abstraction).**
Источник истины — сингулярный инвариант; два мутабельных резидента = баг корректности, поэтому
атомарность вынуждена, не выбрана. Из ~40 write-сайтов большинство — pass-through; реально режут поля
~6-10 фасадов/примитивов (`tool_call_handler`, `prompt/tool_calls`, `StateManager`,
`permission_manager`). Разрозненные прямые писатели (`config_values` из slash/декораторов/`gatherer`,
`available_commands` из `mcp_session_manager`) — вне фасадов.

**Тезис 3 — асимметрия порта (CQRS-lite).** `load`/`save` доменные (write-model), `list` — облегчённая
wire-проекция (read-model: title/updated_at/cwd), явно, не притворяясь доменной. Домен не импортирует
`protocol`; `SessionMapper` остаётся единственным швом на границе.

**Порядок реализации:**
1. **Pre-step (аддитивный, безопасный):** загнать разрозненных прямых писателей `SessionState` в
   фасады (принимающие `SessionState`). Поведение не меняется; после — все мутации через ~6 фасадов.
2. **Каркас:** `SessionRepository` (доменный порт: `load/save -> Session`, `list -> wire-проекция`),
   владеет доменным LRU-кэшем, делегирует диск в `SessionStorage`-backend (wire), `to_domain`/
   `to_protocol` — только тут.
3. **Атомарный switch (один гейтнутый коммит):** entry-points → репозиторий; сигнатуры ~6 фасадов/
   примитивов → `domain.Session`. Гейт: golden-wire + round-trip + live-smoke + `make check`.
4. `SessionState` остаётся только внутри репозитория (DTO). `tool_call_counter`-атомарность —
   бесплатно (домен единственный носитель).

**Новая абстракция обоснована** (CLAUDE.md: исключение): `SessionRepository` — недостающий доменный
шов, не дубль (`SessionStorage` типизирован wire-DTO, остаётся as-is под портом). Имя честное
(repository, не «менеджер»).

### Аудит call-сайтов switch'а + ревизия тезиса 1 (2026-07-27)

**Масштаб.** 31 прикладной call-сайт хранилища (18 load/save, 7 list; `delete_session`/
`session_exists` в прикладном коде не вызываются вовсе); ~202 сигнатуры/поля типа `SessionState`;
4 точки композиции, 1 DI-context-ключ (`di/__init__.py:101`), 13 полей-держателей + ~7
функциональных параметров. Центральный узел — `pipeline/context.py:20` (`session: SessionState`):
смена типа там каскадом задевает ~26 сайтов в stages.

**Находка A — прод работает БЕЗ кэша (опровергает посылку тезиса 1).** Установленный скрипт один:
`codelab = codelab.cli:main`; он (`cli.py:394`) собирает `JsonFileStorage` **без обёртки**.
`CachedSessionStorage` создаётся только в `server/cli.py:282`, а этот вход не зарегистрирован как
скрипт и не имеет вызывающих ни в `src`, ни в тестах. Значит сегодня каждый `load_session` отдаёт
свежий объект с диска, а `domain_session` пересобирается на turn и выбрасывается — **резидентной
идентичности в проде нет**. Тезис 1 был выведен из стека `server/cli.py`, а не из прод-стека.

**Находка B — кэш сделал бы switch не behavior-neutral.** `handlers/session.py:227` (`session/load`)
вызывает `_cleanup_session_state()`, пишет `session.cwd` и `session.mcp_servers` и **никогда не
сохраняет**. Сегодня эти мутации испаряются при следующей загрузке; с резидентным кэшем они остались
бы в памяти и были бы записаны первым же посторонним `save`. Это незаявленное изменение поведения,
«случайно чинящее» намерение из комментария — хуже осознанного решения.

**Находка C — 6 сайтов используют `list_sessions` как lookup по вторичному ключу + мутацию:**
`permissions.py:34/237/259/282`, `client_rpc_response.py:38`, `core.py:300`. Это несовместимо с
read-model-семантикой (тезис 3): найденный объект мутируется и сохраняется. Им нужны доменные
finder'ы на репозитории (`find_by_permission_request_id`, `find_by_pending_client_request_id`,
скан активных turn'ов), иначе после поиска потребуется повторный `load_session` — лишний round-trip
и окно гонки.

**Ревизия тезиса 1 (одобрено владельцем).** Кэш из порта убран; `SessionRepository` — чистая граница
wire↔domain. Switch расщеплён:
- **D4-d1 — смена типа, без кэша.** Жизненный цикл объектов ровно как сегодня → behavior-neutral
  по построению. Включает доменные finder'ы для 6 сайтов из находки C.
- **D4-d2 — резидентный кэш.** Отдельно и осознанно, после ревизии сайтов «мутирует-без-save».

**Behavior-neutrality требует sync-back метки.** Backend штампует `updated_at` in-place на объекте
вызывающего, поэтому тот видит свежую метку сразу после `save` (она уходит в session_info-нотификации).
Порт пересобирает wire-DTO, поэтому обязан вернуть штамп в доменный объект — иначе поведение
изменится. Зафиксировано тестом.

**Прочие наблюдения аудита (для D4-d1):**
- `background_executor.py:146-190` держит ОБА представления сразу (`session` + `domain_session`) —
  switch схлопывает этот шов;
- `commands/session_cancel.py:95` и `:108` — два последовательных `save` в одном пути;
- `mcp_session_manager` (`mcp_prompt_handlers`, `exclude=True`), `prompt/tool_calls`, `replay_manager`
  (сырые wire-события), `session_factory`, весь `storage/*` — остаются на `SessionState`;
- `prompt_orchestrator.handle_prompt` принимает `storage`, но в теле не использует — мёртвый
  параметр, удалить, а не переносить;
- `describe_storage`/`parse_storage_arg` (`server/cli.py:32/69/76`) работают на уровне backend —
  должны остаться на backend, не на репозитории.

### Шаг 1 D4-d1 подтверждён живьём (2026-07-27)

Три tombstone-транзакции переведены на `SessionRepository.iter_sessions`
(`consume_cancelled_permission_response`, `consume_cancelled_client_rpc_response`,
`find_session_with_cancelled_permission`). Живая проверка на сессии
`sess_15f471dd19d9`, снята наблюдателем за файлом сессии (опрос 10 мс):

```
12:09:37.771  turn=awaiting_permission, permission_request_id=5cfaaa4c, tombstones=[]
12:09:39.911  session_cancel_handled
      .911892 tombstones_perm: ["5cfaaa4c"]   ← отмена записала (seam cancel_permission_request)
      .919604 tombstones_perm: []             ← поглощено через доменный порт
```

Разрыв 8 мс — round-trip ответа клиента: при отмене turn'а клиент сам шлёт
`session/request_permission_response` с cancelled-outcome
(`client/application/permission_handler.py:119-131`,`resolve_with_cancellation`).
Ответ прошёл цепочку `response_router → consume_cancelled_permission_response →
iter_sessions → uncancel_permission_request → repository.save_session`.

**Доказательство штатности:** непоглощённый ответ дал бы warning
`permission_response_for_unknown_request` и ошибку `-32603`; в логе прогона
**0 warning и 0 ошибок**. Удалить tombstone способен только
`uncancel_permission_request`, а его вызывают ровно два переключённых пути.

**Методическая заметка.** Ранее пустые `cancelled_permission_requests` в дампах
принимались за «tombstone не пишется» — на деле это выборка файла уже ПОСЛЕ
поглощения. Окно жизни tombstone'а — единицы миллисекунд, поэтому наблюдение по
конечному состоянию файла вводит в заблуждение; нужен покадровый снимок. Заведённая
по ошибочному анализу запись tech-debt P2-35 отозвана, дефекта нет.

Регрессионное покрытие: `test_handle_cancel_writes_permission_tombstone`
(запись tombstone при отмене) и `TestCancelThenLateResponse` (полный цикл
отмена → поздний ответ → поглощение).

### Фасадный разбор и декомпозиция остатка D4-d1 (аудит 2026-07-27, только чтение)

Разбор трёх осей: карта «фасад → транзакции», выполнимость доменной типизации по
каждому фасаду, постоянная wire-граница и каскад pipeline.

**Находка 1 — prompt-turn и resume неразделимы.** `LLMLoopStage` имеет второй вход
`execute_pending_tool` (`background_executor.py:179` → `prompt_orchestrator.py:432`),
поэтому весь `pipeline/stages/agent_loop/**` и всё, что он дёргает (`StateManager`,
`ToolCallHandler`, `PermissionManager`, `ReplayManager`(write), `tool_policy`,
`PlanBuilder`), обслуживает обе транзакции. Это ОДИН шаг миграции.

**Находка 2 — домен беднее wire; это блокер, а не деталь.** До переключения нужно
закрыть:
- `ToolCallStatus` без `in_progress`/`cancelled` (`domain/value_objects.py:27-33`) —
  матрицы переходов не выражаются;
- `ToolCall` — `frozen=True` (`domain/tool_call.py:23`), а фасады делают
  `state.status = ...` in-place;
- `ToolCallRegistry.create(tool_name, arguments)` (`domain/session.py:68`) не принимает
  `title`/`kind`/`tool_call_id_from_llm`/`locations`/`raw_input`;
- нет read-seam'ов `get_config_value` / `get_permission_policy` (есть только write) —
  их отсутствие держит на wire `tool_policy.py` и `permission_manager.py`;
- `TurnState` без `session_id` — несовместим конструктор
  (`turn_lifecycle_manager.py:46-50`);
- `TurnState.pending_external_request: dict` против типизированного
  `PendingClientRequestState` — потеря статической проверки на 4 сайтах `directives.py`;
- `state_manager` пишет в историю сырые dict (`:75`, `:109`) — нужен history-seam;
- `PlanEntry` не pydantic, а `replay_manager.py:333` зовёт `model_dump()`.

**Находка 3 — `prompt/tool_calls.py` придётся расщепить.** Он режет ЧЕТЫРЕ транзакции
(prompt-turn, resume, permission-response, client-RPC response) и совмещает два разных
дела: мутацию состояния сессии и рендер ACP-нотификаций из `ToolCallState`. Второе
законно остаётся wire, первое обязано уехать в домен. Пока они в одном модуле,
независимое переключение permission-response и client-RPC невозможно.
Аналогично расщепляем `replay_manager`: write-методы обслуживают prompt-turn/resume,
read-методы (`replay_history:259`, `replay_latest_plan:310`) — session/load; наборы
не пересекаются.

**Находка 4 — значительный объём мёртвого кода** (живых вызовов нет, только тесты):
`ClientRPCHandler` целиком (`client_rpc_handler.py`, 8 методов — реальный путь идёт
через `client_rpc_response.py`); `PromptOrchestrator.handle_pending_client_rpc_response`
(`:364`) и `handle_permission_response` (`:386`); `PermissionManager.decide`/
`find_session_by_permission_request_id`/`request_tool_permission`;
`PlanBuilder.update_session_plan`/`build_plan_updates`; `ToolCallHandler.can_run_tools`/
`build_executor_execution_updates`/`build_policy_execution_updates`; 5 методов
`ReplayManager`; `prompt/tool_calls.cancel_active_tool_calls`;
`prompt/client_requests.can_run_tool_runtime`; `ValidationStage._state_manager`.

**Каскад pipeline атомарен.** `context.session` (`pipeline/context.py:20`) — 31 сайт в
5 из 6 stages, плюс ~35 сигнатур транзитивно в `agent_loop/**`. По одному stage
мигрировать нельзя: тип поля общий. При переключении `context.domain_session`
обязателен к УДАЛЕНИЮ — иначе два поля указывают на разные снимки и возникает
конфликт source-of-truth (сейчас `directives.py:118` и `:135` намеренно пишут в разные
объекты).

**Постоянная wire-граница** (не мигрирует никогда): `mcp_session_manager`
(`mcp_prompt_handlers`, `exclude=True`, в домен не переезжает по
`domain/session.py:208`); `replay_manager` (элементы `events_history` — готовые
ACP-нотификации); ACP-рендер из `prompt/tool_calls.py`; `session_factory`;
весь `storage/*`; `session_load_impl` (проекция сессии в нотификации).
`_cleanup_session_state` (`handlers/session.py:43`) — напротив, может переехать.

**Декомпозиция остатка (порядок вынужденный):**
- **Фаза A — сжать поверхность.** Удалить мёртвый код (находка 4). Независимо,
  уменьшает объём всего дальнейшего; снимает `ClientRPCHandler` из карты миграции.
- **Фаза B — обогатить домен.** Закрыть пробелы находки 2. Аддитивно, поведение не
  меняется. Порядок: read-seam'ы → tool-call группа → `TurnState` → history-seam →
  Plan↔ACP.
- **Фаза C — расщепить двуликие фасады** (находка 3): `prompt/tool_calls.py`,
  `replay_manager`.
- **Фаза D — переключить транзакции** по возрастанию связности: session/new+list+config
  → session/load → cancel (2 точки сцепления: `TurnLifecycleManager` и
  `ToolCallHandler.cancel_active_tools`) → permission-response + client-RPC response
  (возможно только после C) → **prompt-turn + resume** (атомарно, самый крупный).

D невозможна без B; независимость внутри D — без C.

### Фаза A выполнена — мёртвый код удалён (2026-07-27)

Удалено по находке 4: `ClientRPCHandler` целиком (модуль, DI-провайдер, проводка в
`orchestrator_builder`, параметр конструктора `PromptOrchestrator`),
`PromptOrchestrator.handle_pending_client_rpc_response` и `handle_permission_response`,
`PermissionManager.decide`/`find_session_by_permission_request_id`/
`request_tool_permission`, `PlanBuilder.update_session_plan`/`build_plan_updates`,
`ToolCallHandler.can_run_tools`/`build_executor_execution_updates`/
`build_policy_execution_updates`, 5 сеттеров `ReplayManager`
(`save_user_message_chunk`, `save_session_info`, `save_config_option_update`,
`save_current_mode_update`, `save_available_commands_update`),
`prompt/tool_calls.cancel_active_tool_calls`,
`prompt/client_requests.can_run_tool_runtime`, `ValidationStage._state_manager`
вместе с параметром конструктора. Итог: −2744 строки.

**Уточнения к аудиту, найденные при удалении:**
- мёртв *метод* `PermissionManager.find_session_by_permission_request_id`;
  одноимённая модульная функция в `handlers/permissions.py` — живая
  (`response_router:191`, `commands/permission_response.py:77`);
- `PermissionDecision` в `permission_manager.py` — дубль алиаса из `tool_policy.py`,
  после снятия `decide` не используется, удалён;
- каскад в `PlanBuilder`: `build_plan_updates` был единственным вызывающим
  `should_publish_plan` и `extract_plan_from_directives`, поэтому сняты все четыре.
  Живая поверхность класса — `validate_plan_entries` и `build_plan_notification`.

**Гарантия P2-26 перенесена на живой путь.** Тест
`test_stored_plan_matches_wire_notification` проверял тождество `latest_plan` и
wire-entries через удалённый `update_session_plan` — то есть через метод, которого в
проде не было. Перенесён на `DirectivesStage`
(`tests/server/pipeline/test_directives_stage.py`), где `latest_plan` пишется на самом
деле (`directives.py:118`). Покрытие не ослаблено, а привязано к реальному писателю.

Тесты живого `ReplayManager.replay_history` сеяли историю удалёнными сеттерами;
переведены на локальные хелперы, пишущие `events_history` в той же форме, что
прод-путь (тогда — `StateManager.add_event` из `PromptOrchestrator`; в фазе C сведено
к `EventHistoryWriter`).

Внешние контракты не затронуты: ACP wire, CLI, форматы сессий без изменений.
Изменены внутренние сигнатуры `PromptOrchestrator.__init__` (убран
`client_rpc_handler`) и `ValidationStage.__init__` (убран `state_manager`).

`make check` зелёный: ruff, ty, import-linter (4 контракта), 7316 passed.

Не тронуто намеренно: `PlanBuilder.normalize_plan_entries` (вызывающих в `src` нет, но
это не пункт находки 4 — дубль модульной функции из `prompt/normalization.py`, решать
при расщеплении фасадов в фазе C) и мёртвый параметр `storage` в
`PromptOrchestrator.handle_prompt` (смена живой сигнатуры, место — фаза D).

**Живая валидация фазы A.** Пострефакторный сервер (pid 49779) отработал prompt-turn,
permission-цикл (26 запросов, 24 `resume_after_permission`), `session/cancel`,
`session/new` и `session/load` крупной сессии — 278 КБ, 102 события `events_history`,
46 tool call'ов, `latest_plan` из 8 пунктов. Это покрывает живые аналоги удалённого:
`ToolCallHandler.cancel_active_tools`, `PermissionManager.build_permission_acceptance_updates`,
`ReplayManager.replay_history`/`replay_latest_plan`, `_cleanup_session_state`,
`ValidationStage` без параметра. Ноль warning'ов и ошибок на этих путях; единственная
ошибка в прогоне — `terminal_alias_not_found` (модель выдумала алиас терминала,
registry отказал корректно), к затронутому коду отношения не имеет.

**Пробел наблюдаемости `session/load` закрыт.** Успешный `session/load` не логировал
ничего: на всём пути единственным логом был `warning` про orphaned permission request
(`commands/session_load.py:94`), а факт загрузки восстанавливался лишь косвенно, по
`subscribed_to_notification_bus` из `stdio_runner._update_stdio_subscription`
(клиентский `session_history_loaded` в файл не попадает — TUI-процесс файловое
логирование не настраивает). Добавлены две точки в `handlers/session.session_load`:

- `session_loaded` (info) — состав реплея: `notifications_total`,
  `history_notifications`, `plan_replayed`, `tool_call_fallback_used`,
  `events_history`, `tool_calls`;
- `session_load_not_found` (warning) — ранее `-32001` возвращался молча.

Счётчики выбраны так, чтобы служить критерием поведенческой нейтральности при
переключении `session/load` на `SessionRepository` в фазе D: состав реплея до и после
switch'а должен совпадать. Покрыто тестами через `structlog.testing.capture_logs`
(`tests/server/protocol/handlers/test_session_coverage.py`).

### Фаза B — статус (2026-07-28)

Порядок из декомпозиции соблюдён; все пять шагов закрыты. Остаётся блокер фазы D
(обогащение `MessageContent`, ниже) — он найден по ходу и в исходный список не входил.

| шаг | коммит | содержание |
|---|---|---|
| read-seam'ы | `2216bede` | `get_config_value` / `get_permission_policy` — парные на wire и в домене; переведены `tool_policy`, `PermissionManager._resolve_policy`, `permissions.resolve_remembered_permission_decision` |
| tool-call группа | `4ef604e2` | `ToolCallStatus` приведён к ACP (`in_progress`/`cancelled`, снят артефакт `RUNNING`); `ToolCall` размутабелен как entity; `ToolCallRegistry.create` принимает поверхность turn-пути, `update` мутирует на месте |
| `TurnState` | `6d6ee4de` | обязательный `session_id`; `pending_external_request` → типизированный `PendingExternalRequest` |
| history-seam | `d4405121` | парные `add_user_message` / `add_assistant_message`; разбор блоков сведён в `MessageContent.from_acp_blocks`; снят no-op `_sanitize_history_entry` |

| Plan↔ACP | — | `PlanMapper` — единственный шов плана; путь реплея пропускает доменные записи; `AgentPlan.update_step` типизирован |

**Шаг 5 — Plan↔ACP (закрыт).** `PlanMapper.entries_to_acp` приводит к ACP-записи любую
форму плана (доменный `PlanEntry`, wire-`PlanStep`, сырой dict); на неё переведены три
места, где форма собиралась вручную: `replay_latest_plan` (звал `model_dump()` — доменная
запись роняла `to_json`), `SessionMapper.to_protocol`/`_build_plan` (inline-разбор,
дублировавший `to_acp`/`from_acp` и молча отбрасывавший не-dict записи) и
`DirectivesStage._apply_publish_plan`.

Побочно исправлено **нарушение ACP в реплее**: pre-P2-26 запись (`{description, status}`)
уходила клиенту как есть, тогда как ACP 11-Agent Plan требует
`content`/`priority`/`status` у каждой записи. Теперь такая запись нормализуется
(`description` → `content`). Тест, закреплявший старую форму, обновлён — это изменение
wire-вывода на пути `session/load` для сессий с legacy-планом.

Молчаливые отказы вокруг плана сняты: `AgentPlan.update_step` принимает `PlanStatus`
(строка позволяла откатить статус к прежнему, то есть write-операция могла не сделать
ничего) и бросает `IndexError` вне границ плана; коэрция невалидных значений в
`PlanMapper.from_acp` и `entries_to_acp` логируется
(`plan_entry_priority_coerced` / `plan_entry_status_coerced` / `plan_entry_dropped_unknown_type`).
Коэрция сохранена намеренно: загрузка старой сессии не должна падать.

**Наблюдения по живому пути плана (прогон 2026-07-28, `sess_deed831f19f1`).** Модель дважды
вызвала `update_plan`; `latest_plan` на диске совпал с последним wire-событием по составу и
статусам (9 пунктов), то есть семантика P2-26 держится. Но форма расходится, и источник
один — `PlanToolExecutor`, стоящий в стороне от шва:

- **Лишний ключ `description: ""` в wire.** `plan_executor.py:181-190` добавляет четвёртое
  поле, которого нет ни в ACP 11-Agent Plan, ни в схеме самого инструмента
  (`definitions/plan.py`: `required: [content, priority, status]`). Оно уходит в нотификацию
  и в `events_history`, а `latest_plan` пишется через `PlanMapper` и получает три поля.
  Значит до перезагрузки клиент видит 4-ключевые записи, после — 3-ключевые: байт-идентичность
  «`latest_plan` = ушедшее в wire» из P2-26 на этом писателе не выполняется, а `description` —
  ровно тот legacy-артефакт, который P2-26 убирал.
- **`cancelled` как допустимый статус шага.** `plan_executor.py:21` разрешает
  `{pending, in_progress, completed, cancelled}`; `cancelled` нет ни в ACP, ни в доменном
  `PlanStatus`, ни в наборе `PlanBuilder.validate_plan_entries`. Такой статус пройдёт
  валидацию, уйдёт в wire невалидным и будет молча приведён к `pending` при загрузке —
  статус шага перевернётся. В прогоне не выстрелило только потому, что модель его не
  прислала; после шага 5 коэрция хотя бы логируется, но источник здесь.
- **Два писателя плана с разной формой.** `update_plan` (минуя
  `PlanBuilder.validate_plan_entries`, с `description`) и `loop.py:453` (`response.plan`
  через валидатор, три поля) формируют одно и то же ACP-событие по-разному и с разными
  наборами допустимых статусов.
- **`replay_latest_plan` вызывается безусловно**, хотя комментарий в `handlers/session.py:267`
  обещает «если не был в `events_history`». На загрузке этой сессии клиент получил три
  plan-обновления (два исторических + `latest_plan`). Итог верен — ACP требует полной
  замены плана каждым обновлением, — но два обновления лишние.

Правка `plan_executor` — продолжение того же шага (свести к `PlanMapper` и к единому набору
статусов, убрать `description`), но это смена wire-вывода живого пути, поэтому отдельным
изменением.

**Наблюдение (вне шага).** `agent/core/plan_extractor.py:25` — третий `PlanEntry`
(dataclass с `Literal`-полями и `to_dict`), дубль доменного. Его результат в
`llm_adapter.py:203/205/275/277` не используется вовсе («для будущих стратегий»):
план извлекается и выбрасывается. Кандидат либо на удаление, либо на сведение к
доменному типу — решать при расщеплении фасадов (фаза C).

#### Блокер фазы D закрыт: домен хранит упорядоченные блоки

`domain.MessageContent` держит текст **одной строкой**, а ресурсы и картинки —
отдельными списками. Следствия: несколько `text`-блоков склеиваются через перевод
строки, а исходный порядок блоков не восстанавливается — `HistoryMapper._build_blocks`
собирает их фиксированно (текст → ресурсы → картинки).

На живом промпте с приложенным файлом (`[resource, text]`) домен даёт `[text, resource]`:
инструкция оказывается **до** контекста, который она комментирует. Сегодня безвредно —
доменная копия dual-carry выбрасывается; в момент switch'а резидента изменится и
хранимый формат, и то, что видит модель.

Было зафиксировано `xfail(strict=True)` в `tests/server/mapping/test_history_seam_parity.py`
— он и выстрелил (XPASS) в момент обогащения, то есть закрытие подтвердил тест, а не разбор.

**Решение.** Источник истины — `MessageContent.blocks`: упорядоченный кортеж
`TextBlock | Resource | Image`. `text`/`resources`/`images` остались как проекции-свойства
(`text` — все `text`-блоки через перевод строки), поэтому все читатели этих полей не
затронуты; изменились только конструирующие сайты (`MessageContent.from_text` вместо
`MessageContent(text=...)`). Обратная сборка блоков переехала из
`HistoryMapper._build_blocks` в `MessageContent.to_acp_blocks` — рядом с `from_acp_blocks`
и `Resource.to_acp`/`Image.to_acp`, то есть форма блока целиком в домене, а роль-driven
выбор wire-слота (`text` vs `content`) остался политикой маппера.

`TextBlock` введён намеренно: без него текст — единственный вид блока, не имеющий
представления, и порядок для него невыразим. Пустые `text`-блоки по-прежнему
отбрасываются — так их отбрасывала и прежняя сборка, поэтому wire не меняется.

Гейт расширен: parity-кейсы `resource-before-text` и `image-before-text` (живой порядок),
плюс round-trip порядка и «несколько `text`-блоков не склеиваются».

#### Семья расхождений «wire ↔ история ↔ состояние»

Четыре дефекта, найденные сверкой инварианта «последний статус tool call в
`events_history` = статус в `tool_calls`» на файлах живых сессий. Ни один не ловился
тестами; в одном случае тест закреплял артефакт дефекта как ожидаемый результат.

| коммит | дефект |
|---|---|
| `6b841b46` | состояние отставало от wire: `pending → completed` молча отбрасывался матрицей переходов, так как resume-путь не проставлял `in_progress` |
| `b8054b3e` | история отставала от состояния: `session/cancel` не писал отмену в `events_history` |
| `e8cee205` | `_cleanup_session_state` помечал вызовы `cancelled` только в памяти — ни клиенту, ни в историю |
| `a7998786` | payload ACP-блока `resource` уничтожался при перезагрузке сессии (коэрция в снятую wire-модель `MessageContent`); `image` выживал случайно |

Диагностический приём: сверять расхождения по файлу сессии и проверять арифметику
реплея по счётчикам `session_loaded` (реплеируемых событий на диске + записанные на
загрузке = `history_notifications`). Отказ в переходе статуса теперь логируется
(`tool_call_status_transition_rejected`) — молчаливый пропуск и позволил первому дефекту
дожить незамеченным.

#### Прочие наблюдения (вне фазы B)

- **`session/load` грузит сессию дважды.** `SessionLoadCommandHandler` берёт свою копию
  (правит `runtime_capabilities`, сбрасывает orphaned `active_turn`, сохраняет), а
  `handlers.session.session_load` — другую, свежую с диска. Поэтому orphan-ветка
  сохраняет `active_turn: None`, но статус вызова на диске остаётся `pending`. Шов
  схлопнется сам при переходе на `SessionRepository`.

  **Подтверждено живьём (2026-07-28, `sess_deed831f19f1`)** — и это не «мутации
  испаряются» (Находка B), а расхождение wire↔диск. `call_046` (`terminal/create`,
  оставшийся в permission-паузе) на загрузке помечен `cancelled`, отмена записана в
  историю копией `session_load` (`events_history=117` в логе против 115 на диске), клиент
  получил `cancelled` в реплее. Но `session_load` не сохраняет, а `updated_at` файла
  (15:22:47.882) позже лога `session_loaded` (15:22:47.855) — на диск легла копия
  команд-хендлера: `active_turn: null`, `call_046: pending`, 115 событий. Следующая
  загрузка снова покажет `pending` и снова его отменит; инвариант «последний статус в
  `events_history` = статус в `tool_calls`» при этом на диске цел (0 расхождений на 46
  вызовах), потому что разошлись не история и состояние, а диск и то, что увидел клиент.
  Это отдельный критерий поведенческой нейтральности для переключения `session/load`:
  после switch'а состав реплея должен совпасть, а `call_046`-подобный вызов — остаться
  `cancelled` и на диске.
- **Ожидаемая отмена RPC логируется как error.** `session/cancel` отменяет клиентский
  `terminal/wait_for_exit`, и `client_rpc_bridge.py:294-296` пишет
  `logger.error("Ошибка при ожидании завершения терминала")`: `ClientRPCError` про отмену
  попадает в ту же ветку, что таймауты и реальные сбои. На прогоне 2026-07-28 это
  единственный error за сеанс — и ложный, из-за чего «0 ошибок» перестаёт работать как
  критерий чистоты прогона. Заодно модель получает результат инструмента с признаком
  ошибки там, где был штатный cancel. Отмену нужно отделить от сбоя (уровень info/debug
  и отдельный признак в результате).
- ~~**`_REPLAYABLE_UPDATE_TYPES` содержит мёртвый `session_info`.**~~ Закрыто при
  расщеплении `replay_manager` (см. ниже): мёртвое значение снято, `session_info_update`
  реплеить не стали.
- **Клиент молча создаёт новую сессию** после `session_load_not_found`, ничего не сообщая
  пользователю (`session_controller._load_history` пишет только `warning` в свой логгер,
  а TUI-процесс файловое логирование не настраивает).

### Фаза C, шаг 1 — `replay_manager` расщеплён (2026-07-29)

`ReplayManager` совмещал два набора методов, у которых не пересекались вызывающие:
писатели обслуживали prompt-turn и resume, читатели — только `session/load`. Разделён
по этому шву:

- **`EventHistoryWriter`** (`event_history_writer.py`) — владеет ФОРМОЙ события истории
  (`{"type": "session_update", "update": …, "timestamp": …}`): `save_agent_message_chunk`,
  `save_tool_call`, `save_tool_call_update`, `save_plan`.
- **`SessionReplayer`** (`session_replayer.py`) — `replay_history`, `replay_latest_plan`
  и набор `_REPLAYABLE_UPDATE_TYPES`.

Обе половины остаются на постоянной wire-границе: элементы `events_history` — готовые
ACP-нотификации. Имена честные (писатель и реплеер), а не «менеджер» над двумя делами.
Поведение не менялось; `make check` — 7365 passed.

**Решение по `session_info` — из спецификации, а не по вкусу.** Мёртвое значение
`session_info` из набора снято (писателя нет со времён фазы A). `session_info_update`
реплеить не стали, и основание такое:

- `03-Session Setup.md:132` обязывает реплеить **conversation** («MUST replay the entire
  conversation… in the form of `session/update` notifications»), и примеры там —
  `user_message_chunk` / `agent_message_chunk`. Обязательство привязано к беседе, а не ко
  всем когда-либо отправленным `session/update`.
- `04-Session List.md:166,186` описывает `session_info_update` как канал метаданных сессии
  с инкрементальной семантикой: «Only include fields that have changed — omitted fields
  are left unchanged». Это поток патчей текущего состояния, а не элемент беседы, поэтому
  реплей истории патчей прогонял бы клиента по промежуточным состояниям, которых уже нет.
- Актуальность метаданных обеспечена: `session/load` в конце реплея сам эмитит свежий
  `session_info_update`, то есть канал используется по назначению.

Следствие для наблюдаемости: постоянная разница `events_history` − `history_notifications`
в логе `session_loaded` (по 3 события на прогонах 2026-07-28 и 2026-07-29) — ожидаемое
поведение. Счётчик по-прежнему годен как критерий нейтральности фазы D, но сверять надо
разницу, а не равенство.

**Ещё один тест, закреплявший артефакт.** Хелпер `_seed_session_info` в тестах реплея сеял
`sessionUpdate: "session_info"` с комментарием «так же, как прод-путь», хотя такого
писателя нет со времён фазы A. Заменён на `_seed_session_info_update` (прод-форма), и
теперь тесты проверяют, что она НЕ реплеится.

### Фаза C, шаг 2 — единственный писатель `events_history` (2026-07-29)

Второй писатель истории убран: `StateManager.add_event` принимал уже собранный сырой
dict, и `prompt_orchestrator` строил форму события сам — `user_message_chunk` на каждый
блок промпта (`:195`) и `session_info_update` (`:250`). Пока так, «владелец формы события»
владел ею лишь наполовину.

Оба сайта переведены на `EventHistoryWriter.save_user_message_chunk` /
`save_session_info_update`, после чего `add_event` не имел вызывающих и удалён вместе с
тестами на его ветки. Форма записи байт-идентична (`add_event` собирал тот же
`{"type": "session_update", "update": …, "timestamp": …}`), поведение не менялось.

Побочный эффект для тестов: раньше тесты реплея и e2e сеяли `user_message_chunk`
руками через `add_event` — «как прод-путь», но мимо писателя. Теперь они сеют историю
тем же писателем, что и прод (12 сайтов в 5 файлах). Это ровно тот класс проверок, что
уже дважды подводил в этой ветке: тест воспроизводил форму вручную и переставал зависеть
от кода, который проверяет.

**Наблюдение, поднятое спецификацией (осталось открытым).** Раз `session_info_update` не
реплеится и больше никем не читается, его хранение в `events_history` (3 записи на сессию)
— мёртвый вес. Спецификация про наше хранилище ничего не требует; решать отдельно, потому
что это смена содержимого файла сессии.

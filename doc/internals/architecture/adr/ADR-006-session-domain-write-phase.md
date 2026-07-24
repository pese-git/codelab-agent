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

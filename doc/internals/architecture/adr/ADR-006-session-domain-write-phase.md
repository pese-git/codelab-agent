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

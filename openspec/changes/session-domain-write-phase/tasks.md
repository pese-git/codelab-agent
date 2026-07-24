# Write-фаза доменной миграции сессии — Задачи

> Эпик = Workstream D плана ADR-005. Гейты (ADR-006): fake driver, смена формата с миграцией,
> golden wire-тесты. Каждый шаг — за `make check` + `import-linter`.

## Фаза D0: Предпосылки (страховка до рефактора)

- [x] D0.1 Golden-харнесс `session/update` wire — `tests/server/protocol/test_session_update_wire_golden.py` (agent_message_chunk, plan, tool_call, tool_call_update; полная + минимальная формы, 6 тестов)
- [x] D0.2 Round-trip baseline `SessionMapper` — `tests/server/mapping/test_session_mapper_roundtrip_baseline.py`; зафиксированы потери (роль `tool`→`assistant`, `tool_call_id` истории) как `BASELINE LOSS` — цель флипа в D1
- [x] D0.3 Замороженная фикстура формата v6 (`tests/server/storage/fixtures/session_v6.json`) + baseline-тест чтения/маппинга — гарантирует обратную совместимость чтения при миграции D2

## Фаза D1: `SessionMapper` без потерь

- [x] D1.1 Устранена асимметрия роли `tool`: `HistoryMessage.role` += `"tool"`; `SessionMapper.to_protocol`/`_build_history` сохраняют роль и `tool_call_id` (флип `BASELINE LOSS` D0.2 → passed)
- [x] D1.2 Round-trip без потерь: plan, tool_calls (registry), permissions, multi-agent — проверено. **Multimodal (images/resources) истории — xfail-гэп, вынесен в D2** (фикс меняет форму сериализации content: строка→блоки — это формат/миграция)
- [x] D1.3 D0.1 golden + D0.2 round-trip зелёные (8 passed, 1 xfail multimodal→D2)

> **Переупорядочено (2026-07-23, см. finding в ADR-006):** тип `storage`/`tools`
> следует за рабочей моделью, а не ведёт её (81 сайт держит `SessionState` как рабочую
> модель: load→mutate→save). Поэтому **D4 (рабочая модель → `domain.Session`) идёт
> ПЕРЕД D2/D3** — иначе storage-on-domain создаёт throwaway-конверсии на 81 сайте.
> Порядок выполнения: **D0 → D1 → D4 → D2 → D3 → D5**.

## Фаза D4: Рабочая модель → `domain.Session` (СТРАТЕГИЯ — strangler)

> Threaded-объект сессии нельзя мигрировать «наполовину». Подход: strangler —
> под-стейты `SessionState` по одному переводятся на domain-backed представление
> (поле хранит доменный VO, сериализация сохранена), пока `SessionState` не станет
> тонкой обёрткой над `domain.Session`; затем threaded-объект = `domain.Session`,
> `SessionState` — только на границе wire/storage. Каждая стадия — за golden-wire (D0.1)
> + round-trip (D0.2) + полный `make check`. Стадии по возрастанию связности.

- [x] D4.1 Карта мутаций/чтений по под-стейтам — `d4.1-mutation-map.md`; самые изолированные: `plan`/`multi_agent` (0 рантайм-сайтов), затем `terminals`. Классификация полей финализирована в design.md
- [x] D4-a (scaffold) Доменные VO `TurnState`/`SessionRuntime` + `SessionMapper` round-trip без потерь turn/runtime; `PromptContext.domain_session` строится через `to_domain` (аддитивно, source-of-truth пока `SessionState`). Гейт зелёный
- [x] D4.2 Стадия b1 (`plan`): записи `latest_plan` маршрутизированы через доменный агрегат
      (`domain_session.plan`) + dual-carry. `SessionUpdateSink` несёт `domain_session` пер-turn (проброс
      через `AgentLoop.run`/`resume_after_permission`); `emit_and_save_plan` — единый писатель для
      loop/tool_processor (latest_plan **деривируется из домена**, вход валидирован → байт-в-байт), убраны
      2 инлайн-записи. `directives` (вход невалидирован): latest_plan пишется точь-в-точь, домен
      **синхронизируется** из тех же entries. Resume-путь (`execute_pending_tool` через `background_executor`)
      — на fallback (legacy-запись; домен туда не тредится до D4-d). Находка: `PlanBuilder.build_plan_updates`/
      `update_session_plan` — мёртвый код (нет прод-вызовов). Гейт: golden-wire байт-в-байт + round-trip + make check
- [x] D4-b/b3a (prep) Доменный дом полей tool_call (`ToolCall`+kind/title/llm_id; `ToolResult`+content/
      result_content) + lossless `ToolCallMapper`; `SessionMapper` делегирует ему (round-trip tool_calls без
      потерь, дубль inline-билдеров снят). Валидирован на проде (E-resume, 33×).
- [x] D4-b E-resume `domain_session` на permission-resume пути (`background_executor` строит `to_domain`,
      пробрасывает до `resume_after_permission`). Нужен и для D4-d.

> **Ре-секвенирование (пивот, 2026-07-24, см. ADR-006):** дальнейшие per-sub-state write-flip'ы
> **сняты** (упираются в «`domain_session` не на всех путях» + общий counter + multimodal). Остаток:
> **prep (lossless round-trip) → D2 → D4-d (один флип threaded-объекта)**. b3b (tool_calls write-flip)
> заменён флипом на границе в D4-d.

- [ ] D4-prep Сквозной round-trip тест `domain.Session ↔ SessionState` без потерь для ВСЕХ полей
      (turn/runtime/tool_calls/plan/permissions/multi_agent/config; history multimodal — xfail до D2).
      Опц.: дедуп оставшихся inline-мапперов (`_build_plan` → `PlanMapper`).
- [ ] D4.4 (D4-d) Threaded `context.session` = `domain.Session`; `SessionState` строится только на границе
      wire/storage через lossless `SessionMapper`. ОДИН флип, риск сконцентрирован (после D2).
- [ ] D4.5 Golden wire (D0.1) байт-в-байт на флипе D4-d + live-smoke полного turn'а

## Фаза D2: Хранение на `domain.Session` + миграция формата (после D4-prep, ПЕРЕД D4-d — пивот)

- [ ] D2.1 `SessionStorage` (ABC + реализации) работает с `domain.Session`
- [ ] D2.2 Versioned schema хранения; upgrade старого `SessionState`-JSON на чтении через `SessionMapper`
- [ ] D2.3 Миграция существующих сессий читается без потерь (тест D0.3); запись — новый формат
- [ ] D2.4 Мультимодальный контент истории (images/resources) round-trip без потерь — форма сериализации content (блоки); снять xfail `test_multimodal_history_preserved` (перенос из D1)
- [ ] D2.5 Снять `ignore_imports` `storage.base -> protocol.state`

## Фаза D3: `ToolContext` для executor'ов (после D4)

- [ ] D3.1 Доменный `ToolContext` (проекция агрегата: cwd, permission, active_turn, client-RPC)
- [ ] D3.2 `ToolExecutorProtocol.execute(ToolContext)`; перевести executor'ы (fs/terminal/plan/mcp)
- [ ] D3.3 `file_cache_decorator` на `ToolContext` → снять `ignore_imports`
      `file_cache_decorator -> protocol.state` и `tools.executors.decorators.base -> protocol.state`

## Фаза D5: Capabilities + закрытие долга

- [ ] D5.1 Унифицировать `ClientRuntimeCapabilities` ↔ `shared.ClientCapabilities` (P2-32)
- [ ] D5.2 `ignore_imports` пуст для `agent`/`storage`/`tools` в контракте «Server layers»
- [ ] D5.3 **ADR-003 закрыт целиком**; `Server layers` зелёный без исключений

## Документация

- [ ] D.1 Обновить ADR-003 (закрыт), ADR-006 (статус), ADR-005 (разблокировано C/B)
- [ ] D.2 `tech-debt.md`: закрыть остаток ADR-003, P2-32
- [ ] D.3 Обновить `ARCHITECTURE.md` (домен как рабочая модель); синхронизировать Mermaid
      (целевой референс готов — `doc/internals/architecture/server-target-state.md`)
- [ ] D.4 Документировать формат хранения + миграцию

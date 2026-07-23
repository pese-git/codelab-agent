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

- [ ] D4.1 Выбрать самый изолированный под-стейт — карта мутаций/чтений
- [ ] D4.2 Стадия 1: выбранный под-стейт → доменные операции агрегата; golden-wire/round-trip зелёные
- [ ] D4.3 Стадии по возрастанию связности (напр. `plan` → `tool_calls` → `history` → `active_turn`)
- [ ] D4.4 Threaded `context.session` = `domain.Session`; `SessionState` строится только на границе wire/storage
- [ ] D4.5 Golden wire (D0.1) байт-в-байт на КАЖДОЙ стадии

## Фаза D2: Хранение на `domain.Session` + миграция формата (после D4)

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
- [ ] D.4 Документировать формат хранения + миграцию

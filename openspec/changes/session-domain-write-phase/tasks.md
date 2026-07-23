# Write-фаза доменной миграции сессии — Задачи

> Эпик = Workstream D плана ADR-005. Гейты (ADR-006): fake driver, смена формата с миграцией,
> golden wire-тесты. Каждый шаг — за `make check` + `import-linter`.

## Фаза D0: Предпосылки (страховка до рефактора)

- [ ] D0.1 Golden-харнесс `session/update` wire: снять байт-фикстуры по каждому типу
      (`agent_message_chunk`, `plan`, `tool_call`, `tool_call_update`) — гейт байт-идентичности
- [ ] D0.2 Property-тест round-trip `SessionMapper` (domain → protocol → domain) на репрезентативных
      сессиях (история с tool_calls, plan, multimodal) — фиксирует текущие потери как baseline
- [ ] D0.3 Тест-фикстуры реальных старых сессий (`~/.codelab/.../sessions` формат) для миграции

## Фаза D1: `SessionMapper` без потерь

- [ ] D1.1 Устранить асимметрию роли `tool` (`to_protocol`: `TOOL → assistant`) — сохранять роль/tool_call_id
- [ ] D1.2 Round-trip без потерь: tool_calls, plan, multimodal content, permissions, multi-agent state
- [ ] D1.3 Golden/property-тесты D0.1/D0.2 зелёные

## Фаза D2: Хранение на `domain.Session` + миграция формата

- [ ] D2.1 `SessionStorage` (ABC + реализации) работает с `domain.Session`
- [ ] D2.2 Versioned schema хранения; upgrade старого `SessionState`-JSON на чтении через `SessionMapper`
- [ ] D2.3 Миграция существующих сессий читается без потерь (тест D0.3); запись — новый формат
- [ ] D2.4 Снять `ignore_imports` `storage.base -> protocol.state`

## Фаза D3: `ToolContext` для executor'ов

- [ ] D3.1 Доменный `ToolContext` (проекция агрегата: cwd, permission, active_turn, client-RPC)
- [ ] D3.2 `ToolExecutorProtocol.execute(ToolContext)`; перевести executor'ы (fs/terminal/plan/mcp)
- [ ] D3.3 `file_cache_decorator` на `ToolContext` → снять `ignore_imports`
      `file_cache_decorator -> protocol.state` и `tools.executors.decorators.base -> protocol.state`

## Фаза D4: Turn-путь на доменном агрегате

- [ ] D4.1 Мутации по ходу turn-а (`active_turn`) → доменные операции `domain.Session`
- [ ] D4.2 `history`/`tool_calls`/`plan` мутации → операции агрегата
- [ ] D4.3 Хендлеры/pipeline оперируют `domain.Session`; `SessionState` строится только на границе wire/storage
- [ ] D4.4 Golden wire (D0.1) байт-в-байт на всех шагах

## Фаза D5: Capabilities + закрытие долга

- [ ] D5.1 Унифицировать `ClientRuntimeCapabilities` ↔ `shared.ClientCapabilities` (P2-32)
- [ ] D5.2 `ignore_imports` пуст для `agent`/`storage`/`tools` в контракте «Server layers»
- [ ] D5.3 **ADR-003 закрыт целиком**; `Server layers` зелёный без исключений

## Документация

- [ ] D.1 Обновить ADR-003 (закрыт), ADR-006 (статус), ADR-005 (разблокировано C/B)
- [ ] D.2 `tech-debt.md`: закрыть остаток ADR-003, P2-32
- [ ] D.3 Обновить `ARCHITECTURE.md` (домен как рабочая модель); синхронизировать Mermaid
- [ ] D.4 Документировать формат хранения + миграцию

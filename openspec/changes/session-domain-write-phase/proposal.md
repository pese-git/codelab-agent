# Proposal: Write-фаза доменной миграции сессии (`domain.Session` как рабочий агрегат)

## Why

ADR-005 (read-фаза) развязал ядро `agent.core.*` от `protocol` — ноль рёбер, driver-независимость
доказана. Но **корень долга ADR-003 (вариант B)** не устранён:

- Рабочая модель сервера — Pydantic `protocol.SessionState`, которую хендлеры **мутируют** по ходу
  turn-а; `domain.Session` — промежуточная, а не агрегат системы.
- **Тройное представление** `domain.Session` / `SessionState` / порты — точка рассинхрона (P2-32).
- Остаточные рёбра `→ protocol.state` (`storage.base` — рантайм-импорт; `tools.executors.decorators.base`;
  `agent.context.file_cache_decorator`) read-фазой **не снимаются** → цель ADR-003
  «`Server layers` без исключений для agent» недостижима.

Решение и гейты — **ADR-006** (вариант B, одобрен: fake driver, смена формата сессий с миграцией,
golden wire-тесты).

## What Changes

### Домен как рабочая модель

- `domain.Session` — рабочий агрегат turn-пути; мутации сессии (`active_turn`, `history`,
  `tool_calls`, `plan`) — доменные операции агрегата.
- `protocol.SessionState` низводится до **сериализационного DTO** на границе wire/storage.
- `SessionMapper` — единственная точка конвертации domain ↔ protocol; довести симметрию
  (устранить схлопывание роли `tool`, потерю полей — round-trip без потерь).

### Хранение (изменение формата — с миграцией)

- `SessionStorage` работает с `domain.Session` (не `SessionState`).
- Versioned schema хранения + миграция существующих `~/.codelab/.../sessions` (upgrade на чтении).

### Инструменты

- Доменный `ToolContext` (или проекция агрегата) с богатой поверхностью executor'ов
  (`cwd`, permission, `active_turn`, client-RPC); `ToolExecutorProtocol` ретайпится с него.
- `file_cache_decorator` теряет ребро `→ protocol.state`.

### Capabilities

- Унификация `ClientRuntimeCapabilities` ↔ `shared.ClientCapabilities` (закрывает P2-32).

### Снятие долга

- Удаляются строки `ignore_imports`: `file_cache_decorator`, `storage.base`,
  `tools.executors.decorators.base` → `protocol.state`.

## Совместимость

- **Контракт (BREAKING на хранении):** формат сериализации сессий меняется → миграция обязательна
  (backward-совместимое чтение старых сессий).
- **Wire `session/update` — байт-в-байт** (golden-гейт).
- ACP JSON-RPC, Content Types, Tool Call State — без изменений.

## Impact

- Закрывает **ADR-003 целиком**; `Server layers` зелёный без исключений для `agent`.
- Разблокирует ADR-005 Workstream **C** (прод turn-loop через `AgentRunner`) и **B**
  (доменная эмиссия `UpdateSink`).
- Специфицируемые capabilities: **session-serialization** (MODIFIED — формат + миграция).

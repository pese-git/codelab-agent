# Design: Write-фаза доменной миграции сессии

Технический дизайн эпика write-фазы (Workstream D плана ADR-005). Основание: ADR-006 (решение),
ADR-003 (вариант B), ADR-005 (read-фаза, порты).

## Принципы

1. `domain.Session` — рабочий агрегат; `SessionState` — сериализационный DTO на границе.
2. Единственная точка конвертации — `SessionMapper`; round-trip без потерь (гейт).
3. Изменение формата хранения — с миграцией (versioned schema, upgrade на чтении).
4. Wire `session/update` — байт-в-байт (golden-гейт перед любыми правками эмиссии).
5. Инкрементально, каждый шаг за `make check` + import-linter.

## Как сейчас (as-is)

```mermaid
flowchart TB
    subgraph protocol["protocol"]
        H["handlers / pipeline (мутируют SessionState по ходу turn'а)"]
        ST["SessionState (Pydantic, РАБОЧАЯ модель)"]
    end
    subgraph storage["storage"]
        STO["SessionStorage.save/load(SessionState)"]
    end
    subgraph tools["tools"]
        EX["ToolExecutorProtocol.execute(session: SessionState)"]
    end
    subgraph domain["domain"]
        DS["domain.Session (промежуточная)"]
    end
    H --> ST
    STO -. rt-импорт .-> ST
    EX -. type .-> ST
    ST <-. SessionMapper .-> DS
    classDef debt fill:#ffe0e0,stroke:#c00;
    class ST,STO,EX debt;
```

## Как будет (to-be)

```mermaid
flowchart TB
    subgraph protocol["protocol (ACP-адаптер)"]
        H["handlers (доменные операции агрегата)"]
        MAP["SessionMapper (граница: domain ↔ SessionState-DTO)"]
    end
    subgraph domain["domain (рабочая модель)"]
        DS["domain.Session (агрегат)"]
        TC["ToolContext (проекция для executor'ов)"]
    end
    subgraph storage["storage"]
        STO["SessionStorage.save/load(domain.Session) + versioned schema"]
    end
    subgraph tools["tools"]
        EX["ToolExecutorProtocol.execute(ToolContext)"]
    end
    H --> DS
    DS <-. только сериализация .-> MAP
    STO --> DS
    EX --> TC
    TC --> DS
    classDef ok fill:#e0f0ff,stroke:#06c;
    class DS,TC ok;
```

## Ключевые решения

### `SessionMapper` симметричность
Round-trip `domain.Session → SessionState → domain.Session` без потерь. Известная асимметрия —
схлопывание `MessageRole.TOOL → assistant` в `to_protocol`; довести до сохранения роли/tool_call_id.
Гейт: property-тест round-trip на репрезентативных сессиях (история с tool_calls, plan, multimodal).

### Формат хранения + миграция
`SessionStorage` сериализует `domain.Session`. Схема версионируется (`schema_version`); на чтении
старые версии (текущий `SessionState`-JSON) распознаются и апгрейдятся через `SessionMapper.to_domain`.
Существующие `~/.codelab/.../sessions` читаются без потерь; запись — в новом формате.

### `ToolContext`
Executor'ам нужна поверхность шире read-`SessionView`: `cwd`, permission-policy, `active_turn`,
client-RPC state. Вводится доменный `ToolContext` (проекция агрегата или сам агрегат), `ToolExecutorProtocol.execute`
ретайпится с него. `file_cache_decorator` использует его же → теряет `protocol.state`.

### Мутации по ходу turn-а
Хендлеры сейчас пишут в `SessionState.active_turn`/`history`/… напрямую. Переводятся на доменные
операции `domain.Session`. Это самая рискованная часть (горячий путь) — идёт по под-состояниям,
каждое за тестами поведения.

### `domain.Session` ⊊ `SessionState`: протокольный runtime-остаток
Агрегат `domain.Session` покрывает `id/config/history/tool_calls/permissions/plan/multi_agent`.
Часть полей `SessionState` — чистый **протокольный/turn-runtime** без доменного дома. Втаскивать их
в доменный агрегат **запрещено** (протокол в домен не течёт).

**Обязательное действие (D4-a):** классифицировать ВСЕ поля `SessionState` полным перечнем — не
частичным списком. Предварительная классификация:

| Класс | Поля |
|---|---|
| Доменный агрегат (уже есть дом) | `session_id`→`id`; `cwd`/`config_values`/`runtime_capabilities`→`SessionConfig`; `history`; `tool_calls`/`tool_call_counter`→`ToolCallRegistry`; `latest_plan`→`AgentPlan`; `permission_policy`/`cancelled_permission_requests`→`PermissionState`; `active_strategy`/`active_agents`/`parent_session_id`/`child_session_ids`/`is_child_session`→`MultiAgentState` |
| **Turn-runtime** (компаньон, turn-scoped) | `active_turn`, `pending_prompt_response`, `cancelled_client_rpc_requests` |
| **Session-runtime** (компаньон, session-scoped) | `terminals`/`terminal_counter`, `events_history`, `session_metrics`, `correlation_id`, `mcp_prompt_handlers` (`exclude=True`), `available_commands`, `mcp_servers` |
| storage-мета / решить отдельно | `schema_version`, `updated_at`, `title`, `task_result`, `sliced_summary` |

**Компаньон живёт в `protocol`, НЕ в `domain`** (иначе станет свалкой и/или протечёт в `agent.core`).
Инвариант: `agent.core` видит только `domain.Session` + порты; компаньон тредится хендлерами
protocol-слоя; `ToolContext` (D3) проецирует из обоих. По времени жизни — разделить на **`TurnRuntime`**
(turn-scoped, сбрасывается per turn) и **`SessionRuntime`** (session-scoped). Границы фиксируются на D4-a
(классификация) и D4-d/D3.1 (реализация).

### `ToolCallState` богаче доменного `ToolCall`
Wire-модель `ToolCallState` шире `ToolCall`; на b2/D4-c решить по каждому полю, гейт — байт-идентичность
tool_call/tool_call_update:
- **wire-only** (нет дома; остаётся полем DTO, восстанавливается маппером): `title`, `kind`,
  `tool_call_id_from_llm`, `raw_input`.
- **есть доменный дом** (`ToolCall` уже несёт): `locations`, `raw_output`, `status`, `tool_name`→,
  `tool_arguments`→`arguments`.
- **mapping-решение** (домен `ToolCall.result` vs wire `content`/`result_content`): выбрать
  представление результата в VO и правило маппинга в оба ACP-поля.

## Риски и решения

- **Горячий путь + мутации** — крупнейший риск; дробить по под-состояниям (`active_turn`, `history`,
  `tool_calls`, `plan`), byte-identity wire как страховка.
- **Миграция формата** — тесты на реальных старых сессиях; upgrade-путь обязателен.
- **`SessionMapper` на горячем пути** — стоимость конвертации; замерять, при необходимости —
  ленивые проекции.
- **Consumer-driven порты** — форму `AgentRunner`/`UpdateSink` доводит fake driver (Workstream E),
  не спекуляция.

## План работ (staged, механизм M2)

> Порядок эпика: **D0 → D1 → D4 → D2 → D3 → D5** (реордер, см. ADR-006 finding: тип
> storage/tools следует за рабочей моделью). Механизм D4 — **M2**: рабочая модель
> флипается по стадиям пайплайна (threaded `context.session` → `domain.Session`), а не
> по под-стейтам гибридного DTO (M1 отклонён). На время миграции — **транзиентный
> scaffold** (dual-carry SessionState↔domain), снимается в D4-d.

### D4 — рабочая модель → `domain.Session` (ядро)

**D4-a. Граница: конструирование `domain.Session` + классификация полей (аддитивно)**
- Классификация: полный перечень полей `SessionState` → {агрегат / TurnRuntime / SessionRuntime /
  storage-мета} (см. таблицу в «Ключевые решения»). Определяет границу компаньона до реализации.
- Работа: на входе turn-а строить `domain.Session` из `SessionState` через `SessionMapper.to_domain`;
  положить в `PromptContext` как `domain_session` (новое поле). `SessionState` — пока source-of-truth,
  сохраняется как есть. Потребителей нет.
- Гейт: аддитивно, поведение не меняется; golden-wire + round-trip + `make check`.

**D4-b. Миграция ЧТЕНИЙ по под-стейтам (изолированные первыми)**
- b1 `plan` (1 read-site) → `domain_session.plan` + `PlanMapper`.
- b2 `tool_calls` (3) → `domain_session.tool_calls`. Развилку wire-only полей `ToolCallState`
  (`title`/`kind`/`result_content`/`tool_call_id_from_llm`/`raw_input`) решить здесь (см. «Ключевые решения»).
- b3 `history` (5) → `domain_session.history`.
- b4 `active_turn` (7) → проекция turn-runtime в компаньон (см. «runtime-остаток»), не в агрегат.
- b5 `permissions` + `multi_agent` (низкая связность, но нужны для полного флипа D4-d):
  `permission_policy`/`cancelled_*` → `PermissionState`; multi-agent поля → `MultiAgentState`.
  `cancelled_client_rpc_requests` отсутствует в VO — расширить VO или оставить компаньону (решить здесь).
- Гейт каждого b: чтения дают идентичные значения; golden-wire + round-trip + `make check`.

**D4-c. Миграция ЗАПИСЕЙ (мутаций) по тем же под-стейтам**
- Мутации → доменные операции (`plan.add_step`, `tool_calls.create/update`, `history.add`, turn-переходы);
  `SessionState`-проекция пересобирается из домена на границе (пока dual-carry).
- Порядок: plan → tool_calls → history → **active_turn последним** (pause/resume, permission, client-RPC).
- Гейт: golden-wire байт-в-байт; permission-flow (pause/resume) на live-smoke; `make check`.

**D4-d. Флип source-of-truth + снятие scaffold**
- `context.session` = `domain.Session` (+ `SessionRuntime`-компаньон для протокольного остатка);
  `SessionState` строится только на границе wire/storage через `SessionMapper.to_protocol`;
  dual-carry убран; сигнатуры pipeline-стадий → `domain.Session` (+ компаньон, где нужен runtime).
- Зафиксировать границу компаньона: `terminals`/`terminal_counter`, `events_history`,
  `pending_prompt_response`, `session_metrics`, `correlation_id`, `mcp_prompt_handlers` — в компаньоне,
  не в агрегате.
- Гейт: golden-wire + round-trip; live-smoke полного turn-а (стриминг + permission + tool-calling);
  immediate-delivery сохранён; `make check`.

### D2 — storage на `domain.Session` + миграция (после D4)
- D2.1 `SessionStorage` (ABC + `JsonFile`/`InMemory`/`Cached`) на `domain.Session`.
- D2.2 versioned schema; чтение старого v6 `SessionState`-JSON → upgrade через `SessionMapper.to_domain`; запись — v7.
- D2.3 фикстура v6 (D0.3) читается без потерь; добавить v7 round-trip.
- D2.4 multimodal контент истории (блоки) — снять `xfail`.
- D2.5 снять `ignore_imports` `storage.base -> protocol.state`.

### D3 — `ToolContext` для executor'ов (после D4)
- D3.1 доменный `ToolContext` (cwd, permission, active_turn, client-RPC).
- D3.2 `ToolExecutorProtocol.execute(ToolContext)`; перевести `fs`/`terminal`/`plan`/`mcp`.
- D3.3 `file_cache_decorator` на `ToolContext` → снять оба `ignore_imports` (file_cache + decorators.base).

### D5 — capabilities + закрытие ADR-003
- D5.1 унифицировать `ClientRuntimeCapabilities` ↔ `shared.ClientCapabilities` (P2-32).
- D5.2 `ignore_imports` пуст для `agent`/`storage`/`tools`.
- D5.3 ADR-003 закрыт; обновить ADR-003/005/006, `tech-debt.md`, `ARCHITECTURE.md`.

### Разблокируется после write-фазы (ADR-005)
- **B** — доменная эмиссия `UpdateSink` (перенос 3.3/3.4), golden-wire гейт.
- **C** — прод turn-loop через `AgentRunner` (4.3), поверх доменного `active_turn`.
- **E** — fake driver как полноценный не-ACP адаптер (валидирует порты end-to-end).

### Сквозные правила
1. Гейт до коммита: golden-wire (D0.1) + round-trip (D0.2) + `make check`.
2. Атомарные коммиты по стадиям (b1, b2, …) со ссылкой на ADR-006.
3. Байт-идентичность wire — жёстко; форматы сессий — только с миграцией.
4. Транзиентный scaffold (dual-carry) помечать явно, снять в D4-d.
5. После каждого этапа — анализ `~/.codelab/logs` на регрессии живого пути.

## Вне области

- Прод turn-loop через `AgentRunner` (ADR-005 Workstream C) — после этого эпика.
- Доменная эмиссия `UpdateSink` (ADR-005 3.3/3.4, Workstream B) — после/параллельно C.
- Второй реальный драйвер (A2A) — отдельно; здесь только fake driver как потребитель.

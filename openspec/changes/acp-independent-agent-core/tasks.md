# ACP-независимое ядро агента — Задачи

## Фаза 0: Hexagon layout (реорганизация каталогов) — механическая, без логики

> Отдельный PR: только `git mv` + правка импортов, **ноль изменений поведения**.
> Границы `import-linter` (`codelab.server.{agent,protocol,domain}`) не двигаются.

- [x] 0.1 Создать `server/agent/contracts/ports.py` (пока пустой каркас портов) и `contracts/events.py` — перенести доменные события из `contracts/base.py` (`DomainEvent`, `AgentRequest`, `AgentResult`, `AgentResponse`), `base.py` → тонкий re-export
- [x] 0.2 Создать `server/agent/core/`; `git mv` ядра: `execution_engine`, `system_prompt_builder`, `history_builder`, `message_sanitizer`, `plan_extractor`, `tool_filter`, `strategies/`
- [x] 0.3 Определить судьбу `agent/base.py` по содержимому: `LLMAgent` + turn-контексты — цельный контракт агента, перенесён как `core/agent_base.py` (без дробления; `SessionState`-протечка адресуется в Фазе 1)
- [x] 0.4 `llm_adapter.py` оставить на месте (driven-адаптер, граница ADR-001); `factory.py`/`registry.py` — composition, остаются в `agent/`
- [x] 0.5 Разовое обновление импортёров (src + tests) на `core/` пути; публичный `agent/__init__.py` сохранён (без re-export старых путей ядра)
- [x] 0.6 `legacy_bridge.py` в `agent/` отсутствует — переносить нечего (P2-31 решается отдельно)
- [x] 0.7 `make check` зелёный (7330 passed); `import-linter` зелёный (4 контракта kept, рёбра те же); diff — только перемещения и импорты

## Фаза 1: `SessionView` (read-фаза ADR-003) — низкий риск

- [x] 1.1 Объявить порт `SessionView(Protocol)` + `ClientCapabilitiesView(Protocol)` в `server/agent/contracts/ports.py`. **Решение:** структурный read-порт (`session_id`, `cwd`, `config_values`, `runtime_capabilities`, `history`), а не доменный `id`/`config`/`messages()`. Причина: `messages() -> ConversationMessage` лоссовый (теряет `tool_calls` — ломает multi-turn tool-flow); живая `SessionState` удовлетворяет структурный порт без адаптера и конверсии → byte-identity гарантирован. Доменный content-VO отложен до второго драйвера (см. design.md)
- [~] 1.2 `config_to_domain`/`history_to_domain` из `SessionMapper` — **не потребовалось**: структурный порт не конвертирует в domain (иначе лоссово). Отложено до write-фазы/второго драйвера
- [~] 1.3 ACP-адаптер `SessionStateView` — **не потребовался**: живая `SessionState` структурно удовлетворяет `SessionView` (чтение сквозь живую сессию — тривиально, это она и есть). Call-sites (`single_strategy`) не оборачивают
- [x] 1.4 `ExecutionEngine.build_context`/`build_continuation_context` → `SessionView`; `HistoryBuilder.build` расширен до `Sequence[Any]` (только итерирует)
- [x] 1.5 `strategies/{base,dispatcher}`, `SystemPromptBuilder` → `SessionView`; `single_strategy` (impl `LLMCallStrategy`) → `SessionView`. `context/file_cache_decorator` — **отложен** (форвардит `session` в tools-executor, типизированный против `SessionState`; развязка вместе с цепочкой tools вне области Фазы 1)
- [x] 1.6 `tool_filter` — capabilities через `ClientCapabilitiesView` (порт удовлетворяют и `ClientRuntimeCapabilities`, и `shared.ClientCapabilities`)
- [x] 1.7 `FakeSessionView`/`FakeCapabilities` в `tests/server/agent/fakes/`; `test_session_view.py` — ядро работает без Pydantic-фикстур
- [x] 1.8 Регресс round-trip: `tool_calls` и мультимодальный image-блок не теряются (P2-32)
- [x] 1.9 Удалены 6 строк `ignore_imports` (`agent.core.{agent_base,execution_engine,strategies.base,strategies.dispatcher,system_prompt_builder,tool_filter} → protocol.state`); `file_cache_decorator` оставлен (отложен, см. 1.5)
- [x] 1.10 `make check` зелёный (7336 passed); `import-linter` зелёный (4 контракта kept) без снятых строк

## Фаза 2: `ContentCodec` — средний риск (главная работа)

- [x] 2.1 Порт `ContentCodec(Protocol)` в `ports.py` (`decode(blocks) -> list[ContentPart]`); канон — `llm.ContentPart`, доменный content-VO не вводился (см. решение в design.md — окупается лишь при 2-м драйвере)
- [x] 2.2 `ACPContentMapper` → `protocol/content/acp_codec.py` как `ACPContentCodec` (тело 1:1, `map_blocks`→`decode`); `prompt_orchestrator` и тесты-импортёры обновлены
- [x] 2.3 `HistoryBuilder(content_codec)` — инъекция порта; без кодека мультимодальные блоки схлопываются в текст (ACP-специфики в ядре нет). Codec протянут через `ExecutionEngine`, `DefaultContextManager`, `DefaultChildSessionManager`; DI (`di/agent.py`) создаёт `ACPContentCodec` и инъектит в roots
- [x] 2.4 `FakeContentCodec` в `tests/server/agent/fakes/`; `test_history_builder*` работают через инъекцию (Fake/ACP), не через хардкод ACP
- [x] 2.5 `agent/acp_content_mapper.py` удалён; в `agent/` нет ACP-импортов (только упоминание в docstring порта)
- [x] 2.6 `make check` зелёный (7336 passed); детерминизм prompt-payload сохранён (context-тесты зелёные); `import-linter` — 4 контракта kept. Прим.: рёбер `import-linter` Фаза 2 не снимает (маппер зависел только от `llm`) — ценность в развязке под 2-й драйвер, не в графе зависимостей

## Фаза 3: `ToolGateway` + `UpdateSink` — scoped (см. решение ниже)

> **Решение (архитектурное, не по ROI):** сделан scoped-срез. Единственная граница
> ядро↔адаптер, которую нарушал Phase 3 — конструкция `ACPMessage` в ядре; она снята
> (3.6). Порты объявлены как контракты (3.1/3.2). Полная 3.3 (переписывание ~10 точек
> эмиссии на доменные аргументы) перенесена в **Фазу 4**: форму доменного `UpdateSink`
> должен диктовать его потребитель (`AgentRunner`), иначе это спекулятивная абстракция
> + риск байт-идентичности горячего пути без бенефициара. Turn-loop = ACP-адаптер,
> ему строить wire — норма (границу не нарушает).

- [x] 3.1 `ToolGateway(Protocol)` в `ports.py` (`get_available_tools`/`to_llm_tools`/`execute_tool`); `ExecutionEngine.tool_registry: ToolGateway` (сужение существующего `ToolRegistry`)
- [x] 3.2 `UpdateSink(Protocol)` в `ports.py` — минимально-честно (`emit_agent_message`/`emit_streaming_delta`, что уже есть у `SessionUpdateSink`). Доменные `emit_plan`/`emit_tool_call`/`emit_tool_update` НЕ вводились: их форму продиктует `AgentRunner` (Фаза 4), consumer-driven
- [~] 3.3 → **Фаза 4**: переписывание точек эмиссии на доменные аргументы + маппинг домен→ACP внутри адаптера — вместе с `AgentRunner` (потребитель порта)
- [~] 3.4 → **Фаза 4**: унификация success/exception буферизации (P1-4) — вместе с 3.3
- [x] 3.5 Golden-тест wire: `SessionUpdateSink.build_agent_message_chunk` даёт прежний `agent_message_chunk` (в `test_strategy_integration`); полный wire-golden — с 3.3 в Фазе 4
- [x] 3.6 Ядро не конструирует `ACPMessage`: `build_fallback_notification`→`build_fallback_text` (домен-текст), ACP-wire строит `llm_loop` через `SessionUpdateSink`. **Бонус:** fallback теперь доставляется НЕМЕДЛЕННО через callback (не в буфер) — принцип immediate-delivery. `make check` зелёный (7336 passed)

## Фаза 4: `AgentRunner` + `ChildSessionFactory`

> **Полный объём одобрен** (гейты: fake driver, смена формата сессий с миграцией,
> golden wire-тесты — все закрыты). Идёт по потокам A→D→B→C→E (см. ADR-005 / эпик
> write-фазы). **Workstream A выполнен** (безопасный капстоун); B–E — планируемый эпик.

**Workstream A (выполнено):**
- [x] 4.1 `AgentRunner(Protocol)` в `ports.py` (`run_turn`/`continue_turn`) + `LLMPort(Protocol)` (фиксация `LLMAdapter`, ADR-001)
- [x] 4.2 `CoreAgentRunner` (`agent/core/agent_runner.py`) — связка `ExecutionEngine` + `LLMPort`. **Отличие от эскиза:** без `StrategyDispatcher`/EventBus — тонкий runner на портах (build_context → llm.call). Полная привязка `StrategyDispatcher` + прод-loop — 4.3, Workstream C
- [x] 4.4 `ChildSessionFactory(Protocol)` в `ports.py`; `DefaultChildSessionManager.session_factory: ChildSessionFactory`; ACP-`SessionFactory` удовлетворяет структурно (адаптер не нужен). Результат — `cast(Any)` seam до write-фазы (storage ещё `SessionState`)
- [x] 4.5 Снята строка `ignore_imports` `child_session → session_factory`
- [x] 4.7 Smoke `test_agent_runner_smoke.py`: не-ACP fake-драйвер (`FakeSessionView`/`FakeContentCodec`/`FakeToolGateway`/`FakeLLM`) прогоняет `run_turn`/`continue_turn` без `protocol/`. **Приёмочный пруф driver-независимости ядра**

**Workstream C (отложено — с прод-loop):**
- [~] 4.3 Turn-loop через `AgentRunner` — согласовать с pause/resume автоматом `ActiveTurn`; вместе с B (эмиссия). Высокий риск, требует golden wire

**Workstream D (write-фаза ADR-003 — выполнено отдельным эпиком):**
- [x] 4.6 «Server layers без исключений для agent» — **признак снят** (2026-08-04). Пункт был помечен как недостижимый в этом change: остаток (`file_cache_decorator`, `storage.base`, `tools.executors.decorators.base` → `protocol.state`) требовал развязки storage/tools от `SessionState`, то есть write-фазы. Эта write-фаза выполнена **фазой D ADR-006** (коммит `03e72d08`): носителем состояния стал доменный `Session`, документ сессии переехал в `storage/document.py` как `SessionDocument`. Текущее состояние, проверенное по коду, а не по галочкам:
  - контракт «Server layers» — `ignore_imports` **пуст**; `lint-imports`: 4 контракта kept, 0 broken;
  - `grep` импортов `protocol` внутри `server/agent/` — **ноль совпадений**;
  - `file_cache_decorator` (отложенный в 1.5) типизирован против `domain.session.Session`.

  **Долга ADR-003 больше нет — искать его не нужно.** Гейт этого change (см. «Совместимость» в `proposal.md`) выполнен: пустой `ignore_imports` в контракте «Server layers» и есть признак чистоты слоя. Строку в `pyproject.toml` про это не добавлять: новая протечка — чинить протечку, а не заводить исключение.

## Документация

- [ ] D.1 Обновить `ADR-003` (read-фаза выполнена), `ADR-005` (статус)
- [ ] D.2 Обновить `tech-debt.md`: закрыть строки ADR-003, P2-32 по мере фаз
- [ ] D.3 Обновить `ARCHITECTURE.md` (порты ядра); синхронизировать Mermaid
- [ ] D.4 Обновить `openspec/specs/` (session-state, client-capabilities, новая agent-ports) при архивации change

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

- [ ] 2.1 Добавить порт `ContentCodec(Protocol)` в `server/agent/contracts/ports.py` (`decode(blocks) -> list[ContentPart]`)
- [ ] 2.2 Перенести `ACPContentMapper` → `server/protocol/content/acp_codec.py` как `ACPContentCodec` (тело 1:1)
- [ ] 2.3 `HistoryBuilder` зависит от `ContentCodec` (инъекция), не от ACP-специфики
- [ ] 2.4 Fake `FakeContentCodec`; тесты `history_builder` без ACP
- [ ] 2.5 Удалить `agent/acp_content_mapper.py` из ядра; проверить отсутствие импортов ACP в `agent/`
- [ ] 2.6 `make check` зелёный; детерминизм prompt-payload сохранён (321 context-тест)

## Фаза 3: `ToolGateway` + `UpdateSink` — средний риск

- [ ] 3.1 Объявить `ToolGateway(Protocol)` (сужение `ToolRegistry` до `execute_tool`/`get_available_tools`/`to_llm_tools`)
- [ ] 3.2 Объявить `UpdateSink(Protocol)` в доменных терминах (`emit_agent_message`/`emit_plan`/`emit_tool_call`/`emit_tool_update`)
- [ ] 3.3 Обернуть `SessionUpdateSink` как ACP-адаптер `UpdateSink` (маппинг домен → ACP wire внутри адаптера)
- [ ] 3.4 Унифицировать success/exception буферизацию update (P1-4)
- [ ] 3.5 Golden-тест: `session/update` wire-формат байт-в-байт прежний
- [ ] 3.6 Ядро/loop не конструируют `ACPMessage`; `make check` зелёный

## Фаза 4: `AgentRunner` + `ChildSessionFactory` — средний риск

- [ ] 4.1 Объявить driving-порт `AgentRunner(Protocol)` (`run_turn`/`continue_turn`)
- [ ] 4.2 Реализация `AgentRunner` — связка `ExecutionEngine` + `StrategyDispatcher`
- [ ] 4.3 Turn-loop (`agent_loop/`) оформить как ACP driving-адаптер, вызывающий `AgentRunner`
- [ ] 4.4 `context/child_session` → доменный `ChildSessionFactory`; ACP-реализация в `protocol/`
- [ ] 4.5 Удалить оставшиеся строки `ignore_imports` `agent → protocol` (в т.ч. `child_session → session_factory`)
- [ ] 4.6 Контракт «Server layers» зелёный **без исключений для agent**; долг ADR-003 снят целиком
- [ ] 4.7 Smoke: подать в `AgentRunner` не-ACP драйвер (тест-харнесс) — turn проходит без `protocol/`

## Документация

- [ ] D.1 Обновить `ADR-003` (read-фаза выполнена), `ADR-005` (статус)
- [ ] D.2 Обновить `tech-debt.md`: закрыть строки ADR-003, P2-32 по мере фаз
- [ ] D.3 Обновить `ARCHITECTURE.md` (порты ядра); синхронизировать Mermaid
- [ ] D.4 Обновить `openspec/specs/` (session-state, client-capabilities, новая agent-ports) при архивации change

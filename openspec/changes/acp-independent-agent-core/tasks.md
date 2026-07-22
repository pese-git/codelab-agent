# ACP-независимое ядро агента — Задачи

## Фаза 0: Hexagon layout (реорганизация каталогов) — механическая, без логики

> Отдельный PR: только `git mv` + правка импортов, **ноль изменений поведения**.
> Границы `import-linter` (`codelab.server.{agent,protocol,domain}`) не двигаются.

- [ ] 0.1 Создать `server/agent/contracts/ports.py` (пока пустой каркас портов) и `contracts/events.py` — перенести доменные события из `contracts/base.py` (`DomainEvent`, `AgentRequest`, `AgentResult`, `AgentResponse`), `base.py` → тонкий re-export
- [ ] 0.2 Создать `server/agent/core/`; `git mv` ядра: `execution_engine`, `system_prompt_builder`, `history_builder`, `message_sanitizer`, `plan_extractor`, `tool_filter`, `strategies/`
- [ ] 0.3 Определить судьбу `agent/base.py` по содержимому: контракты → `contracts/events.py`, базовый класс агента → `core/`
- [ ] 0.4 `llm_adapter.py` оставить на месте (driven-адаптер, граница ADR-001); `factory.py`/`registry.py` — composition, остаются в `agent/`
- [ ] 0.5 Re-export совместимости: старые пути (`agent/execution_engine.py` и т.д.) — тонкие re-export ЛИБО разовое обновление импортёров (`grep` внешних потребителей); публичный `agent/__init__.py` сохранить
- [ ] 0.6 `legacy_bridge.py` НЕ переносить как есть — кандидат на удаление (tech-debt P2-31), решить отдельно
- [ ] 0.7 `make check` зелёный; `import-linter` зелёный (рёбра те же); diff — только перемещения и импорты

## Фаза 1: `SessionView` (read-фаза ADR-003) — низкий риск

- [ ] 1.1 Объявить порт `SessionView(Protocol)` в `server/agent/contracts/ports.py` (доменный словарь: `id`, `config`, `messages()`)
- [ ] 1.2 Выделить `config_to_domain`/`history_to_domain` из `SessionMapper` (переиспользовать `_build_history`)
- [ ] 1.3 Реализовать ACP-адаптер `SessionStateView(state: SessionState)` — чтение сквозь живую сессию (не снимок)
- [ ] 1.4 Перевести `ExecutionEngine.build_context`/`build_continuation_context` на `SessionView`
- [ ] 1.5 Перевести `strategies/*`, `SystemPromptBuilder`, `context/file_cache_decorator` на `SessionView`
- [ ] 1.6 `tool_filter` — capabilities через `shared.ClientCapabilities` (снять зависимость от `ClientRuntimeCapabilities`)
- [ ] 1.7 Fake `FakeSessionView` в `tests/server/agent/fakes/`; юнит-тесты ядра без Pydantic-фикстур
- [ ] 1.8 Регресс-тест round-trip: `image_prompts`/`embedded_context` не теряются (P2-32)
- [ ] 1.9 Удалить строки `ignore_imports` для `agent.{base,execution_engine,strategies.*,system_prompt_builder,tool_filter}` и `context.file_cache_decorator → protocol.state`
- [ ] 1.10 `make check` зелёный; `import-linter` зелёный без этих строк

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

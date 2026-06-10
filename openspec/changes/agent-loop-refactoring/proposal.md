# AgentLoop Refactoring — Унифицированный цикл итераций LLM

## Why

Текущая реализация `LLMLoopStage` имеет фундаментальные архитектурные проблемы:

### 1. Нарушение Single Responsibility Principle

`LLMLoopStage` отвечает одновременно за:
- Цикл итераций (max_iterations)
- Вызов LLM (через AgentOrchestrator или StrategyDispatcher)
- Обработку tool_calls
- Permission pause/resume
- Cancellation handling

### 2. Дублирование логики

Существуют два параллельных пути выполнения:
- `_run_llm_loop()` — legacy путь через AgentOrchestrator
- `_process_via_event_bus()` — новый путь через StrategyDispatcher

**Критическая проблема:** `_process_via_event_bus()` делает **ОДИН вызов LLM** и не имеет цикла итераций. Это приводит к тому, что tools не выполняются корректно — после tool_calls цикл не продолжается.

### 3. Нарушение Open/Closed Principle

Добавление новой стратегии вызова LLM требует изменения `LLMLoopStage`.

### 4. Несоответствие ACP спецификации

- Используется `max_iterations` вместо `max_turn_requests` (ACP 05-Prompt Turn.md:277-279)
- Отсутствует поддержка `refusal` stop reason (ACP 05-Prompt Turn.md:281)

## What Changes

### Архитектурное решение: Strategy Pattern + AgentLoop

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentLoop                                 │
│  (отвечает за цикл итераций, tool-calling, permission)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ использует
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLMCallStrategy (Protocol)                     │
│  + execute(session, prompt, mcp_manager) → AgentResponse        │
│  + continue_execution(session, mcp_manager) → AgentResponse     │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│  LegacyCallStrategy     │     │  StrategyDispatcher     │
│  (AgentOrchestrator)    │     │  (EventBus)             │
└─────────────────────────┘     └─────────────────────────┘
```

### Ключевые изменения

1. **`LLMCallStrategy` Protocol** — интерфейс для стратегии вызова LLM
2. **`LegacyCallStrategy`** — адаптер AgentOrchestrator под Protocol
3. **`AgentLoop`** — единый цикл итераций (в отдельном файле)
4. **`LLMLoopStage`** — тонкий адаптер к pipeline (< 50 строк)
5. **`StopReason` enum** — ACP-compliant stop reasons
6. **`max_iterations` → `max_turn_requests`** — соответствие ACP

## Capabilities

### New Capabilities

- `agent-loop`: Унифицированный цикл итераций LLM tool-calling
- `llm-call-strategy`: Strategy Pattern для вызова LLM
- `legacy-call-strategy`: Адаптер для AgentOrchestrator
- `acp-stop-reasons`: ACP-compliant stop reasons enum

### Modified Capabilities

- `llm-loop-stage`: Тонкий адаптер pipeline → AgentLoop
- `strategy-dispatcher`: Адаптирован под LLMCallStrategy Protocol

## ACP Compliance

| ACP требование | Документ | Строка | Реализация |
|----------------|----------|--------|------------|
| `loop Until completion` | 05-Prompt Turn.md | 30 | `AgentLoop.run()` с циклом |
| `max_turn_requests` | 05-Prompt Turn.md | 277-279 | `StopReason.MAX_TURN_REQUESTS` |
| Tool results → LLM | 05-Prompt Turn.md | 261-263 | `continue_execution()` |
| Permission flow | 08-Tool Calls.md | 110-166 | `resume_after_permission()` |
| Cancellation | 05-Prompt Turn.md | 285-317 | `_is_cancel_requested()` |
| `end_turn` | 05-Prompt Turn.md | 269-271 | ✅ |
| `max_tokens` | 05-Prompt Turn.md | 273-275 | ✅ |
| `refusal` | 05-Prompt Turn.md | 281 | Добавить |
| `cancelled` | 05-Prompt Turn.md | 283 | ✅ |

## Impact

**Новые файлы:**
- `codelab/src/codelab/server/protocol/stop_reasons.py` — StopReason enum
- `codelab/src/codelab/server/agent/strategies/base.py` — LLMCallStrategy Protocol
- `codelab/src/codelab/server/agent/strategies/legacy_adapter.py` — LegacyCallStrategy
- `codelab/src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py` — AgentLoop
- `tests/server/protocol/handlers/pipeline/stages/test_agent_loop.py`
- `tests/server/agent/strategies/test_legacy_adapter.py`

**Изменяемые файлы:**
- `codelab/src/codelab/server/protocol/handlers/pipeline/stages/llm_loop.py` — рефакторинг
- `codelab/src/codelab/server/agent/strategies/dispatcher.py` — адаптировать под Protocol
- `codelab/src/codelab/server/di.py` — обновить PipelineProvider

**Удаляемый код:**
- `_run_llm_loop()` — заменён `AgentLoop.run()`
- `_process_via_event_bus()` — заменён `AgentLoop.run()`
- `_process_tool_calls_for_llm_loop()` — перенесён в `AgentLoop`

**Breaking Changes:**
- `stop_reason="max_iterations"` → `stop_reason="max_turn_requests"`

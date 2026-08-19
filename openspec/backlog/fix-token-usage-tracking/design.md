## Context

Token usage tracking имеет три разрыва в цепочке данных:

**Текущий flow:**
```
LLM API → Provider (usage dict) → LLMAdapter._extract_usage() → TokenUsage
    → EventBus → MetricsTracker (записывает в observability)
    → SessionState.session_metrics (никогда не set)
    → Footer.update_tokens() (никогда не call)
```

**Проблемы:**
1. OpenAI provider возвращает `{"prompt_tokens": X, "completion_tokens": Y, "total_tokens": Z}`
2. LLMAdapter._extract_usage() читает `usage_data.get("input_tokens", 0)` → всегда 0 для OpenAI
3. SessionState.session_metrics остаётся None после prompt turn
4. Footer UI не получает обновления токенов

## Goals / Non-Goals

**Goals:**
- Нормализовать ключи usage во всех LLM провайдерах
- Аккумулировать token usage в SessionState после каждого prompt turn
- Отображать token usage в TUI footer и `/status` команде
- Обеспечить консистентность между Anthropic и OpenAI providers

**Non-Goals:**
- Реализация cost estimation (отдельная задача)
- Streaming token updates (показываем только после завершения turn)
- Token usage per tool call (granular tracking)

## Decisions

### Decision 1: Нормализация на уровне provider, не adapter

**Выбор:** Изменить OpenAI provider для возврата `input_tokens`/`output_tokens` вместо `prompt_tokens`/`completion_tokens`.

**Альтернативы:**
- A) Добавить маппинг в LLMAdapter._extract_usage() → Плохо: дублирование логики, каждый provider должен возвращать одинаковый формат
- B) **Выбрано:** Нормализовать в provider → Хорошо: единая ответственность, provider знает свой формат и нормализует его

**Обоснование:** LLMAdapter не должен знать о provider-specific форматах. Каждый provider отвечает за нормализацию своего usage формата.

### Decision 2: Обновление session_metrics в AgentLoop

**Выбор:** Обновлять `session.session_metrics` в `AgentLoop.run()` после каждого LLM call.

**Альтернативы:**
- A) Обновлять в LLMLoopStage → Плохо: Stage не имеет прямого доступа к response.usage
- B) Обновлять в StrategyDispatcher → Плохо: стратегия возвращает AgentResponse, но не имеет доступа к session
- C) **Выбрано:** Обновлять в AgentLoop → Хорошо: AgentLoop имеет и session, и response с usage

**Обоснование:** AgentLoop.run() — это место, где LLM вызывается и обрабатывается. Здесь есть доступ к session и response.usage.

### Decision 3: Инициализация SessionMetrics лениво

**Выбор:** Инициализировать `SessionMetrics()` при первом обновлении, если `session.session_metrics is None`.

**Альтернативы:**
- A) Инициализировать при создании сессии → Плохо: лишние данные для сессий без LLM calls
- B) **Выбрано:** Ленивая инициализация → Хорошо: создаём только когда нужно

**Обоснование:** Не все сессии используют LLM (например, только slash commands). Ленивая инициализация экономит память.

### Decision 4: Footer обновление через ViewModel

**Выбор:** Вызывать `footer.update_tokens()` из `ChatViewModel` при получении обновлений session_metrics.

**Альтернативы:**
- A) Прямой вызов из SessionState → Плохо: нарушение Clean Architecture (domain → presentation)
- B) Event-based обновление → Избыточно для простой синхронизации
- C) **Выбрано:** ViewModel → Хорошо: ViewModel координирует между domain и presentation

**Обоснование:** ChatViewModel уже координирует обновления UI. Добавление token updates следует существующему паттерну.

## Risks / Trade-offs

### Risk 1: Breaking change для существующих сессий
**Проблема:** Существующие сессии имеют `session_metrics: None`.
**Mitigation:** Ленивая инициализация при первом обновлении. Старые сессии продолжат работать.

### Risk 2: Неполная нормализация в других providers
**Проблема:** Другие providers (OpenRouter, Zen, Go) могут иметь свои форматы.
**Mitigation:** Проверить все providers в отдельной задаче. Этот change фокусируется на OpenAI.

### Risk 3: Производительность при частых обновлениях
**Проблема:** Обновление session_metrics после каждого LLM call может замедлить выполнение.
**Mitigation:** Обновление — это простая операция инкремента. Impact минимальный.

## Migration Plan

### Phase 1: Нормализация OpenAI usage
1. Изменить `openai_compatible.py:350-356`
2. Добавить unit тесты
3. Проверить что Anthropic не сломался

### Phase 2: Аккумуляция в SessionState
1. Добавить обновление session_metrics в AgentLoop.run()
2. Добавить unit тесты
3. Проверить что MetricsTracker продолжает работать

### Phase 3: UI интеграция
1. Добавить вызов footer.update_tokens() в ChatViewModel
2. Добавить token usage в /status команду
3. Manual testing в TUI

**Rollback:** Все изменения обратно совместимы. Можно откатить по фазам.

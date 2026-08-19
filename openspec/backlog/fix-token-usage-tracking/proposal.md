## Why

Token usage metrics всегда отображаются как 0 в UI и `/status` команде, несмотря на то, что LLM провайдеры возвращают корректные данные об использовании токенов. Проблема вызвана тремя багами в цепочке данных:

1. **Несовпадение ключей usage**: OpenAI provider возвращает `prompt_tokens`/`completion_tokens`, но LLMAdapter ожидает `input_tokens`/`output_tokens`
2. **SessionState.session_metrics никогда не обновляется**: Поле определено, но ни один handler не аккумулирует токены после prompt turn
3. **Footer.update_tokens() никогда не вызывается**: TUI footer имеет метод для отображения токенов, но нет кода, который бы его вызывал

Это делает невозможным отслеживание стоимости использования и лимитов токенов.

## What Changes

### Исправление 1: Нормализация ключей usage в OpenAI provider
- Изменить `openai_compatible.py:350-356` для маппинга `prompt_tokens` → `input_tokens`, `completion_tokens` → `output_tokens`
- Это обеспечит консистентность с Anthropic provider и ожиданиями LLMAdapter

### Исправление 2: Аккумуляция token usage в SessionState
- Добавить обновление `session.session_metrics` в `AgentLoop` или `LLMLoopStage` после каждого prompt turn
- Аккумулировать `input_tokens`, `output_tokens`, `total_tokens` из `response.usage`
- Инициализировать `SessionMetrics` если `session.session_metrics is None`

### Исправление 3: Интеграция token metrics в TUI
- Добавить вызов `footer.update_tokens()` из `ChatViewModel` при получении обновлений метрик
- Связать `SessionState.session_metrics` с UI через ViewModel

### Исправление 4: Token usage в `/status` команде
- Добавить отображение token usage в `StatusCommandHandler.execute()`
- Показывать input_tokens, output_tokens, total_tokens из `session.session_metrics`

## Capabilities

### New Capabilities
- `token-usage-accumulation`: Аккумуляция token usage метрик в SessionState после каждого prompt turn

### Modified Capabilities
- `multi-provider-llm`: Нормализация ключей usage в OpenAI provider для консистентности с другими провайдерами
- `session-state`: Добавление логики обновления session_metrics в pipeline
- `tui-status-display`: Интеграция token metrics в TUI footer и /status команду

## Impact

**Изменяемые файлы:**
- `src/codelab/server/llm/providers/openai_compatible.py` — нормализация ключей usage
- `src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py` — обновление session_metrics
- `src/codelab/server/protocol/handlers/slash_commands/builtin/status.py` — отображение token usage
- `src/codelab/client/presentation/chat_view_model.py` — вызов footer.update_tokens()

**Тесты:**
- Unit тесты для нормализации ключей OpenAI usage
- Unit тесты для аккумуляции session_metrics
- Integration тесты для end-to-end flow от LLM до UI

**Обратная совместимость:**
- Изменение не ломает существующий функционал
- Anthropic provider уже использует правильные ключи
- SessionMetrics остаётся опциональным полем

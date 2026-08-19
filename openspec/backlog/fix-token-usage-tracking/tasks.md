## 1. Нормализация ключей usage в OpenAI provider

- [ ] 1.1 Изменить `src/codelab/server/llm/providers/openai_compatible.py:350-356` для маппинга `prompt_tokens` → `input_tokens`, `completion_tokens` → `output_tokens`
- [ ] 1.2 Добавить unit тесты для нормализации ключей в `tests/server/llm/providers/test_openai_compatible.py`
- [ ] 1.3 Проверить что Anthropic provider не сломался: `pytest tests/server/llm/providers/test_anthropic.py`

## 2. Аккумуляция token usage в SessionState

- [ ] 2.1 Добавить метод `_update_session_metrics(session, response.usage)` в `AgentLoop` (`src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py`)
- [ ] 2.2 Вызывать `_update_session_metrics()` после каждого LLM call в `AgentLoop.run()` (строка ~325 после обработки response)
- [ ] 2.3 Реализовать логику: инициализация SessionMetrics если None, инкремент токенов
- [ ] 2.4 Добавить unit тесты для аккумуляции в `tests/server/protocol/handlers/pipeline/stages/test_agent_loop.py`

## 3. Отображение token usage в /status команде

- [ ] 3.1 Изменить `src/codelab/server/protocol/handlers/slash_commands/builtin/status.py` для добавления секции token usage
- [ ] 3.2 Показывать input_tokens, output_tokens, total_tokens, total_llm_calls из session.session_metrics
- [ ] 3.3 Добавить unit тесты для /status с token usage в `tests/server/protocol/handlers/slash_commands/builtin/test_status.py`

## 4. Интеграция token metrics в TUI footer

- [ ] 4.1 Добавить метод обновления footer в `ChatViewModel` (`src/codelab/client/presentation/chat_view_model.py`)
- [ ] 4.2 Вызывать `footer.update_tokens(total_tokens)` при завершении prompt turn
- [ ] 4.3 Добавить integration тесты для TUI отображения

## 5. Verification

- [ ] 5.1 Запустить `make check` для проверки всех изменений
- [ ] 5.2 Manual testing: запустить TUI, отправить prompt, проверить отображение токенов в footer
- [ ] 5.3 Manual testing: вызвать `/status`, проверить отображение token usage

## Tasks

### 1. Ядро LLMAdapter

- [ ] 1.1 Создать `codelab/src/codelab/server/agent/llm_adapter.py`
- [ ] 1.2 Определить класс `LLMAdapter` с полями: `_llm_provider`, `_tool_registry`, `_tracer`, `_event_bus`, `_active_tasks`, `_name`
- [ ] 1.3 Реализовать метод `call()`: messages, tools, config, parent_span → `AgentResult`
- [ ] 1.4 Реализовать внутренний метод `_execute()`: цикл LLM вызовов (макс. 5 итераций)
- [ ] 1.5 Реализовать выполнение инструментов внутри цикла: execute tools, добавить результаты в messages
- [ ] 1.6 Реализовать сборку `AgentResult`: text, tool_calls, usage (из LLM response), stop_reason, agent_name, plan
- [ ] 1.7 Реализовать отмену: отслеживание asyncio.Task, возврат cancelled AgentResult

### 2. Регистрация в EventBus

- [ ] 2.1 Реализовать метод `_handle_request()`: конвертация `AgentRequest` → `AgentResult`
- [ ] 2.2 Реализовать `register_with_bus(event_bus, agent_name)` — регистрация как `RequestHandler`
- [ ] 2.3 Написать тесты: register_with_bus → send_request → корректный ответ

### 3. Интеграция Tracing

- [ ] 3.1 Интегрировать Tracer: `start_span("llm_call", parent=parent_span)` в начале call()
- [ ] 3.2 Интегрировать Tracer: `end_span` с атрибутами (model, provider, tokens, latency)
- [ ] 3.3 Написать тесты: span создан с правильным родительским контекстом
- [ ] 3.4 Написать тесты: атрибуты span включают данные usage

### 4. Отмена

- [ ] 4.1 Реализовать dict `_active_tasks` для отслеживания активных задач
- [ ] 4.2 Обработать `asyncio.CancelledError` → `AgentResult(stop_reason="cancelled")`
- [ ] 4.3 Очистить ссылку на задачу в блоке finally
- [ ] 4.4 Написать тесты: отмена активной задачи → cancelled result
- [ ] 4.5 Написать тесты: нормальное завершение → задача очищена

### 5. Маппинг имён инструментов и извлечение плана

> **Существующий код:** `server/tools/mapping.py` уже содержит `acp_name_to_llm_name()` и `llm_name_to_acp_name()`. `PlanExtractor` уже существует в `server/agent/plan_extractor.py`. Переиспользовать, не дублировать.

- [ ] 5.1 Переиспользовать `acp_name_to_llm_name()` из `server/tools/mapping.py` для конвертации имён инструментов
- [ ] 5.2 Переиспользовать `PlanExtractor` из `server/agent/plan_extractor.py` для извлечения плана
- [ ] 5.3 Написать тесты: корректность маппинга имён инструментов в контексте LLMAdapter
- [ ] 5.4 Написать тесты: извлечение плана через PlanExtractor в LLMAdapter

### 6. Тесты

- [ ] 6.1 Написать unit тесты: LLM вызов без tools → текстовый ответ
- [ ] 6.2 Написать unit тесты: LLM вызов с tools → цикл выполнения инструментов
- [ ] 6.3 Написать unit тесты: сохранение usage из ответа LLM
- [ ] 6.4 Написать unit тесты: достигнут лимит итераций → stop_reason="max_iterations"
- [ ] 6.5 Написать integration тесты: полный цикл через EventBus

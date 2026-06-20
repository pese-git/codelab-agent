## Почему

Согласно ACP спецификации (10-Terminal.md), при превышении `outputByteLimit` клиент ДОЛЖЕН обрезать output с начала, сохраняя character boundary UTF-8. Предыдущая реализация обрезала целые строки, что могло приводить к некорректному UTF-8 и потере данных. Также отсутствовал флаг `truncated` в response, что не позволяло серверу информировать LLM о потере данных.

## Что изменяется

- Добавлена функция `truncate_to_byte_limit()` для безопасной обрезки на character boundary UTF-8
- Добавлено поле `was_truncated` в `TerminalSession` для отслеживания факта обрезки
- Обновлена сигнатура `get_output()` — возвращает tuple из 4 элементов (output, is_complete, exit_code, truncated)
- `TerminalCallbackExecutor.get_output()` формирует ACP-compliant response с `truncated` флагом
- Сервер добавляет "Output was truncated." в completion_text для LLM

## Возможности

### Новые возможности

- `terminal-truncation-character-boundary`: Безопасная обрезка output на границе UTF-8 символа
- `terminal-truncation-flag`: Флаг `truncated` в terminal/output response

### Изменённые возможности

- `terminal-embedding`: TerminalExecutor теперь возвращает truncated флаг

## Влияние

**Client Infrastructure Layer:**
- `client/infrastructure/services/terminal_executor.py` — функция `truncate_to_byte_limit()`, поле `was_truncated`, обновлённая сигнатура `get_output()`

**Client Presentation Layer:**
- `client/presentation/chat/executors/terminal_callback_executor.py` — формирование ACP-compliant response

**Client Presentation Layer (Protocol):**
- `client/presentation/chat/executors/terminal_executor_adapter.py` — обновлён для нового протокола

**Server Protocol Layer:**
- `server/protocol/handlers/prompt.py` — обработка `truncated` флага, добавление "Output was truncated." в completion_text

**Tests:**
- `tests/client/test_terminal_truncation.py` — 7 тестов для truncation функции
- Обновлены все тесты terminal для новой сигнатуры get_output()

**Dependencies:** Нет новых зависимостей.

**Backward Compatibility:** Breaking change в сигнатуре `get_output()` — все вызовы обновлены.

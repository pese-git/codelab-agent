## 1. truncate_to_byte_limit функция

- [x] 1.1 Создать функцию `truncate_to_byte_limit(text, byte_limit)` в `terminal_executor.py`
- [x] 1.2 Реализовать обрезку на character boundary UTF-8
- [x] 1.3 Возвращать tuple (truncated_text, was_truncated)
- [x] 1.4 Написать unit тесты (7 тестов)

## 2. TerminalSession обновление

- [x] 2.1 Добавить поле `was_truncated: bool = False` в dataclass
- [x] 2.2 Обновить docstring

## 3. TerminalExecutor обновление

- [x] 3.1 Обновить `_read_output()` для применения truncation
- [x] 3.2 Обновить `get_output()` — возвращать tuple из 4 элементов
- [x] 3.3 Обновить docstring и пример использования

## 4. TerminalCallbackExecutor обновление

- [x] 4.1 Обновить `get_output()` для формирования ACP-compliant response
- [x] 4.2 Включить `truncated` флаг в response
- [x] 4.3 Включить `exitStatus` объект если процесс завершён

## 5. TerminalExecutorAdapter обновление

- [x] 5.1 Обновить `get_output()` для новой сигнатуры
- [x] 5.2 Обновить `wait_for_exit()` для новой сигнатуры

## 6. Обновление тестов

- [x] 6.1 Обновить `test_terminal_executor.py` — новая сигнатура get_output()
- [x] 6.2 Обновить `test_terminal_executor_coverage.py` — проверка was_truncated
- [x] 6.3 Обновить `test_terminal_handler.py` — новая сигнатура
- [x] 6.4 Обновить `test_terminal_callback_executor.py` — mock с 4 элементами
- [x] 6.5 Обновить `test_terminal_executor_adapter.py` — новая сигнатура
- [x] 6.6 Обновить `test_chat_components_integration.py` — MockTerminalExecutor
- [x] 6.7 Обновить `test_client_decomposition_e2e.py` — MockTerminalExecutor

## 7. Интеграция

- [x] 7.1 Все 6695 тестов проходят
- [x] 7.2 Ruff check проходит
- [x] 7.3 Type check проходит

# Спецификация: Terminal Output Truncation

## ДОБАВЛЕННЫЕ Требования

### Требование: Функция truncate_to_byte_limit

Система ДОЛЖНА предоставлять функцию `truncate_to_byte_limit(text, byte_limit)` для безопасной обрезки текста на character boundary UTF-8.

#### Сценарий: Обрезка в пределах лимита
- **КОГДА** размер текста в байтах <= byte_limit
- **ТОГДА** возвращается исходный текст, `was_truncated=False`

#### Сценарий: Обрезка с превышением лимита
- **КОГДА** размер текста в байтах > byte_limit
- **ТОГДА** возвращается обрезанный текст (последние byte_limit байт), `was_truncated=True`

#### Сценарий: Обрезка на character boundary
- **КОГДА** текст содержит multi-byte UTF-8 символы
- **ТОГДА** обрезка происходит на границе символа, результат — валидный UTF-8

### Требование: Поле was_truncated в TerminalSession

`TerminalSession` ДОЛЖНА содержать поле `was_truncated: bool = False` для отслеживания факта обрезки output.

#### Сценарий: Установка флага при обрезке
- **КОГДА** output превышает byte_limit
- **ТОГДА** `was_truncated` устанавливается в `True`

### Требование: Обновлённая сигнатура get_output()

`TerminalExecutor.get_output()` ДОЛЖНА возвращать tuple из 4 элементов: `(output, is_complete, exit_code, truncated)`.

#### Сценарий: Возврат truncated флага
- **КОГДА** вызван `get_output(terminal_id)`
- **ТОГДА** возвращается tuple с truncated флагом из session.was_truncated

### Требование: ACP-compliant response в TerminalCallbackExecutor

`TerminalCallbackExecutor.get_output()` ДОЛЖНА формировать response согласно ACP спецификации:
```python
{
    "output": "...",
    "truncated": True/False,
    "exitStatus": {"exitCode": ..., "signal": ...}  # если завершён
}
```

#### Сценарий: Response с truncated флагом
- **КОГДА** вызван `get_output()` и output был обрезан
- **ТОГДА** response содержит `"truncated": True`

### Требование: Влияние truncated на LLM context

Сервер ДОЛЖЕН добавлять "Output was truncated." в completion_text при `pending.terminal_truncated=True`.

#### Сценарий: LLM получает информацию о truncation
- **КОГДА** terminal output был обрезан
- **ТОГДА** completion_text содержит "Output was truncated."
- **ТОГДА** LLM может адаптировать поведение (разбить команду, использовать другой подход)

### Требование: Отправка truncated клиенту

Сервер ДОЛЖЕН включать `truncated` флаг в `rawOutput` tool_call_update notification.

#### Сценарий: Клиент получает truncated флаг
- **КОГДА** terminal output был обрезан
- **ТОГДА** notification содержит `"rawOutput": {"truncated": True, ...}`

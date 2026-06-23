## ADDED Requirements

### Requirement: Token usage display in /status command
Система SHALL отображать token usage метрики в выводе команды `/status`.

#### Scenario: Display token usage in status
- **WHEN** пользователь вызывает команду `/status`
- **WHEN** `session.session_metrics` не None и содержит токены
- **THEN** вывод ДОЛЖЕН включать:
  - `**Input tokens:** X`
  - `**Output tokens:** Y`
  - `**Total tokens:** Z`
  - `**LLM calls:** N`

#### Scenario: No token usage available
- **WHEN** пользователь вызывает команду `/status`
- **WHEN** `session.session_metrics is None` или токены равны 0
- **THEN** вывод ДОЛЖЕН включать `**Token usage:** N/A` или не показывать секцию токенов

### Requirement: Token usage display in TUI footer
Система SHALL отображать token usage в footer TUI приложения.

#### Scenario: Footer shows token count
- **WHEN** сессия имеет накопленные токены в session_metrics
- **THEN** footer ДОЛЖЕН отображать `🎯 X tokens` где X — total_tokens

#### Scenario: Footer updates after prompt turn
- **WHEN** prompt turn завершён и session_metrics обновлён
- **THEN** footer ДОЛЖЕН обновить отображение токенов
- **THEN** отображение ДОЛЖНО показывать актуальное значение total_tokens

#### Scenario: Footer token display format
- **WHEN** total_tokens больше 1000
- **THEN** footer ДОЛЖЕН форматировать число с разделителями тысяч (например, `1,234 tokens`)

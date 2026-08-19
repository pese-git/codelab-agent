# Delta Spec: agent-config (agents-instructions-support)

## ДОБАВЛЕННЫЕ Требования

### Требование: Конфигурация инструкций AGENTS.md

Система ДОЛЖНА парсить секцию `[agents.instructions]` из `codelab.toml` с полями:

| Поле | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `mode` | `"local" \| "remote"` | `"local"` | Режим чтения файлов инструкций |
| `file_names` | `list[str]` | `["AGENTS.md", "CLAUDE.md"]` | Приоритетный список имён файлов |
| `watch` | `bool` | `true` | Отслеживание изменений файлов |
| `max_file_size` | `int` | `100000` | Максимальный размер файла (байты) |

**Пример конфигурации**:
```toml
[agents.instructions]
mode = "local"
file_names = ["AGENTS.md", "CLAUDE.md", ".cursorrules"]
watch = true
max_file_size = 100000
```

### Требование: Переменные окружения

Система ДОЛЖНА поддерживать переменные окружения для overrides:

| Переменная | Описание |
|------------|----------|
| `CODELAB_INSTRUCTIONS_MODE` | Override для `mode` |
| `CODELAB_INSTRUCTIONS_MAX_FILE_SIZE` | Override для `max_file_size` |

### Требование: Pydantic модель

Система ДОЛЖНА определить `AgentsInstructionsConfig(BaseModel)` с валидацией:

```python
class AgentsInstructionsConfig(BaseModel):
    mode: Literal["local", "remote"] = "local"
    file_names: list[str] = Field(default_factory=lambda: ["AGENTS.md", "CLAUDE.md"])
    watch: bool = True
    max_file_size: int = 100_000
```

### Требование: Интеграция в AppConfig

`AgentsInstructionsConfig` ДОЛЖЕН быть доступен через `AppConfig.agents.instructions`.

---

## ИЗМЕНЁННЫЕ Требования

### `AgentsConfig` — добавление поля `instructions`

**Было**:
```python
class AgentsConfig(BaseModel):
    strategy: str = "single"
    fallback_strategy: str = "single"
    default_model: str = "openai/gpt-4o"
    max_steps: int = 7
```

**Стало**:
```python
class AgentsConfig(BaseModel):
    strategy: str = "single"
    fallback_strategy: str = "single"
    default_model: str = "openai/gpt-4o"
    max_steps: int = 7
    instructions: AgentsInstructionsConfig = Field(default_factory=AgentsInstructionsConfig)
```

---

## Обратная совместимость

- Если секция `[agents.instructions]` отсутствует — используются значения по умолчанию
- Существующая конфигурация продолжает работать без изменений
- Новые поля не ломают существующие тесты

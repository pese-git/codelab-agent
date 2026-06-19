## Контекст

ACP сервер в текущей реализации объявляет все опциональные prompt capabilities как `false`:
- `image: false` — клиенты не могут отправлять изображения
- `audio: false` — аудио отложено (требует транскрипции)
- `embeddedContext: false` — клиенты не могут встраивать ресурсы (файлы, контекст)

Согласно ACP спецификации (02-Initialization.md, 06-Content.md):
- Baseline: `text` и `resource_link` — обязательны
- Optional: `image`, `audio`, `resource` (embedded) — объявляются через capabilities

Текущий поток данных:
```
Client → session/prompt [ContentBlock[]]
  → validate_prompt_content() — принимает только text/resource_link
  → _extract_full_text() — схлопывает в строку, теряя multimodal
  → HistoryBuilder → LLMMessage(content: str) — только текст
  → LLM Provider — получает строку, не multimodal
```

Проблема: на каждом уровне трансформации multimodal content теряется.

**Заинтересованные стороны:**
- Клиенты (IDE, TUI) — хотят отправлять изображения для анализа
- LLM providers (OpenAI, Anthropic) — поддерживают vision API
- ACP spec compliance — требуется для интероперабельности

## Цели / Не цели

**Цели:**
- Включить `image` и `embeddedContext` capabilities в handshake
- Поддержка multimodal content в pipeline без потери данных
- Capability-aware validation (проверка поддержки типа перед приёмом)
- Graceful fallback для providers без vision support
- Полная backward compatibility с text-only путём
- Соответствие ACP 06-Content.md (image, resource форматы)

**Не цели:**
- Audio support — отложен до отдельного change (требует Whisper/API)
- Image generation — только analysis (input), не output
- Custom content types — расширение через `_meta` (ACP extensibility)
- Client-side rendering — сервер не возвращает multimodal в session/update

## Решения

### Решение 1: Доменная модель — ContentPart (frozen dataclass)

**Выбор:** Ввести `ContentPart` как domain model для multimodal content.

```python
@dataclass(frozen=True)
class ContentPart:
    type: Literal["text", "image"]
    text: str | None = None
    data: str | None = None          # base64
    mime_type: str | None = None
```

**Обоснование:**
- **Типобезопасность** — `frozen=True` dataclass вместо `dict[str, Any]` (который = `Any`)
- **Неизменяемость** — безопасно шарить между слоями pipeline
- **Фабричные методы** — единая точка валидации при создании
- **Слоёная архитектура** — domain model отделён от ACP dict-ов (protocol) и provider format (infra)

**Рассмотренные альтернативы:**
1. `list[dict[str, Any]]` в LLMMessage — нет type safety, dict = Any
2. Pydantic model — избыточно для value object, нет мутаций
3. Union type `str | ImagePart | TextPart` — сложно расширять, pattern matching

### Решение 2: Профиль возможностей — единый источник истины

**Выбор:** `PromptCapabilityProfile` в `auth.py` — единое место определения capabilities.

```python
@dataclass(frozen=True)
class PromptCapabilityProfile:
    image: bool = False
    audio: bool = False
    embedded_context: bool = False
```

**Обоснование:**
- **DRY** — возможности определяются ОДИН раз, не дублируются в валидации
- **OCP** — добавление возможности = одно изменение в профиле
- **Согласованность** — handshake response и валидация используют один источник

**Рассмотренные альтернативы:**
1. Хардкод в `validate_prompt_content` — дублирование, легко рассинхронизировать
2. Config file — избыточно, capabilities — compile-time decision
3. Environment variables — не подходит, capabilities — protocol-level

### Решение 3: Маппер ACP — конвертация на границе

**Выбор:** `ACPContentMapper` — отдельный класс на границе protocol → domain.

```python
class ACPContentMapper:
    def map_blocks(self, blocks: list[dict]) -> list[ContentPart]:
        # ACP ContentBlock → domain ContentPart
```

**Обоснование:**
- **SRP** — protocol layer не знает про domain model
- **Тестируемость** — pure function, легко мокается
- **Логика fallback** — здесь же: `resource` → `ContentPart.text()` (извлечение встроенного текста)

**Рассмотренные альтернативы:**
1. Маппинг в HistoryBuilder — смешение слоёв (protocol + agent)
2. Маппинг в validate_prompt_content — валидация не должна трансформировать
3. Inline conversion — дублирование в каждом месте использования

### Решение 4: LLMMessage.content — Union тип

**Выбор:** Расширить `LLMMessage.content: str | list[ContentPart] | None`.

**Обоснование:**
- **Обратная совместимость** — `str` остаётся валидным, text-only путь не меняется
- **Явность** — `list[ContentPart]` явно указывает на мультимодальность
- **Сопоставление образцов** — downstream code проверяет тип: `isinstance(content, list)`

**Рассмотренные альтернативы:**
1. Всегда `list[ContentPart]` — ломает backward compatibility, нужно переписывать все providers
2. Отдельное поле `multimodal_content` — дублирование, сложно синхронизировать
3. `ContentPart` wrapper — избыточно для text-only

### Решение 5: Проверка возможностей провайдера — поддержка vision в runtime

**Выбор:** Перед отправкой image — проверить `provider.capabilities.supports_vision`.

```python
if part.is_multimodal and not provider.capabilities.supports_vision:
    logger.warning("provider does not support vision, skipping image")
    return None  # filter out
```

**Обоснование:**
- **Плавная деградация** — если провайдер не поддерживает vision, fallback в текстовое описание
- **Гибкость в runtime** — можно переключать провайдеры без изменения кода
- **Безопасность** — не ломает pipeline, просто пропускает неподдерживаемое содержимое

**Рассмотренные альтернативы:**
1. Raise error — ломает pipeline, клиент получает ошибку
2. Convert to text placeholder — теряет информацию, но работает
3. Block at validation — слишком рано, provider может смениться

### Решение 6: Интеграция в pipeline — content_parts в PromptContext

**Выбор:** Добавить `content_parts: list[ContentPart]` в `PromptContext`.

**Обоснование:**
- **Явный передача данных** — content_parts проходят через все стадии pipeline
- **Нет скрытого состояния** — каждая стадия видит мультимодальное содержимое
- **Тестируемость** — можно проверить content_parts в любой стадии

**Рассмотренные альтернативы:**
1. Хранить в `context.meta["content_parts"]` — hidden state, сложно отслеживать
2. Передавать через session — смешение protocol и agent layers
3. Пересоздавать в каждой стадии — дублирование, потеря данных

## Риски / Компромиссы

### Риск 1: Размер изображения — нагрузка на память

**Риск:** Base64 изображения могут быть большими (20MB+), загружая память.

**Смягчение:**
- Добавить лимит в валидации: `MAX_IMAGE_SIZE = 20 * 1024 * 1024` (20 МБ)
- Логировать размер при получении
- В будущем: streaming upload (не в этом change)

### Риск 2: Несовместимость провайдера — тихий fallback

**Риск:** Provider без vision support молча пропускает image, пользователь не знает.

**Смягчение:**
- `logger.warning` при пропуске — видно в логах
- В будущем: уведомлять клиента через session/update (не в этом change)
- Документация: какие провайдеры поддерживают vision

### Риск 3: Обратная совместимость — путаница с Union типом

**Риск:** `str | list[ContentPart]` может запутать downstream code.

**Смягчение:**
- Чёткая документация в docstring LLMMessage
- Вспомогательные методы: `is_multimodal()`, `get_text()`
- Type guards в критических путях

### Риск 4: Эволюция спецификации ACP — новые типы содержимого

**Риск:** ACP spec добавит новые content types (video, 3D model), нужно расширять.

**Смягчение:**
- `ContentPart.type: Literal[...]` — закрытый набор, расширяется явно
- ACPContentMapper — единая точка маппинга, легко добавить новый тип
- OCP: новый тип = добавить вариант + mapper + provider formatter

### Риск 5: Сложность тестирования — комбинации мультимодальности

**Риск:** Комбинаторика: text-only, text+image, image-only, resource, mixed.

**Смягчение:**
- Параметризованные тесты для каждого типа содержимого
- Интеграционные тесты: end-to-end промпт → LLM
- Unit тесты для каждого слоя (mapper, builder, provider)

## План миграции

### Фаза 1: Доменная модель (Неделя 1)

1. Создать `ContentPart` dataclass
2. Создать `ACPContentMapper`
3. Unit tests для mapper

**Откат:** Удалить новые файлы, нет изменений в существующем коде.

### Фаза 2: Слой протокола (Неделя 1)

1. Добавить `PromptCapabilityProfile` в `auth.py`
2. Расширить `validate_prompt_content` (image, resource)
3. Обновить `content/validator.py` (REQUIRED_FIELDS)
4. Integration tests: валидация multimodal

**Откат:** Откатить возможности в `false`, валидация отклоняет image/resource.

### Фаза 3: Слой pipeline (Неделя 2)

1. Добавить `content_parts` в `PromptContext`
2. Маппинг в `prompt_orchestrator.py`
3. Обновить `ValidationStage` (multimodal empty check)
4. Integration tests: pipeline с multimodal

**Откат:** Удалить поле `content_parts`, pipeline работает с text-only.

### Фаза 4: Слой агента + LLM (Неделя 2)

1. Расширить `LLMMessage.content` type
2. Обновить `HistoryBuilder` (multimodal conversion)
3. Обновить `ExecutionEngine` (передаёт content_parts)
4. Providers: OpenAI + Anthropic formatting
5. E2E tests: prompt с image → LLM response

**Откат:** Откатить `LLMMessage.content` в `str`, провайдеры работают с текстом.

### Стратегия развёртывания

- **Поэтапный rollout:** Фазы 1-2 можно merge без Фаз 3-4
- **Feature flag:** `PROMPT_MULTIMODAL_ENABLED` env var (опционально, по умолчанию: true)
- **Мониторинг:** логи при пропуске image (неподдерживаемый провайдер)
- **План отката:** откатить возможности в `false` — клиенты вернутся к text-only

## Открытые вопросы

### Вопрос 1: Ограничение размера изображения

**Вопрос:** Какой максимальный размер изображения? 20MB? 50MB?

**Варианты:**
- 20 МБ — безопасно для памяти, покрывает большинство случаев
- 50 МБ — больше гибкости, но риск OOM
- Настраиваемый — `MAX_IMAGE_SIZE` env var

**Требуется решение:** Перед Фазой 1.

### Вопрос 2: Неподдерживаемый провайдер — поведение

**Вопрос:** Что делать если provider не поддерживает vision?

**Варианты:**
- Пропускать молча + логировать предупреждение — текущий план
- Конвертировать в текстовый placeholder — `[Image: ...]`
- Возбуждать ошибку — отклонить промпт

**Требуется решение:** Перед Фазой 4.

### Вопрос 3: Fallback для ресурса — извлечение текста

**Вопрос:** Как маппить `resource` (embedded) в ContentPart?

**Варианты:**
- Извлекать `resource.text` → `ContentPart.text()` — текущий план
- Оставлять как `ContentPart.resource(uri, text)` — явное представление
- Пропускать нетекстовые ресурсы (blob) — только текстовые ресурсы

**Требуется решение:** Перед Фазой 1.

### Вопрос 4: Уведомление клиента — неподдерживаемое содержимое

**Вопрос:** Уведомлять клиента если image пропущен (unsupported provider)?

**Варианты:**
- Нет — только log warning (текущий план)
- Да — `session/update` с warning (будущая работа)
- Настраиваемый — `NOTIFY_UNSUPPORTED_CONTENT` env var

**Требуется решение:** После Фазы 4 (будущее улучшение).

## 1. Доменная модель — ContentPart

- [x] 1.1 Создать `src/codelab/server/llm/content_parts.py` с `ContentPart` frozen dataclass
- [x] 1.2 Добавить фабричные методы: `ContentPart.text()`, `ContentPart.image()`
- [x] 1.3 Добавить свойство `is_multimodal`
- [x] 1.4 Написать unit тесты для создания ContentPart, неизменяемости, фабричных методов

## 2. Маппер содержимого ACP

- [x] 2.1 Создать `src/codelab/server/protocol/content/acp_mapper.py` с классом `ACPContentMapper`
- [x] 2.2 Реализовать метод `map_blocks()`: text → ContentPart.text()
- [x] 2.3 Реализовать маппинг image: блок image → ContentPart.image()
- [x] 2.4 Реализовать маппинг resource: блок resource → ContentPart.text() с fallback
- [x] 2.5 Реализовать маппинг resource_link: resource_link → ContentPart.text()
- [x] 2.6 Написать unit тесты для всех сценариев маппинга (text, image, resource, resource_link, mixed)

## 3. Слой протокола — объявление возможностей

- [x] 3.1 Создать `PromptCapabilityProfile` dataclass в `src/codelab/server/protocol/handlers/auth.py`
- [x] 3.2 Установить `_PROMPT_CAPABILITIES = PromptCapabilityProfile(image=True, audio=False, embedded_context=True)`
- [x] 3.3 Обновить `initialize()` для использования `_PROMPT_CAPABILITIES` в ответе
- [x] 3.4 Написать тест: ответ initialize включает `image: true`, `embeddedContext: true`, `audio: false`

## 4. Слой протокола — валидация промпта

- [x] 4.1 Обновить `validate_prompt_content()` в `src/codelab/server/protocol/handlers/prompt.py` для приёма типа `image`
- [x] 4.2 Добавить валидацию: image требует `data` (str) и `mimeType` (str)
- [x] 4.3 Добавить валидацию: ограничение размера данных image 20 МБ
- [x] 4.4 Обновить `validate_prompt_content()` для приёма типа `resource`
- [x] 4.5 Добавить валидацию: resource требует `resource.uri` (str)
- [x] 4.6 Написать тесты: валидный image, image без полей, image превышает размер, валидный resource, resource без URI
- [x] 4.7 Обновить REQUIRED_FIELDS в `content/validator.py` для соответствия спецификации ACP (image: data+mimeType, resource: resource)

## 5. Слой pipeline — PromptContext

- [x] 5.1 Добавить `content_parts: list[ContentPart] = field(default_factory=list)` в `PromptContext` в `src/codelab/server/protocol/handlers/pipeline/context.py`
- [x] 5.2 Написать тест: PromptContext с content_parts, по умолчанию пустой список

## 6. Слой pipeline — PromptOrchestrator

- [x] 6.1 Импортировать `ACPContentMapper` в `src/codelab/server/protocol/handlers/prompt_orchestrator.py`
- [x] 6.2 В `handle_prompt()` маппить блоки промпта в content_parts используя `ACPContentMapper`
- [x] 6.3 Передать `content_parts` в конструктор `PromptContext`
- [x] 6.4 Написать интеграционный тест: промпт с image → content_parts заполнены

## 7. Слой pipeline — ValidationStage

- [x] 7.1 Обновить `ValidationStage.process()` в `src/codelab/server/protocol/handlers/pipeline/stages/validation.py`
- [x] 7.2 Проверить `has_multimodal = any(p.is_multimodal for p in context.content_parts)`
- [x] 7.3 Разрешить промпт если `has_text or has_multimodal`, отклонить если оба пусты
- [x] 7.4 Написать тесты: только image проходит, только текст проходит, пустой не проходит

## 8. Слой агента — LLMMessage

- [x] 8.1 Обновить тип `LLMMessage.content` до `str | list[ContentPart] | None` в `src/codelab/server/llm/models.py`
- [x] 8.2 Написать тест: LLMMessage со строковым содержимым, LLMMessage с list[ContentPart]

## 9. Слой агента — HistoryBuilder

- [x] 9.1 Импортировать `ContentPart`, `ACPContentMapper` в `src/codelab/server/agent/history_builder.py`
- [x] 9.2 Обновить обработку содержимого списка: определять мультимодальные блоки
- [x] 9.3 Если мультимодальное: конвертировать в `list[ContentPart]` через маппер
- [x] 9.4 Если только текст: схлопнуть в строку (обратная совместимость)
- [x] 9.5 Написать тесты: история с image → list[ContentPart], история с текстом → строка

## 10. Слой агента — ExecutionEngine

- [x] 10.1 Обновить `ExecutionEngine.build_context()` в `src/codelab/server/agent/execution_engine.py`
- [x] 10.2 Передать `content_parts` как список dict в `AgentContext.prompt`
- [x] 10.3 Fallback до `[{"type": "text", "text": prompt}]` если нет content_parts
- [x] 10.4 Написать тест: build_context с мультимодальным содержимым

## 11. Слой провайдеров LLM — OpenAI

- [x] 11.1 Обновить `OpenAICompatibleProvider.capabilities` до `supports_vision=True` в `src/codelab/server/llm/providers/openai_compatible.py`
- [x] 11.2 Добавить метод `_content_part_to_openai()`: text → `{"type": "text", ...}`, image → `{"type": "image_url", ...}`
- [x] 11.3 Обновить `_convert_to_openai_format()` для обработки `list[ContentPart]`
- [x] 11.4 Написать тесты: форматирование text, форматирование image, форматирование mixed, проверка возможности vision

## 12. Слой провайдеров LLM — Anthropic

- [x] 12.1 Проверить `AnthropicProvider.capabilities` имеет `supports_vision=True` (уже установлено)
- [x] 12.2 Добавить метод `_content_part_to_anthropic()`: text → `{"type": "text", ...}`, image → `{"type": "image", "source": ...}`
- [x] 12.3 Обновить `_convert_to_anthropic_format()` для обработки `list[ContentPart]`
- [x] 12.4 Написать тесты: форматирование text, форматирование image, форматирование mixed

## 13. Fallback для возможности vision

- [x] 13.1 В обоих провайдерах проверять `self.capabilities.supports_vision` перед форматированием image
- [x] 13.2 Если `supports_vision=False`: пропустить image, логировать предупреждение, сохранить text
- [x] 13.3 Написать тесты: провайдер без vision пропускает image, логирует предупреждение

## 14. Интеграционные тесты

- [x] 14.1 E2E тест: `session/prompt` с image → LLM получает форматированный image
- [x] 14.2 E2E тест: `session/prompt` с встроенным ресурсом → LLM получает текстовый fallback
- [x] 14.3 E2E тест: `session/prompt` со смешанным содержимым → LLM получает мультимодальное
- [x] 14.4 E2E тест: ответ initialize включает корректные возможности

## 15. Документация

- [x] 15.1 Обновить docstrings в изменённых файлах
- [x] 15.2 Добавить примеры использования в docstrings модулей
- [x] 15.3 Документировать профиль возможностей в auth.py

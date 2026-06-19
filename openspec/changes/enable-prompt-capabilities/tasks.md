## 1. Доменная модель — ContentPart

- [ ] 1.1 Создать `src/codelab/server/llm/content_parts.py` с `ContentPart` frozen dataclass
- [ ] 1.2 Добавить фабричные методы: `ContentPart.text()`, `ContentPart.image()`
- [ ] 1.3 Добавить свойство `is_multimodal`
- [ ] 1.4 Написать unit тесты для создания ContentPart, неизменяемости, фабричных методов

## 2. Маппер содержимого ACP

- [ ] 2.1 Создать `src/codelab/server/protocol/content/acp_mapper.py` с классом `ACPContentMapper`
- [ ] 2.2 Реализовать метод `map_blocks()`: text → ContentPart.text()
- [ ] 2.3 Реализовать маппинг image: блок image → ContentPart.image()
- [ ] 2.4 Реализовать маппинг resource: блок resource → ContentPart.text() с fallback
- [ ] 2.5 Реализовать маппинг resource_link: resource_link → ContentPart.text()
- [ ] 2.6 Написать unit тесты для всех сценариев маппинга (text, image, resource, resource_link, mixed)

## 3. Слой протокола — объявление возможностей

- [ ] 3.1 Создать `PromptCapabilityProfile` dataclass в `src/codelab/server/protocol/handlers/auth.py`
- [ ] 3.2 Установить `_PROMPT_CAPABILITIES = PromptCapabilityProfile(image=True, audio=False, embedded_context=True)`
- [ ] 3.3 Обновить `initialize()` для использования `_PROMPT_CAPABILITIES` в ответе
- [ ] 3.4 Написать тест: ответ initialize включает `image: true`, `embeddedContext: true`, `audio: false`

## 4. Слой протокола — валидация промпта

- [ ] 4.1 Обновить `validate_prompt_content()` в `src/codelab/server/protocol/handlers/prompt.py` для приёма типа `image`
- [ ] 4.2 Добавить валидацию: image требует `data` (str) и `mimeType` (str)
- [ ] 4.3 Добавить валидацию: ограничение размера данных image 20 МБ
- [ ] 4.4 Обновить `validate_prompt_content()` для приёма типа `resource`
- [ ] 4.5 Добавить валидацию: resource требует `resource.uri` (str)
- [ ] 4.6 Написать тесты: валидный image, image без полей, image превышает размер, валидный resource, resource без URI
- [ ] 4.7 Обновить REQUIRED_FIELDS в `content/validator.py` для соответствия спецификации ACP (image: data+mimeType, resource: resource)

## 5. Слой pipeline — PromptContext

- [ ] 5.1 Добавить `content_parts: list[ContentPart] = field(default_factory=list)` в `PromptContext` в `src/codelab/server/protocol/handlers/pipeline/context.py`
- [ ] 5.2 Написать тест: PromptContext с content_parts, по умолчанию пустой список

## 6. Слой pipeline — PromptOrchestrator

- [ ] 6.1 Импортировать `ACPContentMapper` в `src/codelab/server/protocol/handlers/prompt_orchestrator.py`
- [ ] 6.2 В `handle_prompt()` маппить блоки промпта в content_parts используя `ACPContentMapper`
- [ ] 6.3 Передать `content_parts` в конструктор `PromptContext`
- [ ] 6.4 Написать интеграционный тест: промпт с image → content_parts заполнены

## 7. Слой pipeline — ValidationStage

- [ ] 7.1 Обновить `ValidationStage.process()` в `src/codelab/server/protocol/handlers/pipeline/stages/validation.py`
- [ ] 7.2 Проверить `has_multimodal = any(p.is_multimodal for p in context.content_parts)`
- [ ] 7.3 Разрешить промпт если `has_text or has_multimodal`, отклонить если оба пусты
- [ ] 7.4 Написать тесты: только image проходит, только текст проходит, пустой не проходит

## 8. Слой агента — LLMMessage

- [ ] 8.1 Обновить тип `LLMMessage.content` до `str | list[ContentPart] | None` в `src/codelab/server/llm/models.py`
- [ ] 8.2 Написать тест: LLMMessage со строковым содержимым, LLMMessage с list[ContentPart]

## 9. Слой агента — HistoryBuilder

- [ ] 9.1 Импортировать `ContentPart`, `ACPContentMapper` в `src/codelab/server/agent/history_builder.py`
- [ ] 9.2 Обновить обработку содержимого списка: определять мультимодальные блоки
- [ ] 9.3 Если мультимодальное: конвертировать в `list[ContentPart]` через маппер
- [ ] 9.4 Если только текст: схлопнуть в строку (обратная совместимость)
- [ ] 9.5 Написать тесты: история с image → list[ContentPart], история с текстом → строка

## 10. Слой агента — ExecutionEngine

- [ ] 10.1 Обновить `ExecutionEngine.build_context()` в `src/codelab/server/agent/execution_engine.py`
- [ ] 10.2 Передать `content_parts` как список dict в `AgentContext.prompt`
- [ ] 10.3 Fallback до `[{"type": "text", "text": prompt}]` если нет content_parts
- [ ] 10.4 Написать тест: build_context с мультимодальным содержимым

## 11. Слой провайдеров LLM — OpenAI

- [ ] 11.1 Обновить `OpenAICompatibleProvider.capabilities` до `supports_vision=True` в `src/codelab/server/llm/providers/openai_compatible.py`
- [ ] 11.2 Добавить метод `_content_part_to_openai()`: text → `{"type": "text", ...}`, image → `{"type": "image_url", ...}`
- [ ] 11.3 Обновить `_convert_to_openai_format()` для обработки `list[ContentPart]`
- [ ] 11.4 Написать тесты: форматирование text, форматирование image, форматирование mixed, проверка возможности vision

## 12. Слой провайдеров LLM — Anthropic

- [ ] 12.1 Проверить `AnthropicProvider.capabilities` имеет `supports_vision=True` (уже установлено)
- [ ] 12.2 Добавить метод `_content_part_to_anthropic()`: text → `{"type": "text", ...}`, image → `{"type": "image", "source": ...}`
- [ ] 12.3 Обновить `_convert_to_anthropic_format()` для обработки `list[ContentPart]`
- [ ] 12.4 Написать тесты: форматирование text, форматирование image, форматирование mixed

## 13. Fallback для возможности vision

- [ ] 13.1 В обоих провайдерах проверять `self.capabilities.supports_vision` перед форматированием image
- [ ] 13.2 Если `supports_vision=False`: пропустить image, логировать предупреждение, сохранить text
- [ ] 13.3 Написать тесты: провайдер без vision пропускает image, логирует предупреждение

## 14. Интеграционные тесты

- [ ] 14.1 E2E тест: `session/prompt` с image → LLM получает форматированный image
- [ ] 14.2 E2E тест: `session/prompt` с встроенным ресурсом → LLM получает текстовый fallback
- [ ] 14.3 E2E тест: `session/prompt` со смешанным содержимым → LLM получает мультимодальное
- [ ] 14.4 E2E тест: ответ initialize включает корректные возможности

## 15. Документация

- [ ] 15.1 Обновить docstrings в изменённых файлах
- [ ] 15.2 Добавить примеры использования в docstrings модулей
- [ ] 15.3 Документировать профиль возможностей в auth.py

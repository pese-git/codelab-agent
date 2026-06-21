# Спецификация: Prompt Multimodal Content

## ДОБАВЛЕННЫЕ Требования

### Требование: Объявление возможностей

Система ДОЛЖНА объявлять `image: true` и `embeddedContext: true` в поле `agentCapabilities.promptCapabilities` ответа на `initialize`, согласно ACP 02-Initialization.md.

#### Сценарий: Ответ initialize включает multimodal возможности
- **КОГДА** клиент отправляет запрос `initialize`
- **ТОГДА** ответ включает `agentCapabilities.promptCapabilities.image: true` и `agentCapabilities.promptCapabilities.embeddedContext: true`

#### Сценарий: Возможность audio остаётся отключённой
- **КОГДА** клиент отправляет запрос `initialize`
- **ТОГДА** ответ включает `agentCapabilities.promptCapabilities.audio: false`

### Требование: Валидация содержимого промпта

Система ДОЛЖНА валидировать блоки содержимого `session/prompt` согласно ACP 06-Content.md, принимая типы `text`, `resource_link`, `image` и `resource`, когда они объявлены в возможностях.

#### Сценарий: Валидный блок содержимого image
- **КОГДА** клиент отправляет `session/prompt` с `{"type": "image", "data": "<base64>", "mimeType": "image/png"}`
- **ТОГДА** валидация проходит и промпт обрабатывается

#### Сценарий: Image без обязательных полей
- **КОГДА** клиент отправляет `session/prompt` с `{"type": "image"}` (отсутствуют `data` и `mimeType`)
- **ТОГДА** валидация завершается с ошибкой код `-32602` и сообщением об отсутствующих обязательных полях

#### Сценарий: Валидный встроенный ресурс
- **КОГДА** клиент отправляет `session/prompt` с `{"type": "resource", "resource": {"uri": "file:///path/to/file", "text": "content"}}`
- **ТОГДА** валидация проходит и промпт обрабатывается

#### Сценарий: Resource без URI
- **КОГДА** клиент отправляет `session/prompt` с `{"type": "resource", "resource": {"text": "content"}}` (отсутствует `uri`)
- **ТОГДА** валидация завершается с ошибкой код `-32602`

#### Сценарий: Неподдерживаемый тип содержимого при отключённой возможности
- **КОГДА** клиент отправляет `session/prompt` с `{"type": "audio", ...}` и возможность `audio` равна `false`
- **ТОГДА** валидация завершается с ошибкой код `-32602` и сообщением о неподдерживаемом типе содержимого

### Требование: Доменная модель ContentPart

Система ДОЛЖНА предоставлять `ContentPart` frozen dataclass как доменную модель для multimodal содержимого, с фабричными методами для типобезопасного создания.

#### Сценарий: Создание текстовой части содержимого
- **КОГДА** вызван `ContentPart.text("Hello")`
- **ТОГДА** возвращён `ContentPart(type="text", text="Hello", data=None, mime_type=None)`

#### Сценарий: Создание части содержимого image
- **КОГДА** вызван `ContentPart.image(data="<base64>", mime_type="image/png")`
- **ТОГДА** возвращён `ContentPart(type="image", text=None, data="<base64>", mime_type="image/png")`

#### Сценарий: Неизменяемость ContentPart
- **КОГДА** код пытается изменить `ContentPart.text = "new value"`
- **ТОГДА** возбуждено исключение `FrozenInstanceError`

#### Сценарий: Проверка мультимодальности части содержимого
- **КОГДА** обращён `ContentPart.image(...).is_multimodal`
- **ТОГДА** возвращено `True`

#### Сценарий: Текстовая часть не мультимодальна
- **КОГДА** обращён `ContentPart.text("Hello").is_multimodal`
- **ТОГДА** возвращено `False`

### Требование: Маппер содержимого ACP

Система ДОЛЖНА предоставлять `ACPContentMapper` для конвертации ACP ContentBlock dict в доменные объекты `ContentPart` на границе protocol-domain.

#### Сценарий: Маппинг текстового блока
- **КОГДА** вызван `ACPContentMapper.map_blocks([{"type": "text", "text": "Hello"}])`
- **ТОГДА** возвращён `[ContentPart(type="text", text="Hello")]`

#### Сценарий: Маппинг блока image
- **КОГДА** вызван `ACPContentMapper.map_blocks([{"type": "image", "data": "abc", "mimeType": "image/png"}])`
- **ТОГДА** возвращён `[ContentPart(type="image", data="abc", mime_type="image/png")]`

#### Сценарий: Маппинг встроенного ресурса в текст
- **КОГДА** вызван `ACPContentMapper.map_blocks([{"type": "resource", "resource": {"uri": "file:///test", "text": "content"}}])`
- **ТОГДА** возвращён `[ContentPart(type="text", text="[Resource: file:///test]\ncontent")]`

#### Сценарий: Маппинг смешанных блоков содержимого
- **КОГДА** вызван `ACPContentMapper.map_blocks([{"type": "text", "text": "Look at this:"}, {"type": "image", "data": "abc", "mimeType": "image/png"}])`
- **ТОГДА** возвращён `[ContentPart(type="text", text="Look at this:"), ContentPart(type="image", data="abc", mime_type="image/png")]`

#### Сценарий: Маппинг resource_link в текст
- **КОГДА** вызван `ACPContentMapper.map_blocks([{"type": "resource_link", "uri": "file:///test", "name": "test.txt"}])`
- **ТОГДА** возвращён `[ContentPart(type="text", text="[Resource link: test.txt (file:///test)]")]`

### Требование: Поддержка мультимодальности в PromptContext

Система ДОЛЖНА включать `content_parts: list[ContentPart]` в `PromptContext` для передачи мультимодального содержимого через pipeline.

#### Сценарий: PromptContext с мультимодальным содержимым
- **КОГДА** `PromptContext` создан с `content_parts=[ContentPart.text("Hello"), ContentPart.image(...)]`
- **ТОГДА** поле `content_parts` содержит обе части и доступно всем стадиям pipeline

#### Сценарий: PromptContext по умолчанию с пустым content_parts
- **КОГДА** `PromptContext` создан без `content_parts`
- **ТОГДА** `content_parts` по умолчанию равен пустому списку `[]`

### Требование: Мультимодальное содержимое LLMMessage

Система ДОЛЖНА поддерживать `content: str | list[ContentPart] | None` в `LLMMessage` для представления как текстовых, так и мультимодальных сообщений.

#### Сценарий: Текстовое LLMMessage
- **КОГДА** создано `LLMMessage(role="user", content="Hello")`
- **ТОГДА** `content` является строкой

#### Сценарий: Мультимодальное LLMMessage
- **КОГДА** создано `LLMMessage(role="user", content=[ContentPart.text("Look:"), ContentPart.image(...)])`
- **ТОГДА** `content` является списком объектов `ContentPart`

#### Сценарий: Обратная совместимость со строковым содержимым
- **КОГДА** существующий код создаёт `LLMMessage(role="user", content="text")`
- **ТОГДА** ошибок типов не возникает и downstream код обрабатывает его корректно

### Требование: Конвертация мультимодальности в HistoryBuilder

Система ДОЛЖНА конвертировать блоки мультимодального содержимого в истории сессии в `list[ContentPart]` при построении объектов `LLMMessage`, сохраняя текстовый fallback.

#### Сценарий: История с блоком image
- **КОГДА** история содержит `{"role": "user", "content": [{"type": "text", "text": "Look:"}, {"type": "image", "data": "abc", "mimeType": "image/png"}]}`
- **ТОГДА** `HistoryBuilder.build()` возвращает `LLMMessage(role="user", content=[ContentPart.text("Look:"), ContentPart.image(...)])`

#### Сценарий: История с текстовыми блоками
- **КОГДА** история содержит `{"role": "user", "content": [{"type": "text", "text": "Hello"}]}`
- **ТОГДА** `HistoryBuilder.build()` возвращает `LLMMessage(role="user", content="Hello")` (строка, не список)

#### Сценарий: История с блоком resource
- **КОГДА** история содержит `{"role": "user", "content": [{"type": "resource", "resource": {"uri": "file:///test", "text": "content"}}]}`
- **ТОГДА** `HistoryBuilder.build()` возвращает `LLMMessage(role="user", content="[Resource: file:///test]\ncontent")` (текстовый fallback)

### Требование: Форматирование vision для OpenAI

Система ДОЛЖНА форматировать `ContentPart.image()` как тип содержимого OpenAI `image_url` при отправке в OpenAI-совместимые API.

#### Сценарий: Форматирование image для OpenAI
- **КОГДА** `LLMMessage` содержит `ContentPart(type="image", data="abc", mime_type="image/png")`
- **ТОГДА** провайдер OpenAI форматирует его как `{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}`

#### Сценарий: Форматирование text для OpenAI
- **КОГДА** `LLMMessage` содержит `ContentPart(type="text", text="Hello")`
- **ТОГДА** провайдер OpenAI форматирует его как `{"type": "text", "text": "Hello"}`

#### Сценарий: Провайдер OpenAI объявляет поддержку vision
- **КОГДА** обращён `OpenAICompatibleProvider.capabilities`
- **ТОГДА** возвращён `LLMCapabilities(supports_vision=True, ...)`

### Требование: Форматирование vision для Anthropic

Система ДОЛЖНА форматировать `ContentPart.image()` как тип содержимого Anthropic `image` при отправке в Anthropic API.

#### Сценарий: Форматирование image для Anthropic
- **КОГДА** `LLMMessage` содержит `ContentPart(type="image", data="abc", mime_type="image/png")`
- **ТОГДА** провайдер Anthropic форматирует его как `{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}`

#### Сценарий: Провайдер Anthropic объявляет поддержку vision
- **КОГДА** обращён `AnthropicProvider.capabilities`
- **ТОГДА** возвращён `LLMCapabilities(supports_vision=True, ...)`

### Требование: Fallback для vision возможностей

Система ДОЛЖНА корректно обрабатывать провайдеров без поддержки vision, пропуская части содержимого image и логируя предупреждение.

#### Сценарий: Провайдер без поддержки vision получает image
- **КОГДА** `LLMMessage` содержит `ContentPart(type="image", ...)` и провайдер `supports_vision=False`
- **ТОГДА** часть содержимого image пропущена, предупреждение залогировано, текстовые части сохранены

#### Сценарий: Все части содержимого — image и провайдер не поддерживает vision
- **КОГДА** `LLMMessage` содержит только части image и провайдер `supports_vision=False`
- **ТОГДА** содержимое сообщения становится пустой строкой и предупреждение залогировано

### Требование: Проверка пустого промпта в ValidationStage

Система ДОЛЖНА валидировать, что промпт содержит либо текст, либо мультимодальное содержимое, отклоняя пустые промпты.

#### Сценарий: Промпт только с image проходит валидацию
- **КОГДА** `PromptContext` имеет `raw_text=""`, но `content_parts=[ContentPart.image(...)]`
- **ТОГДА** `ValidationStage` проходит валидацию (без ошибки)

#### Сценарий: Промпт только с текстом проходит валидацию
- **КОГДА** `PromptContext` имеет `raw_text="Hello"` и `content_parts=[ContentPart.text("Hello")]`
- **ТОГДА** `ValidationStage` проходит валидацию

#### Сценарий: Пустой промпт не проходит валидацию
- **КОГДА** `PromptContext` имеет `raw_text=""` и `content_parts=[]`
- **ТОГДА** `ValidationStage` возвращает ответ с ошибкой код `-32602` и сообщением "Empty prompt"

### Требование: Ограничение размера изображения

Система ДОЛЖНА устанавливать максимальный размер изображения 20 МБ для данных изображения в кодировке base64.

#### Сценарий: Изображение в пределах ограничения
- **КОГДА** клиент отправляет изображение с размером данных base64 15 МБ
- **ТОГДА** валидация проходит

#### Сценарий: Изображение превышает ограничение
- **КОГДА** клиент отправляет изображение с размером данных base64 25 МБ
- **ТОГДА** валидация завершается с ошибкой код `-32602` и сообщением о превышении ограничения размера

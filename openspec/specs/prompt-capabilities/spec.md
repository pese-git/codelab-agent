# prompt-capabilities Specification

## Purpose

Мультимодальные возможности промпта (`image`, `audio`, `embeddedContext`) как **один** доменный VO
для обеих сторон: агент их объявляет в `initialize`, клиент читает из ответа. По ACP это
`agentCapabilities.promptCapabilities` — возможности агента принимать контент, а не возможности
клиента (возможности клиента — capability `client-capabilities`: файловая система и терминал).

Создано 2026-08-04 при сведении дублей (tech-debt P2-32): одно понятие жило в трёх местах —
локальный `PromptCapabilityProfile` на сервере, `PromptCapabilities` в клиентском домене и два
поля-заготовки без потребителей в `ClientCapabilities`.

## Requirements

### Requirement: Единый общий тип возможностей промпта

Система SHALL предоставлять `PromptCapabilities` как frozen dataclass в `codelab.shared`:
- `image: bool` — изображения в промпте
- `audio: bool` — аудио в промпте
- `embedded_context: bool` — встроенные ресурсы

Тип MUST быть общим для сервера и клиента (Shared Kernel): форму задаёт спецификация ACP, а не
внутренняя модель одной из сторон.

#### Scenario: Обе стороны используют один тип
- **WHEN** сервер объявляет возможности промпта в `initialize`, а клиент их читает
- **THEN** используется один и тот же `codelab.shared.prompt_capabilities.PromptCapabilities`; локальных копий типа нет

#### Scenario: Baseline без явной поддержки
- **WHEN** создаётся `PromptCapabilities()` без аргументов
- **THEN** все три возможности выключены, `supports_multimodal()` возвращает `false`

#### Scenario: Иммутабельность
- **WHEN** делается попытка присвоить полю значение
- **THEN** возникает ошибка (frozen dataclass)

### Requirement: Wire-форма соответствует ACP

Сериализация MUST использовать имена ACP: `image`, `audio`, `embeddedContext` (camelCase).

#### Scenario: to_dict даёт ACP-имена
- **WHEN** вызывается `to_dict()`
- **THEN** словарь содержит ключи `image`, `audio`, `embeddedContext`

#### Scenario: from_dict читает camelCase
- **WHEN** в `from_dict` приходит `{"embeddedContext": true}`
- **THEN** `embedded_context` равен `true`; snake_case-ключ ACP-формой не является и не читается

#### Scenario: Round-trip без потерь
- **WHEN** VO сериализуется и разбирается обратно
- **THEN** результат равен исходному

#### Scenario: Незнакомые ключи игнорируются
- **WHEN** в `from_dict` приходит ключ вне трёх известных
- **THEN** он игнорируется, разбор не падает

### Requirement: Извлечение из agentCapabilities

`PromptCapabilities` SHALL уметь извлекать себя из блока `agentCapabilities` ответа `initialize`.

#### Scenario: Извлечение вложенного блока
- **WHEN** вызывается `from_agent_capabilities({"promptCapabilities": {...}})`
- **THEN** возвращается VO, собранный из вложенного блока

#### Scenario: Отсутствие блока даёт baseline
- **WHEN** блока `promptCapabilities` нет либо на вход подан `None`
- **THEN** возвращается baseline (все возможности выключены), исключения не возникает

### Requirement: Агент объявляет возможности из единого источника

Сервер MUST объявлять `promptCapabilities` в ответе `initialize` из единственного значения
`_PROMPT_CAPABILITIES` (`server/protocol/handlers/auth.py`), сериализуя его через `to_dict()`.

#### Scenario: Wire-формат ответа initialize не изменился
- **WHEN** клиент вызывает `initialize`
- **THEN** `agentCapabilities.promptCapabilities` содержит `image`, `audio`, `embeddedContext` — как и до сведения дублей

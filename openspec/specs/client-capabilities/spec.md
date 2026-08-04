# client-capabilities Specification

## Purpose
TBD - created by archiving change refactor-domain-models. Update Purpose after archive.
## Requirements
### Requirement: Domain ClientCapabilities

Система SHALL предоставлять `ClientCapabilities` как frozen dataclass:
- `fs_read: bool` — поддержка чтения файлов
- `fs_write: bool` — поддержка записи файлов
- `terminal: bool` — поддержка терминала
- `image_prompts: bool` — поддержка изображений в промптах
- `embedded_context: bool` — поддержка встроенного контекста

#### Scenario: Создание ClientCapabilities
- **WHEN** создается ClientCapabilities
- **THEN** объект содержит поля `fs_read`, `fs_write`, `terminal`, `image_prompts`, `embedded_context`

#### Scenario: ClientCapabilities как frozen dataclass
- **WHEN** создан ClientCapabilities объект
- **THEN** его поля нельзя изменить (immutable)

### Requirement: ClientCapabilities Business Logic

`ClientCapabilities` SHALL предоставлять:
- `supports_fs` property — поддержка файловой системы
- `can_read_files()` — проверка чтения файлов
- `can_write_files()` — проверка записи файлов
- `supports_multimodal()` — поддержка мультимодального контента

#### Scenario: Проверка поддержки файловой системы
- **WHEN** вызывается `supports_fs` property
- **THEN** возвращается `true` если `fs_read` или `fs_write` равны `true`

#### Scenario: Проверка возможности чтения файлов
- **WHEN** вызывается `can_read_files()`
- **THEN** возвращается значение `fs_read`

#### Scenario: Проверка возможности записи файлов
- **WHEN** вызывается `can_write_files()`
- **THEN** возвращается значение `fs_write`

#### Scenario: Проверка поддержки мультимодального контента
- **WHEN** вызывается `supports_multimodal()`
- **THEN** возвращается `true` если `image_prompts` или `embedded_context` равны `true`

### Requirement: Типизированная Session.capabilities

Система SHALL обновить `Session` entity:
- `capabilities: ClientCapabilities` — типизированная модель вместо `dict[str, Any]`

#### Scenario: Session использует типизированные capabilities
- **WHEN** создается Session entity
- **THEN** поле `capabilities` имеет тип `ClientCapabilities` вместо `dict[str, Any]`

### Requirement: Миграция ClientCapabilities

Система SHALL мигрировать все использования `client_capabilities: dict` на `ClientCapabilities`.

#### Scenario: Миграция кодовой базы
- **WHEN** код использует `client_capabilities`
- **THEN** используется типизированная модель `ClientCapabilities` вместо `dict[str, Any]`


### Requirement: Ядро не зависит от конкретной модели client capabilities

Ядро агента MUST получать возможности клиента через порт `ClientCapabilitiesView` (capability
`agent-ports`), а не через конкретную модель — ни персистентную, ни доменную.

> **Уточнение по факту реализации (2026-08-04).** Delta-спека change `acp-independent-agent-core`
> формулировала требование как «ядро оперирует доменным VO `shared.capabilities.ClientCapabilities`».
> Реализация уточнила решение: введён **структурный порт**, который удовлетворяют обе модели без
> конверсии. Это строже по существу — ядро не зависит ни от одной из них, а не переключается с одной
> на другую, и лоссовый маппинг на этом пути невозможен, потому что маппинга нет.
>
> **Свод представлений при этом не сделан** и ведётся как tech-debt P2-32: персистентная
> `ClientRuntimeCapabilities` (три поля) и доменная `ClientCapabilities` (пять полей, из которых
> `image_prompts` и `embedded_context` не имеют потребителей на сервере) существуют по-прежнему.

#### Scenario: tool_filter использует порт, а не модель
- **WHEN** `tool_filter` фильтрует инструменты по возможностям клиента
- **THEN** он типизирован против `ClientCapabilitiesView`, а не против `ClientRuntimeCapabilities` или `ClientCapabilities`

#### Scenario: Обе модели удовлетворяют порт без конверсии
- **WHEN** в ядро приходит любая из двух моделей capabilities
- **THEN** она удовлетворяет порт структурно; конверсии, а значит и потери полей, на этом пути нет

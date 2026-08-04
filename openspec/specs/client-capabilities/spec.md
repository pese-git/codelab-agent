# client-capabilities Specification

## Purpose
TBD - created by archiving change refactor-domain-models. Update Purpose after archive.
## Requirements
### Requirement: Domain ClientCapabilities

Система SHALL предоставлять `ClientCapabilities` как frozen dataclass:
- `fs_read: bool` — поддержка чтения файлов
- `fs_write: bool` — поддержка записи файлов
- `terminal: bool` — поддержка терминала

> **Изменено 2026-08-04 (P2-32).** Поля `image_prompts` и `embedded_context` убраны отсюда: по ACP
> `image`/`audio`/`embeddedContext` входят в `agentCapabilities.promptCapabilities`, то есть
> описывают возможности **агента** принимать контент, а не возможности клиента. Мультимодальность
> сохранена и переехала в `shared.prompt_capabilities.PromptCapabilities`. Здесь эти поля лежали
> дублем без потребителей и создавали видимость лоссового маппинга
> `ClientCapabilities ↔ ClientRuntimeCapabilities`.

#### Scenario: Создание ClientCapabilities
- **WHEN** создается ClientCapabilities
- **THEN** объект содержит поля `fs_read`, `fs_write`, `terminal`

#### Scenario: Мультимодальность не является возможностью клиента
- **WHEN** проверяется поверхность `ClientCapabilities`
- **THEN** полей `image_prompts` / `embedded_context` и метода `supports_multimodal` в ней нет — их носитель `PromptCapabilities`

#### Scenario: Незнакомые ключи в from_dict игнорируются
- **WHEN** в `from_dict` приходит словарь с ключами вне `fs_read`/`fs_write`/`terminal`
- **THEN** они игнорируются, разбор не падает (словари приходят из внешнего обмена)

#### Scenario: ClientCapabilities как frozen dataclass
- **WHEN** создан ClientCapabilities объект
- **THEN** его поля нельзя изменить (immutable)

### Requirement: ClientCapabilities Business Logic

`ClientCapabilities` SHALL предоставлять:
- `supports_fs` property — поддержка файловой системы
- `can_read_files()` — проверка чтения файлов
- `can_write_files()` — проверка записи файлов

#### Scenario: Проверка поддержки файловой системы
- **WHEN** вызывается `supports_fs` property
- **THEN** возвращается `true` если `fs_read` или `fs_write` равны `true`

#### Scenario: Проверка возможности чтения файлов
- **WHEN** вызывается `can_read_files()`
- **THEN** возвращается значение `fs_read`

#### Scenario: Проверка возможности записи файлов
- **WHEN** вызывается `can_write_files()`
- **THEN** возвращается значение `fs_write`

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
> `image_prompts` и `embedded_context` не имели потребителей) существовали по-прежнему.
> **Обновление 2026-08-04:** мультимодальность выделена в `PromptCapabilities`, поэтому доменный VO
> и персистентная модель описывают теперь **один и тот же набор трёх полей** — маппинг между ними
> лосслесс по построению. Остаток P2-32 — свести эти две модели в одну.

#### Scenario: tool_filter использует порт, а не модель
- **WHEN** `tool_filter` фильтрует инструменты по возможностям клиента
- **THEN** он типизирован против `ClientCapabilitiesView`, а не против `ClientRuntimeCapabilities` или `ClientCapabilities`

#### Scenario: Обе модели удовлетворяют порт без конверсии
- **WHEN** в ядро приходит любая из двух моделей capabilities
- **THEN** она удовлетворяет порт структурно; конверсии, а значит и потери полей, на этом пути нет

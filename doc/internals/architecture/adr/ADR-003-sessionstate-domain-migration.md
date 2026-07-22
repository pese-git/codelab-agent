# ADR-003: Протечка SessionState в agent-слой и незавершённая доменная миграция

**Дата:** 20 июля 2026
**Статус:** Принято
**Контекст:** Направление зависимостей между слоями сервера (agent ↔ protocol)
**Авторы:** —
**Связанные документы:**
- `pyproject.toml` — `[tool.importlinter]`, контракт «Server layers» (ratchet)
- `src/codelab/server/protocol/state.py` — `SessionState` (Pydantic-модель)
- `src/codelab/server/domain/session.py` — доменный агрегат `Session`
- `src/codelab/server/mapping/session_mapper.py` — `SessionMapper` (domain ↔ protocol)
- ADR-002 — консолидация Context Manager (потребитель `SessionState` в agent)
- ADR-005 — ACP-независимое ядро агента (read-фаза варианта B = порт `SessionView`)

---

## Контекст

При включении `import-linter` (гейт направления зависимостей) контракт **«Server layers»**
(`transport → protocol → agent → domain`) выявил, что `agent`-слой зависит от `protocol`.
Из выявленных рёбер после устранения runtime-цикла (`ACPContentMapper`, см. историю коммитов)
осталась группа **type-only** зависимостей на `protocol.state`:

| Модуль agent | Использует из `SessionState` |
|---|---|
| `agent/base` | `history` |
| `agent/execution_engine` | `session_id`, `cwd`, `config_values`, `history`, `runtime_capabilities` |
| `agent/system_prompt_builder` | `cwd`, `config_values` |
| `agent/strategies/base` | `history` |
| `agent/strategies/dispatcher` | `session_id`, `config_values` |
| `agent/context/file_cache_decorator` | `session_id` |
| `agent/context/child_session` | `SessionFactory` (тип фабрики) |
| `agent/tool_filter` | `ClientRuntimeCapabilities` (см. актуализацию ниже) |

Плюс замыкающие цепочки `storage/base → protocol.state` и
`tools/executors/decorators/base → protocol.state`.

> **Актуализация (22 июля 2026).** Ребро `runtime_capabilities` (`ClientRuntimeCapabilities`)
> с тех пор живёт в `agent/tool_filter`, а не в `execution_engine`; в `ignore_imports`
> добавлена строка `agent.tool_filter -> protocol.state` (по правилу «расширять строки
> долга»). Таблица выше отражает исходный срез на дату принятия ADR.

Зависимости `agent` — **аннотации типов под `TYPE_CHECKING`**; ни один модуль agent не
**мутирует** сессию и не создаёт `SessionState`. Читаемая поверхность мала и read-only:
`session_id`, `cwd`, `config_values`, `history`, `runtime_capabilities`.

> **Актуализация (22 июля 2026).** Замыкающая цепочка `storage/base` — **не** type-only:
> `storage/base.py` импортирует `SessionState` на уровне модуля (рантайм), ABC-сигнатуры
> `save_session`/`load_session` принимают `SessionState`. Формулировка «все рёбра type-only,
> работе не мешают» к ней неприменима — при эпике B это ребро требует настоящей развязки.

### Корневая причина

Это **не** локальная проблема импортов, а симптом **незавершённой доменной миграции**:

- В проекте **уже есть** доменный агрегат `domain.Session` (config/history/tool_calls/…) и
  **уже есть** `SessionMapper` (domain `Session` ↔ protocol `SessionState`).
- Но в `agent` (бизнес-логику) приходит **протокольно-персистентная `SessionState`**
  (Pydantic, плоская: `cwd`, `config_values`, `history`), а не доменный агрегат
  (`config.cwd`, `history.get_messages()`).
- То есть сериализационная модель **протекает до самого ядра**, минуя агрегат, который
  для этого и создан. Инфраструктура для «правильного» варианта существует, но путь
  `protocol-handlers → execution_engine/strategies` так и не был переведён на агрегат.

> **Актуализация (22 июля 2026).** «Инфраструктура существует» — с оговоркой: `SessionMapper`
> определён, но **не провязан** ни в одном живом пути (единственная ссылка на него — внутри
> собственного модуля и в комментариях `protocol/state.py`). Для эпика B это не готовый
> адаптер к переиспользованию, а незаинтегрированный задел: его нужно сперва довести
> (в т.ч. асимметрию схлопывания роли `tool`) и провязать на границе.

Смежный след той же миграции — дублирование `ClientRuntimeCapabilities` (protocol, Pydantic)
и `ClientCapabilities` (shared VO, вынесен в ADR-эпоху import-linter): одна и та же
концепция в двух представлениях.

## Рассмотренные варианты

**A. Структурный порт `SessionStateView` в agent (hexagonal driven-port).**
Узкий read-only `Protocol` в agent; `protocol.SessionState` удовлетворяет структурно.
- ➕ Каноничный ports-&-adapters / DIP; повышает тестируемость (fake вместо Pydantic);
  низкий риск (только аннотации, проверяется `ty`).
- ➖ Порт зеркалит **плоскую форму `SessionState`** (протокольный вокабуляр), не доменную.
  Не уменьшает тройное дублирование `domain.Session` / `SessionState` / `SessionStateView`,
  а добавляет ещё один тип на синхронизацию. Лечит слоение на бумаге, но не корень.

**B. Передавать в agent доменный агрегат `domain.Session`, маппинг на границе
protocol→agent через существующий `SessionMapper`.**
- ➕ DDD-правильно: ядро работает с агрегатом; `agent → domain` — разрешённое направление;
  устраняет протечку **в источнике**; переиспользует существующую модель; убирает
  дублирование концепции.
- ➖ Крупный рискованный рефактор: весь путь turn-а прошивает `SessionState`, которую
  хендлеры **мутируют** по ходу; маппинг на горячем пути = стоимость + риск; `SessionMapper`
  асимметричен (напр. схлопывание роли `tool`). Эпик на недели.

**C. Спустить `SessionState` в domain/shared.** — Отвергнут: утащит Pydantic и протокольные
типы вниз, ломает чистоту домена, ничего не инвертирует.

## Решение

1. **Целевое архитектурное направление — вариант B** (agent оперирует доменным агрегатом,
   сериализация мапится на границе). Это устраняет корень, а не симптом.
2. **B выполняется как отдельный эпик** — после разбиения God-objects и стабилизации
   Context Manager (см. приоритеты `MEMORY`/ADR-002). Делать его сейчас, в отрыве, —
   несвоевременно и несоразмерно риску.
3. **До эпика B** оставшиеся `agent → protocol.state` (и замыкающие
   `storage/base`, `decorators/base`, `child_session → session_factory`) остаются в
   `import-linter` `ignore_imports` как **осознанный задокументированный долг**. Они
   type-only и работе не мешают; маскировать их порт-зеркалом (вариант A) и объявлять
   проблему решённой — нечестно.
4. Вариант A допустим **только** как сознательный interim, если до эпика B срочно
   понадобится изоляция agent для тестов; тогда — со ссылкой на этот ADR и с явной
   пометкой «временный, растворяется в B». По умолчанию — **не вводить**.

## Последствия

- Контракт «Server layers» остаётся зелёным за счёт `ignore_imports`; эти строки —
  единственный официальный трекер данного долга. Удалять их только по мере выполнения B.
- Новые нарушения направления (вне списка) по-прежнему ломают сборку.
- Дублирование `ClientRuntimeCapabilities` ↔ `ClientCapabilities` рассматривается в
  рамках того же эпика B (унификация session/capabilities представлений).
- До эпика B при добавлении в agent нового чтения из сессии — расширять существующие
  строки долга, **не** вводить обходные абстракции.

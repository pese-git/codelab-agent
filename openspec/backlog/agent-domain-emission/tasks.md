# Доменная эмиссия и прод-вход через AgentRunner — Задачи

> **Статус: заблокировано до появления потребителя.** Признак готовности брать — второй драйвер
> (A2A / hosted multi-user) либо решение переводить прод-loop на `AgentRunner` ради самого turn-а
> (например под pause/resume автомат `ActiveTurn`). Обоснование — в `proposal.md`.
>
> Пункты 1.x–3.x перенесены из change `acp-independent-agent-core` (там были 3.3, 3.4, 4.3).

## Фаза 0: golden wire — предусловие, без него правку не начинать

- [ ] 0.1 Golden-тесты `session/update` для всех четырёх видов: `agent_message_chunk`, `plan`,
      `tool_call`, `tool_call_update` — байт-в-байт снимки текущего wire
- [ ] 0.2 Golden-тест на порядок и немедленность доставки (принцип immediate-delivery:
      уведомления не батчатся к концу turn-а)
- [ ] 0.3 Зафиксировать текущую асимметрию success/exception буферизации тестом **как есть** —
      чтобы правка P1-4 была видимым изменением поведения, а не тихим

## Фаза 1: доменный UpdateSink

- [ ] 1.1 Расширить `UpdateSink` в `agent/contracts/ports.py`: `emit_plan`, `emit_tool_call`,
      `emit_tool_update` с доменными аргументами. Форму аргументов брать **от потребителя**
      (`AgentRunner`), а не из эскиза `design.md`
- [ ] 1.2 Реализовать маппинг домен → ACP wire внутри `SessionUpdateSink` (адаптер)
- [ ] 1.3 Переписать ~10 точек эмиссии в `protocol/handlers/pipeline/stages/agent_loop/` на
      доменные вызовы
- [ ] 1.4 `FakeUpdateSink` в `tests/server/agent/fakes/` — ядро эмитит без ACP
- [ ] 1.5 Golden-тесты Фазы 0 зелёные без изменения снимков

## Фаза 2: унификация буферизации (P1-4)

- [ ] 2.1 Свести success- и exception-ветки эмиссии к одному пути
- [ ] 2.2 Обновить тест из 0.3: асимметрии больше нет, изменение поведения зафиксировано явно

## Фаза 3: прод-вход через AgentRunner

- [ ] 3.1 Turn-loop вызывает `AgentRunner.run_turn` / `continue_turn` вместо прямого
      `ExecutionEngine`
- [ ] 3.2 Согласовать с pause/resume автоматом `ActiveTurn`: пауза на разрешение и на клиентский
      RPC не должна утекать в порт как ACP-специфика
- [ ] 3.3 `StrategyDispatcher` привязан к прод-пути (в `acp-independent-agent-core` `CoreAgentRunner`
      сделан тонким, без dispatcher/EventBus)
- [ ] 3.4 Живой прогон: цепочки «пауза → ответ → возобновление» без обрывов, ноль ошибок,
      инварианты документа сессии целы

## Приёмка

- [ ] П.1 `make check` зелёный; `import-linter` — 4 контракта kept, `ignore_imports` контракта
      «Server layers» остаётся **пустым**
- [ ] П.2 Wire `session/update` байт-в-байт по golden-тестам Фазы 0
- [ ] П.3 Fake-драйвер прогоняет turn с доменной эмиссией без `protocol/`
- [ ] П.4 Живой прогон на рабочем транспорте (stdio через сторонний клиент), разбор логов

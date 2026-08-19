# Backlog

Change'ы, принятые к рассмотрению, но не начатые. Ноль выполненных задач у каждого.

Каталог намеренно лежит вне `openspec/changes/`: CLI `openspec list` показывает только
активную работу, поэтому список в нём отражает то, что действительно делается сейчас.

## Как вернуть change в работу

```bash
git mv openspec/backlog/<change> openspec/changes/<change>
```

После переноса — сверить премисы proposal'а с кодом: часть из них написана давно и могла
устареть. Проверка премис по коду обязательна **до** планирования задач.

## Что здесь лежит

| Change | Задач | Примечание |
| --- | --- | --- |
| `agent-domain-emission` | 18 | Остаток ADR-005: доменная эмиссия `UpdateSink`, прод turn-loop через `AgentRunner`, P1-4. Ждёт второго драйвера |
| `agent-thought-chunk` | 68 | |
| `agents-instructions-support` | 57 | |
| `choreography-strategy` | 29 | Одна из трёх стратегий мультиагента |
| `fix-token-usage-tracking` | 16 | |
| `hierarchical-strategy` | 36 | Одна из трёх стратегий мультиагента |
| `mcp-fallback` | — | Только `proposal.md`, задачи не разложены |
| `orchestrated-strategy` | 45 | Одна из трёх стратегий мультиагента |
| `skills-system-support` | 84 | |

## Открытый вопрос

Три стратегии мультиагента (`choreography`, `hierarchical`, `orchestrated`) — один эпик
с тремя этапами или три независимых change'а. Решается при разборе, не заранее.

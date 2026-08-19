# Design: Система Skills

## Context

### Текущее состояние

CodeLab-агент формирует system prompt через `SystemPromptBuilder`, который объединяет:
1. Agent prompt (роль из `AgentRegistry`)
2. Global prompt (из `config.agent.system_prompt`)
3. MCP info (список подключённых MCP-серверов)

**Проблема**: отсутствует механизм динамического подключения специализированных инструкций (skills).

### Stakeholders

- **Пользователь** — создаёт skills для повторяющихся задач
- **Агент (LLM)** — выбирает и загружает skills по мере необходимости
- **Клиент (Zed/IDE)** — предоставляет workspace для выполнения skill scripts

---

## Goals / Non-Goals

### Goals

1. **Discovery навыков** из `.codelab/skills/` и `.agents/skills/` на сервере
2. **Model-driven activation** — модель сама выбирает навык по description
3. **Progressive disclosure** — catalog → body → resources
4. **Два режима работы**: `local` (прямое чтение) и `remote` (через ACP deploy)
5. **Конфигурируемость** через `codelab.toml`
6. **Кэширование** body навыков для избежания повторного чтения
7. **Slash-команды** `/skill-name` для прямого вызова
8. **Тестируемость** — все компоненты с интерфейсами

### Non-Goals

1. **Search engine (BM25/embedding)** — модель сама выбирает навык
2. **Skill dependencies** — граф зависимостей между навыками
3. **`context: fork` execution** — subagent execution (future work)
4. **Dynamic context injection (`!cmd`)** — shell execution в SKILL.md (future work)
5. **Интеграция `allowed_tools` с PermissionManager** — future work
6. **Код-подпись (code signing)** — криптографическая верификация (future work)

---

## Decisions

### Decision 1: Структура модуля `skills/`

**Решение**: Создать отдельный модуль `src/codelab/server/skills/` с компонентами:

```
skills/
├── __init__.py          # Public exports
├── models.py            # SkillDefinition, SkillResources, DeployedSkill
├── exceptions.py        # SkillError hierarchy
├── cache.py             # SkillCache (body cache)
├── loader.py            # SkillConfigLoader (discovery + parsing)
├── registry.py          # SkillRegistry
├── catalog.py           # SkillCatalogBuilder
├── deployer.py          # SkillDeployer (REMOTE mode)
└── tools.py             # skill/load handler
```

**Обоснование**:
- SRP — каждый компонент отвечает за одну задачу
- OCP — легко добавить новый компонент без изменения существующих
- Тестируемость — каждый компонент изолирован

**Альтернативы**:
- ❌ Один файл `skills.py` — сложно тестировать, нарушает SRP
- ❌ Интеграция в `agent/` — смешение ответственности

---

### Decision 2: Следовать спецификации agentskills.io

**Решение**: Реализовать систему в соответствии с открытым стандартом [Agent Skills](https://agentskills.io).

**Обоснование**:
- Совместимость с экосистемой (Claude Code, VS Code Copilot, Cursor)
- Model-driven activation — не нужен search engine
- Проще в реализации и поддержке

**Альтернативы**:
- ❌ Собственный формат с BM25/embedding — лишняя сложность
- ❌ Manifest v2 с отдельными метаданными — отход от spec

---

### Decision 3: Skills всегда на сервере

**Решение**: Skills — конфигурация агента, хранятся на сервере. Не читать через ACP.

**Обоснование**:
- Skills — конфигурация агента, не проекта
- Агент работает на сервере, skills должны быть доступны локально
- Упрощает архитектуру (не нужен RemoteSkillReader)

**Альтернативы**:
- ❌ Читать skills с клиента через `fs/read_text_file` — лишняя сложность

---

### Decision 4: Lazy Deploy для REMOTE режима

**Решение**: При активации skill в REMOTE режиме — деплоить ресурсы в workspace клиента через ACP `fs/write_text_file`.

**Обоснование**:
- Workspace на клиенте, scripts должны быть там для выполнения
- ACP `terminal/create` выполняется на клиенте
- Lazy Deploy — деплой только при активации (не при старте)
- Hash-based cache invalidation — re-deploy только при изменении

**Альтернативы**:
- ❌ Inline execution — не работает для больших скриптов
- ❌ Синхронизация workspace на сервер — двойное хранение
- ❌ Не выполнять scripts в REMOTE — ограниченная функциональность

---

### Decision 5: Markdown catalog в system prompt

**Решение**: Формат catalog — markdown list.

**Обоснование**:
- Проще для модели (читабельный формат)
- Меньше токенов (нет XML тегов)
- Согласовано с другими частями system prompt

**Формат**:
```markdown
## Available Skills

- **pdf-processing**: Extract PDF text, fill forms, merge files
- **data-analysis**: Analyze datasets, generate charts
```

**Альтернативы**:
- ❌ XML формат (`<available_skills>`) — больше токенов
- ❌ JSON формат — менее читаемо для модели

---

### Decision 6: Поддержка invocation control

**Решение**: Поддержать `disable_model_invocation` и `user_invocable` в MVP.

**Обоснование**:
- Часть spec (Claude Code, VS Code)
- Минимальные изменения в коде
- Важно для UX: sensitive операции (deploy) — только manual

**Альтернативы**:
- ❌ Отложить на future — потеря совместимости

---

### Decision 7: `context: fork` — parse only в MVP

**Решение**: Парсить поле `context` и `agent`, но не реализовывать execution в subagent.

**Обоснование**:
- Полная поддержка — сложная (subagent infrastructure)
- Parse only — future-proofing без complexity

**Альтернативы**:
- ❌ Полная поддержка fork в MVP — слишком сложно
- ❌ Не парсить вообще — потеря совместимости

---

### Decision 8: In-memory cache для body

**Решение**: Кэшировать body навыков в памяти (SkillCache).

**Обоснование**:
- Body < 50KB, в памяти нормально для 500+ навыков
- Repeat reads избегают disk I/O

**Альтернативы**:
- ❌ Disk cache (L2) — overhead для MVP
- ❌ Без кэширования — повторное чтение каждый раз

---

### Decision 9: Hash-based cache invalidation

**Решение**: Вычислять SHA-256 hash для SKILL.md + resources.

**Обоснование**:
- Простая и надёжная проверка изменений
- Не зависит от timestamp (проблемы с FS)

**Альтернативы**:
- ❌ mtime-based — ненадёжно (timezone, FS differences)
- ❌ Без invalidation — stale cache

---

### Decision 10: Trust model для project skills

**Решение**: Project skills — untrusted, warn перед deploy.

**Обоснование**:
- Project skills могут быть из untrusted repository
- User skills — доверенные (принадлежат пользователю)

**Альтернативы**:
- ❌ Auto-deploy для всех — security risk
- ❌ Block для всех — ограниченная функциональность

---

### Decision 11: Нет отдельного `skill/read_resource` tool

**Решение**: Использовать существующий `fs/read_text_file` для чтения ресурсов.

**Обоснование**:
- Не дублировать функциональность (SRP)
- `skill/load` возвращает `base_dir`, модель использует абсолютные пути

**Альтернативы**:
- ❌ Создать `skill/read_resource` — дублирование

---

## Risks / Trade-offs

### Risk 1: Malicious deploy в REMOTE режиме

**Риск**: Сервер может подменить содержимое skill scripts перед деплоем на клиент.

**Митигация**:
- Trust model: warn для project skills
- Audit logging всех deploy операций
- Future: code signing

---

### Risk 2: Производительность discovery

**Риск**: 500+ skills могут замедлить discovery.

**Митигация**:
- Benchmark: target < 100ms для 500 skills
- Lazy body loading (не читать body при discovery)
- In-memory cache для body

---

### Risk 3: Path traversal уязвимость

**Риск**: Malicious skill может попытаться выйти за пределы skill directory.

**Митигация**:
- Path validation: `resolved.is_relative_to(base_dir)`
- Unit tests для security cases

---

### Risk 4: Stale cache в REMOTE

**Риск**: Deploy cache может стать неактуальным.

**Митигация**:
- Hash-based invalidation
- Re-deploy при изменении hash

---

## Migration Plan

### Phase 1: Core (Week 1)

1. Создать модуль `skills/`
2. Реализовать `models.py`, `exceptions.py`, `cache.py`
3. Реализовать `loader.py`, `registry.py`
4. Unit tests

**Rollback**: Удалить модуль.

### Phase 2: Activation (Week 2)

1. Реализовать `catalog.py`, `tools.py`
2. Интеграция в `SystemPromptBuilder`
3. Регистрация `skill/load` tool
4. Slash command registration
5. DI integration

### Phase 3: REMOTE (Week 3)

1. Реализовать `deployer.py`
2. REMOTE mode detection
3. Deploy flow integration
4. Unit tests для deployer

### Phase 4: Polish (Week 4)

1. Integration tests
2. Performance tests
3. Documentation
4. Security review

---

## Open Questions

1. **Нужен ли fallback при ошибке deploy?** — Пропустить skill или вернуть ошибку?
   - **Решение**: Вернуть ошибку, логировать.

2. **Поддерживать ли вложенные skills?** — Skills в поддиректориях?
   - **Решение**: Нет в MVP. Только один уровень вложенности.

3. **Нужен ли API для получения списка загруженных skills?**
   - **Решение**: Нет в MVP. Можно добавить через `_meta` в response.

# Tasks: Система Skills

## 1. Модуль `skills/` — основа

- [ ] 1.1 Создать структуру модуля `src/codelab/server/skills/`
- [ ] 1.2 Создать `__init__.py` с экспортами
- [ ] 1.3 Создать `exceptions.py` — классы `SkillError`, `SkillNotFoundError`, `SkillLoadError`, `SkillPathTraversalError`
- [ ] 1.4 Создать `models.py` — dataclass `SkillDefinition`, `SkillResources`, `DeployedSkill`

---

## 2. Cache — кэширование body

- [ ] 2.1 Создать `cache.py` — класс `SkillCache`
- [ ] 2.2 Реализовать `get()`, `set()`, `invalidate()`, `clear()`
- [ ] 2.3 Добавить тесты `test_cache.py`

---

## 3. Loader — discovery и парсинг

- [ ] 3.1 Создать `loader.py` — класс `SkillConfigLoader`
- [ ] 3.2 Реализовать `load_all()` — сканирование scopes
- [ ] 3.3 Реализовать `parse_skill_md()` — парсинг YAML frontmatter
- [ ] 3.4 Добавить валидацию имени (regex, длина, consecutive hyphens)
- [ ] 3.5 Добавить обработку collision (project > user)
- [ ] 3.6 Добавить логирование discovery операций
- [ ] 3.7 Добавить тесты `test_loader.py`

---

## 4. Registry — центральный реестр

- [ ] 4.1 Создать `registry.py` — класс `SkillRegistry`
- [ ] 4.2 Реализовать `initialize()` — загрузка через loader
- [ ] 4.3 Реализовать `get()`, `get_all()`
- [ ] 4.4 Реализовать `load_body()` — с кэшированием
- [ ] 4.5 Реализовать `list_resources()` — перечисление scripts/, references/, assets/
- [ ] 4.6 Добавить тесты `test_registry.py`

---

## 5. Catalog — генерация catalog для system prompt

- [ ] 5.1 Создать `catalog.py` — класс `SkillCatalogBuilder`
- [ ] 5.2 Реализовать `build_catalog()` — markdown list
- [ ] 5.3 Реализовать `build_behavioral_instructions()` — инструкции для модели
- [ ] 5.4 Добавить фильтрацию `disable_model_invocation=True`
- [ ] 5.5 Добавить truncation `MAX_DESCRIPTION_LENGTH = 200`
- [ ] 5.6 Добавить лимит `MAX_CATALOG_SKILLS = 100`
- [ ] 5.7 Добавить тесты `test_catalog.py`

---

## 6. Deployer — Lazy Deploy для REMOTE

- [ ] 6.1 Создать `deployer.py` — класс `SkillDeployer`
- [ ] 6.2 Реализовать `deploy_if_needed()` — деплой при изменении hash
- [ ] 6.3 Реализовать `_compute_hash()` — SHA-256 для SKILL.md + resources
- [ ] 6.4 Реализовать `_get_client_base_dir()` — target path на клиенте
- [ ] 6.5 Реализовать `_list_all_resources()` — все ресурсы (relative paths)
- [ ] 6.6 Реализовать `_read_resource()` — чтение содержимого
- [ ] 6.7 Добавить `invalidate()`, `clear()` для кэша deploy
- [ ] 6.8 Добавить тесты `test_deployer.py` (mock ClientRPCBridge)

---

## 7. Tools — skill/load handler

- [ ] 7.1 Создать `tools.py` — функция `create_skill_load_handler()`
- [ ] 7.2 Реализовать ToolDefinition для `skill/load`
- [ ] 7.3 Реализовать handler — загрузка body + resources
- [ ] 7.4 Добавить REMOTE mode detection и вызов deployer
- [ ] 7.5 Добавить форматирование output (body + base_dir + resources)
- [ ] 7.6 Добавить тесты `test_tools.py`

---

## 8. Конфигурация — интеграция в AppConfig

- [ ] 8.1 Модифицировать `src/codelab/server/config.py` — добавить `SkillsConfig`
- [ ] 8.2 Добавить секцию `skills` в `AppConfig`
- [ ] 8.3 Добавить переменные окружения `CODELAB_SKILLS_ENABLED`, `CODELAB_SKILLS_MAX_CATALOG`
- [ ] 8.4 Обновить `AppConfig.load()` для загрузки `[skills]`
- [ ] 8.5 Обновить тесты конфигурации

---

## 9. SystemPromptBuilder — интеграция

- [ ] 9.1 Модифицировать `SystemPromptBuilder.__init__()` — добавить `skill_registry`
- [ ] 9.2 Модифицировать `build()` — добавить skill catalog + instructions
- [ ] 9.3 Порядок: agent prompt → skill catalog → global prompt → MCP info
- [ ] 9.4 Обновить тесты `test_system_prompt_builder.py`

---

## 10. DI-контейнер — регистрация

- [ ] 10.1 Модифицировать `src/codelab/server/di.py` — добавить `SkillsProvider`
- [ ] 10.2 Добавить `get_skill_cache()`, `get_skill_config_loader()`, `get_skill_registry()`
- [ ] 10.3 Добавить `get_skill_catalog_builder()`, `get_skill_deployer()`
- [ ] 10.4 Обновить `get_system_prompt_builder()` — передать `skill_registry`
- [ ] 10.5 Обновить `ToolsProvider` — регистрация `skill/load` tool

---

## 11. SlashCommandRouter — регистрация skills

- [ ] 11.1 Добавить регистрацию skills как `/skill-name` команд
- [ ] 11.2 Фильтрация по `user_invocable=True`
- [ ] 11.3 Обработка `$ARGUMENTS` substitution
- [ ] 11.4 Добавить тесты

---

## 12. Тесты — модуль skills

- [ ] 12.1 Создать `tests/server/skills/` структуру
- [ ] 12.2 Создать `test_models.py` — тесты dataclasses
- [ ] 12.3 Создать `test_exceptions.py` — тесты exception hierarchy
- [ ] 12.4 Создать `test_cache.py` — тесты кэша
- [ ] 12.5 Создать `test_loader.py` — тесты discovery + parsing
- [ ] 12.6 Создать `test_registry.py` — тесты registry
- [ ] 12.7 Создать `test_catalog.py` — тесты catalog builder
- [ ] 12.8 Создать `test_deployer.py` — тесты deployer
- [ ] 12.9 Создать `test_tools.py` — тесты skill/load handler

---

## 13. Тесты — интеграция

- [ ] 13.1 Создать `test_skills_integration.py` — end-to-end flow
- [ ] 13.2 Тест: Discovery → Catalog → Activation
- [ ] 13.3 Тест: Slash command invocation
- [ ] 13.4 Тест: REMOTE deploy flow (mock client)
- [ ] 13.5 Тест: Path traversal blocked
- [ ] 13.6 Тест: Hash-based cache invalidation

---

## 14. Документация

- [ ] 14.1 Обновить `AGENTS.md` — описать новый модуль
- [ ] 14.2 Создать `doc/specs/skills-system-specification.md` — полная спецификация
- [ ] 14.3 Создать `doc/specs/adr-001-skills-system.md` — ADR
- [ ] 14.4 Добавить пример конфигурации в `codelab.toml.example`
- [ ] 14.5 Добавить примеры skills в `doc/examples/skills/`

---

## 15. Проверки

- [ ] 15.1 Запустить `uv run ruff check .` — линтер
- [ ] 15.2 Запустить `uv run ty check` — тайпчекер
- [ ] 15.3 Запустить `uv run python -m pytest tests/server/skills/` — тесты модуля
- [ ] 15.4 Запустить `uv run python -m pytest tests/server/agent/test_system_prompt_builder.py` — тесты builder
- [ ] 15.5 Запустить `make check` — полная проверка

---

## Зависимости задач

```
1.x → 2.x → 3.x → 4.x → 5.x → 6.x → 7.x → 8.x → 9.x → 10.x → 11.x → 12.x → 13.x → 14.x → 15.x
```

**Критический путь**: 1.4 → 3.2 → 4.2 → 5.2 → 7.2 → 9.2 → 10.1 → 12.5 → 13.1 → 15.5

---

## Оценка объёма

| Группа | Количество задач | Примерное время |
|--------|------------------|-----------------|
| 1. Основа | 4 | 1 час |
| 2. Cache | 3 | 30 мин |
| 3. Loader | 7 | 3 часа |
| 4. Registry | 6 | 2 часа |
| 5. Catalog | 7 | 2 часа |
| 6. Deployer | 8 | 3 часа |
| 7. Tools | 6 | 2 часа |
| 8. Конфигурация | 5 | 1 час |
| 9. SystemPromptBuilder | 4 | 1 час |
| 10. DI-контейнер | 5 | 1 час |
| 11. SlashCommandRouter | 4 | 1 час |
| 12. Тесты модуля | 9 | 4 часа |
| 13. Тесты интеграции | 6 | 3 часа |
| 14. Документация | 5 | 2 часа |
| 15. Проверки | 5 | 1 час |
| **Итого** | **84** | **~27 часов** |

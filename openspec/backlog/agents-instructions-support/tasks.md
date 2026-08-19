# Tasks: Поддержка AGENTS.md инструкций

## 1. Модуль `instructions/` — основа

- [ ] 1.1 Создать структуру модуля `src/codelab/server/agent/instructions/`
- [ ] 1.2 Создать `__init__.py` с экспортами
- [ ] 1.3 Создать `config.py` — Pydantic модель `AgentsInstructionsConfig`
- [ ] 1.4 Создать `protocol.py` — Protocol `AgentsFileReader`
- [ ] 1.5 Создать `sanitizer.py` — класс `AgentsFileSanitizer` с regex-паттернами

---

## 2. Readers — чтение файлов

- [ ] 2.1 Создать `local_reader.py` — класс `LocalAgentsFileReader`
- [ ] 2.2 Реализовать `LocalAgentsFileReader.read()` с `Path.read_text()`
- [ ] 2.3 Добавить проверку `max_file_size` в local reader
- [ ] 2.4 Добавить обработку ошибок (FileNotFoundError, PermissionError)
- [ ] 2.5 Создать `remote_reader.py` — класс `RemoteAgentsFileReader`
- [ ] 2.6 Реализовать `RemoteAgentsFileReader.read()` через `ClientRPCBridge.read_file()`
- [ ] 2.7 Добавить обработку ошибок remote reader (timeout, capability missing)

---

## 3. Discovery — поиск файлов

- [ ] 3.1 Создать `discovery.py` — класс `AgentsFileDiscovery`
- [ ] 3.2 Реализовать `discover(cwd)` — поиск в корне (root-only)
- [ ] 3.3 Реализовать приоритетный список `file_names`
- [ ] 3.4 Добавить логирование discovery операций

---

## 4. Merger — объединение инструкций

- [ ] 4.1 Создать `merger.py` — класс `AgentsFileMerger`
- [ ] 4.2 Реализовать `merge(files)` — объединение с указанием источника
- [ ] 4.3 Форматирование: `### Instructions from \`{path}\``

---

## 5. Resolver — оркестрация

- [ ] 5.1 Создать `resolver.py` — класс `AgentsInstructionsResolver`
- [ ] 5.2 Реализовать `resolve(session, bridge)` — основной метод
- [ ] 5.3 Добавить кэширование (CacheEntry с hash и timestamp)
- [ ] 5.4 Реализовать проверку актуальности кэша
- [ ] 5.5 Интегрировать discovery → read → sanitize → merge

---

## 6. Конфигурация — интеграция в AppConfig

- [ ] 6.1 Модифицировать `src/codelab/server/config.py` — добавить `AgentsInstructionsConfig`
- [ ] 6.2 Добавить секцию `instructions` в `AgentsConfig`
- [ ] 6.3 Добавить переменные окружения `CODELAB_INSTRUCTIONS_MODE`, `CODELAB_INSTRUCTIONS_MAX_FILE_SIZE`
- [ ] 6.4 Обновить `AppConfig.load()` для загрузки `[agents.instructions]`

---

## 7. SystemPromptBuilder — интеграция

- [ ] 7.1 Модифицировать `SystemPromptBuilder.__init__()` — добавить `instructions_resolver`
- [ ] 7.2 Изменить `build()` на `async def build()`
- [ ] 7.3 Добавить вызов `resolver.resolve()` между agent prompt и global prompt
- [ ] 7.4 Обновить вызывающий код (`AgentLoop`, `LLMLoopStage`) для `await build()`
- [ ] 7.5 Обновить тесты `SystemPromptBuilder` на async

---

## 8. DI-контейнер — регистрация

- [ ] 8.1 Модифицировать `src/codelab/server/di.py` — добавить `get_agents_instructions_resolver`
- [ ] 8.2 Добавить `get_agents_file_reader` (factory по mode)
- [ ] 8.3 Обновить `get_system_prompt_builder` — передать resolver
- [ ] 8.4 Обновить `get_llm_loop_stage` — передать client_rpc_bridge

---

## 9. Тесты — модуль instructions

- [ ] 9.1 Создать `tests/server/agent/instructions/` структуру
- [ ] 9.2 Создать `test_config.py` — тесты конфигурации
- [ ] 9.3 Создать `test_sanitizer.py` — тесты санитизации
- [ ] 9.4 Создать `test_local_reader.py` — тесты local reader
- [ ] 9.5 Создать `test_remote_reader.py` — тесты remote reader (mock bridge)
- [ ] 9.6 Создать `test_discovery.py` — тесты discovery
- [ ] 9.7 Создать `test_merger.py` — тесты merger
- [ ] 9.8 Создать `test_resolver.py` — тесты resolver (end-to-end)

---

## 10. Тесты — интеграция

- [ ] 10.1 Обновить `tests/server/agent/test_system_prompt_builder.py` — async + instructions
- [ ] 10.2 Создать `test_system_prompt_integration.py` — интеграция builder + resolver
- [ ] 10.3 Обновить `tests/server/test_config.py` — новая секция конфигурации
- [ ] 10.4 Обновить существующие тесты на async `build()`

---

## 11. Документация

- [ ] 11.1 Обновить `AGENTS.md` — описать новый модуль
- [ ] 11.2 Обновить `doc/protocols/AGENTS-GUIDE.md` — упомянуть поддержку
- [ ] 11.3 Добавить пример конфигурации в `codelab.toml.example`

---

## 12. Проверки

- [ ] 12.1 Запустить `uv run ruff check .` — линтер
- [ ] 12.2 Запустить `uv run ty check` — тайпчекер
- [ ] 12.3 Запустить `uv run python -m pytest tests/server/agent/instructions/` — тесты модуля
- [ ] 12.4 Запустить `uv run python -m pytest tests/server/agent/test_system_prompt_builder.py` — тесты builder
- [ ] 12.5 Запустить `make check` — полная проверка

---

## Зависимости задач

```
1.x → 2.x → 3.x → 4.x → 5.x → 6.x → 7.x → 8.x → 9.x → 10.x → 11.x → 12.x
```

**Критический путь**: 1.3 → 2.1 → 3.1 → 4.1 → 5.1 → 7.1 → 8.1 → 9.8 → 10.1 → 12.5

---

## Оценка объёма

| Группа | Количество задач | Примерное время |
|--------|------------------|-----------------|
| 1. Основа | 5 | 1 час |
| 2. Readers | 7 | 2 часа |
| 3. Discovery | 4 | 1 час |
| 4. Merger | 3 | 30 мин |
| 5. Resolver | 5 | 2 часа |
| 6. Конфигурация | 4 | 1 час |
| 7. SystemPromptBuilder | 5 | 2 часа |
| 8. DI-контейнер | 4 | 1 час |
| 9. Тесты модуля | 8 | 3 часа |
| 10. Тесты интеграции | 4 | 2 часа |
| 11. Документация | 3 | 1 час |
| 12. Проверки | 5 | 30 мин |
| **Итого** | **57** | **~16 часов** |

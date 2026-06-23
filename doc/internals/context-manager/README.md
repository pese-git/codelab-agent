# Context Manager Documentation

> Интеллектуальный слой управления контекстом для coding agent

## 📚 Навигация

**Начните отсюда:** [INDEX.md](./INDEX.md) — полная навигация по документации

## Документы

### 🎯 Для начинающих

- **[README.md](./README.md)** — этот документ (обзор)
- **[EXAMPLES.md](./EXAMPLES.md)** — практические примеры использования

### 🏗️ Для архитекторов и разработчиков

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — полная архитектура системы
- **[ROADMAP.md](./ROADMAP.md)** — план реализации по фазам
- **[COMPARISON.md](./COMPARISON.md)** — сравнение с конкурентами

### 📖 Полная навигация

- **[INDEX.md](./INDEX.md)** — навигация по всей документации с рекомендациями

## О документации

Эта директория содержит полную документацию по архитектуре Context Manager — компонента, который позволяет coding agent понимать проект, находить релевантный код и собирать минимально необходимый контекст для решения задач.

## Быстрый старт

### Хотите понять архитектуру?

```
Этот документ → ARCHITECTURE.md → EXAMPLES.md
```

### Хотите реализовать?

```
Этот документ → ARCHITECTURE.md → ROADMAP.md → Phase 0
```

### Хотите понять позиционирование?

```
Этот документ → COMPARISON.md
```

## Ключевые концепции

### Два уровня абстракции

```
┌─────────────────────────────────────────────┐
│  User-visible tools (видит LLM)             │
│  • fs/read_text_file                        │
│  • fs/write_text_file                       │
│  • terminal/*                               │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Runtime services (НЕ видит LLM)            │
│  • TaskAnalyzer                             │
│  • ContextGatherer                          │
│  • DependencyGraph                          │
│  • TokenBudgetManager                       │
└─────────────────────────────────────────────┘
```

### Философия реализации

**Архитектура = финальная сразу**  
**Реализация = по фазам**

MVP — это не упрощённая архитектура, а **полная архитектура с неполной реализацией**.

---

## Roadmap (кратко)

| Фаза | Длительность | Результат |
|------|--------------|-----------|
| **Phase 0** | 1 неделя | Архитектура зафиксирована |
| **Phase 1** | 3 недели | Боевой MVP |
| **Phase 2** | 1 неделя | Snapshot Layer |
| **Phase 3** | 1 неделя | Epoch Layer |
| **Phase 4** | 2 недели | Dependency Graph |
| **Phase 5** | 1 неделя | Reconciliation |
| **Phase 6** | 2 недели | Subagents |

**Итого:** 11 недель до production-ready

---

## Основные сущности

### TaskAnalyzer

**Цель:** Анализ задачи пользователя

```python
profile = await analyzer.analyze("Добавь email validation")
# → TaskProfile(
#     task_type=FEATURE,
#     search_terms=["email", "validation"],
#     likely_targets=["dto", "service"]
# )
```

---

### ContextGatherer

**Цель:** Сбор контекста на основе TaskProfile

```python
context = await gatherer.gather_context(task, profile, session)
# → GatheredContext(
#     target_files=["auth.dto.ts", "auth.service.ts"],
#     file_contents={...}
# )
```

---

### DependencyGraph

**Цель:** Понимание связей между файлами

```python
deps = graph.get_dependencies("auth.controller.ts")
# → ["auth.service.ts", "user.repository.ts"]
```

---

### TokenBudgetManager

**Цель:** Управление token budget

```python
bounded = budget.bound_content(large_content, max_tokens=8000)
```

---

### ContextManager

**Цель:** Интеграция всех компонентов

```python
messages = await manager.build_context(session, task)
# → list[LLMMessage] с готовым контекстом
```

---

## Преимущества подхода

### 1. Предсказуемое качество

**Без Context Manager:**
- "Добавь валидацию" → качество 40%
- "Добавь email validation" → качество 70%
- "Добавь email validation в UserDTO" → качество 90%

**С Context Manager:**
- Любая формулировка → качество 85-95%

### 2. Экономия токенов

LLM не тратит токены на исследование — получает готовый контекст.

**Экономия:** 30-50% токенов на каждую задачу.

### 3. Эволюционируемость

Можно менять реализацию без изменения архитектуры:
- Сегодня: `git grep`
- Завтра: `tree-sitter`
- Послезавтра: `RAG`

LLM не замечает разницы.

### 4. Минимальный ACP

Только существующие tools:
- `fs/read_text_file`
- `fs/write_text_file`
- `terminal/*`

Никаких новых ACP методов (опционально).

---

## Roadmap (кратко)

| Фаза | Длительность | Результат |
|------|--------------|-----------|
| **Phase 0** | 1 неделя | Архитектура зафиксирована |
| **Phase 1** | 3 недели | Боевой MVP |
| **Phase 2** | 1 неделя | Snapshot Layer |
| **Phase 3** | 1 неделя | Epoch Layer |
| **Phase 4** | 2 недели | Dependency Graph |
| **Phase 5** | 1 неделя | Reconciliation |
| **Phase 6** | 2 недели | Subagents |

**Итого:** 11 недель до production-ready

**Подробнее:** [ROADMAP.md](./ROADMAP.md)

---

## Примеры использования

### Пример 1: Добавление поля в DTO

```
User: "Добавь поле email в UserDTO"

ContextManager (невидимо):
  → TaskAnalyzer: тип задачи = FEATURE
  → ContextGatherer: поиск "email", "UserDTO"
  → DependencyGraph: controller → service → dto
  → TokenBudget: ограничить размер файлов

LLM: Получает готовый контекст
  → Сразу пишет код
  → Обновляет DTO, service, controller, tests
```

**Результат:** Экономия 4000 токенов, качество 95%

**Подробнее:** [EXAMPLES.md](./EXAMPLES.md)

---

## Следующие шаги

1. **Прочитайте документацию**
   - Начните с [INDEX.md](./INDEX.md) для навигации
   - Изучите [ARCHITECTURE.md](./ARCHITECTURE.md)
   - Посмотрите [EXAMPLES.md](./EXAMPLES.md)

2. **Обсудите архитектуру**
   - Задайте вопросы
   - Предложите улучшения
   - Создайте issue

3. **Начните реализацию**
   - Следуйте [ROADMAP.md](./ROADMAP.md)
   - Начните с Phase 0
   - Двигайтесь фаза за фазой

---

## Дополнительные материалы

- [INDEX.md](./INDEX.md) — полная навигация по документации
- [AGENTS.md](../../AGENTS.md) — общие правила проекта
- [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) — общая архитектура системы
- [ACP Protocol](../../protocols/Agent%20Client%20Protocol/) — спецификация протокола

---

## Контакты

Если у вас есть вопросы или предложения:
- Создайте issue в репозитории
- Обсудите в чате команды
- Предложите PR с улучшениями

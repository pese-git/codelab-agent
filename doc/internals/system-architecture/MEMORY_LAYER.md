# Memory Layer — Память между сессиями

> Компоненты для сохранения и использования памяти задач, сессий и проектов

## Оглавление

- [Обзор](#обзор)
- [TaskMemory](#taskmemory)
- [SessionMemory](#sessionmemory)
- [ProjectMemory](#projectmemory)
- [Интеграция с ContextManager](#интеграция-с-contextmanager)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Memory Layer отвечает за **сохранение памяти** между сессиями и использование её для улучшения качества работы агента.

**Компоненты:**
- `TaskMemory` — память о задачах (что делали, какие решения принимали)
- `SessionMemory` — память сессии (контекст текущей сессии)
- `ProjectMemory` — память проекта (структура, паттерны, зависимости)

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  ├─ TaskMemory       ← Memory Layer                          │
│  ├─ SessionMemory    ← Memory Layer                          │
│  └─ ProjectMemory    ← Memory Layer                          │
└─────────────────────────────────────────────────────────────┘
```

---

## TaskMemory

### Назначение

Память о задачах: что делали, какие решения принимали, какие файлы изменяли.

**Зачем нужно:**
- Не повторять одни и те же ошибки
- Использовать предыдущие решения
- Понимать контекст задачи

### Интерфейс

```python
@dataclass
class TaskRecord:
    """Запись о задаче."""
    task_id: str
    task_description: str
    created_at: datetime
    completed_at: datetime | None
    status: Literal["pending", "in_progress", "completed", "failed"]
    files_modified: list[str]
    decisions: list[str]  # Какие решения принимали
    errors: list[str]  # Какие ошибки возникали
    solution_summary: str  # Краткое описание решения

class TaskMemory:
    """Память о задачах."""
    
    def __init__(self, storage: MemoryStorage):
        self.storage = storage
    
    async def save_task(self, record: TaskRecord) -> None:
        """Сохранить запись о задаче."""
        await self.storage.save(f"task:{record.task_id}", record)
    
    async def get_task(self, task_id: str) -> TaskRecord | None:
        """Получить запись о задаче."""
        return await self.storage.load(f"task:{task_id}")
    
    async def search_similar_tasks(
        self,
        description: str,
        limit: int = 5,
    ) -> list[TaskRecord]:
        """Найти похожие задачи."""
        all_tasks = await self.storage.list("task:*")
        
        # Простое сравнение по ключевым словам
        scored = []
        for task in all_tasks:
            score = self._calculate_similarity(description, task.task_description)
            scored.append((score, task))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [task for _, task in scored[:limit]]
    
    async def get_task_history(self, file_path: str) -> list[TaskRecord]:
        """Получить историю изменений файла."""
        all_tasks = await self.storage.list("task:*")
        return [
            task for task in all_tasks
            if file_path in task.files_modified
        ]
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Вычислить сходство между текстами."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0
```

### Пример использования

```python
memory = TaskMemory(storage)

# Сохранить задачу
await memory.save_task(TaskRecord(
    task_id="task_123",
    task_description="Добавить email validation",
    created_at=datetime.now(),
    completed_at=datetime.now(),
    status="completed",
    files_modified=["src/auth.dto.ts", "src/auth.service.ts"],
    decisions=[
        "Использовать class-validator для валидации",
        "Добавить @IsEmail() декоратор"
    ],
    errors=[],
    solution_summary="Добавил валидацию email через class-validator"
))

# Найти похожие задачи
similar = await memory.search_similar_tasks("добавить валидацию телефона")
for task in similar:
    print(f"{task.task_id}: {task.task_description}")

# Получить историю файла
history = await memory.get_task_history("src/auth.service.ts")
for task in history:
    print(f"{task.created_at}: {task.solution_summary}")
```

---

## SessionMemory

### Назначение

Память сессии: контекст текущей сессии, какие файлы открыты, какие изменения сделаны.

**Зачем нужно:**
- Сохранять контекст между turns
- Понимать что уже делали в этой сессии
- Не повторять одни и те же действия

### Интерфейс

```python
@dataclass
class SessionContext:
    """Контекст сессии."""
    session_id: str
    started_at: datetime
    files_opened: list[str]
    files_modified: list[str]
    decisions_made: list[str]
    errors_encountered: list[str]
    current_task: str | None

class SessionMemory:
    """Память сессии."""
    
    def __init__(self, storage: MemoryStorage):
        self.storage = storage
    
    async def update_context(
        self,
        session_id: str,
        updates: dict[str, Any],
    ) -> None:
        """Обновить контекст сессии."""
        context = await self.get_context(session_id)
        
        if context is None:
            context = SessionContext(
                session_id=session_id,
                started_at=datetime.now(),
                files_opened=[],
                files_modified=[],
                decisions_made=[],
                errors_encountered=[],
                current_task=None
            )
        
        for key, value in updates.items():
            if hasattr(context, key):
                current = getattr(context, key)
                if isinstance(current, list):
                    current.extend(value)
                else:
                    setattr(context, key, value)
        
        await self.storage.save(f"session:{session_id}", context)
    
    async def get_context(self, session_id: str) -> SessionContext | None:
        """Получить контекст сессии."""
        return await self.storage.load(f"session:{session_id}")
    
    async def add_file_opened(
        self,
        session_id: str,
        file_path: str,
    ) -> None:
        """Добавить файл в список открытых."""
        await self.update_context(session_id, {"files_opened": [file_path]})
    
    async def add_file_modified(
        self,
        session_id: str,
        file_path: str,
    ) -> None:
        """Добавить файл в список изменённых."""
        await self.update_context(session_id, {"files_modified": [file_path]})
    
    async def add_decision(
        self,
        session_id: str,
        decision: str,
    ) -> None:
        """Добавить решение."""
        await self.update_context(session_id, {"decisions_made": [decision]})
    
    async def add_error(
        self,
        session_id: str,
        error: str,
    ) -> None:
        """Добавить ошибку."""
        await self.update_context(session_id, {"errors_encountered": [error]})
```

### Пример использования

```python
memory = SessionMemory(storage)

# Обновить контекст сессии
await memory.update_context("session_123", {
    "current_task": "Добавить email validation"
})

# Добавить открытый файл
await memory.add_file_opened("session_123", "src/auth.dto.ts")

# Добавить изменённый файл
await memory.add_file_modified("session_123", "src/auth.dto.ts")

# Добавить решение
await memory.add_decision(
    "session_123",
    "Использовать class-validator для валидации"
)

# Получить контекст сессии
context = await memory.get_context("session_123")
print(context.files_modified)  # ["src/auth.dto.ts"]
print(context.decisions_made)  # ["Использовать class-validator..."]
```

---

## ProjectMemory

### Назначение

Память проекта: структура проекта, паттерны, зависимости, часто используемые файлы.

**Зачем нужно:**
- Быстро понимать структуру проекта
- Использовать известные паттерны
- Предсказывать какие файлы могут быть нужны

### Интерфейс

```python
@dataclass
class ProjectInfo:
    """Информация о проекте."""
    project_path: str
    language: str
    framework: str | None
    dependencies: list[str]
    common_patterns: list[str]  # Паттерны проекта
    frequently_used_files: list[str]  # Часто используемые файлы
    last_analyzed: datetime

class ProjectMemory:
    """Память проекта."""
    
    def __init__(self, storage: MemoryStorage):
        self.storage = storage
    
    async def save_project_info(self, info: ProjectInfo) -> None:
        """Сохранить информацию о проекте."""
        await self.storage.save(f"project:{info.project_path}", info)
    
    async def get_project_info(
        self,
        project_path: str,
    ) -> ProjectInfo | None:
        """Получить информацию о проекте."""
        return await self.storage.load(f"project:{project_path}")
    
    async def update_frequently_used_files(
        self,
        project_path: str,
        files: list[str],
    ) -> None:
        """Обновить список часто используемых файлов."""
        info = await self.get_project_info(project_path)
        
        if info is None:
            info = ProjectInfo(
                project_path=project_path,
                language="unknown",
                framework=None,
                dependencies=[],
                common_patterns=[],
                frequently_used_files=files,
                last_analyzed=datetime.now()
            )
        else:
            # Объединить и убрать дубликаты
            all_files = list(set(info.frequently_used_files + files))
            info.frequently_used_files = all_files
            info.last_analyzed = datetime.now()
        
        await self.save_project_info(info)
    
    async def add_pattern(
        self,
        project_path: str,
        pattern: str,
    ) -> None:
        """Добавить паттерн проекта."""
        info = await self.get_project_info(project_path)
        
        if info and pattern not in info.common_patterns:
            info.common_patterns.append(pattern)
            await self.save_project_info(info)
    
    async def get_frequently_used_files(
        self,
        project_path: str,
    ) -> list[str]:
        """Получить часто используемые файлы."""
        info = await self.get_project_info(project_path)
        return info.frequently_used_files if info else []
```

### Пример использования

```python
memory = ProjectMemory(storage)

# Сохранить информацию о проекте
await memory.save_project_info(ProjectInfo(
    project_path="/path/to/project",
    language="typescript",
    framework="nestjs",
    dependencies=["@nestjs/core", "rxjs"],
    common_patterns=[
        "Controllers в src/**/*.controller.ts",
        "Services в src/**/*.service.ts"
    ],
    frequently_used_files=[
        "src/auth/auth.service.ts",
        "src/auth/auth.controller.ts"
    ],
    last_analyzed=datetime.now()
))

# Обновить часто используемые файлы
await memory.update_frequently_used_files(
    "/path/to/project",
    ["src/user/user.service.ts"]
)

# Добавить паттерн
await memory.add_pattern(
    "/path/to/project",
    "DTOs в src/**/*.dto.ts"
)

# Получить часто используемые файлы
files = await memory.get_frequently_used_files("/path/to/project")
print(files)  # ["src/auth/auth.service.ts", ...]
```

---

## Интеграция с ContextManager

```python
class ContextManager:
    def __init__(
        self,
        task_memory: TaskMemory,
        session_memory: SessionMemory,
        project_memory: ProjectMemory,
        ...
    ):
        self.task_memory = task_memory
        self.session_memory = session_memory
        self.project_memory = project_memory
    
    async def build_context(self, session, task):
        # 1. Получить похожие задачи из памяти
        similar_tasks = await self.task_memory.search_similar_tasks(task)
        
        # 2. Получить контекст текущей сессии
        session_context = await self.session_memory.get_context(session.id)
        
        # 3. Получить информацию о проекте
        project_info = await self.project_memory.get_project_info(session.cwd)
        
        # 4. Добавить память в контекст
        memory_context = []
        
        if similar_tasks:
            memory_context.append("## Similar Tasks")
            for task in similar_tasks:
                memory_context.append(f"- {task.task_description}")
                memory_context.append(f"  Solution: {task.solution_summary}")
        
        if session_context:
            memory_context.append("## Current Session")
            memory_context.append(f"Files modified: {', '.join(session_context.files_modified)}")
            memory_context.append(f"Decisions: {', '.join(session_context.decisions_made)}")
        
        if project_info:
            memory_context.append("## Project Info")
            memory_context.append(f"Language: {project_info.language}")
            memory_context.append(f"Framework: {project_info.framework}")
            memory_context.append(f"Frequently used: {', '.join(project_info.frequently_used_files)}")
        
        # 5. Собрать остальной контекст
        gathered = await self.gatherer.gather_context(task, profile, session)
        
        # 6. Объединить
        all_context = memory_context + [gathered.summary]
        
        return all_context
```

---

## Roadmap реализации

### Phase 3: Базовая реализация (2 недели)

**Задачи:**
- [ ] Реализовать `MemoryStorage` (файловое хранилище)
- [ ] Реализовать `TaskMemory` с сохранением и поиском
- [ ] Реализовать `SessionMemory` с обновлением контекста
- [ ] Реализовать `ProjectMemory` с информацией о проекте
- [ ] Unit tests

**Результат:** Базовая память между сессиями.

### Phase 3: Расширенная реализация (1 неделя)

**Задачи:**
- [ ] Реализовать поиск похожих задач
- [ ] Реализовать историю изменений файлов
- [ ] Интеграция с ContextManager
- [ ] Integration tests

**Результат:** Полная память с поиском и интеграцией.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы

# Context Lifecycle — Жизненный цикл контекста

> Компоненты для управления жизненным циклом контекста: epochs, snapshots, sources

## Оглавление

- [Обзор](#обзор)
- [ContextRegistry](#contextregistry)
- [ContextSource](#contextsource)
- [InstructionContextSource](#instructioncontextsource)
- [ProjectContextSource](#projectcontextsource)
- [EnvironmentContextSource](#environmentcontextsource)
- [SkillContextSource](#skillcontextsource)
- [ContextSnapshot](#contextsnapshot)
- [ContextEpoch](#contextepoch)
- [ContextReconciliation](#contextreconciliation)
- [ConversationSummarizer](#conversationsummarizer)
- [Интеграция с ContextManager](#интеграция-с-contextmanager)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Context Lifecycle отвечает за **управление жизненным циклом контекста**: регистрация источников, отслеживание изменений, immutable baseline, mid-conversation updates, суммаризация диалога.

**Компоненты:**
- `ContextRegistry` — реестр источников контекста
- `ContextSource` — базовый класс для источников
- `InstructionContextSource` — AGENTS.md иерархия
- `ProjectContextSource` — структура проекта
- `EnvironmentContextSource` — environment variables
- `SkillContextSource` — каталог доступных skills
- `ContextSnapshot` — отслеживание изменений
- `ContextEpoch` — immutable baseline + updates
- `ContextReconciliation` — согласование изменений
- `ConversationSummarizer` — суммаризация диалога при compaction

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ ContextRegistry       ← Context Lifecycle                │
│      ├─ InstructionContextSource                             │
│      ├─ ProjectContextSource                                 │
│      ├─ EnvironmentContextSource                             │
│      ├─ GitContextSource                                     │
│      └─ SkillContextSource                                   │
│  └─ ContextSnapshot       ← Context Lifecycle                │
│  └─ ContextEpoch          ← Context Lifecycle                │
│  └─ ContextReconciliation ← Context Lifecycle                │
│  └─ ConversationSummarizer← Context Lifecycle                │
└─────────────────────────────────────────────────────────────┘
```

---

## ContextRegistry

### Назначение

Реестр источников контекста: регистрация, получение, рендеринг baseline и updates.

### Интерфейс

```python
class ContextRegistry:
    """Реестр источников контекста."""
    
    def __init__(self):
        self._sources: dict[str, ContextSource] = {}
    
    def register(self, source: ContextSource) -> None:
        """Зарегистрировать источник контекста."""
        self._sources[source.key] = source
    
    def get(self, key: str) -> ContextSource | None:
        """Получить источник по ключу."""
        return self._sources.get(key)
    
    def get_all(self) -> list[ContextSource]:
        """Получить все источники."""
        return list(self._sources.values())
    
    async def render_baseline(self) -> str:
        """
        Рендер baseline контекста.
        
        Вызывает render_baseline() для каждого источника.
        """
        parts = []
        
        for source in self._sources.values():
            value = await source.load()
            rendered = source.render_baseline(value)
            if rendered:
                parts.append(rendered)
        
        return "\n\n".join(parts)
    
    async def render_updates(self, changes: dict[str, Any]) -> str:
        """
        Рендер updates для mid-conversation messages.
        
        Вызывает render_update() для изменённых источников.
        """
        parts = []
        
        for key, value in changes.items():
            source = self._sources.get(key)
            if source:
                rendered = source.render_update(value)
                if rendered:
                    parts.append(rendered)
        
        return "\n".join(parts)
    
    async def detect_changes(
        self,
        snapshot: ContextSnapshot
    ) -> dict[str, Any]:
        """
        Обнаружить изменения в источниках.
        
        Сравнивает текущие значения с snapshot.
        """
        changes = {}
        
        for key, source in self._sources.items():
            current = await source.load()
            old = snapshot.get(key)
            
            if old is None or source.has_changed(old, current):
                changes[key] = current
        
        return changes
```

---

## ContextSource

### Назначение

Базовый класс для источников контекста. Каждый источник:
- Загружает данные
- Сравнивает изменения
- Рендерит baseline и updates

### Интерфейс

```python
class Codec(Generic[T]):
    """Кодек для сравнения значений."""
    
    def equals(self, a: T, b: T) -> bool:
        """Сравнить два значения."""
        return a == b

class ContextSource(Generic[T]):
    """
    Базовый класс для источников контекста.
    
    Типизированный источник с:
    - loader: загрузка данных
    - codec: сравнение значений
    - render_baseline: рендер для начала epoch
    - render_update: рендер для mid-conversation update
    - render_removal: рендер для удаления источника
    """
    
    def __init__(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
        codec: Codec[T],
        render_baseline: Callable[[T], str],
        render_update: Callable[[T], str],
        render_removal: Callable[[], str] | None = None,
    ):
        self.key = key
        self.loader = loader
        self.codec = codec
        self._render_baseline = render_baseline
        self._render_update = render_update
        self._render_removal = render_removal
    
    async def load(self) -> T:
        """Загрузить текущее значение."""
        return await self.loader()
    
    def has_changed(self, old: T, new: T) -> bool:
        """Проверить изменилось ли значение."""
        return not self.codec.equals(old, new)
    
    def render_baseline(self, value: T) -> str:
        """Рендер baseline контекста."""
        return self._render_baseline(value)
    
    def render_update(self, value: T) -> str:
        """Рендер update для mid-conversation message."""
        return self._render_update(value)
    
    def render_removal(self) -> str:
        """Рендер removal message."""
        if self._render_removal:
            return self._render_removal()
        return f"[{self.key} removed]"
```

---

## InstructionContextSource

### Назначение

Источник контекста из AGENTS.md файлов: глобальные, проектные, директорные инструкции.

**Иерархия:**
```
~/.config/codelab/AGENTS.md      # Global
./AGENTS.md                       # Project
./src/AGENTS.md                   # Directory
./src/auth/AGENTS.md              # Subdirectory
```

### Интерфейс

```python
@dataclass
class InstructionFile:
    """Файл инструкций."""
    path: str
    content: str
    scope: Literal["global", "project", "directory"]

class InstructionContextSource(ContextSource[list[InstructionFile]]):
    """Источник контекста из AGENTS.md файлов."""
    
    def __init__(self, cwd: str):
        self.cwd = cwd
        super().__init__(
            key="instructions",
            loader=self.load_instructions,
            codec=InstructionCodec(),
            render_baseline=self.render_baseline,
            render_update=self.render_update
        )
    
    async def load_instructions(self) -> list[InstructionFile]:
        """Загрузить все AGENTS.md файлы иерархически."""
        instructions = []
        
        # 1. Global instructions
        global_path = Path.home() / '.config' / 'codelab' / 'AGENTS.md'
        if global_path.exists():
            content = await self._read_file(str(global_path))
            instructions.append(InstructionFile(
                path=str(global_path),
                content=content,
                scope="global"
            ))
        
        # 2. Project и directory instructions (walk up от cwd)
        current = Path(self.cwd)
        visited = set()
        
        while current not in visited:
            visited.add(current)
            
            agents_md = current / 'AGENTS.md'
            if agents_md.exists():
                content = await self._read_file(str(agents_md))
                
                # Определить scope
                if current == Path(self.cwd).root:
                    scope = "project"
                else:
                    scope = "directory"
                
                instructions.append(InstructionFile(
                    path=str(agents_md),
                    content=content,
                    scope=scope
                ))
            
            parent = current.parent
            if parent == current:
                break
            current = parent
        
        # Reverse чтобы global был первым
        instructions.reverse()
        
        return instructions
    
    async def _read_file(self, path: str) -> str:
        """Прочитать файл."""
        with open(path, 'r') as f:
            return f.read()
    
    def render_baseline(self, instructions: list[InstructionFile]) -> str:
        """Рендер baseline контекста."""
        if not instructions:
            return ""
        
        parts = ["# Instructions\n"]
        
        for instr in instructions:
            scope_label = {
                "global": "🌍 Global",
                "project": "📁 Project",
                "directory": "📂 Directory"
            }[instr.scope]
            
            parts.append(f"## {scope_label}: {instr.path}\n")
            parts.append(instr.content)
            parts.append("")
        
        return "\n".join(parts)
    
    def render_update(self, instructions: list[InstructionFile]) -> str:
        """Рендер update для mid-conversation message."""
        paths = [instr.path for instr in instructions]
        return f"[Instructions updated: {', '.join(paths)}]"


class InstructionCodec(Codec[list[InstructionFile]]):
    """Кодек для сравнения инструкций."""
    
    def equals(
        self,
        a: list[InstructionFile],
        b: list[InstructionFile]
    ) -> bool:
        """Сравнить два списка инструкций."""
        if len(a) != len(b):
            return False
        
        for instr_a, instr_b in zip(a, b):
            if instr_a.path != instr_b.path:
                return False
            if instr_a.content != instr_b.content:
                return False
        
        return True
```

### Пример использования

```python
source = InstructionContextSource(cwd="/path/to/project")
instructions = await source.load()

# Результат:
# [
#     InstructionFile(path="~/.config/codelab/AGENTS.md", scope="global"),
#     InstructionFile(path="/path/to/project/AGENTS.md", scope="project"),
#     InstructionFile(path="/path/to/project/src/AGENTS.md", scope="directory"),
# ]

baseline = source.render_baseline(instructions)
print(baseline)
# # Instructions
#
# ## 🌍 Global: ~/.config/codelab/AGENTS.md
# ...
#
# ## 📁 Project: /path/to/project/AGENTS.md
# ...
#
# ## 📂 Directory: /path/to/project/src/AGENTS.md
# ...
```

---

## ProjectContextSource

### Назначение

Источник контекста о структуре проекта: язык, фреймворк, зависимости.

### Интерфейс

```python
@dataclass
class ProjectMetadata:
    """Метаданные проекта."""
    language: str
    framework: str | None
    package_manager: str | None
    dependencies: list[str]
    entry_points: list[str]

class ProjectContextSource(ContextSource[ProjectMetadata]):
    """Источник контекста о структуре проекта."""
    
    def __init__(self, cwd: str, discovery: ProjectDiscovery):
        self.cwd = cwd
        self.discovery = discovery
        super().__init__(
            key="project",
            loader=self.load_metadata,
            codec=ProjectMetadataCodec(),
            render_baseline=self.render_baseline,
            render_update=self.render_update
        )
    
    async def load_metadata(self) -> ProjectMetadata:
        """Загрузить метаданные проекта."""
        structure = await self.discovery.discover(self.cwd)
        
        return ProjectMetadata(
            language=structure.language,
            framework=structure.framework,
            package_manager=structure.package_manager,
            dependencies=structure.dependencies,
            entry_points=structure.entry_points
        )
    
    def render_baseline(self, metadata: ProjectMetadata) -> str:
        """Рендер baseline контекста."""
        parts = ["# Project Structure\n"]
        
        parts.append(f"- **Language:** {metadata.language}")
        
        if metadata.framework:
            parts.append(f"- **Framework:** {metadata.framework}")
        
        if metadata.package_manager:
            parts.append(f"- **Package Manager:** {metadata.package_manager}")
        
        if metadata.dependencies:
            parts.append(f"- **Dependencies:** {len(metadata.dependencies)} packages")
        
        if metadata.entry_points:
            parts.append(f"- **Entry Points:** {', '.join(metadata.entry_points)}")
        
        return "\n".join(parts)
    
    def render_update(self, metadata: ProjectMetadata) -> str:
        """Рендер update."""
        return f"[Project updated: {metadata.language}, {metadata.framework or 'no framework'}]"
```

---

## EnvironmentContextSource

### Назначение

Источник контекста из environment variables и конфигурации.

### Интерфейс

```python
@dataclass
class EnvironmentConfig:
    """Конфигурация окружения."""
    env_vars: dict[str, str]
    config_files: list[str]
    runtime: str  # "node", "python", "go", etc.

class EnvironmentContextSource(ContextSource[EnvironmentConfig]):
    """Источник контекста из environment."""
    
    def __init__(self, cwd: str):
        self.cwd = cwd
        super().__init__(
            key="environment",
            loader=self.load_config,
            codec=EnvironmentConfigCodec(),
            render_baseline=self.render_baseline,
            render_update=self.render_update
        )
    
    async def load_config(self) -> EnvironmentConfig:
        """Загрузить конфигурацию окружения."""
        # Получить важные env vars
        important_vars = ["NODE_ENV", "PYTHON_ENV", "GO_ENV", "DEBUG"]
        env_vars = {
            var: os.environ.get(var, "")
            for var in important_vars
            if os.environ.get(var)
        }
        
        # Найти config файлы
        config_files = await self._find_config_files()
        
        # Определить runtime
        runtime = await self._detect_runtime()
        
        return EnvironmentConfig(
            env_vars=env_vars,
            config_files=config_files,
            runtime=runtime
        )
    
    async def _find_config_files(self) -> list[str]:
        """Найти config файлы."""
        patterns = [
            "*.env",
            ".env.*",
            "config.*",
            "codelab.toml",
            "package.json",
            "pyproject.toml",
        ]
        
        files = []
        for pattern in patterns:
            matches = glob.glob(os.path.join(self.cwd, pattern))
            files.extend(matches)
        
        return files
    
    async def _detect_runtime(self) -> str:
        """Определить runtime."""
        if os.path.exists(os.path.join(self.cwd, "package.json")):
            return "node"
        elif os.path.exists(os.path.join(self.cwd, "pyproject.toml")):
            return "python"
        elif os.path.exists(os.path.join(self.cwd, "go.mod")):
            return "go"
        return "unknown"
    
    def render_baseline(self, config: EnvironmentConfig) -> str:
        """Рендер baseline контекста."""
        parts = ["# Environment\n"]
        
        parts.append(f"- **Runtime:** {config.runtime}")
        
        if config.env_vars:
            parts.append("- **Environment Variables:**")
            for var, value in config.env_vars.items():
                parts.append(f"  - {var}={value}")
        
        if config.config_files:
            parts.append(f"- **Config Files:** {', '.join(config.config_files)}")
        
        return "\n".join(parts)
    
    def render_update(self, config: EnvironmentConfig) -> str:
        """Рендер update."""
        return f"[Environment updated: {config.runtime}]"
```

---

## SkillContextSource

### Назначение

Источник контекста из SkillRegistry: каталог доступных skills, их описания и триггеры для активации.

**Архитектурное место:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ ContextRegistry       ← Context Lifecycle                │
│      ├─ InstructionContextSource  (AGENTS.md иерархия)       │
│      ├─ ProjectContextSource      (структура проекта)        │
│      ├─ EnvironmentContextSource  (environment variables)    │
│      ├─ GitContextSource          (git status, branch)       │
│      └─ SkillContextSource        (каталог skills)           │
└─────────────────────────────────────────────────────────────┘
```

**Ответственность:**
- Загрузка каталога skills из SkillRegistry
- Рендер baseline для system prompt
- Отслеживание изменений (новые/удалённые skills)
- Mid-conversation updates при изменении skills

### Интеграция с SkillRegistry

SkillContextSource является адаптером между SkillRegistry (источник данных) и ContextRegistry (система управления контекстом):

```python
class SkillContextSource(ContextSource[dict[str, SkillDefinition]]):
    """Источник контекста из SkillRegistry."""
    
    def __init__(self, skill_registry: SkillRegistry):
        self.skill_registry = skill_registry
        super().__init__(
            key="skills",
            loader=self.load_skills,
            codec=SkillCatalogCodec(),
            render_baseline=self.render_baseline,
            render_update=self.render_update
        )
    
    async def load_skills(self) -> dict[str, SkillDefinition]:
        """Загрузить все доступные skills."""
        return self.skill_registry.get_all()
    
    def render_baseline(self, skills: dict[str, SkillDefinition]) -> str:
        """Рендер каталога skills для system prompt."""
        if not skills:
            return ""
        
        parts = ["# Available Skills\n"]
        parts.append("Use skill/load tool to activate a skill when needed.\n")
        
        for name, skill in skills.items():
            parts.append(f"## {name}")
            parts.append(f"**Description:** {skill.description}")
            if skill.triggers:
                parts.append(f"**Triggers:** {', '.join(skill.triggers)}")
            parts.append("")
        
        return "\n".join(parts)
    
    def render_update(self, skills: dict[str, SkillDefinition]) -> str:
        """Рендер update при изменении skills."""
        names = list(skills.keys())
        return f"[Skills updated: {', '.join(names)}]"


class SkillCatalogCodec(Codec[dict[str, SkillDefinition]]):
    """Кодек для сравнения каталога skills."""
    
    def equals(
        self,
        a: dict[str, SkillDefinition],
        b: dict[str, SkillDefinition]
    ) -> bool:
        """Сравнить два каталога skills."""
        if set(a.keys()) != set(b.keys()):
            return False
        
        for name in a:
            if a[name].version != b[name].version:
                return False
        
        return True
```

### Пример использования

```python
# Инициализация
skill_registry = SkillRegistry(loader, cache)
skill_source = SkillContextSource(skill_registry)

# Загрузка skills
skills = await skill_source.load()

# Результат:
# {
#     "pdf-processing": SkillDefinition(name="pdf-processing", ...),
#     "code-review": SkillDefinition(name="code-review", ...),
# }

# Рендер baseline
baseline = skill_source.render_baseline(skills)
print(baseline)
# # Available Skills
#
# Use skill/load tool to activate a skill when needed.
#
# ## pdf-processing
# **Description:** Process PDF files, extract text, merge documents
# **Triggers:** pdf, document, extract
#
# ## code-review
# **Description:** Automated code review with best practices
# **Triggers:** review, code quality
```

### Инициализация в ContextManager

```python
class ContextManager:
    async def initialize(self, session: SessionState) -> None:
        # Регистрация sources
        self.registry.register(InstructionContextSource(session.cwd))
        self.registry.register(ProjectContextSource(session.cwd, discovery))
        self.registry.register(EnvironmentContextSource(session.cwd))
        self.registry.register(GitContextSource(session.cwd))
        
        # Регистрация SkillContextSource (если skills включены)
        if self.skill_registry:
            self.registry.register(SkillContextSource(self.skill_registry))
```

### Управление и ответственность

| Компонент | Роль |
|-----------|------|
| **ContextManager** | Регистрирует SkillContextSource в ContextRegistry, вызывает render_baseline() |
| **ContextRegistry** | Хранит SkillContextSource, управляет lifecycle |
| **SkillRegistry** | Предоставляет данные о skills (get_all()) |
| **SkillContextSource** | Адаптер между SkillRegistry и ContextRegistry |

---

## ContextSnapshot

### Назначение

Отслеживание изменений в источниках контекста. Хранит последние известные значения.

### Интерфейс

```python
class ContextSnapshot:
    """Отслеживание изменений в context sources."""
    
    def __init__(self):
        self._values: dict[str, Any] = {}
    
    def capture(self) -> dict[str, Any]:
        """Захватить текущее состояние."""
        return dict(self._values)
    
    def get(self, key: str) -> Any | None:
        """Получить значение по ключу."""
        return self._values.get(key)
    
    def set(self, key: str, value: Any) -> None:
        """Установить значение."""
        self._values[key] = value
    
    def apply(self, changes: dict[str, Any]) -> None:
        """Атомарно применить изменения."""
        self._values.update(changes)
    
    def detect_changes(
        self,
        sources: dict[str, ContextSource],
        current_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Обнаружить изменения в sources."""
        changes = {}
        
        for key, source in sources.items():
            current = current_values.get(key)
            old = self._values.get(key)
            
            if old is None:
                # Новый source
                changes[key] = current
            elif source.has_changed(old, current):
                # Изменилось значение
                changes[key] = current
        
        return changes
```

---

## ContextEpoch

### Назначение

Immutable baseline контекста. Epoch — это span, в котором baseline остаётся неизменным. Изменения добавляются как mid-conversation messages.

**Зачем нужно:**
- Консистентность: LLM работает в рамках одного baseline
- Кэширование: provider может кэшировать baseline
- История: mid-conversation messages сохраняют историю изменений

### Интерфейс

```python
@dataclass
class ContextEpoch:
    """
    Immutable baseline контекста.
    
    Epoch = span, в котором Baseline System Context остаётся неизменным.
    Изменения добавляются как Mid-Conversation System Messages.
    
    После compaction начинается новый epoch с новым baseline.
    """
    
    baseline: str  # Полный system context на момент начала epoch
    snapshot: dict[str, Any]  # Snapshot значений всех sources
    started_at: datetime
    mid_conversation_messages: list[str] = field(default_factory=list)
    
    def add_mid_conversation_message(self, message: str) -> None:
        """Добавить mid-conversation system message."""
        self.mid_conversation_messages.append(message)
    
    def get_full_context(self) -> str:
        """
        Получить полный контекст: baseline + mid-conversation messages.
        
        Пример:
            baseline: "You are a helpful assistant..."
            mid_conversation_messages: [
                "[Instructions updated: AGENTS.md]",
                "[Project updated: TypeScript, NestJS]"
            ]
            
            Result:
                You are a helpful assistant...
                
                [Instructions updated: AGENTS.md]
                [Project updated: TypeScript, NestJS]
        """
        parts = [self.baseline]
        parts.extend(self.mid_conversation_messages)
        return "\n\n".join(parts)
```

### Пример использования

```python
# Создать epoch
epoch = ContextEpoch(
    baseline="# Instructions\n...",
    snapshot={"instructions": [...], "project": {...}},
    started_at=datetime.now()
)

# Добавить mid-conversation message
epoch.add_mid_conversation_message("[Instructions updated: AGENTS.md]")

# Получить полный контекст
full_context = epoch.get_full_context()
# "# Instructions\n...\n\n[Instructions updated: AGENTS.md]"
```

---

## ContextReconciliation

### Назначение

Согласование изменений: обнаружение изменений и применение их к контексту.

### Интерфейс

```python
class ContextReconciliation(Enum):
    """Результат reconciliation."""
    UNCHANGED = "unchanged"  # Контекст не изменился
    UPDATED = "updated"      # Есть изменения, нужно добавить mid-conversation message
    DEFERRED = "deferred"    # Изменения отложены (не безопасная граница)

class ContextManager:
    async def reconcile(self) -> ContextReconciliation:
        """
        Reconcile context at safe provider-turn boundary.
        
        Safe boundary = нет pending tool calls, user input promoted.
        
        Returns:
            UNCHANGED — контекст не изменился
            UPDATED — есть изменения, нужно добавить mid-conversation message
            DEFERRED — изменения отложены
        """
        if not self.snapshot:
            return ContextReconciliation.UNCHANGED
        
        # Проверить безопасную границу
        if not self.is_safe_boundary():
            return ContextReconciliation.DEFERRED
        
        # Обнаружить изменения
        changes = await self.registry.detect_changes(self.snapshot)
        
        if not changes:
            return ContextReconciliation.UNCHANGED
        
        # Render update message
        update_msg = await self.registry.render_updates(changes)
        
        # Update snapshot atomically
        self.snapshot.apply(changes)
        
        # Add to epoch if available
        if self.epoch:
            self.epoch.add_mid_conversation_message(update_msg)
        
        return ContextReconciliation.UPDATED
    
    def is_safe_boundary(self) -> bool:
        """
        Проверить безопасную границу.
        
        Safe boundary:
        - Нет pending tool calls
        - User input promoted
        - Tools settled
        """
        return (
            not self.has_pending_tools() and
            self.input_promoted() and
            self.tools_settled()
        )
```

---

## ConversationSummarizer

### Назначение

Суммаризация диалога при compaction истории. Когда история становится слишком длинной, ConversationSummarizer сжимает старые сообщения в краткое резюме, сохраняя ключевую информацию.

**Зачем нужно:**
- Длинные диалоги превышают контекстное окно LLM
- Простое удаление сообщений теряет важную информацию
- Суммаризация сохраняет ключевые решения и контекст
- Позволяет работать с длинными сессиями

**Отличие от ContextCompactor:**
- `ContextCompactor` — низкоуровневый компонент (prune tool outputs, summarize middle)
- `ConversationSummarizer` — высокоуровневый компонент (интеллектуальная суммаризация с сохранением ключевых решений)

### Интерфейс

```python
@dataclass
class SummaryResult:
    """Результат суммаризации."""
    summary: str
    original_message_count: int
    summarized_message_count: int
    key_decisions: list[str]
    key_context: list[str]
    tokens_saved: int

class ConversationSummarizer:
    """
    Суммаризация диалога при compaction.
    
    Использует LLM для создания краткого резюме, сохраняющего:
    - Ключевые решения
    - Важный контекст
    - Текущее состояние задачи
    """
    
    def __init__(
        self,
        llm: LLMProvider,
        model: str = "openai/gpt-4o-mini",
    ):
        self.llm = llm
        self.model = model
    
    async def summarize(
        self,
        messages: list[LLMMessage],
        preserve_recent: int = 5,
    ) -> SummaryResult:
        """
        Суммаризировать старые сообщения.
        
        Args:
            messages: Полная история сообщений
            preserve_recent: Количество последних сообщений для сохранения
        
        Returns:
            SummaryResult с резюме и метаданными
        """
        if len(messages) <= preserve_recent:
            return SummaryResult(
                summary="",
                original_message_count=len(messages),
                summarized_message_count=0,
                key_decisions=[],
                key_context=[],
                tokens_saved=0
            )
        
        # Разделить на старые и новые
        to_summarize = messages[:-preserve_recent]
        to_preserve = messages[-preserve_recent:]
        
        # Суммаризировать старые
        summary = await self._generate_summary(to_summarize)
        
        # Извлечь ключевые решения
        key_decisions = await self._extract_key_decisions(to_summarize)
        
        # Извлечь ключевой контекст
        key_context = await self._extract_key_context(to_summarize)
        
        # Подсчитать сэкономленные токены
        original_tokens = self._estimate_tokens(to_summarize)
        summary_tokens = self._estimate_tokens_text(summary)
        tokens_saved = original_tokens - summary_tokens
        
        return SummaryResult(
            summary=summary,
            original_message_count=len(to_summarize),
            summarized_message_count=len(to_summarize),
            key_decisions=key_decisions,
            key_context=key_context,
            tokens_saved=tokens_saved
        )
    
    async def _generate_summary(
        self,
        messages: list[LLMMessage]
    ) -> str:
        """Сгенерировать резюме диалога."""
        # Форматировать сообщения для LLM
        conversation_text = self._format_messages(messages)
        
        prompt = f"""
Summarize the following conversation concisely.

Preserve:
- Key decisions made
- Important context about the task
- Current state of the work
- Files that were modified
- Errors encountered and how they were resolved

Keep the summary under 500 words.

Conversation:
{conversation_text}

Provide a concise summary:
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model=self.model,
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=1000,
                temperature=0.0,
            )
        )
        
        return response.text
    
    async def _extract_key_decisions(
        self,
        messages: list[LLMMessage]
    ) -> list[str]:
        """Извлечь ключевые решения из диалога."""
        conversation_text = self._format_messages(messages)
        
        prompt = f"""
Extract key decisions from this conversation.

Return a list of decisions made, one per line.
If no decisions were made, return an empty list.

Conversation:
{conversation_text}

Key decisions:
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model=self.model,
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=500,
                temperature=0.0,
            )
        )
        
        decisions = [
            line.strip()
            for line in response.text.strip().split('\n')
            if line.strip() and line.strip().startswith('-')
        ]
        
        return [d.lstrip('- ').strip() for d in decisions]
    
    async def _extract_key_context(
        self,
        messages: list[LLMMessage]
    ) -> list[str]:
        """Извлечь ключевой контекст из диалога."""
        conversation_text = self._format_messages(messages)
        
        prompt = f"""
Extract key context from this conversation.

Return a list of important context items, one per line.
Include: files mentioned, technologies used, task description.
If no important context, return an empty list.

Conversation:
{conversation_text}

Key context:
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model=self.model,
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=500,
                temperature=0.0,
            )
        )
        
        context_items = [
            line.strip()
            for line in response.text.strip().split('\n')
            if line.strip() and line.strip().startswith('-')
        ]
        
        return [c.lstrip('- ').strip() for c in context_items]
    
    def _format_messages(self, messages: list[LLMMessage]) -> str:
        """Форматировать сообщения для LLM."""
        parts = []
        
        for msg in messages:
            role = msg.role.upper()
            content = msg.content or ""
            
            # Обрезать длинные сообщения
            if len(content) > 1000:
                content = content[:1000] + "... (truncated)"
            
            parts.append(f"[{role}]: {content}")
        
        return "\n\n".join(parts)
    
    def _estimate_tokens(self, messages: list[LLMMessage]) -> int:
        """Оценить количество токенов в сообщениях."""
        total = 0
        for msg in messages:
            if msg.content:
                total += len(msg.content) // 4
        return total
    
    def _estimate_tokens_text(self, text: str) -> int:
        """Оценить количество токенов в тексте."""
        return len(text) // 4
    
    def apply_summary(
        self,
        messages: list[LLMMessage],
        summary_result: SummaryResult,
    ) -> list[LLMMessage]:
        """
        Применить суммаризацию к истории.
        
        Заменяет старые сообщения на summary message.
        """
        if not summary_result.summary:
            return messages
        
        # Создать summary message
        summary_msg = LLMMessage(
            role="system",
            content=self._format_summary_message(summary_result)
        )
        
        # Сохранить только последние сообщения
        preserve_recent = 5
        preserved = messages[-preserve_recent:]
        
        return [summary_msg] + preserved
    
    def _format_summary_message(self, result: SummaryResult) -> str:
        """Форматировать summary message для LLM."""
        parts = [
            "# Conversation Summary",
            "",
            f"Summarized {result.original_message_count} messages.",
            "",
            "## Summary",
            result.summary,
        ]
        
        if result.key_decisions:
            parts.append("")
            parts.append("## Key Decisions")
            for decision in result.key_decisions:
                parts.append(f"- {decision}")
        
        if result.key_context:
            parts.append("")
            parts.append("## Key Context")
            for context in result.key_context:
                parts.append(f"- {context}")
        
        parts.append("")
        parts.append(f"Tokens saved: {result.tokens_saved}")
        
        return "\n".join(parts)
```

### Пример использования

```python
summarizer = ConversationSummarizer(llm)

# Длинная история
messages = [
    LLMMessage(role="user", content="Добавь email validation"),
    LLMMessage(role="assistant", content="...", tool_calls=[...]),
    LLMMessage(role="tool", content="..."),
    # ... 50+ сообщений ...
]

# Суммаризировать
result = await summarizer.summarize(messages, preserve_recent=5)

print(result.summary)
# "The user requested email validation. We decided to use class-validator..."

print(result.key_decisions)
# ["Use class-validator for validation", "Add @IsEmail() decorator to UserDTO"]

print(result.key_context)
# ["TypeScript project with NestJS", "UserDTO in src/auth/dto.ts"]

print(result.tokens_saved)
# 15000

# Применить суммаризацию
compacted_messages = summarizer.apply_summary(messages, result)
# [summary_message, ...last 5 messages...]
```

### Интеграция с ContextManager

```python
class ContextManager:
    def __init__(
        self,
        summarizer: ConversationSummarizer | None = None,
        ...
    ):
        self.summarizer = summarizer
    
    async def ensure_context_fits(
        self,
        history: list[LLMMessage],
    ) -> list[LLMMessage]:
        """Сжать историю если превышает лимит."""
        # Сначала попробовать ContextCompactor (prune tool outputs)
        history = await self.compactor.compact_if_needed(history)
        
        # Если всё ещё много — использовать ConversationSummarizer
        if self._estimate_tokens(history) > self.max_tokens * 0.9:
            if self.summarizer:
                summary_result = await self.summarizer.summarize(history)
                history = self.summarizer.apply_summary(history, summary_result)
                
                # Начать новый epoch после суммаризации
                await self.start_new_epoch()
        
        return history
```

---

## Интеграция с ContextManager

```python
class ContextManager:
    """Единая точка управления контекстом."""
    
    def __init__(
        self,
        registry: ContextRegistry,
        snapshot: ContextSnapshot | None = None,
        epoch: ContextEpoch | None = None,
        ...
    ):
        self.registry = registry
        self.snapshot = snapshot
        self.epoch = epoch
    
    async def initialize(self, session: SessionState) -> None:
        """Инициализация контекста для сессии."""
        # Регистрация sources
        self.registry.register(InstructionContextSource(session.cwd))
        self.registry.register(ProjectContextSource(session.cwd, discovery))
        self.registry.register(EnvironmentContextSource(session.cwd))
        
        # Регистрация SkillContextSource (если skills включены)
        if self.skill_registry:
            self.registry.register(SkillContextSource(self.skill_registry))
        
        # Загрузка initial baseline
        baseline = await self.registry.render_baseline()
        
        if self.snapshot:
            # Захватить snapshot
            for source in self.registry.get_all():
                value = await source.load()
                self.snapshot.set(source.key, value)
            
            # Создать epoch
            self.epoch = ContextEpoch(
                baseline=baseline,
                snapshot=self.snapshot.capture(),
                started_at=datetime.now()
            )
    
    async def build_context(self, session, task):
        """Собрать контекст для LLM."""
        # Получить полный контекст из epoch
        if self.epoch:
            context = self.epoch.get_full_context()
        else:
            context = await self.registry.render_baseline()
        
        return [LLMMessage(role="system", content=context)]
    
    async def start_new_epoch(self) -> None:
        """
        Начать новый epoch после compaction.
        
        Вызывается когда история сжимается.
        """
        baseline = await self.registry.render_baseline()
        
        if self.snapshot:
            self.epoch = ContextEpoch(
                baseline=baseline,
                snapshot=self.snapshot.capture(),
                started_at=datetime.now()
            )
```

---

## Roadmap реализации

### Phase 2: Snapshot Layer (1 неделя)

**Задачи:**
- [ ] Реализовать `ContextRegistry` с регистрацией sources
- [ ] Реализовать `ContextSource` base class
- [ ] Реализовать `InstructionContextSource` (AGENTS.md иерархия)
- [ ] Реализовать `ProjectContextSource`
- [ ] Реализовать `EnvironmentContextSource`
- [ ] Реализовать `SkillContextSource` (каталог skills из SkillRegistry)
- [ ] Реализовать `ContextSnapshot` с detect_changes
- [ ] Unit tests

**Результат:** Базовое отслеживание изменений.

### Phase 3: Epoch Layer (1 неделя)

**Задачи:**
- [ ] Реализовать `ContextEpoch` с baseline + mid-conversation messages
- [ ] Реализовать `ContextReconciliation`
- [ ] Реализовать `ContextManager.reconcile()`
- [ ] Реализовать `ContextManager.start_new_epoch()`
- [ ] Реализовать `ConversationSummarizer` с суммаризацией диалога
- [ ] Интеграция с LLMLoopStage
- [ ] Integration tests

**Результат:** Immutable baseline с историей изменений и интеллектуальной суммаризацией.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Memory Layer](./MEMORY_LAYER.md) — память между сессиями
- [Git Awareness](./GIT_AWARENESS.md) — осведомлённость о Git

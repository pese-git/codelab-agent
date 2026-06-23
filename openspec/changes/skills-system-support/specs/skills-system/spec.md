# Спецификация: Система Skills

> Версия: 3.0  
> Статус: Draft  
> Дата: 2026-06-18

## 1. Обзор

Система Skills предоставляет механизм динамического подключения специализированных инструкций, шаблонов и документации к AI-агенту только в момент необходимости.

### 1.1. Цели

- Минимальный расход контекстного окна
- Масштабирование до 500+ навыков
- Ленивая загрузка контента (progressive disclosure)
- Расширение без изменения ядра агента
- Совместимость с открытым стандартом [Agent Skills](https://agentskills.io)
- Работа в LOCAL и REMOTE режимах (через ACP протокол)

### 1.2. Не-цели (MVP)

- Search engine (BM25, embedding) — модель сама выбирает навык
- Skill dependencies и граф автозагрузки
- Кэширование на диск (L2)
- `context: fork` execution (subagent)
- Dynamic context injection (`!cmd`)
- Интеграция `allowed_tools` с PermissionManager

### 1.3. Терминология

| Термин | Определение |
|--------|-------------|
| **Skill** | Набор знаний и инструкций по конкретной предметной области |
| **Skill Package** | Каталог навыка с `SKILL.md` и опциональными ресурсами |
| **Skill Registry** | Индекс всех зарегистрированных навыков |
| **Progressive Disclosure** | Трёхуровневая загрузка: catalog → instructions → resources |
| **Activation** | Процесс загрузки полного содержимого навыка в контекст |
| **Lazy Deploy** | Механизм загрузки ресурсов skill в workspace клиента в REMOTE режиме |
| **Skill Deployer** | Компонент, отвечающий за деплой ресурсов на клиент |

### 1.4. Режимы работы

Система поддерживает два режима работы агента:

| Режим | Описание |
|-------|----------|
| **LOCAL** | Client и Server на одной машине. Прямой доступ к файловой системе. |
| **REMOTE** | Client и Server на разных машинах. Взаимодействие через ACP протокол (websocket/stdio). |

---

## 2. Архитектура

### 2.1. Распределение компонентов

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SERVER (Agent)                                │
│  ─────────────────                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ SkillConfigLoader│  │   SkillRegistry │  │   SkillCache    │     │
│  │  (scan + parse) │→ │  (in-memory)    │← │  (body cache)   │     │
│  └─────────────────┘  └────────┬────────┘  └─────────────────┘     │
│                                │                                     │
│  ┌─────────────────────────────┴─────────────────────────────┐     │
│  │            SkillCatalogBuilder                            │     │
│  └─────────────────────────────┬─────────────────────────────┘     │
│                                │                                     │
│  ┌─────────────────────────────┴─────────────────────────────┐     │
│  │              skill/load tool handler                      │     │
│  └─────────────────────────────┬─────────────────────────────┘     │
│                                │                                     │
│  ┌─────────────────────────────┴─────────────────────────────┐     │
│  │              SkillDeployer (REMOTE mode only)             │     │
│  └───────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
                                │
                        ACP Protocol
                        (terminal/*, fs/*)
                                │
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT                                        │
│  ────────                                                            │
│  workspace/                                                          │
│  ├── .codelab/skills-cache/  ← deployed resources (REMOTE)          │
│  └── (project files)                                                │
│                                                                      │
│  terminal/create → executes commands in workspace                   │
│  fs/read_text_file → reads files from workspace                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2. Execution Flow

```
1. STARTUP (на сервере)
   Server: SkillConfigLoader.load_all()
   → Scan scopes (project + user) via Path.glob()
   → Parse SKILL.md frontmatter
   → SkillRegistry initialized

2. CATALOG DISCLOSURE (в system prompt)
   Server: SystemPromptBuilder.build()
   → SkillCatalogBuilder.build_catalog()
   → Inject markdown list в system prompt

3. MODEL DECISION
   User: "Help me with PDF processing"
   Model → sees catalog → matches "pdf-processing"
   Model → calls skill/load tool

4. ACTIVATION (skill/load)
   Server: SkillRegistry.get("pdf-processing")
   Server: SkillRegistry.load_body() (from cache or disk)
   
   IF REMOTE MODE:
     Server: SkillDeployer.deploy_if_needed()
     → fs/write_text_file to client (ACP)
     → base_dir = workspace/.codelab/skills-cache/<skill>/
   
   IF LOCAL MODE:
     base_dir = skill.base_dir (server FS)
   
   Return: body + base_dir + resources list

5. EXECUTION (на клиенте через ACP)
   Model: terminal/create("python3 scripts/extract.py")
   Server → Client: terminal/create request (ACP)
   Client: executes command in workspace
   Client → Server: terminal output (ACP response)
```

### 2.3. LOCAL vs REMOTE: Сравнение

| Аспект | LOCAL Mode | REMOTE Mode |
|--------|------------|-------------|
| Skills location | Server FS | Server FS |
| Discovery | `Path.glob()` на сервере | `Path.glob()` на сервере |
| Body reading | `Path.read_text()` на сервере | `Path.read_text()` на сервере |
| Resource deploy | **Не нужен** | **Lazy Deploy** через ACP |
| `base_dir` в ответе | Server FS path | `<workspace>/.codelab/skills-cache/<skill>/` |
| Script execution | На сервере (прямой доступ) | На клиенте через `terminal/create` |

---

## 3. Формат Skill

### 3.1. Директория Skill

```
skill-name/
├── SKILL.md              # Required: metadata + instructions
├── scripts/              # Optional: executable code
├── references/           # Optional: documentation
├── assets/               # Optional: templates, resources
└── examples/             # Optional: usage examples
```

### 3.2. Формат SKILL.md

```yaml
---
# Required fields
name: pdf-processing
description: Extract PDF text, fill forms, merge files. Use when handling PDFs.

# Optional fields
license: Apache-2.0
compatibility: Requires Python 3.12+ and uv
allowed_tools:
  - "bash(python3 *)"
  - "fs/read_text_file"
metadata:
  author: example-org
  version: "1.0"

# Invocation control
disable_model_invocation: false
user_invocable: true

# Execution context (reserved for future)
context: inline  # "inline" | "fork"
agent: null
---

# PDF Processing Skill

Instructions for the agent...
```

### 3.3. Frontmatter Fields

| Поле | Required | Type | Default | Description |
|------|----------|------|---------|-------------|
| `name` | Yes | string | — | Уникальный идентификатор (lowercase, hyphens) |
| `description` | Yes | string | — | Описание навыка (max 1024 chars) |
| `license` | No | string | null | Лицензия |
| `compatibility` | No | string | null | Требования к окружению (max 500 chars) |
| `allowed_tools` | No | list[str] | [] | Pre-approved инструменты |
| `metadata` | No | dict[str,str] | {} | Дополнительные метаданные |
| `disable_model_invocation` | No | bool | false | Запретить автозагрузку моделью |
| `user_invocable` | No | bool | true | Доступен как slash-команда |
| `context` | No | string | "inline" | Контекст выполнения (reserved) |
| `agent` | No | string | null | Тип агента для fork (reserved) |

### 3.4. Валидация имени

- Длина: 1-64 символа
- Символы: lowercase letters, digits, hyphens
- Не начинается/заканчивается на hyphen
- Нет consecutive hyphens (`--`)
- Должен совпадать с именем родительской директории (warning если нет)

---

## 4. Discovery

### 4.1. Scopes

Приоритет (от высшего к низшему):

| Scope | Path | Description |
|-------|------|-------------|
| Project | `<workspace>/.codelab/skills/` | Проектные навыки |
| Project | `<workspace>/.agents/skills/` | Cross-client interoperability |
| User | `~/.codelab/skills/` | Глобальные навыки |
| User | `~/.agents/skills/` | Cross-client interoperability |

### 4.2. Rules

1. **Override**: Project skills override user skills с тем же именем
2. **Collision**: Если два skill с одинаковым именем в одном scope — первый wins, log warning
3. **Validation**:
   - Missing `description` → skip skill, log error
   - Unparseable YAML → skip skill, log error
   - Name mismatch directory → warn, load anyway (lenient)

### 4.3. Limits

- MAX_CATALOG_SKILLS = 100
- MAX_DESCRIPTION_LENGTH = 200

---

## 5. Data Models

### 5.1. SkillDefinition

```python
@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    location: Path          # Абсолютный путь к SKILL.md
    base_dir: Path          # Родительская директория навыка
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    disable_model_invocation: bool = False
    user_invocable: bool = True
    context: str = "inline"
    agent: str | None = None
```

### 5.2. SkillResources

```python
@dataclass(frozen=True)
class SkillResources:
    scripts: list[str]       # Relative paths
    references: list[str]    # Relative paths
    assets: list[str]        # Relative paths
```

### 5.3. DeployedSkill

```python
@dataclass(frozen=True)
class DeployedSkill:
    name: str
    hash: str               # SHA-256 hash
    deployed_at: float
    resources: list[str]
```

---

## 6. Components

### 6.1. SkillCache

```python
class SkillCache:
    def get(self, skill_name: str) -> str | None: ...
    def set(self, skill_name: str, body: str) -> None: ...
    def invalidate(self, skill_name: str) -> None: ...
    def clear(self) -> None: ...
```

### 6.2. SkillConfigLoader

```python
class SkillConfigLoader:
    def load_all(
        self,
        project_root: Path,
        global_config_dir: Path | None = None,
    ) -> dict[str, SkillDefinition]: ...
    
    def parse_skill_md(self, path: Path) -> SkillDefinition: ...
```

### 6.3. SkillRegistry

```python
class SkillRegistry:
    def __init__(self, loader: SkillConfigLoader, cache: SkillCache) -> None: ...
    async def initialize(self, project_root: Path, ...) -> None: ...
    def get(self, name: str) -> SkillDefinition | None: ...
    def get_all(self) -> dict[str, SkillDefinition]: ...
    def load_body(self, skill: SkillDefinition) -> str: ...
    def list_resources(self, skill: SkillDefinition) -> SkillResources: ...
```

### 6.4. SkillCatalogBuilder

```python
class SkillCatalogBuilder:
    MAX_CATALOG_SKILLS = 100
    MAX_DESCRIPTION_LENGTH = 200
    
    def build_catalog(self, skills: dict[str, SkillDefinition]) -> str: ...
    def build_behavioral_instructions(self) -> str: ...
```

### 6.5. SkillDeployer

```python
class SkillDeployer:
    CACHE_DIR = ".codelab/skills-cache"
    
    async def deploy_if_needed(
        self,
        skill: SkillDefinition,
        session: SessionState,
        client_rpc: ClientRPCBridge,
    ) -> str: ...
    
    def invalidate(self, skill_name: str) -> None: ...
    def clear(self) -> None: ...
```

### 6.6. SkillContextSource

Интеграция с Context Manager через Context Lifecycle.

```python
class SkillContextSource(ContextSource[dict[str, SkillDefinition]]):
    """Адаптер между SkillRegistry и ContextRegistry."""
    
    def __init__(self, skill_registry: SkillRegistry) -> None: ...
    async def load_skills(self) -> dict[str, SkillDefinition]: ...
    def render_baseline(self, skills: dict[str, SkillDefinition]) -> str: ...
    def render_update(self, skills: dict[str, SkillDefinition]) -> str: ...
```

**Назначение:**
- Предоставляет каталог доступных skills как источник контекста
- Рендерит baseline для system prompt
- Отслеживает изменения skills (новые/удалённые)
- Генерирует mid-conversation updates

**Архитектурное место:**
```
ContextManager
  └─ ContextRegistry
      ├─ InstructionContextSource
      ├─ ProjectContextSource
      ├─ EnvironmentContextSource
      ├─ GitContextSource
      └─ SkillContextSource ← интеграция со SkillRegistry
```

**Документация:** [Context Lifecycle](../../../../../doc/internals/system-architecture/CONTEXT_LIFECYCLE.md#skillcontextsource)

### 6.7. Tool Handler: skill/load

```python
def create_skill_load_handler(
    skill_registry: SkillRegistry,
    skill_deployer: SkillDeployer | None = None,
) -> Callable: ...
```

Tool definition:
- name: `skill/load`
- parameters: `{"skill_name": {"type": "string"}}`
- kind: `other`
- requires_permission: `false`

---

## 7. Security

### 7.1. Path Traversal Protection

```python
def validate_skill_path(base_dir: Path, requested_path: str) -> Path:
    resolved = (base_dir / requested_path).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise SkillPathTraversalError(...)
    return resolved
```

### 7.2. Trust Model

| Источник Skill | Trust Level | Deploy Behavior |
|----------------|-------------|-----------------|
| User skills (`~/.codelab/skills/`) | Trusted | Auto-deploy |
| Project skills (`.codelab/skills/`) | Untrusted | **Warn before deploy** |

### 7.3. Resource Limits

- MAX_RESOURCE_SIZE = 500 KB
- MAX_TOTAL_RESOURCES = 100
- MAX_DEPLOY_SIZE = 10 MB

---

## 8. File Structure

```
src/codelab/server/skills/
├── __init__.py
├── models.py
├── exceptions.py
├── cache.py
├── loader.py
├── registry.py
├── catalog.py
├── deployer.py
└── tools.py

tests/server/skills/
├── test_models.py
├── test_cache.py
├── test_loader.py
├── test_registry.py
├── test_catalog.py
├── test_deployer.py
└── test_tools.py
```

---

## 9. Compatibility

### 9.1. Agent Skills Standard

Совместимо с [agentskills.io](https://agentskills.io) specification.

### 9.2. Client Compatibility

| Client | Skills Location | Slash Format |
|--------|-----------------|--------------|
| Codelab | `.codelab/skills/` | `/skill-name` |
| Claude Code | `.claude/skills/` | `/skill-name` |
| VS Code Copilot | `.github/skills/`, `.agents/skills/` | `/skill-name` |

---

## 10. References

- [Agent Skills Specification](https://agentskills.io/specification)
- [Claude Code Skills Documentation](https://code.claude.com/docs/skills)
- [VS Code Agent Skills](https://code.visualstudio.com/docs/copilot/agent-skills)

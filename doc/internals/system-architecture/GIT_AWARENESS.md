# Git Awareness — Осведомлённость о Git

> Компоненты для анализа Git состояния и изменений

## Оглавление

- [Обзор](#обзор)
- [GitContextSource](#gitcontextsource)
- [GitDiffAnalyzer](#gitdiffanalyzer)
- [GitStatusProvider](#gitstatusprovider)
- [Интеграция с ContextManager](#интеграция-с-contextmanager)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Git Awareness отвечает за **понимание состояния Git**: какие файлы изменены, какие коммиты сделаны, какие ветки существуют.

**Компоненты:**
- `GitContextSource` — источник контекста из Git (status, branch, recent commits)
- `GitDiffAnalyzer` — анализ изменений (diff между коммитами, ветками)
- `GitStatusProvider` — провайдер Git status

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ ContextRegistry                                          │
│      └─ GitContextSource  ← Git Awareness                    │
│  └─ GitDiffAnalyzer       ← Git Awareness                    │
│  └─ GitStatusProvider     ← Git Awareness                    │
└─────────────────────────────────────────────────────────────┘
```

---

## GitContextSource

### Назначение

Источник контекста из Git: текущая ветка, последние коммиты, изменённые файлы.

### Интерфейс

```python
@dataclass
class GitState:
    """Состояние Git."""
    branch: str
    recent_commits: list[CommitInfo]
    modified_files: list[str]
    untracked_files: list[str]
    staged_files: list[str]

@dataclass
class CommitInfo:
    """Информация о коммите."""
    hash: str
    message: str
    author: str
    date: datetime
    files_changed: list[str]

class GitContextSource(ContextSource[GitState]):
    """Источник контекста из Git."""
    
    def __init__(self, cwd: str):
        self.cwd = cwd
        super().__init__(
            key="git",
            loader=self.load_git_state,
            codec=GitStateCodec(),
            render_baseline=self.render_baseline,
            render_update=self.render_update
        )
    
    async def load_git_state(self) -> GitState:
        """Загрузить состояние Git."""
        branch = await self._get_current_branch()
        recent_commits = await self._get_recent_commits(limit=5)
        status = await self._get_status()
        
        return GitState(
            branch=branch,
            recent_commits=recent_commits,
            modified_files=status["modified"],
            untracked_files=status["untracked"],
            staged_files=status["staged"]
        )
    
    async def _get_current_branch(self) -> str:
        """Получить текущую ветку."""
        result = await self._run_git("rev-parse --abbrev-ref HEAD")
        return result.strip()
    
    async def _get_recent_commits(self, limit: int = 5) -> list[CommitInfo]:
        """Получить последние коммиты."""
        result = await self._run_git(
            f"log --oneline --format='%H|%s|%an|%ai' -n {limit}"
        )
        
        commits = []
        for line in result.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 3)
            if len(parts) >= 4:
                commits.append(CommitInfo(
                    hash=parts[0],
                    message=parts[1],
                    author=parts[2],
                    date=datetime.fromisoformat(parts[3]),
                    files_changed=[]
                ))
        
        return commits
    
    async def _get_status(self) -> dict[str, list[str]]:
        """Получить Git status."""
        result = await self._run_git("status --porcelain")
        
        status = {
            "modified": [],
            "untracked": [],
            "staged": []
        }
        
        for line in result.strip().split('\n'):
            if not line:
                continue
            
            code = line[:2]
            file = line[3:]
            
            if code == "??":
                status["untracked"].append(file)
            elif code == " M":
                status["modified"].append(file)
            elif code in ("M ", "A ", "D "):
                status["staged"].append(file)
        
        return status
    
    async def _run_git(self, command: str) -> str:
        """Выполнить Git команду."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": f"git {command}", "cwd": self.cwd}
        )
        return result.output
    
    def render_baseline(self, state: GitState) -> str:
        """Рендер начального контекста."""
        parts = []
        
        parts.append(f"# Git State")
        parts.append(f"Branch: {state.branch}")
        parts.append("")
        
        if state.recent_commits:
            parts.append("## Recent Commits")
            for commit in state.recent_commits:
                parts.append(f"- {commit.hash[:7]}: {commit.message}")
            parts.append("")
        
        if state.modified_files:
            parts.append("## Modified Files")
            for file in state.modified_files:
                parts.append(f"- {file}")
            parts.append("")
        
        if state.untracked_files:
            parts.append("## Untracked Files")
            for file in state.untracked_files:
                parts.append(f"- {file}")
            parts.append("")
        
        return '\n'.join(parts)
    
    def render_update(self, state: GitState) -> str:
        """Рендер обновления."""
        return f"[Git updated: branch={state.branch}, {len(state.modified_files)} modified]"
```

---

## GitDiffAnalyzer

### Назначение

Анализ изменений: diff между коммитами, ветками, рабочим деревом.

### Интерфейс

```python
@dataclass
class DiffResult:
    """Результат diff."""
    files_changed: list[str]
    additions: int
    deletions: int
    diff_content: str

class GitDiffAnalyzer:
    """Анализ изменений Git."""
    
    def __init__(self, cwd: str, tool_registry: ToolRegistry):
        self.cwd = cwd
        self.tools = tool_registry
    
    async def diff_working_tree(self) -> DiffResult:
        """Diff рабочего дерева (unstaged changes)."""
        result = await self._run_git("diff")
        return self._parse_diff(result)
    
    async def diff_staged(self) -> DiffResult:
        """Diff staged changes."""
        result = await self._run_git("diff --cached")
        return self._parse_diff(result)
    
    async def diff_commits(
        self,
        from_commit: str,
        to_commit: str = "HEAD",
    ) -> DiffResult:
        """Diff между коммитами."""
        result = await self._run_git(f"diff {from_commit}..{to_commit}")
        return self._parse_diff(result)
    
    async def diff_branches(
        self,
        from_branch: str,
        to_branch: str,
    ) -> DiffResult:
        """Diff между ветками."""
        result = await self._run_git(f"diff {from_branch}..{to_branch}")
        return self._parse_diff(result)
    
    async def diff_file(
        self,
        file_path: str,
        from_commit: str | None = None,
    ) -> str:
        """Diff конкретного файла."""
        if from_commit:
            result = await self._run_git(f"diff {from_commit} -- {file_path}")
        else:
            result = await self._run_git(f"diff -- {file_path}")
        return result
    
    async def get_commit_changes(self, commit_hash: str) -> list[str]:
        """Получить список изменённых файлов в коммите."""
        result = await self._run_git(f"diff-tree --no-commit-id --name-only -r {commit_hash}")
        return [f for f in result.strip().split('\n') if f]
    
    async def _run_git(self, command: str) -> str:
        """Выполнить Git команду."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": f"git {command}", "cwd": self.cwd}
        )
        return result.output
    
    def _parse_diff(self, diff_output: str) -> DiffResult:
        """Парсить diff output."""
        files_changed = []
        additions = 0
        deletions = 0
        
        current_file = None
        
        for line in diff_output.split('\n'):
            if line.startswith('diff --git'):
                # Извлечь имя файла
                parts = line.split(' b/')
                if len(parts) > 1:
                    current_file = parts[1]
                    files_changed.append(current_file)
            elif line.startswith('+') and not line.startswith('+++'):
                additions += 1
            elif line.startswith('-') and not line.startswith('---'):
                deletions += 1
        
        return DiffResult(
            files_changed=files_changed,
            additions=additions,
            deletions=deletions,
            diff_content=diff_output
        )
```

### Пример использования

```python
analyzer = GitDiffAnalyzer(cwd="/path/to/project", tool_registry=tool_registry)

# Diff рабочего дерева
diff = await analyzer.diff_working_tree()
print(f"Changed files: {diff.files_changed}")
print(f"Additions: {diff.additions}, Deletions: {diff.deletions}")

# Diff между коммитами
diff = await analyzer.diff_commits("abc123", "def456")
print(f"Changed files: {diff.files_changed}")

# Diff конкретного файла
file_diff = await analyzer.diff_file("src/auth.service.ts")
print(file_diff)
```

---

## GitStatusProvider

### Назначение

Провайдер Git status: какие файлы изменены, какие staged, какие untracked.

### Интерфейс

```python
class GitStatusProvider:
    """Провайдер Git status."""
    
    def __init__(self, cwd: str, tool_registry: ToolRegistry):
        self.cwd = cwd
        self.tools = tool_registry
    
    async def get_status(self) -> dict[str, list[str]]:
        """Получить полный Git status."""
        result = await self._run_git("status --porcelain")
        
        status = {
            "modified": [],
            "untracked": [],
            "staged": [],
            "deleted": [],
            "renamed": []
        }
        
        for line in result.strip().split('\n'):
            if not line:
                continue
            
            code = line[:2]
            file = line[3:]
            
            if code == "??":
                status["untracked"].append(file)
            elif code == " M":
                status["modified"].append(file)
            elif code == "M ":
                status["staged"].append(file)
            elif code == "D ":
                status["deleted"].append(file)
            elif code.startswith("R"):
                status["renamed"].append(file)
        
        return status
    
    async def is_clean(self) -> bool:
        """Проверить чистое ли рабочее дерево."""
        status = await self.get_status()
        return all(len(v) == 0 for v in status.values())
    
    async def get_modified_files(self) -> list[str]:
        """Получить список изменённых файлов."""
        status = await self.get_status()
        return status["modified"] + status["staged"]
    
    async def _run_git(self, command: str) -> str:
        """Выполнить Git команду."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": f"git {command}", "cwd": self.cwd}
        )
        return result.output
```

---

## Интеграция с ContextManager

```python
class ContextManager:
    def __init__(
        self,
        git_source: GitContextSource,
        diff_analyzer: GitDiffAnalyzer,
        ...
    ):
        self.git_source = git_source
        self.diff_analyzer = diff_analyzer
    
    async def build_context(self, session, task):
        # 1. Получить Git состояние
        git_state = await self.git_source.load()
        
        # 2. Добавить в контекст
        git_context = self.git_source.render_baseline(git_state)
        
        # 3. Если задача связана с изменениями — добавить diff
        if self._is_change_related_task(task):
            diff = await self.diff_analyzer.diff_working_tree()
            git_context += f"\n\n## Current Changes\n{diff.diff_content}"
        
        return [git_context] + other_context
```

---

## Roadmap реализации

### Phase 3: Базовая реализация (1 неделя)

**Задачи:**
- [ ] Реализовать `GitContextSource` с загрузкой состояния
- [ ] Реализовать `GitStatusProvider` с парсингом status
- [ ] Реализовать `GitDiffAnalyzer` с базовым diff
- [ ] Unit tests

**Результат:** Базовая осведомлённость о Git.

### Phase 3: Расширенная реализация (1 неделя)

**Задачи:**
- [ ] Реализовать diff между коммитами и ветками
- [ ] Реализовать анализ изменений файлов
- [ ] Интеграция с ContextManager
- [ ] Integration tests

**Результат:** Полная осведомлённость о Git с анализом изменений.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Memory Layer](./MEMORY_LAYER.md) — память между сессиями

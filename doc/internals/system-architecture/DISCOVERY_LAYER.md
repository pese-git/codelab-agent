# Discovery Layer — Обнаружение и поиск

> Компоненты для анализа проекта и поиска релевантного кода

## Оглавление

- [Обзор](#обзор)
- [ProjectDiscovery](#projectdiscovery)
- [SearchEngine](#searchengine)
- [Интеграция с ContextGatherer](#интеграция-с-contextgatherer)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Discovery Layer отвечает за **обнаружение структуры проекта** и **поиск релевантного кода**.

**Компоненты:**
- `ProjectDiscovery` — анализ структуры проекта
- `SearchEngine` — поиск по кодовой базе

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ ContextGatherer                                          │
│      ├─ ProjectDiscovery  ← Discovery Layer                  │
│      ├─ SearchEngine      ← Discovery Layer                  │
│      └─ DependencyGraph                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## ProjectDiscovery

### Назначение

Анализ структуры проекта: определение языка, фреймворка, зависимостей, точки входа.

### Интерфейс

```python
@dataclass
class ProjectStructure:
    """Структура проекта."""
    root_path: str
    language: str  # "python", "typescript", "go", etc.
    framework: str | None  # "nestjs", "django", "fastapi", etc.
    package_manager: str | None  # "npm", "pnpm", "uv", "pip", etc.
    dependencies: list[str]
    entry_points: list[str]
    test_patterns: list[str]
    build_system: str | None  # "webpack", "vite", "make", etc.
    monorepo: bool
    workspaces: list[str]

class ProjectDiscovery:
    """Обнаружение структуры проекта."""
    
    async def discover(self, cwd: str) -> ProjectStructure:
        """
        Проанализировать структуру проекта.
        
        Pipeline:
        1. Определить язык (по файлам: package.json, pyproject.toml, etc.)
        2. Определить фреймворк (по зависимостям)
        3. Определить package manager
        4. Извлечь зависимости
        5. Найти точки входа
        6. Найти тестовые паттерны
        7. Определить monorepo структуру
        """
        ...
    
    async def detect_language(self, cwd: str) -> str:
        """Определить язык проекта."""
        # Проверить наличие сигнатурных файлов
        signatures = {
            "package.json": "typescript",
            "pyproject.toml": "python",
            "go.mod": "go",
            "Cargo.toml": "rust",
            "pom.xml": "java",
        }
        
        for file, lang in signatures.items():
            if await self.file_exists(join(cwd, file)):
                return lang
        
        return "unknown"
    
    async def detect_framework(self, cwd: str, language: str) -> str | None:
        """Определить фреймворк по зависимостям."""
        if language == "typescript":
            deps = await self.read_package_json(cwd)
            if "nestjs" in deps.get("dependencies", {}):
                return "nestjs"
            if "next" in deps.get("dependencies", {}):
                return "nextjs"
            if "react" in deps.get("dependencies", {}):
                return "react"
        
        elif language == "python":
            deps = await self.read_pyproject_toml(cwd)
            if "django" in deps:
                return "django"
            if "fastapi" in deps:
                return "fastapi"
            if "flask" in deps:
                return "flask"
        
        return None
    
    async def find_entry_points(self, cwd: str, language: str) -> list[str]:
        """Найти точки входа."""
        patterns = {
            "typescript": ["src/main.ts", "src/index.ts", "app.ts"],
            "python": ["main.py", "app.py", "manage.py"],
            "go": ["main.go", "cmd/*/main.go"],
        }
        
        entry_points = []
        for pattern in patterns.get(language, []):
            matches = await self.glob(cwd, pattern)
            entry_points.extend(matches)
        
        return entry_points
    
    async def find_test_patterns(self, cwd: str, language: str) -> list[str]:
        """Найти паттерны тестов."""
        patterns = {
            "typescript": ["**/*.test.ts", "**/*.spec.ts", "tests/**/*.ts"],
            "python": ["**/test_*.py", "**/*_test.py", "tests/**/*.py"],
            "go": ["**/*_test.go"],
        }
        
        return patterns.get(language, [])
    
    async def detect_monorepo(self, cwd: str, language: str) -> tuple[bool, list[str]]:
        """Определить monorepo структуру."""
        if language == "typescript":
            # Проверить pnpm-workspace.yaml
            if await self.file_exists(join(cwd, "pnpm-workspace.yaml")):
                workspaces = await self.parse_pnpm_workspaces(cwd)
                return True, workspaces
            
            # Проверить package.json workspaces
            package_json = await self.read_package_json(cwd)
            if "workspaces" in package_json:
                return True, package_json["workspaces"]
        
        elif language == "python":
            # Проверить pyproject.toml tool.poetry.packages
            pyproject = await self.read_pyproject_toml(cwd)
            if "tool" in pyproject and "poetry" in pyproject["tool"]:
                packages = pyproject["tool"]["poetry"].get("packages", [])
                if packages:
                    return True, [p["path"] for p in packages]
        
        return False, []
```

### Пример использования

```python
discovery = ProjectDiscovery()
structure = await discovery.discover("/path/to/project")

print(structure.language)  # "typescript"
print(structure.framework)  # "nestjs"
print(structure.package_manager)  # "pnpm"
print(structure.dependencies)  # ["@nestjs/core", "rxjs", ...]
print(structure.entry_points)  # ["src/main.ts"]
print(structure.test_patterns)  # ["**/*.test.ts", "**/*.spec.ts"]
print(structure.monorepo)  # False
```

### Интеграция с ContextGatherer

```python
class ContextGatherer:
    def __init__(self, discovery: ProjectDiscovery, ...):
        self.discovery = discovery
    
    async def gather_context(self, task: str, profile: TaskProfile, session: SessionState):
        # 1. Обнаружить структуру проекта
        structure = await self.discovery.discover(session.cwd)
        
        # 2. Использовать структуру для поиска
        if structure.framework == "nestjs":
            # Искать controllers, services, modules
            search_terms = profile.search_terms + ["controller", "service", "module"]
        
        elif structure.framework == "django":
            # Искать views, models, urls
            search_terms = profile.search_terms + ["views", "models", "urls"]
        
        # 3. Поиск с учётом структуры
        results = await self.search_engine.search(search_terms, structure)
        
        return GatheredContext(...)
```

---

## SearchEngine

### Назначение

Поиск по кодовой базе с использованием различных стратегий:
- Text search (git grep, ripgrep)
- Symbol search (tree-sitter, LSP)
- Semantic search (vector index, RAG)

### Интерфейс

```python
@dataclass
class SearchResult:
    """Результат поиска."""
    file_path: str
    line_number: int
    line_content: str
    match_content: str
    relevance_score: float  # 0.0 - 1.0

@dataclass
class SearchQuery:
    """Запрос на поиск."""
    terms: list[str]
    file_patterns: list[str] | None = None  # ["*.ts", "*.py"]
    exclude_patterns: list[str] | None = None  # ["node_modules/*"]
    max_results: int = 100
    search_type: Literal["text", "symbol", "semantic"] = "text"

class SearchEngine:
    """Поиск по кодовой базе."""
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_discovery: ProjectDiscovery,
    ):
        self.tools = tool_registry
        self.discovery = project_discovery
    
    async def search(
        self,
        query: SearchQuery,
        structure: ProjectStructure,
    ) -> list[SearchResult]:
        """
        Поиск по кодовой базе.
        
        Стратегия:
        1. Определить лучший метод поиска (git grep / rg / grep)
        2. Выполнить поиск
        3. Отфильтровать результаты
        4. Ранжировать по релевантности
        """
        # Определить метод поиска
        method = await self._detect_search_method(structure.root_path)
        
        # Выполнить поиск
        if method == "git_grep":
            results = await self._search_git_grep(query, structure.root_path)
        elif method == "ripgrep":
            results = await self._search_ripgrep(query, structure.root_path)
        else:
            results = await self._search_grep(query, structure.root_path)
        
        # Фильтрация
        results = self._filter_results(results, query)
        
        # Ранжирование
        results = self._rank_results(results, query.terms)
        
        return results[:query.max_results]
    
    async def _detect_search_method(self, cwd: str) -> str:
        """Определить лучший метод поиска."""
        # Проверить git repo
        if await self._is_git_repo(cwd):
            return "git_grep"
        
        # Проверить ripgrep
        if await self._has_ripgrep():
            return "ripgrep"
        
        # Fallback на grep
        return "grep"
    
    async def _search_git_grep(
        self,
        query: SearchQuery,
        cwd: str,
    ) -> list[SearchResult]:
        """Поиск через git grep."""
        results = []
        
        for term in query.terms:
            cmd = f"git grep -n '{term}'"
            
            if query.file_patterns:
                patterns = " ".join(query.file_patterns)
                cmd += f" -- {patterns}"
            
            result = await self.tools.execute(
                "terminal/create",
                {"command": cmd, "cwd": cwd}
            )
            
            if result.exit_code == 0:
                parsed = self._parse_git_grep_output(result.output)
                results.extend(parsed)
        
        return results
    
    async def _search_ripgrep(
        self,
        query: SearchQuery,
        cwd: str,
    ) -> list[SearchResult]:
        """Поиск через ripgrep."""
        results = []
        
        for term in query.terms:
            cmd = f"rg --json '{term}'"
            
            if query.file_patterns:
                for pattern in query.file_patterns:
                    cmd += f" --glob '{pattern}'"
            
            if query.exclude_patterns:
                for pattern in query.exclude_patterns:
                    cmd += f" --glob '!{pattern}'"
            
            result = await self.tools.execute(
                "terminal/create",
                {"command": cmd, "cwd": cwd}
            )
            
            if result.exit_code == 0:
                parsed = self._parse_ripgrep_output(result.output)
                results.extend(parsed)
        
        return results
    
    def _parse_git_grep_output(self, output: str) -> list[SearchResult]:
        """Parse git grep output."""
        results = []
        
        for line in output.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split(':', 2)
            if len(parts) >= 3:
                results.append(SearchResult(
                    file_path=parts[0],
                    line_number=int(parts[1]),
                    line_content=parts[2],
                    match_content=parts[2],
                    relevance_score=1.0
                ))
        
        return results
    
    def _parse_ripgrep_output(self, output: str) -> list[SearchResult]:
        """Parse ripgrep JSON output."""
        results = []
        
        for line in output.strip().split('\n'):
            if not line:
                continue
            
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    results.append(SearchResult(
                        file_path=match_data["path"]["text"],
                        line_number=match_data["line_number"],
                        line_content=match_data["lines"]["text"],
                        match_content=match_data["submatches"][0]["match"]["text"],
                        relevance_score=1.0
                    ))
            except (json.JSONDecodeError, KeyError):
                continue
        
        return results
    
    def _filter_results(
        self,
        results: list[SearchResult],
        query: SearchQuery,
    ) -> list[SearchResult]:
        """Фильтрация результатов."""
        filtered = []
        
        for result in results:
            # Исключить node_modules, .git, etc.
            if any(pattern in result.file_path for pattern in [
                "node_modules", ".git", "__pycache__", ".venv"
            ]):
                continue
            
            filtered.append(result)
        
        return filtered
    
    def _rank_results(
        self,
        results: list[SearchResult],
        terms: list[str],
    ) -> list[SearchResult]:
        """Ранжирование по релевантности."""
        for result in results:
            score = 0.0
            
            # Бонус за совпадение всех терминов
            for term in terms:
                if term.lower() in result.line_content.lower():
                    score += 1.0
            
            # Бонус за совпадение в имени файла
            for term in terms:
                if term.lower() in result.file_path.lower():
                    score += 0.5
            
            result.relevance_score = score
        
        # Сортировка по релевантности
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        
        return results
```

### Пример использования

```python
engine = SearchEngine(tool_registry, discovery)

query = SearchQuery(
    terms=["email", "validation"],
    file_patterns=["*.ts"],
    exclude_patterns=["node_modules/*"],
    max_results=50
)

structure = await discovery.discover("/path/to/project")
results = await engine.search(query, structure)

for result in results:
    print(f"{result.file_path}:{result.line_number}: {result.line_content}")
```

---

## Интеграция с ContextGatherer

```python
class ContextGatherer:
    """Сбор контекста для задачи."""
    
    def __init__(
        self,
        discovery: ProjectDiscovery,
        search_engine: SearchEngine,
        graph_builder: DependencyGraphBuilder,
        tool_registry: ToolRegistry,
    ):
        self.discovery = discovery
        self.search_engine = search_engine
        self.graph_builder = graph_builder
        self.tools = tool_registry
    
    async def gather_context(
        self,
        task: str,
        profile: TaskProfile,
        session: SessionState,
    ) -> GatheredContext:
        """Полный цикл сбора контекста."""
        
        # 1. Обнаружить структуру проекта
        structure = await self.discovery.discover(session.cwd)
        
        # 2. Построить поисковый запрос
        query = SearchQuery(
            terms=profile.search_terms,
            file_patterns=self._get_file_patterns(structure),
            exclude_patterns=["node_modules/*", ".git/*"],
            max_results=100
        )
        
        # 3. Поиск по кодовой базе
        search_results = await self.search_engine.search(query, structure)
        
        # 4. Извлечь файлы из результатов
        candidate_files = self._extract_files(search_results)
        
        # 5. Прочитать файлы
        file_contents = {}
        for file in candidate_files[:20]:
            content = await self.read_file(file)
            file_contents[file] = content
        
        # 6. Построить граф зависимостей
        graph = await self.graph_builder.build_from_files(
            candidate_files,
            self
        )
        
        # 7. Выбрать целевые файлы
        target_files = self._select_targets(graph, profile)
        
        return GatheredContext(
            task_profile=profile,
            project_structure=structure,
            target_files=target_files,
            dependency_graph=graph,
            file_contents=file_contents,
            search_results=search_results,
            summary=self._build_summary(profile, target_files, graph)
        )
    
    def _get_file_patterns(self, structure: ProjectStructure) -> list[str]:
        """Получить паттерны файлов для поиска."""
        patterns = {
            "typescript": ["*.ts", "*.tsx"],
            "python": ["*.py"],
            "go": ["*.go"],
            "rust": ["*.rs"],
        }
        
        return patterns.get(structure.language, ["*"])
```

---

## Roadmap реализации

### Phase 1: Базовая реализация (1 неделя)

**Задачи:**
- [ ] Реализовать `ProjectDiscovery.discover()`
- [ ] Реализовать `detect_language()`
- [ ] Реализовать `detect_framework()`
- [ ] Реализовать `find_entry_points()`
- [ ] Реализовать `SearchEngine.search()`
- [ ] Реализовать `_search_git_grep()`
- [ ] Реализовать `_search_ripgrep()`
- [ ] Unit tests

**Результат:** Базовое обнаружение проекта и поиск.

### Phase 2: Расширенная реализация (1 неделя)

**Задачи:**
- [ ] Реализовать `detect_monorepo()`
- [ ] Реализовать `find_test_patterns()`
- [ ] Реализовать ранжирование результатов
- [ ] Реализовать фильтрацию результатов
- [ ] Интеграция с ContextGatherer
- [ ] Integration tests

**Результат:** Продвинутый поиск с ранжированием.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы

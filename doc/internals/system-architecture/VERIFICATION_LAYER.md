# Verification Layer — Верификация результатов

> Компоненты для проверки корректности изменений: тесты, сборка, линтер

## Оглавление

- [Обзор](#обзор)
- [TestRunner](#testrunner)
- [BuildVerifier](#buildverifier)
- [LintVerifier](#lintverifier)
- [Интеграция с ExecutionEngine](#интеграция-с-executionengine)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Verification Layer отвечает за **проверку корректности изменений**: запуск тестов, проверку сборки, проверку линтера.

**Компоненты:**
- `TestRunner` — запуск тестов
- `BuildVerifier` — проверка сборки
- `LintVerifier` — проверка линтера

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ExecutionEngine                                             │
│  └─ TestRunner       ← Verification Layer                    │
│  └─ BuildVerifier    ← Verification Layer                    │
│  └─ LintVerifier     ← Verification Layer                    │
└─────────────────────────────────────────────────────────────┘
```

---

## TestRunner

### Назначение

Запуск тестов для проверки корректности изменений.

### Интерфейс

```python
@dataclass
class TestResult:
    """Результат тестов."""
    success: bool
    total_tests: int
    passed: int
    failed: int
    errors: list[TestError]
    duration: float
    output: str

@dataclass
class TestError:
    """Ошибка теста."""
    test_name: str
    error_message: str
    stack_trace: str
    file_path: str | None
    line_number: int | None

class TestRunner:
    """Запуск тестов."""
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_discovery: ProjectDiscovery,
    ):
        self.tools = tool_registry
        self.discovery = project_discovery
    
    async def run_tests(
        self,
        cwd: str,
        test_pattern: str | None = None,
    ) -> TestResult:
        """
        Запустить тесты.
        
        Автоматически определяет тестовый фреймворк:
        - Python: pytest
        - TypeScript: jest, vitest
        - Go: go test
        """
        structure = await self.discovery.discover(cwd)
        
        if structure.language == "python":
            return await self._run_pytest(cwd, test_pattern)
        elif structure.language == "typescript":
            return await self._run_jest(cwd, test_pattern)
        elif structure.language == "go":
            return await self._run_go_test(cwd, test_pattern)
        else:
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                errors=[],
                duration=0.0,
                output=f"Unsupported language: {structure.language}"
            )
    
    async def _run_pytest(
        self,
        cwd: str,
        test_pattern: str | None,
    ) -> TestResult:
        """Запустить pytest."""
        cmd = "pytest --tb=short -q"
        if test_pattern:
            cmd += f" -k '{test_pattern}'"
        
        result = await self.tools.execute(
            "terminal/create",
            {"command": cmd, "cwd": cwd}
        )
        
        return self._parse_pytest_output(result.output, result.exit_code)
    
    async def _run_jest(
        self,
        cwd: str,
        test_pattern: str | None,
    ) -> TestResult:
        """Запустить jest."""
        cmd = "npm test --"
        if test_pattern:
            cmd += f" --testPathPattern='{test_pattern}'"
        
        result = await self.tools.execute(
            "terminal/create",
            {"command": cmd, "cwd": cwd}
        )
        
        return self._parse_jest_output(result.output, result.exit_code)
    
    async def _run_go_test(
        self,
        cwd: str,
        test_pattern: str | None,
    ) -> TestResult:
        """Запустить go test."""
        cmd = "go test -v"
        if test_pattern:
            cmd += f" -run '{test_pattern}'"
        
        result = await self.tools.execute(
            "terminal/create",
            {"command": cmd, "cwd": cwd}
        )
        
        return self._parse_go_test_output(result.output, result.exit_code)
    
    def _parse_pytest_output(self, output: str, exit_code: int) -> TestResult:
        """Парсить вывод pytest."""
        # Пример: "5 passed, 2 failed in 1.23s"
        import re
        
        passed = 0
        failed = 0
        duration = 0.0
        
        match = re.search(r'(\d+) passed', output)
        if match:
            passed = int(match.group(1))
        
        match = re.search(r'(\d+) failed', output)
        if match:
            failed = int(match.group(1))
        
        match = re.search(r'in ([\d.]+)s', output)
        if match:
            duration = float(match.group(1))
        
        errors = self._extract_pytest_errors(output)
        
        return TestResult(
            success=exit_code == 0,
            total_tests=passed + failed,
            passed=passed,
            failed=failed,
            errors=errors,
            duration=duration,
            output=output
        )
    
    def _extract_pytest_errors(self, output: str) -> list[TestError]:
        """Извлечь ошибки из вывода pytest."""
        errors = []
        
        # Парсить FAILED тесты
        lines = output.split('\n')
        for i, line in enumerate(lines):
            if 'FAILED' in line:
                test_name = line.split('FAILED')[0].strip()
                error_msg = lines[i + 1] if i + 1 < len(lines) else ""
                
                errors.append(TestError(
                    test_name=test_name,
                    error_message=error_msg,
                    stack_trace="",
                    file_path=None,
                    line_number=None
                ))
        
        return errors
```

### Пример использования

```python
runner = TestRunner(tool_registry, discovery)

# Запустить все тесты
result = await runner.run_tests("/path/to/project")
print(f"Tests: {result.passed} passed, {result.failed} failed")

# Запустить конкретные тесты
result = await runner.run_tests(
    "/path/to/project",
    test_pattern="test_auth"
)

if not result.success:
    for error in result.errors:
        print(f"FAILED: {error.test_name}")
        print(f"Error: {error.error_message}")
```

---

## BuildVerifier

### Назначение

Проверка сборки проекта: компиляция, сборка зависимостей.

### Интерфейс

```python
@dataclass
class BuildResult:
    """Результат сборки."""
    success: bool
    errors: list[BuildError]
    warnings: list[str]
    duration: float
    output: str

@dataclass
class BuildError:
    """Ошибка сборки."""
    message: str
    file_path: str | None
    line_number: int | None
    column: int | None

class BuildVerifier:
    """Проверка сборки."""
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_discovery: ProjectDiscovery,
    ):
        self.tools = tool_registry
        self.discovery = project_discovery
    
    async def verify_build(self, cwd: str) -> BuildResult:
        """
        Проверить сборку проекта.
        
        Автоматически определяет систему сборки:
        - Python: python -m py_compile
        - TypeScript: tsc --noEmit
        - Go: go build
        """
        structure = await self.discovery.discover(cwd)
        
        if structure.language == "python":
            return await self._verify_python(cwd)
        elif structure.language == "typescript":
            return await self._verify_typescript(cwd)
        elif structure.language == "go":
            return await self._verify_go(cwd)
        else:
            return BuildResult(
                success=False,
                errors=[],
                warnings=[],
                duration=0.0,
                output=f"Unsupported language: {structure.language}"
            )
    
    async def _verify_python(self, cwd: str) -> BuildResult:
        """Проверить Python компиляцию."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": "python -m compileall -q .", "cwd": cwd}
        )
        
        return BuildResult(
            success=result.exit_code == 0,
            errors=self._parse_python_errors(result.output),
            warnings=[],
            duration=0.0,
            output=result.output
        )
    
    async def _verify_typescript(self, cwd: str) -> BuildResult:
        """Проверить TypeScript компиляцию."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": "npx tsc --noEmit", "cwd": cwd}
        )
        
        return BuildResult(
            success=result.exit_code == 0,
            errors=self._parse_typescript_errors(result.output),
            warnings=[],
            duration=0.0,
            output=result.output
        )
    
    async def _verify_go(self, cwd: str) -> BuildResult:
        """Проверить Go компиляцию."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": "go build ./...", "cwd": cwd}
        )
        
        return BuildResult(
            success=result.exit_code == 0,
            errors=self._parse_go_errors(result.output),
            warnings=[],
            duration=0.0,
            output=result.output
        )
    
    def _parse_typescript_errors(self, output: str) -> list[BuildError]:
        """Парсить TypeScript ошибки."""
        errors = []
        
        # Пример: "src/auth.service.ts(10,5): error TS2322: Type 'string' is not assignable"
        import re
        
        pattern = r'(.+)\((\d+),(\d+)\): error TS\d+: (.+)'
        for match in re.finditer(pattern, output):
            errors.append(BuildError(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                column=int(match.group(3)),
                message=match.group(4)
            ))
        
        return errors
```

---

## LintVerifier

### Назначение

Проверка линтера: стиль кода, best practices.

### Интерфейс

```python
@dataclass
class LintResult:
    """Результат линтера."""
    success: bool
    issues: list[LintIssue]
    duration: float
    output: str

@dataclass
class LintIssue:
    """Проблема линтера."""
    severity: Literal["error", "warning", "info"]
    message: str
    file_path: str
    line_number: int
    column: int | None
    rule: str | None

class LintVerifier:
    """Проверка линтера."""
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_discovery: ProjectDiscovery,
    ):
        self.tools = tool_registry
        self.discovery = project_discovery
    
    async def verify_lint(self, cwd: str) -> LintResult:
        """
        Проверить линтер.
        
        Автоматически определяет линтер:
        - Python: ruff, flake8
        - TypeScript: eslint
        - Go: golangci-lint
        """
        structure = await self.discovery.discover(cwd)
        
        if structure.language == "python":
            return await self._verify_ruff(cwd)
        elif structure.language == "typescript":
            return await self._verify_eslint(cwd)
        elif structure.language == "go":
            return await self._verify_golangci_lint(cwd)
        else:
            return LintResult(
                success=False,
                issues=[],
                duration=0.0,
                output=f"Unsupported language: {structure.language}"
            )
    
    async def _verify_ruff(self, cwd: str) -> LintResult:
        """Проверить ruff."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": "ruff check .", "cwd": cwd}
        )
        
        return LintResult(
            success=result.exit_code == 0,
            issues=self._parse_ruff_issues(result.output),
            duration=0.0,
            output=result.output
        )
    
    async def _verify_eslint(self, cwd: str) -> LintResult:
        """Проверить eslint."""
        result = await self.tools.execute(
            "terminal/create",
            {"command": "npx eslint . --format json", "cwd": cwd}
        )
        
        return LintResult(
            success=result.exit_code == 0,
            issues=self._parse_eslint_issues(result.output),
            duration=0.0,
            output=result.output
        )
    
    def _parse_ruff_issues(self, output: str) -> list[LintIssue]:
        """Парсить ruff issues."""
        issues = []
        
        # Пример: "src/auth.py:10:5: F401 Import unused"
        import re
        
        pattern = r'(.+):(\d+):(\d+): (\w+) (.+)'
        for match in re.finditer(pattern, output):
            issues.append(LintIssue(
                severity="error",
                file_path=match.group(1),
                line_number=int(match.group(2)),
                column=int(match.group(3)),
                rule=match.group(4),
                message=match.group(5)
            ))
        
        return issues
```

---

## Интеграция с ExecutionEngine

```python
class ExecutionEngine:
    def __init__(
        self,
        test_runner: TestRunner,
        build_verifier: BuildVerifier,
        lint_verifier: LintVerifier,
        ...
    ):
        self.test_runner = test_runner
        self.build_verifier = build_verifier
        self.lint_verifier = lint_verifier
    
    async def execute_with_verification(self, session, task):
        # 1. Выполнить задачу
        result = await self.execute(session, task)
        
        # 2. Проверить сборку
        build_result = await self.build_verifier.verify_build(session.cwd)
        if not build_result.success:
            # Попытаться исправить ошибки сборки
            fixed = await self._fix_build_errors(build_result.errors)
            if not fixed:
                return ExecutionResult(success=False, error="Build failed")
        
        # 3. Проверить линтер
        lint_result = await self.lint_verifier.verify_lint(session.cwd)
        if not lint_result.success:
            # Попытаться исправить ошибки линтера
            await self._fix_lint_issues(lint_result.issues)
        
        # 4. Запустить тесты
        test_result = await self.test_runner.run_tests(session.cwd)
        if not test_result.success:
            # Попытаться исправить ошибки тестов
            fixed = await self._fix_test_errors(test_result.errors)
            if not fixed:
                return ExecutionResult(success=False, error="Tests failed")
        
        return ExecutionResult(success=True, result=result)
```

---

## Roadmap реализации

### Phase 3: Базовая реализация (2 недели)

**Задачи:**
- [ ] Реализовать `TestRunner` с поддержкой pytest, jest, go test
- [ ] Реализовать `BuildVerifier` с поддержкой Python, TypeScript, Go
- [ ] Реализовать `LintVerifier` с поддержкой ruff, eslint, golangci-lint
- [ ] Unit tests

**Результат:** Базовая верификация результатов.

### Phase 3: Расширенная реализация (1 неделя)

**Задачи:**
- [ ] Реализовать автоматическое исправление ошибок
- [ ] Интеграция с ExecutionEngine
- [ ] Integration tests

**Результат:** Полная верификация с автоматическим исправлением.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Git Awareness](./GIT_AWARENESS.md) — осведомлённость о Git

"""Unit тесты для мультиязыкового Skeletonizer."""

import pytest

from codelab.server.agent.context.skeletonizer import (
    CompositeSkeletonizer,
    NoOpStrategy,
    RegexStrategy,
    TreeSitterStrategy,
)
from codelab.server.agent.context.skeletonizer.registry import LanguageRegistry


class TestLanguageRegistry:
    """Тесты для LanguageRegistry."""

    def test_get_language_python(self):
        """Определение Python по расширению."""
        assert LanguageRegistry.get_language("test.py") == "python"

    def test_get_language_typescript(self):
        """Определение TypeScript по расширению."""
        assert LanguageRegistry.get_language("test.ts") == "typescript"
        assert LanguageRegistry.get_language("test.tsx") == "typescript"

    def test_get_language_dart(self):
        """Определение Dart по расширению."""
        assert LanguageRegistry.get_language("test.dart") == "dart"

    def test_get_language_go(self):
        """Определение Go по расширению."""
        assert LanguageRegistry.get_language("test.go") == "go"

    def test_get_language_rust(self):
        """Определение Rust по расширению."""
        assert LanguageRegistry.get_language("test.rs") == "rust"

    def test_get_language_java(self):
        """Определение Java по расширению."""
        assert LanguageRegistry.get_language("test.java") == "java"

    def test_get_language_cpp(self):
        """Определение C++ по расширению."""
        assert LanguageRegistry.get_language("test.cpp") == "cpp"
        assert LanguageRegistry.get_language("test.h") == "cpp"

    def test_get_language_unknown(self):
        """Неизвестное расширение возвращает None."""
        assert LanguageRegistry.get_language("test.xyz") is None

    def test_supported_languages(self):
        """Список поддерживаемых языков."""
        languages = LanguageRegistry.supported_languages()
        assert "python" in languages
        assert "typescript" in languages
        assert "dart" in languages
        assert "go" in languages
        assert "rust" in languages
        assert "java" in languages
        assert "cpp" in languages

    def test_get_parser(self):
        """Получение parser для языка."""
        registry = LanguageRegistry()
        parser = registry.get_parser("python")
        assert parser is not None

    def test_get_parser_unknown(self):
        """Неизвестный язык возвращает None."""
        registry = LanguageRegistry()
        parser = registry.get_parser("unknown")
        assert parser is None


class TestTreeSitterStrategyPython:
    """Тесты для TreeSitterStrategy с Python."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_python(self, strategy):
        """can_handle() возвращает True для .py файлов."""
        assert strategy.can_handle("test.py") is True

    def test_skeletonize_simple_function(self, strategy):
        """Скелетирование простой функции."""
        code = """
def hello():
    print("Hello")
    return "World"
"""
        result = strategy.skeletonize(code, "test.py")

        assert "def hello():" in result
        assert "..." in result
        assert 'print("Hello")' not in result

    def test_skeletonize_class_with_methods(self, strategy):
        """Скелетирование класса с методами."""
        code = """
class MyClass:
    def __init__(self, value: int):
        self.value = value

    def get_value(self) -> int:
        return self.value
"""
        result = strategy.skeletonize(code, "test.py")

        assert "class MyClass:" in result
        assert "def __init__(self, value: int):" in result
        assert "def get_value(self) -> int:" in result
        assert "..." in result
        assert "self.value = value" not in result

    def test_skeletonize_preserves_imports(self, strategy):
        """Скелетирование сохраняет импорты."""
        code = """
import os
import sys
from pathlib import Path

def helper():
    pass
"""
        result = strategy.skeletonize(code, "test.py")

        assert "import os" in result
        assert "import sys" in result
        assert "from pathlib import Path" in result

    def test_skeletonize_multibyte_utf8_not_corrupted(self, strategy):
        """Многобайтовые символы (кириллица) до тела не повреждаются.

        start_point/end_point в tree-sitter — байтовые смещения; при срезах
        по символам кириллица в сигнатуре/строках ломалась. Проверяем, что
        сигнатура сохраняется целиком, а тело сворачивается.
        """
        code = (
            "# Комментарий с кириллицей и эмодзи 🚀\n"
            "def приветствие(имя: str) -> str:\n"
            '    сообщение = f"Привет, {имя}!"\n'
            "    return сообщение\n"
        )
        result = strategy.skeletonize(code, "test.py")

        # Результат — валидный UTF-8 без символов-замен
        assert "�" not in result
        # Сигнатура с кириллицей цела
        assert "def приветствие(имя: str) -> str:" in result
        # Тело свёрнуто
        assert "..." in result
        assert "Привет" not in result


class TestTreeSitterStrategyTypeScript:
    """Тесты для TreeSitterStrategy с TypeScript."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_typescript(self, strategy):
        """can_handle() возвращает True для .ts файлов."""
        assert strategy.can_handle("test.ts") is True
        assert strategy.can_handle("test.tsx") is True

    def test_skeletonize_function(self, strategy):
        """Скелетирование функции TypeScript."""
        code = """
function greet(name: string): string {
    return `Hello, ${name}!`;
}
"""
        result = strategy.skeletonize(code, "test.ts")

        assert "function greet(name: string): string" in result
        assert "{}" in result
        assert "return" not in result

    def test_skeletonize_class(self, strategy):
        """Скелетирование класса TypeScript."""
        code = """
class Person {
    constructor(public name: string) {}

    greet(): string {
        return `Hello, ${this.name}!`;
    }
}
"""
        result = strategy.skeletonize(code, "test.ts")

        assert "class Person" in result
        assert "{}" in result


class TestTreeSitterStrategyDart:
    """Тесты для TreeSitterStrategy с Dart."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_dart(self, strategy):
        """can_handle() возвращает True для .dart файлов."""
        assert strategy.can_handle("test.dart") is True

    def test_skeletonize_function(self, strategy):
        """Скелетирование функции Dart."""
        code = """
String greet(String name) {
    return 'Hello, $name!';
}
"""
        result = strategy.skeletonize(code, "test.dart")

        assert "String greet(String name)" in result
        assert "{}" in result


class TestTreeSitterStrategyGo:
    """Тесты для TreeSitterStrategy с Go."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_go(self, strategy):
        """can_handle() возвращает True для .go файлов."""
        assert strategy.can_handle("test.go") is True

    def test_skeletonize_function(self, strategy):
        """Скелетирование функции Go."""
        code = """
func greet(name string) string {
    return "Hello, " + name
}
"""
        result = strategy.skeletonize(code, "test.go")

        assert "func greet(name string) string" in result
        assert "{}" in result


class TestTreeSitterStrategyRust:
    """Тесты для TreeSitterStrategy с Rust."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_rust(self, strategy):
        """can_handle() возвращает True для .rs файлов."""
        assert strategy.can_handle("test.rs") is True

    def test_skeletonize_function(self, strategy):
        """Скелетирование функции Rust."""
        code = """
fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}
"""
        result = strategy.skeletonize(code, "test.rs")

        assert "fn greet(name: &str) -> String" in result
        assert "{}" in result


class TestTreeSitterStrategyJava:
    """Тесты для TreeSitterStrategy с Java."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_java(self, strategy):
        """can_handle() возвращает True для .java файлов."""
        assert strategy.can_handle("test.java") is True

    def test_skeletonize_method(self, strategy):
        """Скелетирование метода Java."""
        code = """
public class Person {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
"""
        result = strategy.skeletonize(code, "test.java")

        assert "public String greet(String name)" in result
        assert "{}" in result


class TestTreeSitterStrategyCpp:
    """Тесты для TreeSitterStrategy с C++."""

    @pytest.fixture
    def strategy(self):
        return TreeSitterStrategy()

    def test_can_handle_cpp(self, strategy):
        """can_handle() возвращает True для .cpp файлов."""
        assert strategy.can_handle("test.cpp") is True
        assert strategy.can_handle("test.h") is True

    def test_skeletonize_function(self, strategy):
        """Скелетирование функции C++."""
        code = """
int add(int a, int b) {
    return a + b;
}
"""
        result = strategy.skeletonize(code, "test.cpp")

        assert "int add(int a, int b)" in result
        assert "{}" in result


class TestRegexStrategy:
    """Тесты для RegexStrategy."""

    @pytest.fixture
    def strategy(self):
        return RegexStrategy()

    def test_can_handle_any(self, strategy):
        """can_handle() возвращает True для любых файлов."""
        assert strategy.can_handle("test.xyz") is True

    def test_skeletonize_c_like(self, strategy):
        """Скелетирование C-подобного кода."""
        code = """
int main() {
    printf("Hello");
    return 0;
}
"""
        result = strategy.skeletonize(code, "test.c")

        assert "int main()" in result
        assert "{}" in result


class TestNoOpStrategy:
    """Тесты для NoOpStrategy."""

    @pytest.fixture
    def strategy(self):
        return NoOpStrategy()

    def test_can_handle_any(self, strategy):
        """can_handle() возвращает True для любых файлов."""
        assert strategy.can_handle("test.xyz") is True

    def test_skeletonize_returns_original(self, strategy):
        """skeletonize() возвращает оригинальный код."""
        code = "def hello(): pass"
        assert strategy.skeletonize(code, "test.py") == code


class TestCompositeSkeletonizer:
    """Тесты для CompositeSkeletonizer."""

    @pytest.fixture
    def skeletonizer(self):
        return CompositeSkeletonizer()

    def test_can_handle_python(self, skeletonizer):
        """can_handle() возвращает True для Python."""
        assert skeletonizer.can_handle("test.py") is True

    def test_can_handle_binary(self, skeletonizer):
        """can_handle() возвращает False для бинарных файлов."""
        assert skeletonizer.can_handle("test.png") is False
        assert skeletonizer.can_handle("test.exe") is False

    def test_skeletonize_file_python(self, skeletonizer):
        """skeletonize_file() скелетирует Python код."""
        code = """
def hello():
    print("Hello")
"""
        result = skeletonizer.skeletonize_file(code, "test.py")

        assert "def hello():" in result
        assert "..." in result

    def test_skeletonize_file_typescript(self, skeletonizer):
        """skeletonize_file() скелетирует TypeScript код."""
        code = """
function greet(): string {
    return "Hello";
}
"""
        result = skeletonizer.skeletonize_file(code, "test.ts")

        assert "function greet()" in result
        assert "{}" in result


class TestDeterminism:
    """Golden тесты детерминизма."""

    @pytest.fixture
    def skeletonizer(self):
        return CompositeSkeletonizer()

    def test_python_deterministic(self, skeletonizer):
        """Python: 100 запусков дают одинаковый результат."""
        code = """
import os

def hello():
    print("Hello")

class World:
    def method(self):
        pass
"""
        results = [skeletonizer.skeletonize_file(code, "test.py") for _ in range(100)]
        assert len(set(results)) == 1

    def test_typescript_deterministic(self, skeletonizer):
        """TypeScript: 100 запусков дают одинаковый результат."""
        code = """
import { foo } from 'bar';

function hello(): void {
    console.log("Hello");
}

class World {
    method(): void {
        console.log("World");
    }
}
"""
        results = [skeletonizer.skeletonize_file(code, "test.ts") for _ in range(100)]
        assert len(set(results)) == 1

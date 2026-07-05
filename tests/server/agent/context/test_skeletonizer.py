"""Unit тесты для CodeSkeletonizer."""

import pytest

from codelab.server.agent.context.skeletonizer import (
    NoOpSkeletonizer,
    PythonASTSkeletonizer,
)


class TestPythonASTSkeletonizer:
    """Тесты для PythonASTSkeletonizer."""

    @pytest.fixture
    def skeletonizer(self):
        return PythonASTSkeletonizer()

    def test_can_handle_python(self, skeletonizer):
        """can_handle() возвращает True для .py файлов."""
        assert skeletonizer.can_handle("test.py") is True
        assert skeletonizer.can_handle("/path/to/file.py") is True

    def test_can_handle_other_extensions(self, skeletonizer):
        """can_handle() возвращает False для других расширений."""
        assert skeletonizer.can_handle("test.json") is False
        assert skeletonizer.can_handle("test.md") is False
        assert skeletonizer.can_handle("test.dart") is False
        assert skeletonizer.can_handle("test.ts") is False

    def test_skeletonize_simple_function(self, skeletonizer):
        """Скелетирование простой функции."""
        code = '''
def hello():
    print("Hello")
    return "World"
'''
        result = skeletonizer.skeletonize(code)

        assert "def hello():" in result
        assert "..." in result
        assert 'print("Hello")' not in result
        assert 'return "World"' not in result

    def test_skeletonize_function_with_args(self, skeletonizer):
        """Скелетирование функции с аргументами."""
        code = '''
def greet(name: str, greeting: str = "Hello") -> str:
    """Docstring."""
    return f"{greeting}, {name}!"
'''
        result = skeletonizer.skeletonize(code)

        assert "def greet(name: str, greeting: str" in result
        assert "-> str:" in result
        assert "..." in result
        assert "Docstring" not in result

    def test_skeletonize_class(self, skeletonizer):
        """Скелетирование класса с методами."""
        code = '''
class MyClass:
    """Class docstring."""

    def __init__(self, value: int):
        self.value = value

    def get_value(self) -> int:
        return self.value

    @staticmethod
    def helper():
        pass
'''
        result = skeletonizer.skeletonize(code)

        assert "class MyClass:" in result
        assert "def __init__(self, value: int):" in result
        assert "def get_value(self) -> int:" in result
        assert "@staticmethod" in result
        assert "..." in result
        assert "self.value = value" not in result
        assert "return self.value" not in result

    def test_skeletonize_imports(self, skeletonizer):
        """Скелетирование сохраняет импорты."""
        code = '''
import os
import sys
from pathlib import Path
from typing import List, Dict
'''
        result = skeletonizer.skeletonize(code)

        assert "import" in result
        assert "os" in result
        assert "sys" in result
        assert "Path" in result

    def test_skeletonize_async_function(self, skeletonizer):
        """Скелетирование async функции."""
        code = '''
async def fetch_data(url: str) -> dict:
    response = await http.get(url)
    return response.json()
'''
        result = skeletonizer.skeletonize(code)

        assert "async def fetch_data(url: str) -> dict:" in result
        assert "..." in result
        assert "await http.get" not in result

    def test_skeletonize_decorators(self, skeletonizer):
        """Скелетирование сохраняет декораторы."""
        code = '''
@property
def name(self) -> str:
    return self._name

@staticmethod
def helper():
    pass
'''
        result = skeletonizer.skeletonize(code)

        assert "@property" in result
        assert "@staticmethod" in result

    def test_skeletonize_syntax_error_fallback(self, skeletonizer):
        """При SyntaxError возвращает оригинальный код."""
        code = '''
def broken(
    # missing closing paren
'''
        result = skeletonizer.skeletonize(code)

        assert result == code

    def test_skeletonize_deterministic(self, skeletonizer):
        """Детерминированный вывод: 100 запусков дают одинаковый результат."""
        code = '''
import os
import sys
from typing import List

class MyClass:
    def __init__(self):
        self.value = 0

    def method(self) -> int:
        return self.value

def helper():
    pass
'''
        results = [skeletonizer.skeletonize(code) for _ in range(100)]

        assert len(set(results)) == 1

    def test_skeletonize_preserves_type_hints(self, skeletonizer):
        """Скелетирование сохраняет type hints."""
        code = '''
def process(data: list[dict[str, int]]) -> tuple[bool, str]:
    return True, "done"
'''
        result = skeletonizer.skeletonize(code)

        assert "data: list[dict[str, int]]" in result
        assert "-> tuple[bool, str]:" in result

    def test_skeletonize_nested_classes(self, skeletonizer):
        """Скелетирование вложенных классов."""
        code = '''
class Outer:
    class Inner:
        def method(self):
            pass
'''
        result = skeletonizer.skeletonize(code)

        assert "class Outer:" in result
        assert "class Inner:" in result
        assert "..." in result

    def test_skeletonize_empty_code(self, skeletonizer):
        """Скелетирование пустого кода."""
        result = skeletonizer.skeletonize("")
        assert result == "\n"

    def test_skeletonize_comments_removed(self, skeletonizer):
        """Комментарии удаляются при скелетировании (ast.unparse не сохраняет)."""
        code = '''
# This is a comment
def hello():
    # Another comment
    pass
'''
        result = skeletonizer.skeletonize(code)

        assert "# This is a comment" not in result
        assert "def hello():" in result


class TestNoOpSkeletonizer:
    """Тесты для NoOpSkeletonizer."""

    def test_can_handle_always_false(self):
        """can_handle() всегда возвращает False."""
        skeletonizer = NoOpSkeletonizer()
        assert skeletonizer.can_handle("test.py") is False
        assert skeletonizer.can_handle("test.json") is False

    def test_skeletonize_returns_original(self):
        """skeletonize() возвращает оригинальный код."""
        skeletonizer = NoOpSkeletonizer()
        code = "def hello(): pass"
        assert skeletonizer.skeletonize(code) == code

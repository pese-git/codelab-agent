"""Unit тесты для DependencyGraph."""

import pytest

from codelab.server.agent.context.dependency_graph import RegexDependencyGraph


def test_dependency_graph_parse_imports():
    """Тест парсинга импортов из Python кода."""
    graph = RegexDependencyGraph()
    code = """
import os
import sys
from pathlib import Path
from typing import List, Dict
from . import local_module
from ..parent import parent_module
"""
    imports = graph.parse_imports(code)

    assert "os" in imports
    assert "sys" in imports
    assert "pathlib" in imports
    assert "typing" in imports


def test_dependency_graph_add_file_and_get_dependencies():
    """Тест добавления файла и получения зависимостей."""
    graph = RegexDependencyGraph()

    graph.add_file("src/main.py", ["src/utils.py", "src/config.py"])
    graph.add_file("src/utils.py", ["src/helpers.py"])

    deps = graph.get_dependencies("src/main.py")

    assert "src/utils.py" in deps
    assert "src/config.py" in deps


def test_dependency_graph_get_dependents():
    """Тест получения файлов, зависящих от данного."""
    graph = RegexDependencyGraph()

    graph.add_file("src/main.py", ["src/utils.py"])
    graph.add_file("src/other.py", ["src/utils.py"])

    dependents = graph.get_dependents("src/utils.py")

    assert "src/main.py" in dependents
    assert "src/other.py" in dependents


def test_dependency_graph_recursive_dependencies():
    """Тест рекурсивного получения зависимостей."""
    graph = RegexDependencyGraph()

    graph.add_file("src/a.py", ["src/b.py"])
    graph.add_file("src/b.py", ["src/c.py"])
    graph.add_file("src/c.py", ["src/d.py"])

    deps = graph.get_dependencies("src/a.py", recursive=True)

    assert "src/b.py" in deps
    assert "src/c.py" in deps
    assert "src/d.py" in deps


def test_dependency_graph_circular_dependencies():
    """Тест защиты от циклических зависимостей."""
    graph = RegexDependencyGraph()

    graph.add_file("src/a.py", ["src/b.py"])
    graph.add_file("src/b.py", ["src/a.py"])

    deps = graph.get_dependencies("src/a.py", recursive=True)

    assert "src/b.py" in deps
    assert "src/a.py" not in deps


def test_dependency_graph_clear():
    """Тест очистки графа."""
    graph = RegexDependencyGraph()

    graph.add_file("src/main.py", ["src/utils.py"])
    graph.clear()

    deps = graph.get_dependencies("src/main.py")
    assert len(deps) == 0


def test_dependency_graph_nonexistent_file():
    """Тест получения зависимостей для несуществующего файла."""
    graph = RegexDependencyGraph()

    deps = graph.get_dependencies("nonexistent.py")
    assert len(deps) == 0

    dependents = graph.get_dependents("nonexistent.py")
    assert len(dependents) == 0


def test_dependency_graph_parse_complex_imports():
    """Тест парсинга сложных импортов."""
    graph = RegexDependencyGraph()
    code = """
from typing import (
    List,
    Dict,
    Optional,
)
import os.path
from collections.abc import Callable
"""
    imports = graph.parse_imports(code)

    assert "typing" in imports
    assert "os.path" in imports
    assert "collections.abc" in imports

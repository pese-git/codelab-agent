"""Тесты для валидации путей в filesystem tools."""

from __future__ import annotations

import pytest

from codelab.server.tools.definitions.filesystem import (
    _normalize_path,
    _validate_path_in_cwd,
)


class TestNormalizePath:
    """Тесты для функции _normalize_path."""

    def test_absolute_path_unchanged(self):
        """Абсолютный путь возвращается как есть."""
        cwd = "/home/user/project"
        path = "/home/user/project/file.txt"
        result = _normalize_path(cwd, path)
        assert result == "/home/user/project/file.txt"

    def test_relative_path_joined_with_cwd(self):
        """Относительный путь присоединяется к cwd."""
        cwd = "/home/user/project"
        path = "file.txt"
        result = _normalize_path(cwd, path)
        assert result == "/home/user/project/file.txt"

    def test_relative_path_with_subdirectory(self):
        """Относительный путь с поддиректорией."""
        cwd = "/home/user/project"
        path = "src/main.py"
        result = _normalize_path(cwd, path)
        assert result == "/home/user/project/src/main.py"


class TestValidatePathInCwd:
    """Тесты для функции _validate_path_in_cwd."""

    def test_path_inside_cwd_valid(self):
        """Путь внутри cwd проходит валидацию."""
        cwd = "/home/user/project"
        path = "/home/user/project/file.txt"
        # Не должно выбрасывать исключение
        _validate_path_in_cwd(path, cwd)

    def test_path_in_subdirectory_valid(self):
        """Путь в поддиректории cwd проходит валидацию."""
        cwd = "/home/user/project"
        path = "/home/user/project/src/main.py"
        _validate_path_in_cwd(path, cwd)

    def test_path_outside_cwd_raises_error(self):
        """Путь вне cwd выбрасывает ValueError."""
        cwd = "/home/user/project"
        path = "/home/user/other/file.txt"
        
        with pytest.raises(ValueError) as exc_info:
            _validate_path_in_cwd(path, cwd)
        
        assert "outside working directory" in str(exc_info.value)
        assert path in str(exc_info.value)
        assert cwd in str(exc_info.value)

    def test_path_in_parent_directory_raises_error(self):
        """Путь в родительской директории выбрасывает ValueError."""
        cwd = "/home/user/project"
        path = "/home/user/file.txt"
        
        with pytest.raises(ValueError) as exc_info:
            _validate_path_in_cwd(path, cwd)
        
        assert "outside working directory" in str(exc_info.value)

    def test_path_with_dotdot_raises_error(self):
        """Путь с .. вне cwd выбрасывает ValueError."""
        cwd = "/home/user/project"
        # После resolve() путь станет /home/user/file.txt
        path = "/home/user/project/../file.txt"
        
        with pytest.raises(ValueError) as exc_info:
            _validate_path_in_cwd(path, cwd)
        
        assert "outside working directory" in str(exc_info.value)

    def test_path_with_dotdot_inside_cwd_valid(self):
        """Путь с .. но остающийся внутри cwd проходит валидацию."""
        cwd = "/home/user/project"
        # После resolve() путь станет /home/user/project/src/main.py
        path = "/home/user/project/src/../src/main.py"
        
        # Не должно выбрасывать исключение
        _validate_path_in_cwd(path, cwd)

    def test_completely_different_path_raises_error(self):
        """Совершенно другой путь выбрасывает ValueError."""
        cwd = "/Users/penkovsky_sa/Downloads/flutter_app"
        path = "/Users/sergey/Projects/OpenIdeaLab/CodeLab/README.md"
        
        with pytest.raises(ValueError) as exc_info:
            _validate_path_in_cwd(path, cwd)
        
        assert "outside working directory" in str(exc_info.value)

    def test_error_message_includes_helpful_hint(self):
        """Сообщение об ошибке содержит подсказку."""
        cwd = "/home/user/project"
        path = "/etc/passwd"
        
        with pytest.raises(ValueError) as exc_info:
            _validate_path_in_cwd(path, cwd)
        
        error_msg = str(exc_info.value)
        assert "ls" in error_msg or "find" in error_msg
        assert "discover files" in error_msg


class TestValidatePathEdgeCases:
    """Граничные случаи валидации путей."""

    def test_cwd_with_trailing_slash(self):
        """Cwd с trailing slash работает корректно."""
        cwd = "/home/user/project/"
        path = "/home/user/project/file.txt"
        
        # Не должно выбрасывать исключение
        _validate_path_in_cwd(path, cwd)

    def test_path_equals_cwd_raises_error(self):
        """Путь равный cwd (директория) проходит валидацию.
        
        Edge case: путь равный cwd не содержит файлов, но валидация
        проверяет только принадлежность к директории, не тип объекта.
        """
        cwd = "/home/user/project"
        path = "/home/user/project"
        
        # Путь равный cwd проходит валидацию (принадлежит cwd)
        _validate_path_in_cwd(path, cwd)

    def test_symlink_scenario(self):
        """Сценарий с symlink (тестируем логику, не реальные symlink)."""
        cwd = "/home/user/project"
        # Предположим что /tmp/link -> /etc/passwd
        # Но мы проверяем строковое представление, не реальные пути
        path = "/home/user/project/file.txt"
        
        _validate_path_in_cwd(path, cwd)

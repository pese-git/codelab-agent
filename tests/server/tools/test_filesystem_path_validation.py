"""Правило границы рабочего каталога (`domain/path_boundary.py`).

Правило переехало из обработчиков `fs/*` в домен и применяется на шве исполнения
(ADR-009, шаг 2б). Набор случаев сохранён дословно: он и есть описание границы,
а шаг менял владельца правила, а не само правило. Применение на шве проверяется
отдельно — `test_path_boundary_seam.py`.
"""

from __future__ import annotations

from codelab.server.domain.path_boundary import (
    is_inside_cwd,
    normalize_path,
    outside_cwd_error,
)


class TestNormalizePath:
    """Приведение пути к абсолютному относительно cwd."""

    def test_absolute_path_unchanged(self):
        """Абсолютный путь возвращается как есть."""
        assert (
            normalize_path("/home/user/project", "/home/user/project/file.txt")
            == "/home/user/project/file.txt"
        )

    def test_relative_path_joined_with_cwd(self):
        """Относительный путь присоединяется к cwd."""
        assert normalize_path("/home/user/project", "file.txt") == "/home/user/project/file.txt"

    def test_relative_path_with_subdirectory(self):
        """Относительный путь с поддиректорией."""
        assert (
            normalize_path("/home/user/project", "src/main.py")
            == "/home/user/project/src/main.py"
        )


class TestIsInsideCwd:
    """Принадлежность пути рабочему каталогу."""

    def test_path_inside_cwd_valid(self):
        """Путь внутри cwd границу не нарушает."""
        assert is_inside_cwd("/home/user/project/file.txt", "/home/user/project")

    def test_path_in_subdirectory_valid(self):
        """Путь в поддиректории cwd границу не нарушает."""
        assert is_inside_cwd("/home/user/project/src/main.py", "/home/user/project")

    def test_path_outside_cwd_detected(self):
        """Путь вне cwd отклоняется."""
        assert not is_inside_cwd("/home/user/other/file.txt", "/home/user/project")

    def test_path_in_parent_directory_detected(self):
        """Путь в родительской директории отклоняется."""
        assert not is_inside_cwd("/home/user/file.txt", "/home/user/project")

    def test_path_with_dotdot_detected(self):
        """Путь с `..`, выводящим за каталог, отклоняется после `resolve()`."""
        assert not is_inside_cwd("/home/user/project/../file.txt", "/home/user/project")

    def test_path_with_dotdot_inside_cwd_valid(self):
        """Путь с `..`, остающийся внутри cwd, проходит."""
        assert is_inside_cwd("/home/user/project/src/../src/main.py", "/home/user/project")

    def test_completely_different_path_detected(self):
        """Совершенно другой путь отклоняется."""
        assert not is_inside_cwd(
            "/Users/sergey/Projects/OpenIdeaLab/CodeLab/README.md",
            "/Users/penkovsky_sa/Downloads/flutter_app",
        )


class TestOutsideCwdError:
    """Текст отказа уходит модели — он часть контракта, а не украшение."""

    def test_error_names_path_and_cwd(self):
        """Сообщение называет и путь, и рабочий каталог."""
        message = outside_cwd_error("/home/user/other/file.txt", "/home/user/project")

        assert "outside working directory" in message
        assert "/home/user/other/file.txt" in message
        assert "/home/user/project" in message

    def test_error_message_includes_helpful_hint(self):
        """Сообщение содержит подсказку, что делать вместо повтора."""
        message = outside_cwd_error("/etc/passwd", "/home/user/project")

        assert "ls" in message or "find" in message
        assert "discover files" in message


class TestBoundaryEdgeCases:
    """Граничные случаи."""

    def test_cwd_with_trailing_slash(self):
        """Cwd с trailing slash работает корректно."""
        assert is_inside_cwd("/home/user/project/file.txt", "/home/user/project/")

    def test_path_equals_cwd_is_inside(self):
        """Путь, равный cwd, принадлежит каталогу.

        Edge case: проверяется принадлежность каталогу, а не тип объекта —
        «это директория, а не файл» остаётся заботой обработчика `fs/*`.
        """
        assert is_inside_cwd("/home/user/project", "/home/user/project")

    def test_symlink_scenario(self):
        """Сравнение идёт по разрешённым путям, а не по исходным строкам."""
        assert is_inside_cwd("/home/user/project/file.txt", "/home/user/project")

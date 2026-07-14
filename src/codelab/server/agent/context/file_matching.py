"""Чистые детерминированные хелперы разрешения и сопоставления путей.

Не выполняют I/O и не зависят от состояния сессии — вынесены из ACPContextGatherer
(Слой A) ради когезии. Детерминированный вывод критичен для стабильности
baseline_fingerprint и prompt cache.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import PurePosixPath

BINARY_EXTENSIONS = {
".pyc",
".pyo",
".so",
".dll",
".exe",
".bin",
".obj",
".o",
".png",
".jpg",
".jpeg",
".gif",
".bmp",
".ico",
".webp",
".mp3",
".mp4",
".wav",
".avi",
".mov",
".mkv",
".zip",
".tar",
".gz",
".bz2",
".rar",
".7z",
".pdf",
".doc",
".docx",
".xls",
".xlsx",
".ppt",
".pptx",
".woff",
".woff2",
".ttf",
".eot",
".db",
".sqlite",
".sqlite3",
".mdb",
}

IGNORE_DIRS = {
".git",
"__pycache__",
"venv",
".venv",
"node_modules",
".idea",
".vscode",
"build",
"dist",
".dart_tool",
".fvm",
"android",
"ios",
"macos",
"linux",
"windows",
"web",
".DS_Store",
".gradle",
".codelab",
".cocoindex_code",
}


def deduplicate(paths: list[str]) -> list[str]:
    """Удалить дубликаты путей."""
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def is_binary(path: str) -> bool:
    """Проверить, является ли файл бинарным."""
    return any(path.lower().endswith(ext) for ext in BINARY_EXTENSIONS)


def is_empty(content: str) -> bool:
    """Проверить, пуст ли файл."""
    return len(content.strip()) == 0


def parse_find_output(output: str) -> list[str]:
    """Парсить вывод find команды в список путей."""
    paths = []
    for line in output.split("\n"):
        line = line.strip()
        if not line or line.startswith("find:"):
            continue
        if line.startswith("./"):
            line = line[2:]
        if line:
            paths.append(line)
    return paths


def normalize_path(path: str, project_root: str | None = None) -> str:
    """Нормализовать путь к относительному формату.

    Удаляет абсолютные пути, приводя их к относительным от корня проекта.
    Убирает префиксы ./, заменяет \\ на /.

    Args:
        path: Путь для нормализации
        project_root: Корень проекта (опционально)

    Returns:
        Нормализованный относительный путь
    """
    if not path:
        return ""

    # Заменяем backslash на forward slash
    normalized = path.replace("\\", "/").strip()

    # Убираем префикс ./
    if normalized.startswith("./"):
        normalized = normalized[2:]

    # Если путь абсолютный, пытаемся сделать его относительным
    if normalized.startswith("/"):
        if project_root:
            # Убираем project_root из начала пути
            project_root_normalized = project_root.replace("\\", "/").rstrip("/")
            if normalized.startswith(project_root_normalized + "/"):
                normalized = normalized[len(project_root_normalized) + 1 :]
            elif normalized.startswith(project_root_normalized):
                normalized = normalized[len(project_root_normalized) :]
        # Если не удалось сделать относительным, берем только последнюю часть
        # Это fallback для случаев, когда project_root не совпадает
        if normalized.startswith("/"):
            # Берем только имя файла или последние компоненты пути
            parts = normalized.split("/")
            # Ищем первые осмысленные компоненты (не корень /)
            meaningful_parts = [p for p in parts if p]
            if len(meaningful_parts) >= 2:
                # Берем последние 2-3 компонента (например, lib/main.dart)
                normalized = "/".join(meaningful_parts[-2:])
            elif meaningful_parts:
                normalized = meaningful_parts[-1]

    return normalized


def filter_paths(paths: list[str]) -> list[str]:
    """Отфильтровать мусорные папки и файлы.

    Args:
        paths: Список путей

    Returns:
        Отфильтрованный список путей
    """
    filtered = []
    for path in paths:
        normalized = path.replace("\\", "/").strip()

        if not normalized or normalized in (".", "./"):
            continue

        if normalized.startswith("./"):
            normalized = normalized[2:]

        if not normalized:
            continue

        parts = normalized.split("/")

        if any(part in IGNORE_DIRS for part in parts):
            continue

        filtered.append(normalized)

    return filtered


def get_fallback_files(project_files: list[str], max_files: int) -> list[str]:
    """Собрать основные файлы проекта, когда нет кандидатов.

    Приоритет:
    1. Конфигурационные файлы проекта (pubspec.yaml, package.json, pyproject.toml)
    2. Главные файлы (main.dart, main.py, index.js, App.tsx)
    3. Остальные файлы исходного кода (lib/, src/, app/)

    Args:
        project_files: Список всех путей в проекте
        max_files: Максимальное количество файлов

    Returns:
        Список основных файлов проекта
    """
    config_files = {
        "pubspec.yaml",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "CMakeLists.txt",
        "Makefile",
        "README.md",
    }
    main_files_patterns = {
        "main.dart",
        "main.py",
        "index.js",
        "index.ts",
        "index.tsx",
        "App.tsx",
        "App.jsx",
        "app.py",
        "server.py",
    }
    source_dirs = {"lib", "src", "app", "pkg", "cmd"}

    priority_1: list[str] = []
    priority_2: list[str] = []
    priority_3: list[str] = []

    for path in project_files:
        filename = PurePosixPath(path).name
        parts = PurePosixPath(path).parts

        if any(part in IGNORE_DIRS for part in parts):
            continue

        if path in config_files or filename in config_files:
            priority_1.append(path)
        elif filename in main_files_patterns:
            priority_2.append(path)
        elif len(parts) > 1 and parts[0] in source_dirs:
            priority_3.append(path)

    result: list[str] = []
    for group in [priority_1, priority_2, priority_3]:
        for path in group:
            if len(result) >= max_files:
                return result
            if path not in result:
                result.append(path)

    return result


def detect_project_type(project_files: list[str]) -> str:
    """Определить тип проекта по файлам.

    Args:
        project_files: Список путей в проекте

    Returns:
        Тип проекта: "dart", "python", "javascript", "unknown"
    """
    file_set = set(project_files)

    if "pubspec.yaml" in file_set:
        return "dart"
    if any(f.endswith(".dart") for f in project_files[:50]):
        return "dart"

    if any(f in file_set for f in ("pyproject.toml", "setup.py", "setup.cfg")):
        return "python"
    if any(f.endswith(".py") for f in project_files[:50]):
        return "python"

    if "package.json" in file_set:
        return "javascript"
    if any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in project_files[:50]):
        return "javascript"

    return "unknown"


def map_path_to_project(target: str, project_type: str) -> list[str]:
    """Сгенерировать варианты путей для поиска в проекте.

    Args:
        target: Целевой путь от LLM (например, "src/auth.py")
        project_type: Тип проекта ("dart", "python", "javascript")

    Returns:
        Список вариантов путей для поиска
    """
    target_path = PurePosixPath(target)
    target_stem = target_path.stem
    target_suffix = target_path.suffix

    candidates: list[str] = []

    if project_type == "dart":
        if target_suffix in (".py", ".js", ".ts"):
            candidates.append(f"lib/{target_stem}.dart")
            candidates.append(f"lib/src/{target_stem}.dart")
            candidates.append(f"lib/screens/{target_stem}_screen.dart")
            candidates.append(f"lib/widgets/{target_stem}_widget.dart")
            candidates.append(f"lib/pages/{target_stem}_page.dart")
            candidates.append(f"lib/models/{target_stem}.dart")
            candidates.append(f"lib/services/{target_stem}_service.dart")
            candidates.append(f"lib/providers/{target_stem}_provider.dart")
        else:
            candidates.append(target)

    elif project_type == "python":
        if target_suffix == ".dart":
            candidates.append(f"src/{target_stem}.py")
            candidates.append(f"app/{target_stem}.py")
        else:
            candidates.append(target)

    elif project_type == "javascript":
        if target_suffix in (".py", ".dart"):
            candidates.append(f"src/{target_stem}.js")
            candidates.append(f"src/{target_stem}.ts")
            candidates.append(f"src/{target_stem}.jsx")
            candidates.append(f"src/{target_stem}.tsx")
            candidates.append(f"lib/{target_stem}.js")
            candidates.append(f"lib/{target_stem}.ts")
        else:
            candidates.append(target)

    else:
        candidates.append(target)

    return candidates


def stem_score(target_stem: str, target_words: set[str], file_stem: str) -> float | None:
    """Оценка похожести basename: подстрока (0.9) > общие слова > fuzzy ratio.

    Возвращает None, если файл не похож (не добавлять в кандидаты).
    """
    if target_stem in file_stem or file_stem in target_stem:
        return 0.9

    file_words = set(file_stem.replace("_", " ").replace("-", " ").split())
    file_words = {w for w in file_words if len(w) > 2}

    common_words = target_words & file_words
    if common_words:
        return min(0.7 + 0.1 * len(common_words), 0.89)

    ratio = SequenceMatcher(None, target_stem, file_stem).ratio()
    if ratio >= 0.6:
        return ratio * 0.7
    return None


def match_mapped_paths(
    mapped_paths: list[str], project_files: list[str], seen_paths: set[str]
) -> list[tuple[float, str]]:
    """Стратегия 1: точное совпадение с путями из path-mapping (score 1.0)."""
    matches: list[tuple[float, str]] = []
    for mapped_path in mapped_paths:
        if mapped_path in project_files and mapped_path not in seen_paths:
            matches.append((1.0, mapped_path))
            seen_paths.add(mapped_path)
    return matches


def match_by_stem(
    target: str, project_files: list[str], seen_paths: set[str]
) -> list[tuple[float, str]]:
    """Стратегия 2: совпадение по basename (подстрока / общие слова / fuzzy)."""
    matches: list[tuple[float, str]] = []
    target_stem = PurePosixPath(target).stem.lower()
    target_words = set(target_stem.replace("_", " ").replace("-", " ").split())
    target_words = {w for w in target_words if len(w) > 2}

    for file_path in project_files:
        if file_path in seen_paths:
            continue

        file_stem = PurePosixPath(file_path).stem.lower()
        score = stem_score(target_stem, target_words, file_stem)
        if score is not None:
            matches.append((score, file_path))
            seen_paths.add(file_path)
    return matches


def match_by_path_segments(
    target: str, project_files: list[str], seen_paths: set[str]
) -> list[tuple[float, str]]:
    """Стратегия 3: совпадение по словам из сегментов пути (>= 2 совпадений)."""
    target_segment_words: set[str] = set()
    for segment in PurePosixPath(target).parts:
        segment_stem = PurePosixPath(segment).stem.lower()
        target_segment_words.update(
            w for w in segment_stem.replace("_", " ").replace("-", " ").split() if len(w) > 2
        )

    matches: list[tuple[float, str]] = []
    for file_path in project_files:
        if file_path in seen_paths:
            continue

        file_lower = file_path.lower()
        segment_match_score = sum(1 for word in target_segment_words if word in file_lower)

        if segment_match_score >= 2:
            matches.append((0.5 + segment_match_score * 0.05, file_path))
            seen_paths.add(file_path)
    return matches


def find_similar_files(target: str, project_files: list[str]) -> list[str]:
    """Найти похожие файлы по имени с fuzzy matching и маппингом путей.

    Args:
        target: Целевой путь от LLM (например, "src/auth.py")
        project_files: Список реальных путей в проекте

    Returns:
        Список похожих путей (максимум 5)
    """
    project_type = detect_project_type(project_files)
    mapped_paths = map_path_to_project(target, project_type)

    seen_paths: set[str] = set()
    matches: list[tuple[float, str]] = []
    matches += match_mapped_paths(mapped_paths, project_files, seen_paths)
    matches += match_by_stem(target, project_files, seen_paths)
    matches += match_by_path_segments(target, project_files, seen_paths)

    matches.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in matches[:5]]

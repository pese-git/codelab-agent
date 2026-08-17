"""Golden-payload сборки контекста — предусловие шага 2 ADR-009 и шага 4 ADR-008.

Гейт снимается **до** правки намеренно: golden, написанный после, закрепляет новое
поведение вместо проверки совместимости. Этот урок в проекте уже оплачен дважды —
гейт D0.1 снимался до write-фазы (ADR-006), поток `session/load` — до шага 3
(ADR-008).

Что защищается и почему именно это:

* **Перечисление файлов.** Шаг 2 ADR-009 сужает полномочие Context Manager: команда
  `find . -type f` уезжает за узкую возможность. Носитель меняется, а **набор путей
  обязан остаться прежним** — иначе изменится контекст, а вместе с ним и payload.
* **Сборка baseline.** Порядок источников, склейка и роли определяют байты, которые
  уходят модели. Их изменение рушит prompt cache, и это должно быть осознанным
  решением, а не побочным эффектом переноса.

Ломается этот тест → цена правки вышла за заявленную область.
"""

from __future__ import annotations

import pytest

from codelab.server.agent.context.file_matching import (
    filter_paths,
    normalize_path,
    parse_path_listing,
)
from codelab.server.agent.context.manager_helpers import split_baseline_tail
from codelab.server.agent.context.models import PayloadEnvelope
from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
    SkillCatalogSource,
)
from codelab.server.llm.models import LLMMessage

# Вывод `find . -type f` в форме, которую отдаёт терминал: с ./-префиксами,
# мусорными каталогами и строкой ошибки, которую find печатает в stdout.
FIND_OUTPUT = """./lib/main.dart
./lib/app.dart
./.git/config
./build/app.o
./test/widget_test.dart
find: './private': Permission denied
./pubspec.yaml
"""

# Golden: что из этого вывода доходит до сборки контекста.
EXPECTED_FILES = [
    "lib/main.dart",
    "lib/app.dart",
    "test/widget_test.dart",
    "pubspec.yaml",
]

SYSTEM_PROMPT = "Ты ассистент."
FILE_A = "<file path=\"lib/main.dart\">void main() {}</file>"
FILE_B = "<file path=\"lib/app.dart\">class App {}</file>"


class TestEnumerationGolden:
    """Набор путей — чистая функция вывода команды (ADR-009, шаг 2).

    Цепочка `parse_path_listing → normalize_path → filter_paths` целиком
    детерминирована, поэтому фиксируется значением, а не свойством: при переносе
    команды за узкую возможность подменяется **носитель**, и именно равенство
    результата доказывает, что перенос ничего не сдвинул.
    """

    def test_find_output_yields_exact_file_list(self) -> None:
        raw = parse_path_listing(FIND_OUTPUT)
        normalized = [normalize_path(path, "/work") for path in raw]

        assert filter_paths(normalized) == EXPECTED_FILES

    def test_absolute_paths_collapse_to_project_relative(self) -> None:
        """Клиент может отдать абсолютные пути — набор обязан совпасть с относительным."""
        absolute = FIND_OUTPUT.replace("./", "/work/")

        raw = parse_path_listing(absolute)
        normalized = [normalize_path(path, "/work") for path in raw]

        assert filter_paths(normalized) == EXPECTED_FILES

    def test_search_output_shares_the_chain(self) -> None:
        """Поиск возвращает пути тем же форматом — цепочка разбора у них одна.

        Диагностика утилиты приходит тем же потоком, что и пути, и путём быть не
        должна: `grep: lib/gen: Is a directory` — не файл проекта.
        """
        search_output = "./lib/main.dart\ngrep: lib/gen: Is a directory\n./lib/app.dart\n"

        raw = parse_path_listing(search_output)
        normalized = [normalize_path(path, "/work") for path in raw]

        assert filter_paths(normalized) == ["lib/main.dart", "lib/app.dart"]

    def test_order_is_preserved(self) -> None:
        """Порядок — часть payload: он определяет порядок файлов в baseline."""
        raw = parse_path_listing(FIND_OUTPUT)
        normalized = [normalize_path(path, "/work") for path in raw]

        assert filter_paths(normalized)[0] == "lib/main.dart"


class TestBaselineRenderGolden:
    """Байты baseline: порядок источников и склейка (ADR-008, шаг 4)."""

    @pytest.mark.asyncio
    async def test_baseline_text_is_byte_identical(self) -> None:
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("system_prompt", SYSTEM_PROMPT))
        registry.register(FileContextSource("lib/main.dart", FILE_A))
        registry.register(FileContextSource("lib/app.dart", FILE_B))

        rendered = await registry.render_baseline()

        # Склейка ровно двумя переводами строки и порядок регистрации — это и есть
        # то, что уходит модели. Константа, а не вычисление: вычисление подогнать
        # под новую реализацию можно, константу — нет.
        assert rendered == (
            "Ты ассистент.\n"
            "\n"
            '<file path="lib/main.dart">void main() {}</file>\n'
            "\n"
            '<file path="lib/app.dart">class App {}</file>'
        )

    @pytest.mark.asyncio
    async def test_empty_sources_do_not_leave_separators(self) -> None:
        """Пустой источник не должен оставлять пустой абзац: это лишние байты."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("system_prompt", SYSTEM_PROMPT))
        registry.register(FileContextSource("empty", ""))
        registry.register(FileContextSource("lib/app.dart", FILE_B))

        rendered = await registry.render_baseline()

        assert rendered == f"{SYSTEM_PROMPT}\n\n{FILE_B}"

    @pytest.mark.asyncio
    async def test_empty_skill_catalog_adds_nothing(self) -> None:
        """Пустой каталог скиллов в payload не попадает."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("system_prompt", SYSTEM_PROMPT))
        registry.register(SkillCatalogSource([]))

        assert await registry.render_baseline() == SYSTEM_PROMPT


class TestPayloadGolden:
    """Плоский список для провайдера — единственная точка конвертации."""

    def test_to_messages_is_baseline_then_tail(self) -> None:
        baseline = [LLMMessage(role="system", content="S")]
        tail = [
            LLMMessage(role="user", content="U"),
            LLMMessage(role="assistant", content="A"),
        ]

        envelope = PayloadEnvelope(baseline=baseline, tail=tail)

        assert [(m.role, m.content) for m in envelope.to_messages()] == [
            ("system", "S"),
            ("user", "U"),
            ("assistant", "A"),
        ]

    def test_split_keeps_leading_system_in_baseline(self) -> None:
        """Разделение baseline/tail — часть детерминизма префикса prompt cache.

        Стабилен именно **ведущий** блок system-сообщений: system, встреченный
        после первого не-system, в baseline не уходит, иначе префикс перестал бы
        быть неизменным между ходами.
        """
        messages = [
            LLMMessage(role="system", content="S1"),
            LLMMessage(role="system", content="S2"),
            LLMMessage(role="user", content="U"),
            LLMMessage(role="system", content="S3"),
        ]

        baseline, tail = split_baseline_tail(messages)

        assert [m.content for m in baseline] == ["S1", "S2"]
        assert [m.content for m in tail] == ["U", "S3"]

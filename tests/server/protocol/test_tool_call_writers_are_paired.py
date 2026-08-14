"""Гейт парности: мутация реестра вызовов без события журнала теряется (шаг 4g ADR-008).

Парный гейт к `test_history_writers_are_paired`. С шага 4g реестр вызовов —
проекция журнала: документ коллекцию `tool_calls` не несёт, поэтому вызов и его
статус переживают транзакцию **только** через событие.

Дефект не гипотетический — он воспроизвёлся тридцатью тремя падениями сразу же,
как коллекция перестала писаться:

* создание без события — вызов исчезал на следующей команде, и запрос
  разрешения не уходил вовсе (`_request_permission` не находил вызов);
* смена статуса без события — вызов оставался `pending`, и завершение упиралось
  в запрет `pending → completed`, о чём говорил только warning в логе;
* хуже всего было то, что дыру нельзя было увидеть: тест, подменивший писателя
  журнала моком, продолжал проходить, пока коллекция уезжала на диск.

Отсюда правило: мутирует реестр только дверь, которая тут же пишет событие.
Мутации в самом домене (`ToolCallRegistry`) гейт не считает — там живёт сама
операция; wire-формы домен не знает, и событие пишет слой протокола.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[3] / "src" / "codelab" / "server"

# Доменные сеймы, меняющие реестр вызовов. Каждый вызов обязан быть парным
# записи события в той же команде.
_REGISTRY_SEAMS = frozenset({"create", "update_status", "restore"})

# Разрешённые двери и то, чем они парны. Пара проверена по коду.
_PAIRED_CALL_SITES: dict[str, str] = {
    # Создание вызова и `ToolCallStarted` — одна команда
    "protocol/handlers/tool_call_handler.py": "save_tool_call",
    # Общий вход turn-пути и client-RPC: создание и смена статуса пишут событие
    "protocol/handlers/prompt/tool_call_state.py": "save_tool_call",
    # Метёлка незавершённых вызовов при switch сессии: пара стоит тут же, явной
    # записью, а не дверью — путь ещё не переведён на доменный шов
    "protocol/handlers/session.py": "save_tool_call_update",
}


def _call_sites() -> dict[str, list[int]]:
    """Файлы сервера, мутирующие `session.tool_calls`, и строки этих вызовов.

    Разбор через `ast`: пример вызова в докстринге кодом не является. Отбор идёт
    по получателю `tool_calls`, иначе гейт ловил бы любой `create` в проекте.
    """
    found: dict[str, list[int]] = {}
    for path in _SERVER.rglob("*.py"):
        relative = path.relative_to(_SERVER).as_posix()
        if relative.startswith(("domain/", "storage/", "mapping/")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _REGISTRY_SEAMS
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "tool_calls"
        ]
        if lines:
            found[relative] = lines
    return found


def test_every_tool_call_writer_is_a_known_paired_site() -> None:
    """Новый писатель реестра обязан быть парным событию журнала.

    Если тест упал на вашем файле — не добавляйте его в список молча: убедитесь,
    что событие пишется в **той же** команде. Иначе вызов доживёт до конца
    команды и исчезнет, а в памяти всё это время будет выглядеть целым.
    """
    unexpected = sorted(set(_call_sites()) - set(_PAIRED_CALL_SITES))

    assert unexpected == [], (
        "писатель реестра вызовов вне списка парных мест: "
        f"{unexpected}. Реестр — проекция журнала (шаг 4g ADR-008): "
        "без парного события вызов теряется на следующей команде."
    )


def test_paired_sites_still_write_their_journal_event() -> None:
    """У каждой разрешённой двери пара на месте — список не устарел."""
    missing: list[str] = []
    for relative, expected in _PAIRED_CALL_SITES.items():
        source = (_SERVER / relative).read_text(encoding="utf-8")
        if expected not in source:
            missing.append(f"{relative}: нет {expected}")

    assert missing == [], f"пара писателя реестра пропала: {missing}"

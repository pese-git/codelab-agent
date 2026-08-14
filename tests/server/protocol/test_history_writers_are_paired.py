"""Гейт парности: запись истории без события журнала теряется (шаг 4f ADR-008).

С шага 4f история — проекция: документ её не несёт, поэтому она переживает
транзакцию **только** через журнал. Отсюда новый класс дефекта: писатель,
добавивший сообщение в `Session.history` и не записавший событие, теряет его на
следующей же команде — молча, потому что в памяти сообщение видно, а команда
загружает свежий агрегат с диска.

Дефект не гипотетический: он воспроизвёлся сразу, на интеграционном тесте с
заглушкой вместо писателя журнала — первое сообщение ассистента исчезало, а
второе оставалось.

Структурный гейт — того же рода, что `test_seam_cannot_be_bypassed` у снятия
turn'а и `test_drain_is_called_only_from_background_task_seams` у дренажа
терминалов: он перечисляет разрешённые места и падает на новом, не парном.
Структурно невозможным этот дефект станет тогда, когда журнал переедет в агрегат
доменной коллекцией и сеймы истории начнут писать событие сами; сегодня
`events_history` хранит wire-записи, а домен формы wire не знает.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[3] / "src" / "codelab" / "server"

# Сеймы, добавляющие сообщение в историю. Каждый вызов обязан быть парным
# записи журнала в той же команде.
_HISTORY_SEAMS = frozenset(
    {
        "add_user_message",
        "add_assistant_message",
        "add_assistant_tool_call_message",
        "add_tool_result",
    }
)

# Разрешённые места и то, чем они парны. Пара проверена по коду: в каждом из них
# событие журнала пишется в той же команде, что и запись истории.
_PAIRED_CALL_SITES: dict[str, str] = {
    # `save_user_message` в той же команде `prompt_received`
    "protocol/handlers/prompt_orchestrator.py": "save_user_message",
    # `save_agent_message` в той же команде `demo_ack`
    "protocol/handlers/pipeline/stages/llm_loop.py": "save_agent_message",
    # `save_agent_message` в той же команде `assistant_message`
    "protocol/handlers/pipeline/stages/agent_loop/loop.py": "save_agent_message",
    # `ToolCallHandler.answer_tool_call` — дверь, где ответ и событие неразделимы
    "protocol/handlers/tool_call_handler.py": "save_tool_call_answer",
    # Делегирование в доменный сейм: сам по себе истории не пишет
    "protocol/handlers/state_manager.py": "",
    # Воронка ответов идёт через дверь `answer_tool_call`
    "protocol/handlers/pipeline/stages/agent_loop/tool_processor.py": "answer_tool_call",
}


def _call_sites() -> dict[str, list[int]]:
    """Файлы сервера, зовущие сеймы истории, и строки этих вызовов.

    Разбор через `ast`, а не по строкам: пример вызова в докстринге кодом не
    является, и гейт, спутавший его с писателем, требовал бы вносить в список
    документацию (первый прогон гейта именно это и показал).
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
            and node.func.attr in _HISTORY_SEAMS
        ]
        if lines:
            found[relative] = lines
    return found


def test_every_history_writer_is_a_known_paired_site() -> None:
    """Новый писатель истории обязан быть парным событию журнала.

    Если этот тест упал на вашем файле — не добавляйте его в список молча:
    убедитесь, что событие журнала пишется в **той же** команде. Иначе сообщение
    доживёт до конца команды и исчезнет.
    """
    unexpected = sorted(set(_call_sites()) - set(_PAIRED_CALL_SITES))

    assert unexpected == [], (
        "писатель истории вне списка парных мест: "
        f"{unexpected}. История — проекция журнала (шаг 4f ADR-008): "
        "без парного события сообщение теряется на следующей команде."
    )


def test_paired_sites_still_write_their_journal_event() -> None:
    """У каждого разрешённого места пара на месте — список не устарел."""
    missing: list[str] = []
    for relative, expected in _PAIRED_CALL_SITES.items():
        if not expected:
            continue
        source = (_SERVER / relative).read_text(encoding="utf-8")
        if expected not in source:
            missing.append(f"{relative}: нет {expected}")

    assert missing == [], f"пара писателя истории пропала: {missing}"

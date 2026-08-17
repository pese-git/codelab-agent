#!/usr/bin/env python3
"""Показать сессию одним видом: снимок плюс журнал (ADR-008, шаг 6b).

С шага 6b сессия лежит в двух файлах — снимок в `{id}.json`, журнал в
`{id}.jsonl`. Разбор документа глазами остаётся частью приёмки в этом ADR (все
его находки получены так), поэтому нужен склеенный вид.

Скрипт, а не команда CLI: у CLI это стало бы публичным интерфейсом, который
придётся поддерживать, а нужен он для разбора, а не пользователю.

Проверки внизу (`--check`) — не украшение. Это ровно те сверки, которыми
снималась приёмка каждого шага начиная с 3a: расхождение «статус вызова ↔
последнее событие журнала», события-сироты и вызовы без ответа `role: tool`.
Каждая из них когда-то находила дефект, поэтому они здесь, а не в голове.

Примеры:
    scripts/session_show.py                      # последняя сессия, сводка
    scripts/session_show.py sess_d89850dfbde1
    scripts/session_show.py --json | jq .        # склеенный документ
    scripts/session_show.py --events             # только журнал, по строке
    scripts/session_show.py --check              # только сверки, код возврата
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path.home() / ".codelab" / "data" / "sessions"

# Статусы, после которых вызов не меняется. Держим строками: скрипт читает файлы
# и не должен зависеть от импорта пакета — им пользуются и на машине без окружения.
_FINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _resolve(target: str | None, sessions_dir: Path) -> Path:
    """Путь к снимку сессии: по идентификатору, по пути или последняя изменённая."""
    if target:
        candidate = Path(target)
        if candidate.exists():
            return candidate if candidate.suffix == ".json" else candidate.with_suffix(".json")
        candidate = sessions_dir / f"{target}.json"
        if candidate.exists():
            return candidate
        sys.exit(f"сессия не найдена: {target}")

    snapshots = sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not snapshots:
        sys.exit(f"в {sessions_dir} нет сессий")
    return snapshots[0]


def load(snapshot_path: Path) -> dict[str, Any]:
    """Склеенный документ: снимок с журналом из соседнего файла.

    Документ до 6b несёт журнал внутри снимка, и тогда соседнего файла нет —
    такой читается как есть. Различать по наличию файла, а не по версии схемы:
    тот же признак, что в 4f, 4g и в самом хранилище.
    """
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))

    journal_path = snapshot_path.with_suffix(".jsonl")
    if journal_path.exists():
        document["events_history"] = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return document


def _calls_from_journal(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Вызовы и их последний статус — так же, как их выводит проекция."""
    calls: dict[str, dict[str, Any]] = {}
    for event in events:
        data = event.get("data", {})
        call_id = data.get("tool_call_id")
        if event.get("event") == "tool_call_started" and isinstance(call_id, str):
            calls[call_id] = {
                "name": data.get("tool_name") or data.get("title"),
                "status": data.get("status", "pending"),
                "llm_id": data.get("tool_call_id_from_llm"),
            }
        elif event.get("event") == "tool_call_status_changed" and isinstance(call_id, str):
            calls.setdefault(call_id, {"name": None, "status": None, "llm_id": None})
            calls[call_id]["status"] = data.get("status")
    return calls


def check(document: dict[str, Any]) -> list[str]:
    """Сверки приёмки. Пустой список — расхождений нет."""
    events = document.get("events_history") or []
    calls = _calls_from_journal(events)
    problems: list[str] = []

    started = {
        e["data"]["tool_call_id"]
        for e in events
        if e.get("event") == "tool_call_started" and "tool_call_id" in e.get("data", {})
    }
    orphans = set(calls) - started
    if orphans:
        problems.append(f"события-сироты (статус без tool_call_started): {sorted(orphans)}")

    # Ответы адресуются идентификатором модели, а не `call_NNN`, поэтому связка
    # берётся из `tool_call_started`. Ответ без вызова — не дефект: метёлка
    # отвечает и на вызов, который не успел им стать (решение шага 4g).
    llm_to_call = {c["llm_id"]: call_id for call_id, c in calls.items() if c["llm_id"]}
    answered = {
        llm_to_call.get(e["data"].get("tool_call_id"))
        for e in events
        if e.get("event") == "tool_call_answered"
    }
    unanswered = sorted(started - answered - {None})
    if unanswered:
        problems.append(f"вызовы без ответа role: tool: {unanswered}")

    non_final = sorted(cid for cid, c in calls.items() if c["status"] not in _FINAL_STATUSES)
    if non_final and document.get("active_turn") is None:
        problems.append(f"нефинальные вызовы у сессии без активного turn'а: {non_final}")

    return problems


def summary(document: dict[str, Any], snapshot_path: Path) -> None:
    events = document.get("events_history") or []
    calls = _calls_from_journal(events)
    journal_path = snapshot_path.with_suffix(".jsonl")

    kinds: dict[str, int] = {}
    for event in events:
        kinds[event.get("event", "?")] = kinds.get(event.get("event", "?"), 0) + 1

    print(f"сессия     {document.get('session_id')}  «{document.get('title') or '—'}»")
    print(f"cwd        {document.get('cwd')}")
    print(f"обновлена  {document.get('updated_at')}   ревизия {document.get('revision')}")
    layout = "снимок + журнал" if journal_path.exists() else "один файл (до 6b)"
    sizes = f"{snapshot_path.stat().st_size} Б"
    if journal_path.exists():
        sizes += f" + {journal_path.stat().st_size} Б"
    print(f"раскладка  {layout}, {sizes}")
    print(f"схема      v{document.get('schema_version')}   turn: {document.get('active_turn')}")
    print()

    print(f"журнал: {len(events)} записей")
    for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:28} {count:>4}")
    print()

    print(f"вызовы: {len(calls)} (счётчик {document.get('tool_call_counter')})")
    for call_id, call in calls.items():
        print(f"  {call_id:10} {str(call['status']):11} {call['name']}")
    print()

    # Коллекции на диске больше нет — это и есть результат 4f/4g, и вид обязан
    # его показывать, иначе пустое поле читается как «данные потерялись».
    for field, step in (("history", "4f"), ("tool_calls", "4g")):
        value = document.get(field)
        note = "проекция журнала" if not value else f"ЛЕГАСИ: коллекция на диске ({len(value)})"
        print(f"{field:11} {note}   [{step}]")
    print()

    problems = check(document)
    if problems:
        print("РАСХОЖДЕНИЯ:")
        for problem in problems:
            print(f"  ! {problem}")
    else:
        print("сверки пройдены: сирот нет, вызовы отвечены, статусы согласованы")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("session", nargs="?", help="идентификатор сессии или путь к снимку")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="каталог сессий")
    parser.add_argument("--json", action="store_true", help="склеенный документ в stdout")
    parser.add_argument("--events", action="store_true", help="только журнал, по записи на строку")
    parser.add_argument("--check", action="store_true", help="только сверки; 1 при расхождениях")
    args = parser.parse_args()

    snapshot_path = _resolve(args.session, args.dir)
    document = load(snapshot_path)

    if args.json:
        json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    if args.events:
        for event in document.get("events_history") or []:
            print(json.dumps(event, ensure_ascii=False))
        return 0

    if args.check:
        problems = check(document)
        for problem in problems:
            print(f"! {problem}")
        return 1 if problems else 0

    summary(document, snapshot_path)
    return 1 if check(document) else 0


if __name__ == "__main__":
    # `session_show.py --events | head` — обычный способ им пользоваться, а он
    # закрывает трубу. Ловить только вокруг `main()` мало: вывод буферизован, и
    # ошибка всплывает на финальном flush интерпретатора, который печатает
    # «Exception ignored» уже после полезного вывода. Поэтому flush делается явно
    # внутри try, а дескриптор подменяется на /dev/null — чтобы flush на выходе
    # не наткнулся на ту же закрытую трубу.
    import os

    try:
        exit_code = main()
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        exit_code = 0
    raise SystemExit(exit_code)

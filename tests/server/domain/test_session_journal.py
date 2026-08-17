"""Журнал как доменная коллекция: единственный владелец дописывания и `seq` (шаг 6a ADR-008).

До 6a журнал был `list[dict]` в `SessionRuntime`: дописать в него мог кто угодно,
а форму записи знали трое — писатель, реплей и обе проекции. Эти тесты держат
оба свойства, ради которых он стал коллекцией: дописывание идёт одной дверью, и
у записи есть позиция, по которой 6b поймёт, что ещё не сохранено.
"""

from __future__ import annotations

from datetime import UTC, datetime

from codelab.server.domain.journal import (
    AgentMessageRecorded,
    JournalEntry,
    SessionJournal,
    UserMessageRecorded,
)


def _user(text: str) -> UserMessageRecorded:
    return UserMessageRecorded(blocks=[{"type": "text", "text": text}])


class TestAppendIsTheOnlyDoor:
    def test_append_returns_monotonic_seq(self) -> None:
        journal = SessionJournal()

        assert journal.append(_user("раз")) == 1
        assert journal.append(_user("два")) == 2
        assert journal.last_seq == 2

    def test_entries_are_immutable_from_outside(self) -> None:
        """`entries()` отдаёт кортеж — дописать мимо `append` нельзя.

        Это и есть разница с прежним носителем: `runtime.events_history` был
        списком, и любой читатель мог в него дописать, не тронув ни `seq`, ни
        писателя.
        """
        journal = SessionJournal()
        journal.append(_user("раз"))

        entries = journal.entries()

        assert isinstance(entries, tuple)
        assert not hasattr(entries, "append")
        assert len(journal) == 1

    def test_empty_journal_has_zero_seq(self) -> None:
        assert SessionJournal().last_seq == 0
        assert len(SessionJournal()) == 0


class TestCursor:
    """`after(seq)` — то, что 6b будет дописывать на носитель."""

    def test_after_returns_the_tail(self) -> None:
        journal = SessionJournal()
        journal.append(_user("раз"))
        seq = journal.append(_user("два"))
        journal.append(AgentMessageRecorded(content={"type": "text", "text": "ответ"}))

        tail = journal.after(seq)

        assert len(tail) == 1
        assert isinstance(tail[0].event, AgentMessageRecorded)

    def test_after_last_seq_is_empty(self) -> None:
        journal = SessionJournal()
        journal.append(_user("раз"))

        assert journal.after(journal.last_seq) == ()

    def test_after_zero_is_everything(self) -> None:
        journal = SessionJournal()
        journal.append(_user("раз"))
        journal.append(_user("два"))

        assert len(journal.after(0)) == 2


class TestRestore:
    def test_restore_keeps_timestamps_from_disk(self) -> None:
        """Восстановление несёт метки с диска, а `append` ставит свои.

        Разные операции: сборка агрегата не должна выдавать историческую запись
        за только что случившееся событие.
        """
        stamp = datetime(2026, 8, 17, 5, 45, tzinfo=UTC)
        journal = SessionJournal()

        journal.restore([JournalEntry(_user("раз"), stamp)])

        assert journal.entries()[0].timestamp == stamp
        assert journal.last_seq == 1

    def test_restore_replaces_rather_than_appends(self) -> None:
        journal = SessionJournal()
        journal.append(_user("мусор"))

        journal.restore([JournalEntry(_user("раз"))])

        assert len(journal) == 1
        assert journal.entries()[0].event == _user("раз")

"""Unit тесты для EpochManager.

Тестирует:
- Создание эпохи с фиксированным baseline
- Разрыв эпохи (break_epoch) с ограничением 1 за ход
- Добавление mid_conversation_messages
- compute_baseline_fingerprint — детерминизм
- reset_turn_counter
"""


from codelab.server.agent.context.epoch import EpochManager
from codelab.server.llm.models import LLMMessage


class TestEpochManagerStartEpoch:
    """Тесты создания эпохи."""

    def test_start_epoch_creates_epoch_with_baseline(self):
        """start_epoch создаёт эпоху с фиксированным baseline."""
        manager = EpochManager()
        baseline = [LLMMessage(role="system", content="System prompt")]
        fingerprint = "abc123"

        epoch = manager.start_epoch(baseline, fingerprint)

        assert manager.is_active
        assert manager.current_epoch is epoch
        assert epoch.baseline == baseline
        assert epoch.baseline_fingerprint == fingerprint
        assert epoch.mid_conversation_messages == []
        assert epoch.epoch_id != ""

    def test_start_epoch_copies_baseline(self):
        """start_epoch копирует baseline, не хранит ссылку."""
        manager = EpochManager()
        baseline = [LLMMessage(role="system", content="test")]
        epoch = manager.start_epoch(baseline, "fp")

        baseline.append(LLMMessage(role="user", content="mutated"))

        assert len(epoch.baseline) == 1

    def test_start_epoch_replaces_previous(self):
        """start_epoch заменяет предыдущую эпоху."""
        manager = EpochManager()
        epoch1 = manager.start_epoch([], "fp1")
        epoch2 = manager.start_epoch([], "fp2")

        assert manager.current_epoch is epoch2
        assert manager.current_epoch is not epoch1


class TestEpochManagerBreakEpoch:
    """Тесты разрыва эпохи."""

    def test_break_epoch_creates_new_epoch(self):
        """break_epoch создаёт новую эпоху."""
        manager = EpochManager()
        manager.start_epoch([], "fp1")

        new_baseline = [LLMMessage(role="system", content="new")]
        new_epoch = manager.break_epoch(new_baseline, "fp2")

        assert new_epoch is not None
        assert new_epoch.baseline_fingerprint == "fp2"
        assert manager.current_epoch is new_epoch

    def test_break_epoch_returns_none_when_no_active_epoch(self):
        """break_epoch возвращает None если нет активной эпохи."""
        manager = EpochManager()

        result = manager.break_epoch([], "fp")

        assert result is None

    def test_break_epoch_limited_to_one_per_turn(self):
        """Не более одного разрыва за ход."""
        manager = EpochManager()
        manager.start_epoch([], "fp1")

        first = manager.break_epoch([], "fp2")
        second = manager.break_epoch([], "fp3")

        assert first is not None
        assert second is None

    def test_reset_turn_counter_allows_new_break(self):
        """reset_turn_counter позволяет новый разрыв."""
        manager = EpochManager()
        manager.start_epoch([], "fp1")
        manager.break_epoch([], "fp2")
        assert manager.break_epoch([], "fp3") is None

        manager.reset_turn_counter()

        result = manager.break_epoch([], "fp4")
        assert result is not None


class TestEpochManagerMidConversation:
    """Тесты mid_conversation_messages."""

    def test_add_mid_conversation_message(self):
        """add_mid_conversation_message добавляет в текущую эпоху."""
        manager = EpochManager()
        manager.start_epoch([], "fp")
        msg = LLMMessage(role="user", content="hello")

        manager.add_mid_conversation_message(msg)

        assert manager.current_epoch.mid_conversation_messages == [msg]

    def test_add_mid_conversation_message_no_epoch(self):
        """add_mid_conversation_message без эпохи — warning, не падает."""
        manager = EpochManager()
        msg = LLMMessage(role="user", content="hello")

        manager.add_mid_conversation_message(msg)

        assert manager.current_epoch is None

    def test_multiple_mid_conversation_messages(self):
        """Несколько сообщений накапливаются."""
        manager = EpochManager()
        manager.start_epoch([], "fp")
        msgs = [
            LLMMessage(role="user", content="1"),
            LLMMessage(role="assistant", content="2"),
            LLMMessage(role="user", content="3"),
        ]

        for msg in msgs:
            manager.add_mid_conversation_message(msg)

        assert len(manager.current_epoch.mid_conversation_messages) == 3


class TestEpochManagerClear:
    """Тесты очистки."""

    def test_clear_removes_epoch(self):
        """clear удаляет текущую эпоху."""
        manager = EpochManager()
        manager.start_epoch([], "fp")

        manager.clear()

        assert not manager.is_active
        assert manager.current_epoch is None


class TestComputeBaselineFingerprint:
    """Тесты детерминированного fingerprint."""

    def test_same_input_same_fingerprint(self):
        """Одинаковый вход → одинаковый fingerprint."""
        baseline = [LLMMessage(role="system", content="test content")]

        fp1 = EpochManager.compute_baseline_fingerprint(baseline)
        fp2 = EpochManager.compute_baseline_fingerprint(baseline)

        assert fp1 == fp2

    def test_different_input_different_fingerprint(self):
        """Разный вход → разный fingerprint."""
        baseline1 = [LLMMessage(role="system", content="content A")]
        baseline2 = [LLMMessage(role="system", content="content B")]

        fp1 = EpochManager.compute_baseline_fingerprint(baseline1)
        fp2 = EpochManager.compute_baseline_fingerprint(baseline2)

        assert fp1 != fp2

    def test_whitespace_normalization(self):
        """Нормализация пробелов: одинаковый контент с разными пробелами → одинаковый fp."""
        baseline1 = [LLMMessage(role="system", content="hello   world")]
        baseline2 = [LLMMessage(role="system", content="hello world")]

        fp1 = EpochManager.compute_baseline_fingerprint(baseline1)
        fp2 = EpochManager.compute_baseline_fingerprint(baseline2)

        assert fp1 == fp2

    def test_empty_baseline(self):
        """Пустой baseline → валидный fingerprint."""
        fp = EpochManager.compute_baseline_fingerprint([])
        assert fp != ""
        assert len(fp) == 16

    def test_fingerprint_is_hex(self):
        """Fingerprint — hex строка."""
        baseline = [LLMMessage(role="system", content="test")]
        fp = EpochManager.compute_baseline_fingerprint(baseline)

        assert all(c in "0123456789abcdef" for c in fp)

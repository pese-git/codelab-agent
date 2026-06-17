"""Тесты покрытия для MessageList компонента.

Проверяют непокрытые строки в:
- DateSeparator
- MessageList
"""

from __future__ import annotations

from datetime import datetime, timedelta

from textual.app import App

from codelab.client.tui.components.message_bubble import MessageRole
from codelab.client.tui.components.message_list import DateSeparator, MessageList


class TestDateSeparator:
    """Тесты для DateSeparator."""

    def test_today_label(self) -> None:
        """Сегодняшняя дата отображается как 'Сегодня'."""
        separator = DateSeparator(datetime.now())
        assert "Сегодня" in separator._Static__content

    def test_yesterday_label(self) -> None:
        """Вчерашняя дата отображается как 'Вчера'."""
        yesterday = datetime.now() - timedelta(days=1)
        separator = DateSeparator(yesterday)
        assert "Вчера" in separator._Static__content

    def test_older_date_label(self) -> None:
        """Более старая дата отображается в формате день месяц год."""
        date = datetime(2023, 5, 15, 10, 30)
        separator = DateSeparator(date)
        assert "15" in separator._Static__content
        assert "2023" in separator._Static__content


class TestMessageList:
    """Тесты для MessageList."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        msg_list = MessageList()
        assert msg_list.messages == []
        assert msg_list.message_count == 0
        assert msg_list._group_by_date is False
        assert msg_list._auto_scroll is True

    def test_set_messages(self) -> None:
        """Установка списка сообщений."""
        msg_list = MessageList()
        msg_list.set_messages([
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ])
        assert msg_list.message_count == 2

    async def test_compose_and_mount_empty(self) -> None:
        """Пустой список показывает empty-state после монтирования."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)
            assert msg_list._container is not None
            assert msg_list.is_mounted

    async def test_add_message(self) -> None:
        """Добавление сообщения в смонтированный список."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)
            msg_list.add_message(MessageRole.USER, "Привет!")
            assert msg_list.message_count == 1
            msg_list.add_message("assistant", "Здравствуйте!")
            assert msg_list.message_count == 2

    async def test_clear_messages(self) -> None:
        """Очистка списка сообщений."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList(messages=[
                {"role": "user", "content": "hello"},
            ])
            await pilot.app.mount(msg_list)
            msg_list.clear()
            assert msg_list.message_count == 0

    async def test_group_by_date(self) -> None:
        """Группировка сообщений по датам добавляет разделители."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            msg_list = MessageList(group_by_date=True)
            await pilot.app.mount(msg_list)
            msg_list.add_message(MessageRole.USER, "Сегодня", timestamp=today)
            msg_list.add_message(MessageRole.ASSISTANT, "Вчера", timestamp=yesterday)
            assert msg_list.message_count == 2

    async def test_streaming_lifecycle(self) -> None:
        """Полный жизненный цикл streaming."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)

            msg_list.start_streaming("начало")
            assert msg_list.is_streaming

            msg_list.update_streaming("обновленный текст")
            msg_list.append_streaming(" дополнение")

            msg_list.stop_streaming()
            assert not msg_list.is_streaming
            assert msg_list.message_count == 1

    async def test_stop_streaming_with_final_text(self) -> None:
        """Завершение streaming с финальным текстом."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)
            msg_list.start_streaming()
            msg_list.stop_streaming("финальный текст")
            assert msg_list.message_count == 1

    async def test_stop_streaming_empty_text(self) -> None:
        """Завершение streaming без текста не добавляет сообщение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)
            msg_list.start_streaming()
            msg_list.stop_streaming("")
            assert msg_list.message_count == 0

    async def test_thinking_indicator(self) -> None:
        """Показ и скрытие индикатора thinking."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)
            msg_list.show_thinking("Думает")
            assert msg_list.is_thinking
            msg_list.hide_thinking()
            assert not msg_list.is_thinking

    async def test_scroll_to_bottom(self) -> None:
        """Прокрутка к последнему сообщению."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            msg_list = MessageList()
            await pilot.app.mount(msg_list)
            # Метод не должен вызывать ошибок
            msg_list.scroll_to_bottom(animate=False)

    async def test_add_message_before_mount(self) -> None:
        """Добавление сообщения до монтирования не вызывает ошибок."""
        msg_list = MessageList()
        msg_list.add_message(MessageRole.USER, "test")
        assert msg_list.message_count == 1

    async def test_render_messages_without_container(self) -> None:
        """_render_messages без контейнера возвращает управление."""
        msg_list = MessageList()
        msg_list._container = None
        msg_list._render_messages()

    async def test_add_message_widget_without_container(self) -> None:
        """_add_message_widget без контейнера возвращает управление."""
        msg_list = MessageList()
        msg_list._add_message_widget({"role": "user", "content": "test"})

    async def test_start_streaming_without_container(self) -> None:
        """start_streaming без контейнера возвращает управление."""
        msg_list = MessageList()
        msg_list.start_streaming()

    async def test_show_thinking_without_container(self) -> None:
        """show_thinking без контейнера возвращает управление."""
        msg_list = MessageList()
        msg_list.show_thinking()

    async def test_update_streaming_no_widget(self) -> None:
        """update_streaming без активного виджета не вызывает ошибок."""
        msg_list = MessageList()
        msg_list.update_streaming("text")

    async def test_append_streaming_no_widget(self) -> None:
        """append_streaming без активного виджета не вызывает ошибок."""
        msg_list = MessageList()
        msg_list.append_streaming("chunk")

    def test_messages_property_returns_copy(self) -> None:
        """Свойство messages возвращает копию списка."""
        msg_list = MessageList(messages=[{"role": "user", "content": "hello"}])
        messages = msg_list.messages
        messages.append({"role": "assistant", "content": "hi"})
        assert msg_list.message_count == 1

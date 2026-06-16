"""Observable Pattern для реактивных обновлений UI.

Простая и легковесная реализация Observer паттерна для MVVM.
"""

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

import structlog

T = TypeVar('T')

logger = structlog.get_logger()


class Observable[T]:
    """Реактивное свойство с поддержкой observers.
    
    Когда значение изменяется, все подписанные observers уведомляются
    о новом значении. Используется для привязки ViewModels к UI компонентам.
    
    Пример:
        >>> name = Observable("Alice")
        >>> name.subscribe(lambda x: print(f"Name: {x}"))
        >>> name.value = "Bob"  # Выведет: Name: Bob
    """

    def __init__(self, initial_value: T) -> None:
        """Инициализировать Observable с начальным значением.
        
        Args:
            initial_value: Начальное значение свойства
        """
        self._value: T = initial_value
        # Используем Any вместо T в списке observers чтобы избежать конфликтов типов
        self._observers: list[Callable[[Any], None]] = []

    @property
    def value(self) -> T:
        """Получить текущее значение свойства."""
        return self._value

    @value.setter
    def value(self, new_value: T) -> None:
        """Установить новое значение и уведомить observers.
        
        Уведомление происходит только если значение действительно изменилось.
        
        Args:
            new_value: Новое значение свойства
        """
        if self._value != new_value:
            self._value = new_value
            self._notify_observers()

    def subscribe(self, observer: Callable[[Any], None]) -> Callable[[], None]:
        """Подписаться на изменения значения.
        
        Args:
            observer: Функция, которая будет вызвана с новым значением
            
        Returns:
            Функция для отписки (unsubscribe)
            
        Пример:
            >>> obs = Observable(42)
            >>> unsubscribe = obs.subscribe(print)
            >>> obs.value = 100  # Выведет: 100
            >>> unsubscribe()    # Отписаться
            >>> obs.value = 200  # Ничего не выведет
        """
        self._observers.append(observer)
        return lambda: self._observers.remove(observer)

    def _notify_observers(self) -> None:
        """Уведомить всех observers об изменении значения.
        
        Обработка ошибок в observers — они не должны останавливать
        цепочку уведомлений других observers.
        """
        for observer in self._observers:
            try:
                observer(self._value)
            except Exception as e:
                # Используем getattr для получения имени, так как callable могут не иметь __name__
                observer_name = getattr(observer, '__name__', repr(observer))
                logger.exception(
                    "Error in observable observer",
                    error=str(e),
                    observer=observer_name,
                )

    def __repr__(self) -> str:
        """Строковое представление Observable."""
        return f"Observable({self._value!r})"


class ObservableCommand:
    """Команда с отслеживанием статуса выполнения.
    
    Используется для асинхронных операций, которые могут быть
    долгими и требуют отображения состояния (loading, error, etc.).
    
    Пример:
        >>> async def fetch_data():
        ...     await asyncio.sleep(1)
        ...     return "data"
        
        >>> cmd = ObservableCommand(fetch_data)
        >>> cmd.is_executing.subscribe(lambda x: print(f"Loading: {x}"))
        >>> await cmd.execute()  # Выведет: Loading: True, Loading: False
    """

    def __init__(self, handler: Callable[..., Any]) -> None:
        """Инициализировать команду с обработчиком.
        
        Args:
            handler: Асинхронная функция для выполнения
        """
        self.handler = handler
        # Observable свойства для отслеживания статуса
        self.is_executing: Observable[bool] = Observable(False)
        # Observable для хранения сообщений об ошибках - может быть строка или None
        self.error: Observable[str | None] = Observable(None)
        self.last_result: Any | None = None

    async def execute(self, *args: Any, **kwargs: Any) -> Any | None:
        """Выполнить команду с обработкой ошибок.
        
        Устанавливает is_executing в True, выполняет handler,
        затем возвращает результат или ошибку.
        
        Args:
            *args: Позиционные аргументы для handler
            **kwargs: Именованные аргументы для handler
            
        Returns:
            Результат выполнения handler или None при ошибке
            
        Raises:
            Любое исключение, возникшее в handler
            
        Пример:
            >>> cmd = ObservableCommand(async_func)
            >>> try:
            ...     result = await cmd.execute("arg1", kwarg1="value1")
            ... except Exception as e:
            ...     print(f"Error: {cmd.error.value}")
        """
        self.is_executing.value = True
        self.error.value = None
        try:
            # Вызываем handler, проверяя является ли он async
            result = self.handler(*args, **kwargs)
            if asyncio.iscoroutine(result):
                self.last_result = await result
            else:
                self.last_result = result
            return self.last_result
        except Exception as e:
            error_msg = str(e)
            self.error.value = error_msg
            logger.exception("Command execution error", error=error_msg)
            raise
        finally:
            self.is_executing.value = False

    def __repr__(self) -> str:
        """Строковое представление ObservableCommand."""
        return f"ObservableCommand(executing={self.is_executing.value})"

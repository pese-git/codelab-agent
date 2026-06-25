# Спецификация возможности Context Storage

## ADDED Requirements

### Requirement: FileContentCache устраняет дублирующиеся RPC
Система ДОЛЖНА кэшировать содержимое файлов для каждой сессии, чтобы устранить дублирующиеся вызовы ACP `read_file()`.

#### Scenario: Попадание в кэш при повторном чтении
- **WHEN** файл читается через `fs/read`, а затем читается снова в той же сессии
- **THEN** второе чтение возвращает содержимое из `FileContentCache` без ACP RPC, логирует debug `file_cache_miss` при первом, без лога при попадании

#### Scenario: Промах кэша при первом чтении
- **WHEN** файл читается впервые
- **THEN** система вызывает ACP RPC `read_file()`, сохраняет содержимое в кэш через `set(path, content)`, возвращает содержимое

#### Scenario: LRU eviction при достижении ёмкости
- **WHEN** кэш достигает лимита `cache_max_files`
- **THEN** система вытесняет наименее недавно используемую запись, логирует debug `file_cache_evicted`

#### Scenario: Инвалидация при fs/write
- **WHEN** `fs/write` успешно завершается для пути
- **THEN** система вызывает `FileContentCache.invalidate(path)`, последующий `get(path)` возвращает `None`

#### Scenario: Инвалидация публикует сигнал изменения
- **WHEN** вызывается `invalidate(path)`
- **THEN** система публикует сигнал изменения в единый источник истины (точка интеграции Phase 2 ↔ Phase 4)

### Requirement: SessionFileCacheRegistry управляет жизненным циклом кэша
Система ДОЛЖНА управлять файловыми кэшами для каждой сессии с правильным жизненным циклом.

#### Scenario: Создание кэша для сессии
- **WHEN** начинается новая сессия
- **THEN** `SessionFileCacheRegistry` создаёт новый `FileContentCache` для сессии

#### Scenario: Очистка кэша при закрытии сессии
- **WHEN** сессия закрывается
- **THEN** registry освобождает память кэша, обеспечивает бюджет < 2 MB на сессию

### Requirement: FileCacheDecorator оборачивает ToolExecutor
Система ДОЛЖНА оборачивать `ToolExecutor` через `FileCacheDecorator` для перехвата `fs/read` и `fs/write`.

#### Scenario: Decorator перехватывает fs/read
- **WHEN** инструмент `fs/read` успешно выполняется
- **THEN** decorator вызывает `FileContentCache.set(path, content)` после возврата результата инструментом

#### Scenario: Decorator перехватывает fs/write
- **WHEN** инструмент `fs/write` успешно выполняется
- **THEN** decorator вызывает `FileContentCache.invalidate(path)` и публикует сигнал изменения

#### Scenario: Decorator I/O через ToolRegistry
- **WHEN** decorator нуждается в чтении/записи файлов
- **THEN** система использует ACP `ToolRegistry`, а не прямой доступ к файловой системе

#### Scenario: Обработка ошибок decorator
- **WHEN** `invalidate()` или `set()` завершается сбоем
- **THEN** decorator логирует ошибку, не распространяет исключение (выполнение инструмента успешно), логирует `file_cache_invalidation_failed` или `file_cache_set_failed`

### Requirement: CodeSkeletonizer сжимает код через AST
Система ДОЛЖНА сжимать код до сигнатур используя AST анализ, сохраняя структуру.

#### Scenario: Python AST skeletonization
- **WHEN** вызывается `skeletonize()` для Python кода
- **THEN** система заменяет тела функций/методов на `...`, сохраняет сигнатуры, импорты, определения классов

#### Scenario: Skeleton обеспечивает экономию 80-85% токенов
- **WHEN** skeleton производится из файла на 3500 токенов
- **THEN** skeleton составляет ~250 токенов (экономия 80-85%)

#### Scenario: Skeleton детерминирован
- **WHEN** `skeletonize()` вызывается 100 раз на одном входе
- **THEN** все 100 выводов байт-идентичны

#### Scenario: Skeleton сохраняет структуру
- **WHEN** код имеет классы, методы, функции
- **THEN** skeleton сохраняет иерархию классов, сигнатуры методов, сигнатуры функций

#### Scenario: Skeleton не выгоден
- **WHEN** количество токенов skeleton >= оригинала
- **THEN** система использует оригинальный код, логирует info `skeleton_not_beneficial`

### Requirement: CodeSkeletonizer обрабатывает неподдерживаемые языки
Система ДОЛЖНА корректно обрабатывать файлы на неподдерживаемых языках.

#### Scenario: can_handle возвращает False для неподдерживаемого языка
- **WHEN** файл имеет расширение `.json`, `.md`, `.dart`, и т.д.
- **THEN** `can_handle(path)` возвращает `False`

#### Scenario: Skeletonization пропускается для неподдерживаемых
- **WHEN** `can_handle()` равен `False`
- **THEN** система не вызывает `skeletonize()`, использует оригинальное содержимое

#### Scenario: SyntaxError в поддерживаемом языке
- **WHEN** Python файл имеет синтаксическую ошибку
- **THEN** `skeletonize()` перехватывает `SyntaxError`, возвращает оригинальный код, логирует warning `skeletonize_syntax_error`

### Requirement: TokenCounter обеспечивает точный подсчёт
Система ДОЛЖНА точно подсчитывать токены используя tiktoken с fallback.

#### Scenario: Подсчёт tiktoken
- **WHEN** вызывается `TiktokenCounter.count(text)`
- **THEN** система возвращает точное количество токенов используя кодировку tiktoken

#### Scenario: Fallback при недоступности tiktoken
- **WHEN** импорт tiktoken завершается сбоем
- **THEN** система возвращает `ApproximateTokenCounter` с `len(text) // 4`, логирует warning `tiktoken_not_available_using_fallback`

#### Scenario: Сбой подсчёта tiktoken
- **WHEN** кодировка tiktoken завершается сбоем на конкретном входе
- **THEN** система возвращается к приблизительному подсчёту для этого вызова, логирует error `tiktoken_encoding_failed_using_fallback`

#### Scenario: count_messages для списка
- **WHEN** вызывается `count_messages(messages)`
- **THEN** система возвращает общее количество токенов для всех сообщений

### Requirement: ContextItem представляет единицу контекста
Система ДОЛЖНА представлять каждый элемент контекста как `ContextItem` с приоритетом.

#### Scenario: Структура ContextItem
- **WHEN** создаётся элемент контекста
- **THEN** элемент имеет `id`, `type`, `content`, `priority` (0-10), `owner_scope`, `token_count`, `last_accessed`

#### Scenario: Eviction на основе приоритета
- **WHEN** компактору нужно вытеснить элементы
- **THEN** система вытесняет сначала наименьший приоритет (`file_skeleton=3` → `terminal_output=4` → `file_content=5` → ... → `system_rules=10`)

#### Scenario: Приоритет >= 10 не вытесняется
- **WHEN** элемент имеет `priority >= 10`
- **THEN** система не вытесняет элемент во время компактирования

### Requirement: Детерминированный вывод для стабильности кэша
Система ДОЛЖНА обеспечивать детерминированный вывод для `CodeSkeletonizer` и `FileContentCache` для поддержания стабильности кэша.

#### Scenario: Детерминированный вывод skeleton
- **WHEN** один и тот же код скелетируется многократно
- **THEN** вывод байт-идентичен (стабильный порядок AST, отсортированные импорты, нормализованные пробелы)

#### Scenario: Детерминированное содержимое кэша
- **WHEN** один и тот же файл читается многократно
- **THEN** кэшированное содержимое байт-идентично

#### Scenario: Стабильность fingerprint baseline
- **WHEN** содержимое baseline не изменяется
- **THEN** `baseline_fingerprint` идентичен между вызовами (детерминированный хеш)

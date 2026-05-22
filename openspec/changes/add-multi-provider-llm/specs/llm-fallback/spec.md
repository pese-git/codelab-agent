# Spec: LLM Fallback

## ADDED Requirements

### Requirement: Интерфейс стратегии fallback
Система ДОЛЖНА определять абстрактный базовый класс `FallbackStrategy`, который реализуют все стратегии fallback.

#### Scenario: Стратегия выбирает провайдер
- **WHEN** вызван `FallbackStrategy.select_provider(candidates, request, context)`
- **THEN** возвращён один `LLMProvider` из списка кандидатов

#### Scenario: Стратегия записывает успех
- **WHEN** вызван `FallbackStrategy.on_success(provider_id)`
- **THEN** стратегия записала успешный запрос для данного провайдера

#### Scenario: Стратегия записывает ошибку
- **WHEN** вызван `FallbackStrategy.on_failure(provider_id, error)`
- **THEN** стратегия записала失败的 запрос для данного провайдера с деталями ошибки

### Requirement: Последовательная стратегия fallback
Система ДОЛЖНА предоставлять стратегию `SequentialFallback`, которая пробует провайдеры в заданном порядке.

#### Scenario: Первый провайдер доступен
- **WHEN** `SequentialFallback` сконфигурирован с `order=["openai", "openrouter", "ollama"]` и все провайдеры доступны
- **THEN** выбран первый провайдер в порядке (`openai`)

#### Scenario: Circuit breaker первого провайдера открыт
- **WHEN** circuit breaker первого провайдера находится в открытом состоянии
- **THEN** выбран следующий доступный провайдер в порядке

#### Scenario: Все провайдеры недоступны
- **WHEN** у всех провайдеров в порядке открыты circuit breakers
- **THEN** возбуждено исключение `AllProvidersFailed`

### Requirement: Оркестратор fallback
Система ДОЛЖНА предоставлять `FallbackOrchestrator` для выполнения запросов с поддержкой цепочки fallback.

#### Scenario: Успешный запрос на первом провайдере
- **WHEN** вызван `FallbackOrchestrator.execute(request)` и основной провайдер успешен
- **THEN** ответ возвращён немедленно без попытки fallback

#### Scenario: Fallback на второй провайдер
- **WHEN** основной провайдер завершился с ошибкой, подлежащей повтору (rate_limit, timeout)
- **THEN** оркестратор пробует следующий провайдер в цепочке fallback

#### Scenario: Ошибка без повтора
- **WHEN** провайдер завершился с ошибкой, не подлежащей повтору (invalid_api_key, model_not_found)
- **THEN** ошибка propagated немедленно без попытки fallback

#### Scenario: Все провайдеры завершились ошибкой
- **WHEN** все провайдеры в цепочке fallback завершились ошибкой
- **THEN** возбуждено исключение `AllProvidersFailed` с деталями всех ошибок

### Requirement: Конфигурация fallback
Система ДОЛЖНА поддерживать конфигурацию fallback, включая `enabled`, `strategy`, `order` и `retry_on`.

#### Scenario: Fallback отключён
- **WHEN** `fallback.enabled=false`
- **THEN** оркестратор использует только основной провайдер без fallback

#### Scenario: Конфигурация retry-on
- **WHEN** `fallback.retry_on=["rate_limit", "timeout"]`
- **THEN** только эти типы ошибок запускают fallback на следующий провайдер

### Requirement: Фабрика стратегий fallback
Система ДОЛЖНА предоставлять `FallbackStrategyFactory` для создания экземпляров стратегий из конфигурации.

#### Scenario: Создание последовательной стратегии
- **WHEN** вызван `FallbackStrategyFactory.create(config)` с `strategy="sequential"`
- **THEN** возвращён экземпляр `SequentialFallback`

#### Scenario: Неизвестная стратегия
- **WHEN** вызван `FallbackStrategyFactory.create(config)` с неизвестным именем стратегии
- **THEN** возбуждено исключение `ValueError`

### Requirement: Circuit Breaker (Extension Point)
Система ДОЛЖНА определять класс `CircuitBreaker` для отслеживания здоровья провайдеров, используемый будущими стратегиями fallback.

#### Scenario: Запись ошибок
- **WHEN** вызван `CircuitBreaker.record_failure()` N раз (threshold)
- **THEN** circuit переходит в состояние `open`

#### Scenario: Circuit открыт
- **WHEN** circuit breaker находится в состоянии `open`
- **THEN** `is_open()` возвращает `True` и провайдер пропускается

#### Scenario: Запись успеха сбрасывает circuit
- **WHEN** вызван `CircuitBreaker.record_success()`
- **THEN** счётчик ошибок сброшен и circuit переходит в состояние `closed`

# Spec: Provider Telemetry

## ADDED Requirements

### Requirement: Интерфейс Telemetry Sink
Система ДОЛЖНА определять абстрактный базовый класс `TelemetrySink`, который реализуют все реализации телеметрии.

#### Scenario: Запись метрик запроса
- **WHEN** вызван `TelemetrySink.record_request(provider, model, latency_ms, success)`
- **THEN** sink телеметрии записал метрики запроса

#### Scenario: Запись метрик стоимости
- **WHEN** вызван `TelemetrySink.record_cost(provider, model, cost_usd)`
- **THEN** sink телеметрии записал метрики стоимости

### Requirement: No-Op телеметрия (по умолчанию)
Система ДОЛЖНА предоставлять реализацию `NoOpTelemetry`, которая ничего не делает (по умолчанию для MVP).

#### Scenario: No-op запись запроса
- **WHEN** вызван `NoOpTelemetry.record_request(...)`
- **THEN** никаких действий не выполнено (silent pass-through)

#### Scenario: No-op запись стоимости
- **WHEN** вызван `NoOpTelemetry.record_cost(...)`
- **THEN** никаких действий не выполнено (silent pass-through)

### Requirement: Интеграция телеметрии
Система ДОЛЖНА интегрировать запись телеметрии в поток запросов провайдера.

#### Scenario: Запись после успешного запроса
- **WHEN** провайдер успешно завершил запрос
- **THEN** вызван `TelemetrySink.record_request()` с `success=True` и измеренной задержкой

#### Scenario: Запись после ошибочного запроса
- **WHEN** провайдер не смог завершить запрос
- **THEN** вызван `TelemetrySink.record_request()` с `success=False` и измеренной задержкой

### Requirement: Prometheus телеметрия (Extension Point)
Система ДОЛЖНА поддерживать реализацию `PrometheusTelemetry` как будущее расширение.

#### Scenario: Экспорт метрик Prometheus
- **WHEN** `PrometheusTelemetry` сконфигурирован
- **THEN** задержка запросов,成功率 и стоимость экспортированы как метрики Prometheus

#### Scenario: Гистограмма для задержки
- **WHEN** вызван `PrometheusTelemetry.record_request()`
- **THEN** задержка записана в метрику-гистограмму `llm_request_duration_seconds`

#### Scenario: Счётчик для запросов
- **WHEN** вызван `PrometheusTelemetry.record_request()`
- **THEN** инкрементирована метрика-счётчик `llm_requests_total` с лейблами `provider`, `model`, `success`

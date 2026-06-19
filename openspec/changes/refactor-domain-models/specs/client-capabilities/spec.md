# Spec: client-capabilities

## ADDED Requirements

### Требование: Domain ClientCapabilities

Система ДОЛЖНА предоставлять `ClientCapabilities` как frozen dataclass:
- `fs_read: bool` — поддержка чтения файлов
- `fs_write: bool` — поддержка записи файлов
- `terminal: bool` — поддержка терминала
- `image_prompts: bool` — поддержка изображений в промптах
- `embedded_context: bool` — поддержка встроенного контекста

### Требование: ClientCapabilities Business Logic

`ClientCapabilities` ДОЛЖНЫ предоставлять:
- `supports_fs` property — поддержка файловой системы
- `can_read_files()` — проверка чтения файлов
- `can_write_files()` — проверка записи файлов
- `supports_multimodal()` — поддержка мультимодального контента

### Требование: Типизированная Session.capabilities

Система ДОЛЖНА обновить `Session` entity:
- `capabilities: ClientCapabilities` — типизированная модель вместо `dict[str, Any]`

### Требование: Миграция ClientCapabilities

Система ДОЛЖНА мигрировать все использования `client_capabilities: dict` на `ClientCapabilities`.

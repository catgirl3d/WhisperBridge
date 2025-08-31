# Руководство по настройке WhisperBridge

## Содержание

1. [Обзор настроек](#обзор-настроек)
2. [API настройки](#api-настройки)
3. [Языковые настройки](#языковые-настройки)
4. [Настройка горячих клавиш](#настройка-горячих-клавиш)
5. [Настройка OCR](#настройка-ocr)
6. [Настройка интерфейса](#настройка-интерфейса)
7. [Системные настройки](#системные-настройки)
8. [Настройка производительности](#настройка-производительности)
9. [Расширенные настройки](#расширенные-настройки)
10. [Импорт и экспорт настроек](#импорт-и-экспорт-настроек)

## Обзор настроек

WhisperBridge предоставляет гибкую систему настроек для адаптации под различные потребности пользователей. Настройки разделены на несколько категорий и могут быть изменены через графический интерфейс или файлы конфигурации.

### Расположение файлов настроек

- **Windows**: `%USERPROFILE%\.whisperbridge\settings.json`
- **macOS**: `~/.whisperbridge/settings.json`
- **Linux**: `~/.whisperbridge/settings.json`

### Структура настроек

```json
{
  "api": {
    "provider": "openai",
    "model": "gpt-3.5-turbo",
    "timeout": 30,
    "max_retries": 3
  },
  "languages": {
    "source_language": "auto",
    "target_language": "ru",
    "supported_languages": ["en", "ru", "es", "fr", "de"]
  },
  "hotkeys": {
    "translate": "ctrl+shift+t",
    "quick_translate": "ctrl+shift+q",
    "activation": "ctrl+shift+a"
  },
  "ocr": {
    "primary_engine": "easyocr",
    "fallback_engine": "paddleocr",
    "languages": ["en", "ru"],
    "confidence_threshold": 0.7
  },
  "ui": {
    "theme": "dark",
    "overlay_timeout": 10,
    "window_opacity": 0.95,
    "font_size": 12
  }
}
```

## API настройки

### OpenAI API

#### Основные параметры

| Параметр | Описание | По умолчанию | Возможные значения |
|----------|----------|--------------|-------------------|
| `api_provider` | Провайдер API | `"openai"` | `"openai"`, `"anthropic"`, `"google"` |
| `model` | Модель GPT | `"gpt-3.5-turbo"` | `"gpt-3.5-turbo"`, `"gpt-4"`, `"gpt-4-turbo"` |
| `api_timeout` | Таймаут запроса (сек) | `30` | `10-120` |
| `max_retries` | Максимум повторов | `3` | `1-10` |

#### Настройка через интерфейс

1. **Откройте настройки**
   - Щелкните по иконке в системном трее
   - Выберите "Открыть настройки"

2. **Введите API ключ**
   - В поле "OpenAI API Key" введите ваш ключ
   - Ключ автоматически сохраняется в безопасном хранилище

3. **Выберите модель**
   - `gpt-3.5-turbo` - быстрая и экономичная
   - `gpt-4` - более качественная, но дорогая
   - `gpt-4-turbo` - оптимальное соотношение скорости и качества

4. **Протестируйте настройки**
   - Нажмите кнопку "Тест API"
   - Убедитесь в успешном подключении

#### Настройка через файл конфигурации

```json
{
  "api_provider": "openai",
  "model": "gpt-3.5-turbo",
  "api_timeout": 30,
  "max_retries": 3,
  "system_prompt": "You are a professional translator. Translate the following text accurately and naturally."
}
```

#### Мониторинг использования API

1. **Проверка баланса**
   - Регулярно проверяйте баланс на platform.openai.com
   - Настройте уведомления о низком балансе

2. **Оптимизация расходов**
   - Используйте кэширование для повторных запросов
   - Выбирайте подходящую модель для задач
   - Настройте разумные лимиты запросов

## Языковые настройки

### Поддерживаемые языки

#### Языки распознавания (OCR)
- **Английский** (`en`) - основной язык
- **Русский** (`ru`) - кириллица
- **Украинский** (`uk`) - кириллица
- **Немецкий** (`de`) - латиница с диакритикой
- **Французский** (`fr`) - латиница с диакритикой
- **Испанский** (`es`) - латиница
- **Итальянский** (`it`) - латиница
- **Японский** (`ja`) - иероглифы, хирагана, катакана
- **Корейский** (`ko`) - хангыль
- **Китайский** (`zh`) - упрощенные и традиционные иероглифы

#### Языки перевода
Поддерживаются все основные языки мира через GPT API.

### Настройка языков

#### Исходный язык

```json
{
  "source_language": "auto"  // Автоопределение
}
```

Варианты:
- `"auto"` - автоматическое определение языка
- `"en"` - английский
- `"ru"` - русский
- Любой другой поддерживаемый код языка

#### Целевой язык

```json
{
  "target_language": "ru"
}
```

#### Языки для OCR

```json
{
  "ocr_languages": ["en", "ru", "de"]
}
```

**Рекомендации:**
- Включайте только необходимые языки для лучшей производительности
- Первый язык в списке имеет приоритет при распознавании
- Для многоязычных текстов добавьте все нужные языки

## Настройка горячих клавиш

### Доступные горячие клавиши

| Функция | По умолчанию | Описание |
|---------|--------------|----------|
| Основной перевод | `Ctrl+Shift+T` | Запуск захвата области экрана |
| Быстрый перевод | `Ctrl+Shift+Q` | Перевод из буфера обмена |
| Активация приложения | `Ctrl+Shift+A` | Показать окно настроек |

### Формат горячих клавиш

#### Модификаторы
- `ctrl` - клавиша Control
- `shift` - клавиша Shift
- `alt` - клавиша Alt
- `win` - клавиша Windows (cmd на Mac)

#### Основные клавиши
- Буквы: `a-z`
- Цифры: `0-9`
- Функциональные: `f1-f12`
- Специальные: `space`, `enter`, `tab`, `esc`
- Стрелки: `up`, `down`, `left`, `right`

#### Примеры комбинаций

```json
{
  "translate_hotkey": "ctrl+shift+t",
  "quick_translate_hotkey": "alt+space",
  "activation_hotkey": "win+shift+w"
}
```

### Настройка через интерфейс

1. **Откройте настройки горячих клавиш**
   - В главном окне найдите секцию "Горячие клавиши"

2. **Измените комбинацию**
   - Кликните в поле ввода
   - Нажмите желаемую комбинацию клавиш
   - Система автоматически определит формат

3. **Проверьте конфликты**
   - Приложение предупредит о конфликтах с системными клавишами
   - Выберите альтернативную комбинацию при необходимости

### Решение конфликтов

#### Проверка занятых комбинаций

**Windows:**
```cmd
# Просмотр системных горячих клавиш
reg query "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
```

**macOS:**
- Системные настройки → Клавиатура → Сочетания клавиш

**Linux:**
```bash
# Просмотр настроенных сочетаний
gsettings list-recursively | grep -i shortcut
```

#### Рекомендуемые комбинации

Безопасные комбинации, редко используемые системой:
- `Ctrl+Shift+[буква]`
- `Alt+Shift+[буква]`
- `Win+Shift+[буква]` (Windows)
- `Cmd+Option+[буква]` (macOS)

## Настройка OCR

### Выбор OCR движка

#### Основной движок

```json
{
  "primary_ocr_engine": "easyocr"
}
```

**Доступные движки:**
- `"easyocr"` - рекомендуется для большинства случаев
- `"paddleocr"` - хорош для азиатских языков

#### Резервный движок

```json
{
  "fallback_ocr_engine": "paddleocr"
}
```

Используется, если основной движок не справился или дал низкую уверенность.

### Настройка точности

#### Порог уверенности

```json
{
  "ocr_confidence_threshold": 0.7
}
```

- `0.5` - низкий порог, больше результатов, но возможны ошибки
- `0.7` - оптимальный баланс (рекомендуется)
- `0.9` - высокий порог, только очень уверенные результаты

#### Предобработка изображений

```json
{
  "ocr_preprocessing": {
    "enhance_contrast": true,
    "reduce_noise": true,
    "deskew": true,
    "resize_factor": 2.0
  }
}
```

**Параметры предобработки:**
- `enhance_contrast` - улучшение контрастности
- `reduce_noise` - удаление шума
- `deskew` - выравнивание наклоненного текста
- `resize_factor` - масштабирование изображения

### Оптимизация для разных типов текста

#### Печатный текст
```json
{
  "primary_ocr_engine": "easyocr",
  "ocr_confidence_threshold": 0.8,
  "enhance_contrast": true
}
```

#### Рукописный текст
```json
{
  "primary_ocr_engine": "easyocr",
  "ocr_confidence_threshold": 0.6,
  "reduce_noise": true
}
```

#### Азиатские языки
```json
{
  "primary_ocr_engine": "paddleocr",
  "ocr_languages": ["zh", "ja", "ko"],
  "resize_factor": 1.5
}
```

## Настройка интерфейса

### Темы оформления

#### Доступные темы

```json
{
  "theme": "dark"
}
```

**Варианты:**
- `"dark"` - темная тема (рекомендуется)
- `"light"` - светлая тема
- `"system"` - следовать системной теме

#### Настройка цветов

```json
{
  "ui_colors": {
    "primary": "#007ACC",
    "secondary": "#6C757D",
    "background": "#1E1E1E",
    "text": "#FFFFFF"
  }
}
```

### Настройка окон

#### Окно результатов (Overlay)

```json
{
  "overlay": {
    "timeout": 10,
    "position": "cursor",
    "opacity": 0.95,
    "auto_close": true,
    "show_animations": true
  }
}
```

**Параметры:**
- `timeout` - время автозакрытия (секунды)
- `position` - позиция окна (`"cursor"`, `"center"`, `"top-right"`)
- `opacity` - прозрачность окна (0.1-1.0)
- `auto_close` - автоматическое закрытие
- `show_animations` - анимации появления/исчезновения

#### Главное окно

```json
{
  "main_window": {
    "width": 600,
    "height": 700,
    "remember_position": true,
    "minimize_to_tray": true
  }
}
```

### Шрифты и размеры

```json
{
  "fonts": {
    "ui_font_size": 12,
    "result_font_size": 11,
    "font_family": "Segoe UI"
  }
}
```

## Системные настройки

### Автозапуск

```json
{
  "startup_with_system": true
}
```

#### Настройка автозапуска

**Windows (через реестр):**
```cmd
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run" /v "WhisperBridge" /t REG_SZ /d "C:\path\to\whisperbridge.exe"
```

**macOS (через LaunchAgent):**
```bash
# Создание plist файла для автозапуска
launchctl load ~/Library/LaunchAgents/com.whisperbridge.app.plist
```

**Linux (через autostart):**
```bash
# Создание desktop файла
cp whisperbridge.desktop ~/.config/autostart/
```

### Уведомления

```json
{
  "notifications": {
    "show_notifications": true,
    "notification_timeout": 5,
    "show_success": true,
    "show_errors": true,
    "show_progress": false
  }
}
```

### Логирование

```json
{
  "logging": {
    "log_level": "INFO",
    "log_to_file": true,
    "max_log_size": 10,
    "log_rotation": true
  }
}
```

**Уровни логирования:**
- `"DEBUG"` - подробная отладочная информация
- `"INFO"` - общая информация (рекомендуется)
- `"WARNING"` - только предупреждения и ошибки
- `"ERROR"` - только ошибки

## Настройка производительности

### Кэширование

```json
{
  "cache": {
    "enabled": true,
    "ttl": 3600,
    "max_size": 100,
    "ocr_cache": true,
    "translation_cache": true
  }
}
```

**Параметры кэша:**
- `enabled` - включить кэширование
- `ttl` - время жизни записей (секунды)
- `max_size` - максимальное количество записей
- `ocr_cache` - кэшировать результаты OCR
- `translation_cache` - кэшировать переводы

### Многопоточность

```json
{
  "performance": {
    "thread_pool_size": 4,
    "max_concurrent_requests": 2,
    "request_queue_size": 10
  }
}
```

### Оптимизация памяти

```json
{
  "memory": {
    "max_image_size": 5242880,
    "compress_images": true,
    "cleanup_interval": 300
  }
}
```

**Параметры:**
- `max_image_size` - максимальный размер изображения (байты)
- `compress_images` - сжимать изображения перед обработкой
- `cleanup_interval` - интервал очистки памяти (секунды)

## Расширенные настройки

### Настройка сети

```json
{
  "network": {
    "proxy": {
      "enabled": false,
      "host": "proxy.example.com",
      "port": 8080,
      "username": "",
      "password": ""
    },
    "ssl_verify": true,
    "connection_timeout": 10,
    "read_timeout": 30
  }
}
```

### Безопасность

```json
{
  "security": {
    "encrypt_api_keys": true,
    "secure_storage": true,
    "clear_clipboard_after": 60,
    "log_sensitive_data": false
  }
}
```

### Экспериментальные функции

```json
{
  "experimental": {
    "gpu_acceleration": false,
    "batch_processing": false,
    "advanced_ocr": false,
    "custom_models": false
  }
}
```

**Внимание:** Экспериментальные функции могут быть нестабильными.

## Импорт и экспорт настроек

### Экспорт настроек

```bash
# Создание резервной копии
cp ~/.whisperbridge/settings.json ~/whisperbridge_backup.json
```

### Импорт настроек

```bash
# Восстановление из резервной копии
cp ~/whisperbridge_backup.json ~/.whisperbridge/settings.json
```

### Сброс настроек

```bash
# Удаление файла настроек (будут созданы настройки по умолчанию)
rm ~/.whisperbridge/settings.json
```

### Миграция настроек

При обновлении приложения настройки мигрируют автоматически. Если возникли проблемы:

1. **Создайте резервную копию**
   ```bash
   cp ~/.whisperbridge/settings.json ~/settings_backup.json
   ```

2. **Запустите миграцию вручную**
   ```bash
   whisperbridge --migrate-config
   ```

3. **Проверьте результат**
   - Откройте настройки в приложении
   - Убедитесь, что все параметры корректны

### Синхронизация между устройствами

Для синхронизации настроек между несколькими устройствами:

1. **Сохраните настройки в облаке**
   ```bash
   # Скопируйте файл настроек в облачное хранилище
   cp ~/.whisperbridge/settings.json ~/Dropbox/whisperbridge_settings.json
   ```

2. **Восстановите на другом устройстве**
   ```bash
   # Скопируйте из облачного хранилища
   cp ~/Dropbox/whisperbridge_settings.json ~/.whisperbridge/settings.json
   ```

---

*Для получения дополнительной помощи обратитесь к разделам [Руководство пользователя](USER_GUIDE.md) или [Устранение неполадок](TROUBLESHOOTING.md).*
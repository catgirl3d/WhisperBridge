# План интеграции компонентов WhisperBridge

## Обзор

Данный документ описывает пошаговый план интеграции всех компонентов системы WhisperBridge, включая порядок разработки, зависимости между модулями и критические точки интеграции.

## Фазы разработки

### Фаза 1: Базовая инфраструктура (1-2 недели)

#### 1.1 Настройка проекта
- [ ] Создание структуры каталогов
- [ ] Настройка виртуального окружения
- [ ] Установка базовых зависимостей
- [ ] Настройка системы логирования
- [ ] Создание базовых конфигурационных файлов

**Приоритет:** Критический  
**Зависимости:** Нет  
**Результат:** Готовая структура проекта с базовой конфигурацией

#### 1.2 Основные модели данных
- [ ] Реализация `models/settings.py`
- [ ] Реализация `models/translation.py`
- [ ] Реализация `models/capture.py`
- [ ] Валидация с помощью Pydantic

**Приоритет:** Высокий  
**Зависимости:** 1.1  
**Результат:** Типизированные модели данных

#### 1.3 Система конфигурации
- [ ] Реализация `core/config.py`
- [ ] Реализация `services/settings_manager.py`
- [ ] Интеграция с keyring для API ключей
- [ ] Создание файлов конфигурации по умолчанию

**Приоритет:** Высокий  
**Зависимости:** 1.2  
**Результат:** Работающая система настроек

### Фаза 2: Основные сервисы (2-3 недели)

#### 2.1 Сервис захвата экрана
- [ ] Реализация `services/screen_capture.py`
- [ ] Интеграция с библиотекой mss
- [ ] Создание интерфейса выбора области
- [ ] Тестирование на разных разрешениях экрана

**Приоритет:** Критический  
**Зависимости:** 1.3  
**Результат:** Функциональный захват экрана

```python
# Пример интеграции
class ScreenCaptureService:
    def __init__(self, settings_manager: SettingsManager):
        self.settings = settings_manager
        self.sct = mss.mss()
        
    def capture_area(self, area: Rectangle) -> Image:
        monitor = {
            "top": area.y,
            "left": area.x,
            "width": area.width,
            "height": area.height
        }
        screenshot = self.sct.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
```

#### 2.2 OCR сервис
- [ ] Реализация `services/ocr_service.py`
- [ ] Интеграция с EasyOCR
- [ ] Оптимизация производительности
- [ ] Обработка различных языков

**Приоритет:** Критический
**Зависимости:** 2.1
**Результат:** Работающее распознавание текста

#### 2.3 Сервис перевода
- [ ] Реализация `services/translation_service.py`
- [ ] Интеграция с OpenAI API
- [ ] Система кэширования переводов
- [ ] Обработка ошибок и retry логика
- [ ] Поддержка различных промптов

**Приоритет:** Критический  
**Зависимости:** 1.3  
**Результат:** Функциональный перевод текста

```python
# Пример интеграции Translation Service
class TranslationService:
    def __init__(self, settings_manager: SettingsManager):
        self.settings = settings_manager
        self.client = OpenAI(api_key=self.settings.get_api_key())
        self.cache = TranslationCache()
        
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        # Проверка кэша
        cache_key = self._generate_cache_key(text, source_lang, target_lang)
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
            
        # Построение промпта
        prompt = self._build_prompt(text, source_lang, target_lang)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.get_translation_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            translated_text = response.choices[0].message.content
            result = TranslationResult(
                original_text=text,
                translated_text=translated_text,
                source_language=source_lang,
                target_language=target_lang,
                timestamp=datetime.now()
            )
            
            # Сохранение в кэш
            self.cache.set(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            raise TranslationError(f"Translation service error: {e}")
```

### Фаза 3: Пользовательский интерфейс (2-3 недели)

#### 3.1 Базовые UI компоненты
- [ ] Настройка CustomTkinter темы
- [ ] Создание базовых компонентов в `ui/components/`
- [ ] Реализация системы событий UI
- [ ] Создание общих стилей и констант

**Приоритет:** Высокий  
**Зависимости:** Фаза 2  
**Результат:** Готовые UI компоненты

#### 3.2 Главное окно настроек
- [ ] Реализация `ui/main_window.py`
- [ ] Панели настроек (языки, API, горячие клавиши)
- [ ] Валидация пользовательского ввода
- [ ] Сохранение и загрузка настроек

**Приоритет:** Средний  
**Зависимости:** 3.1  
**Результат:** Функциональное окно настроек

```python
# Пример интеграции Main Window
class MainWindow(ctk.CTk):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.settings_manager = app_instance.settings_manager
        
        self.title("WhisperBridge Settings")
        self.geometry("800x600")
        
        self._create_widgets()
        self._load_settings()
        
    def _create_widgets(self):
        # Создание вкладок настроек
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Вкладка общих настроек
        self.general_tab = self.tabview.add("General")
        self._create_general_settings()
        
        # Вкладка OCR настроек
        self.ocr_tab = self.tabview.add("OCR")
        self._create_ocr_settings()
        
        # Вкладка перевода
        self.translation_tab = self.tabview.add("Translation")
        self._create_translation_settings()
```

#### 3.3 Оверлей окно результатов
- [ ] Реализация `ui/overlay_window.py`
- [ ] Позиционирование относительно курсора
- [ ] Кнопки копирования и автовставки
- [ ] Автоматическое скрытие по таймауту

**Приоритет:** Критический  
**Зависимости:** 3.1  
**Результат:** Работающий оверлей с результатами

#### 3.4 Интерфейс захвата экрана
- [ ] Реализация `ui/capture_overlay.py`
- [ ] Полноэкранный оверлей для выбора области
- [ ] Визуальная обратная связь при выборе
- [ ] Интеграция с сервисом захвата

**Приоритет:** Критический  
**Зависимости:** 3.1, 2.1  
**Результат:** Интуитивный интерфейс выбора области

### Фаза 4: Системная интеграция (1-2 недели)

#### 4.1 Менеджер горячих клавиш
- [ ] Реализация `services/hotkey_manager.py`
- [ ] Интеграция с pynput
- [ ] Регистрация глобальных горячих клавиш
- [ ] Обработка конфликтов клавиш

**Приоритет:** Критический  
**Зависимости:** Фаза 2, 3  
**Результат:** Работающие глобальные горячие клавиши

```python
# Пример интеграции Hotkey Manager
class HotkeyManager:
    def __init__(self, app_instance):
        self.app = app_instance
        self.listener = None
        self.registered_hotkeys = {}
        
    def register_hotkey(self, combination: str, callback: callable):
        try:
            # Парсинг комбинации клавиш
            keys = self._parse_hotkey_combination(combination)
            
            # Регистрация через pynput
            hotkey = keyboard.GlobalHotKeys({
                combination: callback
            })
            
            self.registered_hotkeys[combination] = {
                'hotkey': hotkey,
                'callback': callback
            }
            
            hotkey.start()
            logger.info(f"Registered hotkey: {combination}")
            
        except Exception as e:
            logger.error(f"Failed to register hotkey {combination}: {e}")
            raise HotkeyError(f"Hotkey registration failed: {e}")
            
    def on_translate_hotkey(self):
        """Основной обработчик горячей клавиши перевода"""
        try:
            # Запуск процесса захвата и перевода
            asyncio.create_task(self.app.start_translation_workflow())
        except Exception as e:
            logger.error(f"Translation workflow failed: {e}")
```

#### 4.2 Системный трей
- [ ] Реализация `ui/system_tray.py`
- [ ] Интеграция с pystray
- [ ] Контекстное меню трея
- [ ] Уведомления о статусе

**Приоритет:** Средний  
**Зависимости:** 3.2  
**Результат:** Функциональный системный трей

### Фаза 5: Интеграция и оптимизация (1-2 недели)

#### 5.1 Основной класс приложения
- [ ] Реализация `app.py`
- [ ] Инициализация всех сервисов
- [ ] Управление жизненным циклом приложения
- [ ] Обработка исключений на уровне приложения

**Приоритет:** Критический  
**Зависимости:** Все предыдущие фазы  
**Результат:** Полностью интегрированное приложение

```python
# Пример основного класса приложения
class WhisperBridgeApp:
    def __init__(self):
        self.settings_manager = None
        self.hotkey_manager = None
        self.screen_capture = None
        self.ocr_service = None
        self.translation_service = None
        self.main_window = None
        self.system_tray = None
        self.overlay_window = None
        
    async def initialize(self):
        """Инициализация всех компонентов"""
        try:
            # Инициализация в правильном порядке
            self.settings_manager = SettingsManager()
            await self.settings_manager.load_settings()
            
            self.screen_capture = ScreenCaptureService(self.settings_manager)
            self.ocr_service = OCRService(self.settings_manager)
            self.translation_service = TranslationService(self.settings_manager)
            
            self.hotkey_manager = HotkeyManager(self)
            self.system_tray = SystemTray(self)
            self.overlay_window = OverlayWindow(self)
            
            # Регистрация горячих клавиш
            self._register_hotkeys()
            
            logger.info("WhisperBridge initialized successfully")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise
            
    async def start_translation_workflow(self):
        """Основной workflow перевода"""
        try:
            # 1. Захват области экрана
            area = await self.screen_capture.start_area_selection()
            if not area:
                return
                
            image = self.screen_capture.capture_area(area)
            
            # 2. OCR распознавание
            languages = self.settings_manager.get_ocr_languages()
            text = self.ocr_service.extract_text(image, languages)
            
            if not text.strip():
                self.show_notification("No text found in selected area")
                return
                
            # 3. Перевод
            source_lang = self.settings_manager.get_source_language()
            target_lang = self.settings_manager.get_target_language()
            
            translation_result = await self.translation_service.translate(
                text, source_lang, target_lang
            )
            
            # 4. Показ результата
            self.overlay_window.show_result(translation_result)
            
        except Exception as e:
            logger.error(f"Translation workflow failed: {e}")
            self.show_notification(f"Translation failed: {str(e)}")
```

#### 5.2 Оптимизация производительности
- [ ] Профилирование узких мест
- [ ] Оптимизация загрузки OCR моделей
- [ ] Кэширование часто используемых данных
- [ ] Асинхронная обработка длительных операций

**Приоритет:** Средний  
**Зависимости:** 5.1  
**Результат:** Оптимизированная производительность

## Критические точки интеграции

### 1. Инициализация сервисов
**Проблема:** Правильный порядок инициализации зависимых сервисов  
**Решение:** Использование dependency injection и четкого порядка инициализации

### 2. Обработка асинхронных операций
**Проблема:** Интеграция async/await с CustomTkinter  
**Решение:** Использование `asyncio.create_task()` и thread-safe операций

### 3. Управление ресурсами OCR
**Проблема:** Большое потребление памяти OCR моделями  
**Решение:** Ленивая загрузка и переиспользование экземпляров

### 4. Глобальные горячие клавиши
**Проблема:** Конфликты с системными горячими клавишами  
**Решение:** Валидация комбинаций и обработка ошибок регистрации

## План тестирования интеграции

### Модульные тесты
```python
# tests/test_integration/test_translation_workflow.py
class TestTranslationWorkflow:
    async def test_full_workflow(self):
        """Тест полного workflow перевода"""
        app = WhisperBridgeApp()
        await app.initialize()
        
        # Mock захват экрана
        with patch.object(app.screen_capture, 'capture_area') as mock_capture:
            mock_capture.return_value = test_image
            
            # Mock OCR
            with patch.object(app.ocr_service, 'extract_text') as mock_ocr:
                mock_ocr.return_value = "Hello world"
                
                # Mock перевод
                with patch.object(app.translation_service, 'translate') as mock_translate:
                    mock_translate.return_value = TranslationResult(...)
                    
                    # Выполнение workflow
                    await app.start_translation_workflow()
                    
                    # Проверки
                    mock_capture.assert_called_once()
                    mock_ocr.assert_called_once()
                    mock_translate.assert_called_once()
```

### Интеграционные тесты
- Тестирование взаимодействия UI и сервисов
- Тестирование обработки ошибок между компонентами
- Тестирование производительности полного workflow

### Системные тесты
- Тестирование на различных операционных системах
- Тестирование с различными разрешениями экрана
- Тестирование с различными языками OCR

## Риски и митигация

### Высокие риски

1. **Производительность OCR**
   - Риск: Медленное распознавание текста
   - Митигация: Оптимизация изображений, выбор быстрых моделей

2. **Стабильность API**
   - Риск: Сбои OpenAI API
   - Митигация: Retry логика, кэширование, fallback провайдеры

3. **Совместимость ОС**
   - Риск: Проблемы с горячими клавишами на разных ОС
   - Митигация: Тестирование на всех платформах, альтернативные методы активации

### Средние риски

1. **Потребление памяти**
   - Риск: Высокое использование RAM
   - Митигация: Профилирование, оптимизация, ленивая загрузка

2. **Безопасность API ключей**
   - Риск: Компрометация ключей
   - Митигация: Использование keyring, шифрование

## Метрики успеха интеграции

### Функциональные метрики
- [ ] Все компоненты успешно инициализируются
- [ ] Workflow перевода работает end-to-end
- [ ] UI отзывчив и не блокируется
- [ ] Горячие клавиши работают глобально

### Производительные метрики
- [ ] Время полного workflow < 5 секунд
- [ ] Потребление памяти < 300MB
- [ ] Время запуска приложения < 3 секунд
- [ ] OCR точность > 90% для четкого текста

### Качественные метрики
- [ ] Покрытие тестами > 80%
- [ ] Отсутствие критических багов
- [ ] Стабильная работа в течение 24 часов
- [ ] Корректная обработка всех типов ошибок

## Заключение

Данный план интеграции обеспечивает:
- **Поэтапную разработку** с четкими зависимостями
- **Раннее выявление проблем** через тестирование на каждом этапе
- **Управление рисками** через митигацию критических точек
- **Измеримые результаты** через метрики успеха

План готов к выполнению и может быть адаптирован в зависимости от конкретных требований и ограничений проекта.
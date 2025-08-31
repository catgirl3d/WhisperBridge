# Рекомендации по реализации WhisperBridge

## Обзор

Данный документ содержит практические рекомендации по реализации проекта WhisperBridge, включая лучшие практики, паттерны проектирования, оптимизации и решения типичных проблем.

## Общие принципы разработки

### 1. Архитектурные паттерны

#### Dependency Injection
Используйте внедрение зависимостей для слабой связанности компонентов:

```python
# services/service_container.py
class ServiceContainer:
    def __init__(self):
        self._services = {}
        self._singletons = {}
    
    def register(self, interface, implementation, singleton=True):
        self._services[interface] = {
            'implementation': implementation,
            'singleton': singleton
        }
    
    def get(self, interface):
        service_info = self._services.get(interface)
        if not service_info:
            raise ServiceNotFoundError(f"Service {interface} not registered")
        
        if service_info['singleton']:
            if interface not in self._singletons:
                self._singletons[interface] = service_info['implementation']()
            return self._singletons[interface]
        
        return service_info['implementation']()

# Использование
container = ServiceContainer()
container.register('settings', SettingsManager)
container.register('ocr', OCRService)
container.register('translation', TranslationService)
```

#### Observer Pattern для событий
Реализуйте систему событий для слабой связанности UI и бизнес-логики:

```python
# core/event_system.py
class EventSystem:
    def __init__(self):
        self._listeners = defaultdict(list)
    
    def subscribe(self, event_type: str, callback: callable):
        self._listeners[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: callable):
        if callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)
    
    def emit(self, event_type: str, data: Any = None):
        for callback in self._listeners[event_type]:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Event callback failed: {e}")

# Использование
events = EventSystem()
events.subscribe('translation_completed', ui.show_result)
events.subscribe('translation_failed', ui.show_error)
```

### 2. Управление состоянием

#### State Machine для UI состояний
```python
# core/state_machine.py
from enum import Enum

class AppState(Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    PROCESSING_OCR = "processing_ocr"
    TRANSLATING = "translating"
    SHOWING_RESULT = "showing_result"
    ERROR = "error"

class StateMachine:
    def __init__(self, initial_state: AppState):
        self.current_state = initial_state
        self.transitions = {
            AppState.IDLE: [AppState.CAPTURING],
            AppState.CAPTURING: [AppState.PROCESSING_OCR, AppState.IDLE],
            AppState.PROCESSING_OCR: [AppState.TRANSLATING, AppState.ERROR],
            AppState.TRANSLATING: [AppState.SHOWING_RESULT, AppState.ERROR],
            AppState.SHOWING_RESULT: [AppState.IDLE],
            AppState.ERROR: [AppState.IDLE]
        }
    
    def transition_to(self, new_state: AppState):
        if new_state in self.transitions[self.current_state]:
            old_state = self.current_state
            self.current_state = new_state
            logger.info(f"State transition: {old_state} -> {new_state}")
            return True
        else:
            logger.warning(f"Invalid transition: {self.current_state} -> {new_state}")
            return False
```

## Специфические рекомендации по компонентам

### 1. OCR Service

#### Оптимизация изображений для OCR
```python
def preprocess_image_for_ocr(image: Image) -> Image:
    """Предобработка изображения для улучшения OCR"""
    # Конвертация в grayscale
    if image.mode != 'L':
        image = image.convert('L')
    
    # Увеличение контраста
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)
    
    # Увеличение резкости
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.5)
    
    # Масштабирование для лучшего распознавания
    width, height = image.size
    if width < 300 or height < 100:
        scale_factor = max(300 / width, 100 / height)
        new_size = (int(width * scale_factor), int(height * scale_factor))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    
    return image
```

#### Ленивая загрузка OCR моделей
```python
class OCRService:
    def __init__(self):
        self._easyocr_readers = {}
    
    def _get_easyocr_reader(self, languages: List[str]) -> easyocr.Reader:
        lang_key = '-'.join(sorted(languages))
        if lang_key not in self._easyocr_readers:
            logger.info(f"Loading EasyOCR model for languages: {languages}")
            self._easyocr_readers[lang_key] = easyocr.Reader(
                languages,
                gpu=torch.cuda.is_available()
            )
        return self._easyocr_readers[lang_key]
```

### 2. Translation Service

#### Умное кэширование
```python
class TranslationCache:
    def __init__(self, max_size: int = 1000, ttl_hours: int = 24):
        self.cache = {}
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
    
    def _generate_key(self, text: str, source_lang: str, target_lang: str) -> str:
        # Нормализация текста для лучшего кэширования
        normalized_text = re.sub(r'\s+', ' ', text.strip().lower())
        return hashlib.md5(f"{normalized_text}:{source_lang}:{target_lang}".encode()).hexdigest()
    
    def get(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        key = self._generate_key(text, source_lang, target_lang)
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now() - entry['timestamp'] < self.ttl:
                return entry['translation']
            else:
                del self.cache[key]
        return None
    
    def set(self, text: str, source_lang: str, target_lang: str, translation: str):
        if len(self.cache) >= self.max_size:
            # Удаление самых старых записей
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        key = self._generate_key(text, source_lang, target_lang)
        self.cache[key] = {
            'translation': translation,
            'timestamp': datetime.now()
        }
```

#### Обработка длинных текстов
```python
async def translate_long_text(self, text: str, source_lang: str, target_lang: str) -> str:
    """Перевод длинных текстов с разбивкой на части"""
    max_chunk_size = 2000  # Ограничение API
    
    if len(text) <= max_chunk_size:
        return await self.translate(text, source_lang, target_lang)
    
    # Разбивка на предложения
    sentences = self._split_into_sentences(text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk + sentence) <= max_chunk_size:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Параллельный перевод частей
    tasks = [self.translate(chunk, source_lang, target_lang) for chunk in chunks]
    translated_chunks = await asyncio.gather(*tasks)
    
    return ' '.join(translated_chunks)
```

### 3. UI Components

#### Responsive Overlay Window
```python
class OverlayWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        
        # Настройка окна
        self.withdraw()  # Скрыть до позиционирования
        self.overrideredirect(True)  # Убрать рамку окна
        self.attributes('-topmost', True)  # Поверх всех окон
        self.attributes('-alpha', 0.95)  # Прозрачность
        
        self._setup_ui()
        self._setup_animations()
    
    def show_at_cursor(self, text: str):
        """Показать окно рядом с курсором"""
        # Получение позиции курсора
        x, y = pyautogui.position()
        
        # Получение размеров экрана
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Расчет размера окна на основе текста
        window_width, window_height = self._calculate_window_size(text)
        
        # Позиционирование с учетом границ экрана
        if x + window_width > screen_width:
            x = screen_width - window_width - 10
        if y + window_height > screen_height:
            y = y - window_height - 10
        
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.deiconify()
        
        # Анимация появления
        self._animate_show()
    
    def _animate_show(self):
        """Анимация появления окна"""
        self.attributes('-alpha', 0)
        self.deiconify()
        
        def fade_in(alpha=0):
            if alpha < 0.95:
                alpha += 0.05
                self.attributes('-alpha', alpha)
                self.after(20, lambda: fade_in(alpha))
        
        fade_in()
```

#### Adaptive Screen Capture Interface
```python
class CaptureOverlay(ctk.CTkToplevel):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.start_x = self.start_y = 0
        self.current_x = self.current_y = 0
        
        self._setup_fullscreen_overlay()
        self._bind_events()
    
    def _setup_fullscreen_overlay(self):
        """Настройка полноэкранного оверлея"""
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.3)
        self.configure(bg='black')
        
        # Canvas для рисования прямоугольника выделения
        self.canvas = tk.Canvas(
            self, 
            highlightthickness=0,
            bg='black'
        )
        self.canvas.pack(fill='both', expand=True)
    
    def _on_mouse_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        
    def _on_mouse_drag(self, event):
        self.current_x, self.current_y = event.x, event.y
        
        # Очистка предыдущего прямоугольника
        self.canvas.delete("selection")
        
        # Рисование нового прямоугольника
        self.canvas.create_rectangle(
            self.start_x, self.start_y,
            self.current_x, self.current_y,
            outline='red',
            width=2,
            tags="selection"
        )
    
    def _on_mouse_release(self, event):
        # Расчет области выделения
        x1, y1 = min(self.start_x, self.current_x), min(self.start_y, self.current_y)
        x2, y2 = max(self.start_x, self.current_x), max(self.start_y, self.current_y)
        
        if abs(x2 - x1) > 10 and abs(y2 - y1) > 10:  # Минимальный размер
            area = Rectangle(x1, y1, x2 - x1, y2 - y1)
            self.destroy()
            self.callback(area)
        else:
            self.destroy()
            self.callback(None)
```

### 4. Performance Optimizations

#### Асинхронная обработка
```python
class AsyncWorkflowManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.loop = asyncio.new_event_loop()
        
    async def run_ocr_async(self, image: Image, languages: List[str]) -> str:
        """Асинхронное выполнение OCR в отдельном потоке"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.ocr_service.extract_text,
            image,
            languages
        )
    
    async def parallel_processing(self, image: Image, text: str):
        """Параллельная обработка OCR и подготовка к переводу"""
        # Запуск OCR и предварительной обработки параллельно
        ocr_task = self.run_ocr_async(image, ['en', 'ru'])
        preprocessing_task = self.preprocess_for_translation(text)
        
        ocr_result, preprocessed = await asyncio.gather(
            ocr_task, 
            preprocessing_task,
            return_exceptions=True
        )
        
        return ocr_result, preprocessed
```

#### Memory Management
```python
class ResourceManager:
    def __init__(self):
        self._cleanup_tasks = []
        self._memory_threshold = 500 * 1024 * 1024  # 500MB
    
    def monitor_memory_usage(self):
        """Мониторинг использования памяти"""
        process = psutil.Process()
        memory_usage = process.memory_info().rss
        
        if memory_usage > self._memory_threshold:
            logger.warning(f"High memory usage: {memory_usage / 1024 / 1024:.1f}MB")
            self._cleanup_resources()
    
    def _cleanup_resources(self):
        """Очистка ресурсов при высоком потреблении памяти"""
        # Очистка кэша переводов
        if hasattr(self, 'translation_cache'):
            self.translation_cache.clear_old_entries()
        
        # Принудительная сборка мусора
        gc.collect()
        
        # Перезагрузка OCR моделей если необходимо
        if hasattr(self, 'ocr_service'):
            self.ocr_service.reload_models()
```

## Обработка ошибок и логирование

### Централизованная обработка ошибок
```python
# core/error_handler.py
class ErrorHandler:
    def __init__(self, event_system: EventSystem):
        self.events = event_system
        self.error_counts = defaultdict(int)
    
    def handle_error(self, error: Exception, context: str = ""):
        """Централизованная обработка ошибок"""
        error_type = type(error).__name__
        self.error_counts[error_type] += 1
        
        logger.error(f"Error in {context}: {error}", exc_info=True)
        
        # Специфическая обработка по типу ошибки
        if isinstance(error, OCRError):
            self._handle_ocr_error(error, context)
        elif isinstance(error, TranslationError):
            self._handle_translation_error(error, context)
        elif isinstance(error, APIError):
            self._handle_api_error(error, context)
        else:
            self._handle_generic_error(error, context)
    
    def _handle_ocr_error(self, error: OCRError, context: str):
        """Обработка ошибок OCR"""
        self.events.emit('ocr_error', {
            'error': str(error),
            'context': context,
            'suggestion': 'Try adjusting image quality or language settings'
        })
    
    def _handle_translation_error(self, error: TranslationError, context: str):
        """Обработка ошибок перевода"""
        if 'rate limit' in str(error).lower():
            self.events.emit('rate_limit_error', {
                'retry_after': 60,
                'message': 'API rate limit reached. Please wait.'
            })
        else:
            self.events.emit('translation_error', {
                'error': str(error),
                'context': context
            })
```

### Структурированное логирование
```python
# core/logger.py
import structlog

def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Настройка структурированного логирования"""
    
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if log_file:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Настройка стандартного логгера
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(file_handler)

# Использование
logger = structlog.get_logger()
logger.info("Translation started", user_id="123", text_length=45)
```

## Тестирование

### Фикстуры для тестирования
```python
# tests/conftest.py
@pytest.fixture
def mock_settings():
    """Mock настроек для тестов"""
    settings = MagicMock()
    settings.get_api_key.return_value = "test-api-key"
    settings.get_ocr_languages.return_value = ["en", "ru"]
    settings.get_source_language.return_value = "en"
    settings.get_target_language.return_value = "ru"
    return settings

@pytest.fixture
def sample_image():
    """Создание тестового изображения"""
    img = Image.new('RGB', (300, 100), color='white')
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Hello World", fill='black')
    return img

@pytest.fixture
async def app_instance(mock_settings):
    """Создание экземпляра приложения для тестов"""
    app = WhisperBridgeApp()
    app.settings_manager = mock_settings
    await app.initialize()
    yield app
    await app.shutdown()
```

### Интеграционные тесты
```python
# tests/test_integration.py
class TestTranslationWorkflow:
    @pytest.mark.asyncio
    async def test_complete_workflow(self, app_instance, sample_image):
        """Тест полного workflow перевода"""
        
        # Мокирование захвата экрана
        with patch.object(app_instance.screen_capture, 'capture_area') as mock_capture:
            mock_capture.return_value = sample_image
            
            # Выполнение workflow
            result = await app_instance.start_translation_workflow()
            
            # Проверки
            assert result is not None
            assert result.translated_text
            assert result.source_language
            assert result.target_language
    
    @pytest.mark.asyncio
    async def test_error_handling(self, app_instance):
        """Тест обработки ошибок"""
        
        # Мокирование ошибки OCR
        with patch.object(app_instance.ocr_service, 'extract_text') as mock_ocr:
            mock_ocr.side_effect = OCRError("OCR failed")
            
            with pytest.raises(OCRError):
                await app_instance.start_translation_workflow()
```

## Развертывание и дистрибуция

### Создание исполняемого файла
```python
# build.py
import PyInstaller.__main__

def build_executable():
    """Создание исполняемого файла с PyInstaller"""
    
    PyInstaller.__main__.run([
        'src/main.py',
        '--name=WhisperBridge',
        '--onefile',
        '--windowed',
        '--icon=assets/icons/app.ico',
        '--add-data=assets;assets',
        '--add-data=config;config',
        '--hidden-import=customtkinter',
        '--hidden-import=easyocr',
        '--hidden-import=pynput',
        '--exclude-module=tkinter.test',
        '--clean',
    ])

if __name__ == "__main__":
    build_executable()
```

### Автоматическое обновление
```python
# core/updater.py
class AutoUpdater:
    def __init__(self, current_version: str, update_url: str):
        self.current_version = current_version
        self.update_url = update_url
    
    async def check_for_updates(self) -> Optional[dict]:
        """Проверка наличия обновлений"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.update_url}/latest")
                update_info = response.json()
                
                if self._is_newer_version(update_info['version']):
                    return update_info
                    
        except Exception as e:
            logger.error(f"Update check failed: {e}")
        
        return None
    
    def _is_newer_version(self, remote_version: str) -> bool:
        """Сравнение версий"""
        from packaging import version
        return version.parse(remote_version) > version.parse(self.current_version)
```

## Мониторинг и аналитика

### Сбор метрик использования
```python
# core/analytics.py
class UsageAnalytics:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.metrics = {
            'translations_count': 0,
            'ocr_success_rate': 0,
            'average_response_time': 0,
            'error_counts': defaultdict(int)
        }
    
    def track_translation(self, duration: float, success: bool):
        """Отслеживание метрик перевода"""
        if not self.enabled:
            return
            
        self.metrics['translations_count'] += 1
        
        if success:
            # Обновление среднего времени отклика
            current_avg = self.metrics['average_response_time']
            count = self.metrics['translations_count']
            self.metrics['average_response_time'] = (
                (current_avg * (count - 1) + duration) / count
            )
    
    def track_error(self, error_type: str):
        """Отслеживание ошибок"""
        if self.enabled:
            self.metrics['error_counts'][error_type] += 1
    
    def get_report(self) -> dict:
        """Получение отчета по использованию"""
        return {
            'total_translations': self.metrics['translations_count'],
            'average_response_time': round(self.metrics['average_response_time'], 2),
            'error_summary': dict(self.metrics['error_counts']),
            'uptime': self._get_uptime()
        }
```

## Заключение

Данные рекомендации обеспечивают:

1. **Качественную архитектуру** - использование проверенных паттернов
2. **Высокую производительность** - оптимизации и асинхронность
3. **Надежность** - комплексная обработка ошибок
4. **Тестируемость** - структура, удобная для тестирования
5. **Поддерживаемость** - чистый код и документация
6. **Масштабируемость** - готовность к расширению функциональности

Следование этим рекомендациям поможет создать качественное, стабильное и производительное приложение WhisperBridge.
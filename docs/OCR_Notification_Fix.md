# Исправление проблемы с уведомлением "OCR service is ready"

## Проблема
В приложении не показывалось уведомление "OCR service is ready" после завершения инициализации OCR-сервиса, хотя другие уведомления (например, "Canceled") работали корректно.

## Причина проблемы
- **OCR инициализация происходит в фоновом потоке** (daemon thread) для загрузки моделей EasyOCR (~12 секунд)
- **Callback `on_complete()` выполняется в том же фоновом потоке**
- **Старый код использовал `QTimer.singleShot(0, lambda: self.ocr_ready_signal.emit())`**
- **Проблема**: `QTimer.singleShot` требует Qt event loop в текущем потоке, но фоновый поток его не имеет
- **Результат**: Сигнал не испускается → слот не вызывается → уведомление не показывается

## Решение
Заменить `QTimer.singleShot` на прямой `emit()` сигнала:

**Файл:** `src/whisperbridge/ui_qt/app.py`  
**Метод:** `_initialize_ocr_service()`

**Было:**
```python
def on_complete():
    QTimer.singleShot(0, lambda: self.ocr_ready_signal.emit())
```

**Стало:**
```python
def on_complete():
    self.ocr_ready_signal.emit()
```

## Почему это работает
- **Qt signals thread-safe по дизайну** - можно безопасно вызывать `.emit()` из любого потока
- **Автоматический queued connection** - Qt автоматически использует `Qt.QueuedConnection` для межпотоковой коммуникации
- **Маршалинг в главный поток** - вызов слота помещается в event loop главного потока
- **Цепочка выполнения**: Фоновый поток → `emit()` → Qt event system → Главный поток → `_on_ocr_service_ready()` → `handle_ocr_service_ready()` → Уведомление


## Дополнительная информация
- **Почему "Canceled" работал**: Сигнал испускается из главного Qt потока, где есть event loop
- **Qt signals vs QTimer**: Signals изначально предназначены для межпотоковой коммуникации, QTimer был избыточным
- **Безопасность**: Прямой `emit()` безопасен и не требует дополнительных проверок

**Дата исправления:** 2025-10-03  
**Файлы изменены:** `src/whisperbridge/ui_qt/app.py`
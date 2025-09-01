Анализ текущего приложения и план перехода на PySide6

## СТАТУС ВЫПОЛНЕНИЯ МИГРАЦИИ

✅ **Фаза 0 — Подготовка** (ЗАВЕРШЕНА)
✅ **Фаза 1 — Бутстрап Qt-приложения** (ЗАВЕРШЕНА)
⏳ **Фаза 2 — Тема и переключение тем** (ОЖИДАЕТ)
⏳ **Фаза 3 — Главное окно и поведение закрытия/трея** (ОЖИДАЕТ)
⏳ **Фаза 4 — Оверлеи (критическая)** (ОЖИДАЕТ)
⏳ **Фаза 5 — Многопоточность/асинхронщина** (ОЖИДАЕТ)
⏳ **Фаза 6 — Финальный паритет функционала** (ОЖИДАЕТ)
⏳ **Фаза 7 — Чистка и переключение по умолчанию** (ОЖИДАЕТ)

Ключевые зависимости от Tkinter/CustomTkinter в вашем коде
- Инициализация и цикл событий:
  - Tk создаётся и управляется в [class WhisperBridgeApp()](src/whisperbridge/ui/app.py:27) → [def __init__()](src/whisperbridge/ui/app.py:30) через ctk.CTk в [def __init__()](src/whisperbridge/ui/app.py:37), цикл — [def run()](src/whisperbridge/ui/app.py:816) (root.mainloop()).
- Темизация/переключение тем:
  - CustomTkinter appearance mode в [def __init__()](src/whisperbridge/ui/app.py:33-35), переключение на F12: [def _bind_global_events()](src/whisperbridge/ui/app.py:190-194) + [def _on_f12_pressed()](src/whisperbridge/ui/app.py:284) → [def _toggle_theme()](src/whisperbridge/ui/app.py:288-294), и апдейт темы в [def update_theme()](src/whisperbridge/ui/app.py:760-778).
- Отрисовка оверлеев:
  - Через overlay_service, но управление временем и проверками завязано на Tk: [def show_overlay_window()](src/whisperbridge/ui/app.py:704-750) + root.after проверки [def show_overlay_window()](src/whisperbridge/ui/app.py:739-744), детальная верификация окна — [def _verify_overlay_visibility()](src/whisperbridge/ui/app.py:969-1095).
- Прозрачность/всегда поверх:
  - Tk-атрибуты окон (-alpha, -topmost) в [def update_window_opacity()](src/whisperbridge/ui/app.py:780-814) и [def _verify_overlay_visibility()](src/whisperbridge/ui/app.py:1000-1037).
- Многопоточность и интеграция с UI:
  - Фоновые thread’ы: [def _on_translate_hotkey()](src/whisperbridge/ui/app.py:296-309) → [def _capture_and_process()](src/whisperbridge/ui/app.py:310-341).
  - Безопасная доставка в UI через root.after: [def _process_ocr_and_translate()](src/whisperbridge/ui/app.py:342-419) (after на 351, 402, 417), таймеры threading.Timer на [def _process_ocr_and_translate()](src/whisperbridge/ui/app.py:409-413).
- Управление главным окном/треем/закрытием:
  - Перехват закрытия окна и сворачивание в трей: [def _on_window_close()](src/whisperbridge/ui/app.py:662-675), [def hide_main_window()](src/whisperbridge/ui/app.py:946-960), System Tray обёртка через TrayService вызывается по месту.
- Завершение:
  - Отмена отложенных коллбеков root.after_cancel и корректное уничтожение окон в [def shutdown()](src/whisperbridge/ui/app.py:831-908).
- Дополнительно:
  - Асинхронные пути OCR/перевода существуют (async def), но UI-триггеры всё равно через Tk after: [async def _handle_capture_result()](src/whisperbridge/ui/app.py:420-449), [async def _process_ocr_async()](src/whisperbridge/ui/app.py:463-483), [async def _handle_ocr_result()](src/whisperbridge/ui/app.py:484-533), [async def _process_translation_async()](src/whisperbridge/ui/app.py:534-556), [async def _handle_translation_result()](src/whisperbridge/ui/app.py:557-594).

Выводы и точки риска
- Главная боль Tkinter (и CustomTkinter) — доставка событий в UI из фоновых потоков + непредсказуемость при сложных оверлеях. Вы используете root.after и threading.Timer, поддерживая список pending_callbacks и их отмену на выключении — это сложная и хрупкая схема.
- Для надёжного оверлея и многопоточности подход Qt (PySide6) с сигналами/слотами, QThread/QThreadPool/QTimer и QSystemTrayIcon снимет большую часть костылей и снизит гонки условий.
- Замена потребует рефактора слоёв: окно(а), оверлей, тема/стили, трей и замена root.after → QTimer.singleShot/сигналы.

Карта соответствий Tk → Qt (PySide6)
- CTk root/окна → QApplication + QWidget/QMainWindow. Цикл: app.exec().
- root.after(...) → QTimer.singleShot(...) или сигналы из QThread/QRunnable.
- threading.Timer → QTimer в главном потоке или QThread+сигнал.
- attributes("-alpha") → QWidget.setWindowOpacity(float) и/или Qt.WA_TranslucentBackground.
- attributes("-topmost")/lift → setWindowFlag(Qt.WindowStaysOnTopHint), raise_(), activateWindow().
- withdraw/deiconify → hide()/show()/showNormal().
- bind("<F12>") → QShortcut(QKeySequence("F12"), widget).
- WM_DELETE_WINDOW → переопределение closeEvent и логика «сворачивания в трей».
- TrayService → QSystemTrayIcon с меню и showMessage.
- Проверка существования/видимости (winfo_*) → QWidget.isVisible()/isWindowModified()/windowHandle()->isExposed(), geometry(), pos(), size().
- pending_callbacks → слоты/сигналы и QTimer; очистка происходит автоматически по жизненному циклу QObject, явные списки чаще не нужны.

План миграции (итеративно, с флагом бекенда)
Фаза 0 — Подготовка
- Добавить PySide6 в зависимости (requirements.txt).
- Ввести фичефлаг UI_BACKEND = "tk" | "qt" в конфиге, чтобы переключать реализацию без удаления Tk.
- Сохранить текущие сервисы (OCR, перевод, hotkey) без изменений; изолировать только слой UI.

✅ ВЫПОЛНЕНО:
- [pyproject.toml](pyproject.toml) — добавлен PySide6>=6.6.0
- [requirements.txt](requirements.txt) — добавлен pydantic-settings
- [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py) — добавлен ui_backend флаг
- [src/whisperbridge/core/settings_manager.py](src/whisperbridge/core/settings_manager.py) — добавлена миграция

Фаза 1 — Бутстрап Qt-приложения
- Создать оболочку Qt-приложения (новый пакет, например ui_qt/):
  - QtApp класс (аналог [class WhisperBridgeApp()](src/whisperbridge/ui/app.py:27)), предоставляющий те же публичные методы: show_main_window(), show_overlay_window(), hide_main_window(), update_window_opacity(), update_theme(), update_tray_status(), shutdown().
  - Запуск QApplication и обработка цикла (эквивалент [def run()](src/whisperbridge/ui/app.py:816)).
- При UI_BACKEND="qt" маршрутизировать [def init_app()](src/whisperbridge/ui/app.py:1112) на QtApp (временный роутер).

✅ ВЫПОЛНЕНО:
- [src/whisperbridge/ui_qt/](src/whisperbridge/ui_qt/) — новый пакет Qt UI
- [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py) — QtApp класс
- [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py) — главное окно Qt
- [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py) — окно оверлея Qt
- [src/whisperbridge/ui/__init__.py](src/whisperbridge/ui/__init__.py) — маршрутизация UI
- [src/main.py](src/main.py) — обновлена точка входа

Критерии приёмки фазы 1:
- Приложение стартует с пустым окном Qt и корректно завершается.

### Реализованная архитектура Dual UI Backend
- Система маршрутизации по флагу ui_backend работает корректно
- UI_BACKEND=ctk → CustomTkinter (по умолчанию)
- UI_BACKEND=qt → PySide6 Qt
- Все существующие сервисы сохранены без изменений
- Протестирована совместимость обоих бэкендов

Фаза 2 — Тема и переключение тем
- Реализовать управление темой: стиль Fusion + палитры для dark/light; подключить QShortcut для F12 (замена [def _bind_global_events()](src/whisperbridge/ui/app.py:190-194), [def _toggle_theme()](src/whisperbridge/ui/app.py:288-294)).
- Восстановить соответствие settings.theme и переключения.

Критерии:
- Темы переключаются горячей клавишей и через публичный метод update_theme() (замена [def update_theme()](src/whisperbridge/ui/app.py:760-778)).

Фаза 3 — Главное окно и поведение закрытия/трея
- Реализовать главное окно (QMainWindow или QWidget) с обработкой closeEvent «свернуть в трей» (замена [def _on_window_close()](src/whisperbridge/ui/app.py:662-675), [def hide_main_window()](src/whisperbridge/ui/app.py:946-960)).
- Перенести системный трей на QSystemTrayIcon (замена логики TrayService вызовов, совместимость API show_notification/update_status_icon).

Критерии:
- Кнопка закрытия скрывает окно в трей, иконка отражает статусы (active/error/loading) — эквивалент [def update_tray_status()](src/whisperbridge/ui/app.py:935-945), уведомления работают — эквивалент [def show_tray_notification()](src/whisperbridge/ui/app.py:925-934).

Фаза 4 — Оверлеи (критическая)
- Реализовать OverlayWindow на Qt: frameless, always-on-top, опционально полупрозрачный фон (Qt.FramelessWindowHint, Qt.WA_TranslucentBackground, Qt.WindowStaysOnTopHint).
- Перенести API overlay_service.show_overlay()/hide_overlay()/get_overlay() под Qt-окна.
- Заменить root.after-проверки видимости на QTimer.singleShot и прямые проверки isVisible()/raise_() (замена [def show_overlay_window()](src/whisperbridge/ui/app.py:704-750) и [def _verify_overlay_visibility()](src/whisperbridge/ui/app.py:969-1095)).
- Перенести управление непрозрачностью (замена [def update_window_opacity()](src/whisperbridge/ui/app.py:780-814)).

Критерии:
- Оверлей стабильно показывается/скрывается, сохраняет topmost, прозрачность регулируется.

Фаза 5 — Многопоточность/асинхронщина
- Убрать root.after/Threading.Timer в пути OCR/перевода:
  - Заменить вызовы root.after на QTimer.singleShot или сигналы от воркеров (замены точек: [def _process_ocr_and_translate()](src/whisperbridge/ui/app.py:351), [def _process_ocr_and_translate()](src/whisperbridge/ui/app.py:402), [def _process_ocr_and_translate()](src/whisperbridge/ui/app.py:417)).
  - Фоновые задачи запускать через QThreadPool/QRunnable или QThread; UI-обновления только по сигналам в главный поток.
- Триггер горячей клавиши начинает фоновую работу (аналог [def _on_translate_hotkey()](src/whisperbridge/ui/app.py:296-309)), по завершении приходит сигнал в UI, вызывающий show_overlay_window.

Критерии:
- На горячую клавишу запускается захват/обработка; UI не зависает; оверлей показывается по сигналу.

Фаза 6 — Финальный паритет функционала
- Портировать в Qt все используемые фичи главного окна из [src/whisperbridge/ui/main_window.py](src/whisperbridge/ui/main_window.py).
- Портировать селекторы/выделение если они есть в [src/whisperbridge/ui/selection_overlay.py](src/whisperbridge/ui/selection_overlay.py).
- Перенести и выровнять overlay_service под Qt: [src/whisperbridge/services/overlay_service.py](src/whisperbridge/services/overlay_service.py).
- Убрать временные pending_callbacks и связанные с ними пути в [def shutdown()](src/whisperbridge/ui/app.py:880-888).

Критерии:
- Полный паритет: темы, трей, горячие клавиши, оверлеи, прозрачность, закрытие/сворачивание, уведомления.

Фаза 7 — Чистка и переключение по умолчанию
- Переключить UI_BACKEND по умолчанию на "qt".
- Удалить зависимости от CustomTkinter, когда Tk-ветка больше не нужна.
- Регрессионные тесты GUI (по возможности автотесты smoke) и сборка для Windows.

Диаграмма новой потоковой модели (Qt)
```mermaid
flowchart LR
  A[HotkeyService] --> B[Worker (QThreadPool/QRunnable)]
  B -- Signal(result) --> C[Main UI (Qt)]
  C --> D[Overlay Window (Qt)]
  C --> E[Tray Icon (QSystemTrayIcon)]
  C <-- QShortcut/F12 --> C
```

Единообразный интерфейс (какие методы должен предоставить Qt-слой)
- Аналоги публичных методов класса Tk-приложения:
  - show_main_window() — замена логики [def show_main_window()](src/whisperbridge/ui/app.py:676-703)
  - show_overlay_window(original, translated, position, overlay_id) — замена [def show_overlay_window()](src/whisperbridge/ui/app.py:704-750)
  - hide_overlay_window(overlay_id) — замена [def hide_overlay_window()](src/whisperbridge/ui/app.py:751-759)
  - update_theme(theme) — замена [def update_theme()](src/whisperbridge/ui/app.py:760-778)
  - update_window_opacity(opacity) — замена [def update_window_opacity()](src/whisperbridge/ui/app.py:780-814)
  - update_tray_status(is_active, has_error, is_loading) — замена [def update_tray_status()](src/whisperbridge/ui/app.py:935-945)
  - show_tray_notification(title, message) — замена [def show_tray_notification()](src/whisperbridge/ui/app.py:925-934)
  - run() — замена [def run()](src/whisperbridge/ui/app.py:816-829)
  - shutdown() — замена [def shutdown()](src/whisperbridge/ui/app.py:831-908)

Риски и примечания
- Global hotkeys: остаются во внешнем сервисе; убедиться, что их потоки не трогают UI напрямую — только сигналы в Qt.
- Прозрачность и кликабельность оверлея: в Qt можно добиться «клика сквозь» атрибутами окна; при необходимости разделить окно контента и «маску» для интерактивных областей.
- DPI/HiDPI: включить AA_EnableHighDpiScaling/UseHighDpiPixmaps, протестировать геометрию оверлеев.
- Уведомления: QSystemTrayIcon.showMessage работает стабильно, но на Windows иногда требует активную иконку трея.

Итоговая задача (backlog checklist)
- ✅ Добавить PySide6 и флаг UI_BACKEND (qt/tk) в конфиг.
- ✅ Ввести ui_qt с QtApp, пустым окном и app.exec() маршрутом через [def init_app()](src/whisperbridge/ui/app.py:1112).
- ⏳ Реализовать тему и F12 через QShortcut; сопоставить settings.theme.
- Перенести трей на QSystemTrayIcon, поведение closeEvent «в трей».
- Реализовать Qt-оверлей (frameless, topmost, opacity), адаптировать overlay_service под Qt.
- Заменить root.after/Timer на QTimer/сигналы в пути OCR/перевода (точки: [def _process_ocr_and_translate()](src/whisperbridge/ui/app.py:342), [def show_overlay_window()](src/whisperbridge/ui/app.py:739-744)).
- Удалить pending_callbacks и Tk-зависимости из [def shutdown()](src/whisperbridge/ui/app.py:880-888), переключить UI_BACKEND по умолчанию на "qt".
- Очистка: удалить CustomTkinter и Tk-ветку после стабилизации.

## Текущее состояние проекта
- ✅ Фазы 0 и 1 миграции успешно завершены
- ✅ Создана dual UI backend архитектура с поддержкой CustomTkinter и PySide6
- ✅ Система переключения UI бэкендов работает и протестирована
- ✅ Все существующие сервисы сохранены и интегрированы
- 🎯 Готов к выполнению фаз 2-7 для полного перехода на Qt
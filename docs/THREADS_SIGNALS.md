# Руководство по потокам и сигналам

Короткое практическое руководство по работе с Qt/PySide6 в проекте WhisperBridge.
Цель — избегать ошибок типа "QObject::setParent: Cannot set parent, new parent is in a different thread".

1) Главное правило
- Все объекты Qt (виджеты, окна, диалоги и т.д.) должны создаваться и модифицироваться только в главном (GUI) потоке.

2) Как реагировать на события из фоновых потоков (hotkeys, сетевые и т.д.)
- Не вызывать методы UI напрямую из рабочих потоков.
- Использовать Qt сигналы/слоты для передачи команд в главный поток.
  Пример: добавлены сигналы в [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:196).

3) Ленивая (отложенная) инициализация UI
- Создавать окна и overlay только внутри главного потока, при первом обращении.
- В проекте реализовано в [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:110).

4) Обработка глобальных хоткеев
- HotkeyService использует фоновый executor (ThreadPoolExecutor). Не вызывать UI из его worker-потоков.
- При обработке хоткея эмитировать сигнал, например из [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:595), чтобы слот в главном потоке сделал UI-действие.
- См. логику регистрации в [`src/whisperbridge/services/hotkey_service.py`](src/whisperbridge/services/hotkey_service.py:142).

5) Диагностика и проверки потока
- Добавлять логирование текущего потока в обработчики хоткеев и при создании виджетов.
- Проверять поток перед выполнением UI-операций:
  QThread.currentThread() == QApplication.instance().thread()
- В проекте примеры проверок в [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:151).

5.1) Декоратор @main_thread_only
- Для автоматической проверки потока используется декоратор `@main_thread_only` из [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:28).
- Декоратор проверяет, что метод вызывается только из главного Qt потока.
- Если метод вызывается из фонового потока, декоратор блокирует выполнение и логирует ошибку.
- Пример использования: `@main_thread_only` применяется ко всем методам UIService, изменяющим UI.

6) Взаимодействие с QThread и QObject
- Перемещать QObject в QThread только если есть точное понимание ownership и lifecycle.
- Для worker-объектов (QObject с сигналами) использовать moveToThread и связывать сигналы со слотами в главном потоке.
- Пример безопасной организации worker в [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:518).

7) Tray/OS интеграция
- Действия из системного трея тоже должны попадать в главный поток через сигналы; избегать вызовов UI из callback OS.
- Трей-менеджер — [`src/whisperbridge/ui_qt/tray.py`](src/whisperbridge/ui_qt/tray.py:1).

8) Частые ошибки и как их обнаружить
- "QObject::setParent: Cannot set parent..." — создание/перемещение виджета из фонового потока.
- "Widgets not responding / freeze" — блокировка главного потока длительной синхронной операцией.
- Логиррвать стек и поток в момент ошибки.

9) Быстрые рецепты
- Нужно показать окно из background: emit signal -> слот создает/показывает окно.
- Нужна асинхронная работа: выполнять I/O в asyncio или ThreadPool, возвращать результат через signal.

10) Паттерн QTimer.singleShot для вызова из фоновых потоков
- `QTimer.singleShot(0, callback)` — это простой способ выполнить код в главном Qt потоке из фонового потока.
- Таймер с задержкой 0 мс помещает callback в очередь event loop главного потока.
- Пример использования в [`src/whisperbridge/services/notification_service.py`](src/whisperbridge/services/notification_service.py:78):
  ```python
  if app and QThread.currentThread() != app.thread():
      QTimer.singleShot(0, lambda: self.show(message, title, notification_type, duration))
      return
  ```

10.1) Когда использовать QTimer.singleShot, а когда — сигналы?
- **Использовать QTimer.singleShot для:**
  - Одноразовых, простых действий (fire-and-forget)
  - Утилитарных сервисов без четкой ownership структуры
  - Когда вызывающий код не владеет получателем
  - Пример: NotificationService — сервис может вызываться из любого места

- **Использовать сигналы для:**
  - Регулярного взаимодействия между конкретными объектами
  - Отношений 1-to-many (один сигнал, несколько слотов)
  - Когда данные передаются в обе стороны
  - Когда есть четкая структура владения (parent-child, controller-worker)
  - Пример: worker -> UI controller (как в хоткеях)

Необходимо поддерживать это руководство — добавлять примеры при новых паттернах
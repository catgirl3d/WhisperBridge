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
- Создавайте окна и overlay только внутри главного потока, при первом обращении.
- В проекте реализовано в [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:110).

4) Обработка глобальных хоткеев
- HotkeyService использует фоновый executor (ThreadPoolExecutor). Не вызывать UI из его worker-потоков.
- При обработке хоткея эмитируйте сигнал, например из [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:595), чтобы слот в главном потоке сделал UI-действие.
- См. логику регистрации в [`src/whisperbridge/services/hotkey_service.py`](src/whisperbridge/services/hotkey_service.py:142).

5) Диагностика и проверки потока
- Добавляйте логирование текущего потока в обработчики хоткеев и при создании виджетов.
- Проверяйте поток перед выполнением UI-операций:
  QThread.currentThread() == QApplication.instance().thread()
- В проекте примеры проверок в [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:151).

6) Взаимодействие с QThread и QObject
- Перемещайте QObject в QThread только если вы точно понимаете ownership и lifecycle.
- Для worker-объектов (QObject с сигналами) используйте moveToThread и связывайте сигналы со слотами в главном потоке.
- Пример безопасной организации worker в [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:518).

7) Tray/OS интеграция
- Действия из системного трея тоже должны попадать в главный поток через сигналы; избегайте вызовов UI из callback OS.
- Трей-менеджер — [`src/whisperbridge/ui_qt/tray.py`](src/whisperbridge/ui_qt/tray.py:1).

8) Частые ошибки и как их обнаружить
- "QObject::setParent: Cannot set parent..." — создание/перемещение виджета из фонового потока.
- "Widgets not responding / freeze" — блокировка главного потока длительной синхронной операцией.
- Логируйте стек и поток в момент ошибки.

9) Быстрые рецепты
- Нужен показать окно из background: emit signal -> слот создает/показывает окно.
- Нужна асинхронная работа: выполняйте I/O в asyncio или ThreadPool, возвращайте результат через signal.

Поддерживайте это руководство — добавляйте примеры при новых паттернах.
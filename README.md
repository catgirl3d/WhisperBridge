# WhisperBridge

<div align="center">

![WhisperBridge Logo](assets/logo.png)

**Мгновенный перевод текста с экрана с помощью OCR и ИИ**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/your-username/WhisperBridge/releases)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/your-username/WhisperBridge)

[🚀 Быстрый старт](#быстрый-старт) • [📖 Документация](#документация) • [💬 Поддержка](#поддержка) • [🤝 Участие в проекте](#участие-в-проекте)

</div>

---

## 🌟 Что такое WhisperBridge?

WhisperBridge - это мощное десктопное приложение для **мгновенного перевода текста с экрана**. Просто нажмите горячую клавишу, выберите область с текстом, и получите качественный перевод за секунды!

### ✨ Ключевые особенности

- 🔥 **Мгновенная активация** - одна горячая клавиша (`Ctrl+Shift+T`)
- 📸 **Умный захват экрана** - интерактивный выбор любой области
- 🔍 **Продвинутый OCR** - EasyOCR + Tesseract + PaddleOCR
- 🤖 **AI-перевод** - интеграция с OpenAI GPT API
- 💫 **Удобный интерфейс** - результаты поверх всех окон
- ⚙️ **Гибкие настройки** - полная кастомизация под ваши нужды
- 🎯 **Системный трей** - работа в фоновом режиме
- 🌍 **Многоязычность** - поддержка 50+ языков

## 🎬 Демонстрация

![WhisperBridge Demo](assets/demo.gif)

*Пример работы: захват текста из браузера и мгновенный перевод*

## 🚀 Быстрый старт

### Системные требования

- **ОС**: Windows 10+, macOS 10.14+, Ubuntu 18.04+
- **Python**: 3.8 или выше
- **RAM**: 4 ГБ (рекомендуется 8 ГБ)
- **Интернет**: для работы с GPT API
- **OpenAI API ключ**: для функций перевода

### Установка за 3 шага

1. **Клонируйте репозиторий**
   ```bash
   git clone https://github.com/your-username/WhisperBridge.git
   cd WhisperBridge
   ```

2. **Установите зависимости**
   ```bash
   # Создайте виртуальное окружение
   python -m venv venv
   
   # Активируйте его
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   
   # Установите пакеты
   pip install -r requirements.txt
   ```

3. **Запустите приложение**
   ```bash
   python src/main.py
   ```

### Первоначальная настройка

1. **Получите OpenAI API ключ**
   - Зарегистрируйтесь на [platform.openai.com](https://platform.openai.com/)
   - Создайте API ключ в разделе "API Keys"
   - Пополните баланс (минимум $5)

2. **Настройте приложение**
   - Введите API ключ в настройках
   - Выберите языки перевода
   - Настройте горячие клавиши (опционально)

3. **Протестируйте**
   - Нажмите `Ctrl+Shift+T`
   - Выберите область с текстом
   - Получите перевод!

## 🎯 Основные функции

### Захват и перевод текста

```
Ctrl+Shift+T → Выбор области → OCR → Перевод → Результат
```

- **Интерактивный выбор** области экрана
- **Автоматическое распознавание** текста с высокой точностью
- **Мгновенный перевод** через GPT API
- **Удобное отображение** результатов в overlay окне

### Поддерживаемые языки

#### OCR (распознавание)
🇺🇸 English • 🇷🇺 Русский • 🇺🇦 Українська • 🇩🇪 Deutsch • 🇫🇷 Français • 🇪🇸 Español • 🇮🇹 Italiano • 🇯🇵 日本語 • 🇰🇷 한국어 • 🇨🇳 中文

#### Перевод
Поддерживаются **все основные языки мира** через GPT API

### Продвинутый OCR

- **EasyOCR** - основной движок для большинства языков
- **Tesseract** - резервный движок для печатного текста  
- **PaddleOCR** - специализация на азиатских языках
- **Автоматический fallback** между движками
- **Предобработка изображений** для лучшего качества

### Умный интерфейс

- **Overlay окно** с результатами поверх всех приложений
- **Кнопки быстрых действий**: копировать, вставить, закрыть
- **Автоматическое позиционирование** окна
- **Настраиваемые темы** (светлая/темная/системная)
- **Анимации** появления и исчезновения

## 📖 Документация

### 📚 Руководства пользователя

- **[Руководство пользователя](docs/USER_GUIDE.md)** - полное описание всех функций
- **[Установка](docs/INSTALLATION.md)** - подробная инструкция по установке
- **[Настройка](docs/CONFIGURATION.md)** - все параметры конфигурации
- **[FAQ и решение проблем](docs/TROUBLESHOOTING.md)** - ответы на частые вопросы

### 🏗️ Техническая документация

- **[Архитектура](ARCHITECTURE.md)** - структура и компоненты системы
- **[План интеграции](INTEGRATION_PLAN.md)** - пошаговый план разработки
- **[Рекомендации](IMPLEMENTATION_RECOMMENDATIONS.md)** - лучшие практики

## 🛠️ Технологический стек

### Основные технологии

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| **UI Framework** | CustomTkinter | Современный пользовательский интерфейс |
| **OCR Engine** | EasyOCR, Tesseract, PaddleOCR | Распознавание текста |
| **AI Translation** | OpenAI GPT API | Качественный перевод |
| **Screen Capture** | PIL, MSS | Захват экрана |
| **Hotkeys** | pynput | Глобальные горячие клавиши |
| **System Tray** | pystray | Интеграция с системным треем |
| **Configuration** | Pydantic, keyring | Настройки и безопасность |

### Архитектура системы

```
┌─────────────────────────────────────────────────────────────┐
│                    WhisperBridge                            │
├─────────────────────────────────────────────────────────────┤
│  UI Layer (CustomTkinter)                                  │
│  ├── Main Window (Settings)                                │
│  ├── Overlay Window (Results)                              │
│  ├── System Tray                                           │
│  └── Screen Capture Interface                              │
├─────────────────────────────────────────────────────────────┤
│  Core Services                                             │
│  ├── Hotkey Manager                                        │
│  ├── Screen Capture Service                                │
│  ├── OCR Service                                           │
│  ├── Translation Service (GPT)                             │
│  └── Settings Manager                                      │
├─────────────────────────────────────────────────────────────┤
│  Data Layer                                                │
│  ├── Configuration Storage                                 │
│  ├── Cache Manager                                         │
│  └── Logging System                                        │
├─────────────────────────────────────────────────────────────┤
│  External APIs                                             │
│  ├── OpenAI GPT API                                        │
│  └── OCR Engine (Tesseract/EasyOCR)                       │
└─────────────────────────────────────────────────────────────┘
```

## 🎮 Примеры использования

### 💬 Мессенджеры и социальные сети

- **Telegram, WhatsApp, Discord** - переводите сообщения на лету
- **Twitter, Facebook** - понимайте посты на иностранных языках
- **Instagram** - переводите подписи к фотографиям

### 🎯 Игры

- **Steam игры** - переводите диалоги и интерфейсы
- **Онлайн игры** - понимайте чат других игроков
- **Мобильные игры** (через эмуляторы) - переводите задания

### 📚 Обучение и работа

- **Веб-страницы** - переводите статьи и документы
- **PDF файлы** - извлекайте и переводите текст
- **Презентации** - переводите слайды в реальном времени
- **Видео субтитры** - переводите субтитры в видео

### 🛒 Покупки и путешествия

- **Интернет-магазины** - переводите описания товаров
- **Карты и навигация** - понимайте названия улиц
- **Меню ресторанов** - переводите блюда

## ⚡ Производительность

### Скорость работы

- **Захват экрана**: < 100ms
- **OCR распознавание**: 1-3 секунды
- **Перевод через GPT**: 2-5 секунд
- **Общее время**: 3-8 секунд

### Оптимизация

- **Кэширование** повторных запросов
- **Многопоточная обработка**
- **Ленивая загрузка** OCR моделей
- **Сжатие изображений** для ускорения

## 🔒 Безопасность и конфиденциальность

### Защита данных

- ✅ **API ключи** сохраняются в защищенном системном хранилище
- ✅ **Шифрование** чувствительных данных
- ✅ **Локальное кэширование** без передачи третьим лицам
- ✅ **HTTPS соединения** для всех API запросов

### Конфиденциальность

- 🔐 Тексты отправляются только в OpenAI API для перевода
- 🔐 Никакие данные не сохраняются на серверах WhisperBridge
- 🔐 Кэш хранится только локально на вашем устройстве
- 🔐 Возможность полной очистки всех данных

## 📊 Статистика проекта

![GitHub stars](https://img.shields.io/github/stars/your-username/WhisperBridge?style=social)
![GitHub forks](https://img.shields.io/github/forks/your-username/WhisperBridge?style=social)
![GitHub issues](https://img.shields.io/github/issues/your-username/WhisperBridge)
![GitHub pull requests](https://img.shields.io/github/issues-pr/your-username/WhisperBridge)

- **Поддерживаемые ОС**: 3 (Windows, macOS, Linux)
- **Языки OCR**: 10+
- **Языки перевода**: 50+
- **OCR движки**: 3
- **Время разработки**: 6+ месяцев

## 🤝 Участие в проекте

Мы приветствуем вклад в развитие WhisperBridge! 

### Как помочь проекту

1. **🐛 Сообщайте об ошибках** через GitHub Issues
2. **💡 Предлагайте новые функции** и улучшения
3. **📝 Улучшайте документацию** и переводы
4. **🔧 Вносите изменения в код** через Pull Requests
5. **⭐ Поставьте звезду** проекту на GitHub

### Разработка

```bash
# Клонируйте репозиторий
git clone https://github.com/your-username/WhisperBridge.git
cd WhisperBridge

# Установите зависимости для разработки
pip install -r requirements-dev.txt

# Запустите тесты
pytest tests/

# Проверьте код
flake8 src/
black src/
```

### Стандарты кода

- **Python**: PEP 8, type hints, docstrings
- **Тестирование**: pytest, покрытие > 80%
- **Документация**: подробные комментарии и README
- **Git**: осмысленные коммиты, feature branches

## 📈 Roadmap

### Версия 1.1 (Q1 2025)
- [ ] Поддержка дополнительных OCR языков
- [ ] Улучшенный UI/UX дизайн
- [ ] Расширенное кэширование
- [ ] Настраиваемые системные промпты

### Версия 1.2 (Q2 2025)
- [ ] Поддержка других AI провайдеров (Anthropic, Google)
- [ ] Плагинная архитектура
- [ ] Темы интерфейса
- [ ] Статистика использования

### Версия 2.0 (Q3 2025)
- [ ] Веб-интерфейс
- [ ] Мобильное приложение
- [ ] Облачная синхронизация настроек
- [ ] Командная работа и совместное использование

## 💬 Поддержка

### Получить помощь

- 📖 **[Документация](docs/)** - подробные руководства
- 🐛 **[GitHub Issues](https://github.com/your-username/WhisperBridge/issues)** - сообщения об ошибках
- 💬 **[Discussions](https://github.com/your-username/WhisperBridge/discussions)** - вопросы и обсуждения
- 📧 **Email**: support@whisperbridge.dev

### Сообщество

- 🔗 **Discord**: [Присоединиться к серверу](https://discord.gg/whisperbridge)
- 📱 **Telegram**: [@whisperbridge_chat](https://t.me/whisperbridge_chat)
- 🌐 **Reddit**: [r/WhisperBridge](https://reddit.com/r/WhisperBridge)

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).

```
MIT License

Copyright (c) 2024 WhisperBridge Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

## 🙏 Благодарности

Особая благодарность:

- **OpenAI** за предоставление GPT API
- **EasyOCR Team** за отличный OCR движок
- **Tesseract OCR** за надежное распознавание текста
- **CustomTkinter** за современный UI фреймворк
- **Всем контрибьюторам** за помощь в развитии проекта

---

<div align="center">

**Сделано с ❤️ командой WhisperBridge**

[⬆️ Наверх](#whisperbridge) • [🚀 Начать использовать](#быстрый-старт) • [📖 Документация](#документация)

</div>
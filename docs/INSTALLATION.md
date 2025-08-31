# Руководство по установке WhisperBridge

## Содержание

1. [Системные требования](#системные-требования)
2. [Подготовка к установке](#подготовка-к-установке)
3. [Установка Python](#установка-python)
4. [Установка приложения](#установка-приложения)
5. [Установка зависимостей](#установка-зависимостей)
6. [Настройка API ключей](#настройка-api-ключей)
7. [Первый запуск](#первый-запуск)
8. [Решение проблем установки](#решение-проблем-установки)
9. [Обновление приложения](#обновление-приложения)

## Системные требования

### Минимальные требования

- **Операционная система**: Windows 10/11, macOS 10.14+, Ubuntu 18.04+
- **Процессор**: Intel Core i3 или AMD эквивалент
- **Оперативная память**: 4 ГБ RAM
- **Свободное место**: 2 ГБ на диске
- **Интернет**: Стабильное подключение для API запросов

### Рекомендуемые требования

- **Операционная система**: Windows 11, macOS 12+, Ubuntu 20.04+
- **Процессор**: Intel Core i5 или AMD Ryzen 5
- **Оперативная память**: 8 ГБ RAM
- **Свободное место**: 4 ГБ на диске
- **Интернет**: Высокоскоростное подключение

### Дополнительные требования

- **Python**: версия 3.8 или выше
- **OpenAI API ключ**: для функций перевода
- **Права администратора**: для установки системных компонентов

## Подготовка к установке

### 1. Проверка системы

**Windows:**
```cmd
# Проверка версии Windows
winver

# Проверка архитектуры системы
systeminfo | findstr "System Type"
```

**macOS:**
```bash
# Проверка версии macOS
sw_vers

# Проверка архитектуры
uname -m
```

**Linux:**
```bash
# Проверка дистрибутива
lsb_release -a

# Проверка архитектуры
uname -m
```

### 2. Освобождение места на диске

Убедитесь, что у вас есть достаточно свободного места:

- **Основное приложение**: ~500 МБ
- **Python и зависимости**: ~1 ГБ
- **OCR модели**: ~500 МБ
- **Временные файлы**: ~500 МБ

## Установка Python

WhisperBridge требует Python 3.8 или выше.

### Windows

1. **Скачайте Python**
   - Перейдите на [python.org](https://www.python.org/downloads/)
   - Скачайте последнюю версию Python 3.x

2. **Установите Python**
   - Запустите установщик
   - ✅ Обязательно отметьте "Add Python to PATH"
   - Выберите "Install Now"

3. **Проверьте установку**
   ```cmd
   python --version
   pip --version
   ```

### macOS

1. **Используя Homebrew (рекомендуется)**
   ```bash
   # Установите Homebrew, если его нет
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   
   # Установите Python
   brew install python
   ```

2. **Или скачайте с официального сайта**
   - Перейдите на [python.org](https://www.python.org/downloads/)
   - Скачайте macOS installer

3. **Проверьте установку**
   ```bash
   python3 --version
   pip3 --version
   ```

### Linux (Ubuntu/Debian)

1. **Обновите пакеты**
   ```bash
   sudo apt update
   sudo apt upgrade
   ```

2. **Установите Python**
   ```bash
   sudo apt install python3 python3-pip python3-venv
   ```

3. **Проверьте установку**
   ```bash
   python3 --version
   pip3 --version
   ```

## Установка приложения

### Способ 1: Установка из исходного кода (рекомендуется)

1. **Клонируйте репозиторий**
   ```bash
   git clone https://github.com/your-username/WhisperBridge.git
   cd WhisperBridge
   ```

2. **Создайте виртуальное окружение**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Установите приложение**
   ```bash
   pip install -e .
   ```

### Способ 2: Установка через pip (когда будет доступно)

```bash
pip install whisperbridge
```

### Способ 3: Скачивание готовой сборки

1. **Перейдите на страницу релизов**
   - GitHub: [Releases](https://github.com/your-username/WhisperBridge/releases)

2. **Скачайте подходящую версию**
   - `WhisperBridge-Windows-x64.zip` для Windows
   - `WhisperBridge-macOS.dmg` для macOS
   - `WhisperBridge-Linux-x64.tar.gz` для Linux

3. **Распакуйте и запустите**
   - Распакуйте архив в удобную папку
   - Запустите исполняемый файл

## Установка зависимостей

### Основные зависимости

После установки приложения установите все необходимые зависимости:

```bash
# Активируйте виртуальное окружение (если используете)
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

## Настройка API ключей

### Получение OpenAI API ключа

1. **Зарегистрируйтесь на OpenAI**
   - Перейдите на [platform.openai.com](https://platform.openai.com/)
   - Создайте аккаунт или войдите

2. **Создайте API ключ**
   - Перейдите в раздел "API Keys"
   - Нажмите "Create new secret key"
   - Скопируйте ключ (он показывается только один раз!)

3. **Пополните баланс**
   - Перейдите в "Billing"
   - Добавьте способ оплаты
   - Пополните баланс (минимум $5)

### Настройка ключа в приложении

1. **Через интерфейс приложения**
   - Запустите WhisperBridge
   - Откройте настройки
   - Введите API ключ в соответствующее поле
   - Нажмите "Тест API" для проверки

2. **Через переменную окружения**
   ```bash
   # Windows
   set OPENAI_API_KEY=your-api-key-here
   
   # macOS/Linux
   export OPENAI_API_KEY=your-api-key-here
   ```

3. **Через файл .env**
   ```bash
   # Создайте файл .env в корне проекта
   echo "OPENAI_API_KEY=your-api-key-here" > .env
   ```

## Первый запуск

### 1. Запуск приложения

**Из исходного кода:**
```bash
# Активируйте виртуальное окружение
source venv/bin/activate  # или venv\Scripts\activate на Windows

# Запустите приложение
python src/main.py
```

**Из установленного пакета:**
```bash
whisperbridge
```

**Готовая сборка:**
- Запустите исполняемый файл из распакованной папки

### 2. Первоначальная настройка

1. **Настройте API ключ**
   - Введите ваш OpenAI API ключ
   - Нажмите "Тест API" для проверки

2. **Выберите языки**
   - Исходный язык: "auto" (автоопределение)
   - Целевой язык: выберите нужный

3. **Настройте горячие клавиши**
   - По умолчанию: `Ctrl+Shift+T`
   - Измените при необходимости

4. **Сохраните настройки**
   - Нажмите "Сохранить"
   - Приложение свернется в системный трей

### 3. Тестирование функций

1. **Тест захвата экрана**
   - Нажмите `Ctrl+Shift+T`
   - Выберите область с текстом
   - Проверьте результат

2. **Тест OCR**
   - Откройте любой текст на экране
   - Захватите область с четким текстом
   - Убедитесь в правильном распознавании

3. **Тест перевода**
   - Захватите текст на иностранном языке
   - Проверьте качество перевода
   - Убедитесь в работе кнопок копирования

## Решение проблем установки

### Проблемы с Python

**Ошибка: "python не является внутренней или внешней командой"**
```bash
# Решение для Windows:
# 1. Переустановите Python с галочкой "Add to PATH"
# 2. Или добавьте Python в PATH вручную
```

**Ошибка: "pip не найден"**
```bash
# Установите pip
python -m ensurepip --upgrade
```

### Проблемы с зависимостями

**Ошибка установки пакетов**
```bash
# Обновите pip
pip install --upgrade pip

# Установите с дополнительными флагами
pip install --no-cache-dir -r requirements.txt
```

**Проблемы с компиляцией**
```bash
# Windows: установите Visual Studio Build Tools
# macOS: установите Xcode Command Line Tools
xcode-select --install

# Linux: установите build-essential
sudo apt install build-essential
```

### Проблемы с правами доступа

**Linux/macOS: Permission denied**
```bash
# Дайте права на выполнение
chmod +x whisperbridge

# Или запустите с sudo (не рекомендуется)
sudo python src/main.py
```

**Windows: Требуются права администратора**
- Запустите командную строку от имени администратора
- Или добавьте исключение в антивирус

### Проблемы с сетью

**Ошибки SSL/TLS**
```bash
# Обновите сертификаты
pip install --upgrade certifi

# Или отключите проверку SSL (не рекомендуется)
pip install --trusted-host pypi.org --trusted-host pypi.python.org
```

**Проблемы с прокси**
```bash
# Настройте прокси для pip
pip install --proxy http://user:password@proxy.server:port package_name
```

## Обновление приложения

### Обновление из исходного кода

```bash
# Перейдите в папку проекта
cd WhisperBridge

# Получите последние изменения
git pull origin main

# Обновите зависимости
pip install -r requirements.txt --upgrade

# Переустановите приложение
pip install -e . --upgrade
```

### Обновление через pip

```bash
pip install --upgrade whisperbridge
```

### Обновление готовой сборки

1. Скачайте новую версию с GitHub Releases
2. Остановите текущее приложение
3. Замените файлы новой версией
4. Запустите обновленное приложение

### Сохранение настроек при обновлении

Настройки сохраняются в:
- **Windows**: `%USERPROFILE%\.whisperbridge\`
- **macOS**: `~/.whisperbridge/`
- **Linux**: `~/.whisperbridge/`

При обновлении эти файлы сохраняются автоматически.

## Автозапуск с системой

### Windows

1. **Через планировщик задач**
   - Откройте "Планировщик заданий"
   - Создайте базовую задачу
   - Укажите путь к исполняемому файлу
   - Настройте запуск при входе в систему

2. **Через автозагрузку**
   - Нажмите `Win+R`, введите `shell:startup`
   - Создайте ярлык на WhisperBridge
   - Поместите ярлык в открывшуюся папку

### macOS

```bash
# Создайте plist файл для LaunchAgent
cat > ~/Library/LaunchAgents/com.whisperbridge.app.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whisperbridge.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/whisperbridge</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

# Загрузите задачу
launchctl load ~/Library/LaunchAgents/com.whisperbridge.app.plist
```

### Linux

```bash
# Создайте desktop файл
cat > ~/.config/autostart/whisperbridge.desktop << EOF
[Desktop Entry]
Type=Application
Name=WhisperBridge
Exec=/path/to/whisperbridge
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```

---

*После успешной установки перейдите к [Руководству пользователя](USER_GUIDE.md) для изучения основных функций приложения.*
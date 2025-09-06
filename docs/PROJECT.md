## Project Overview

WhisperBridge is a desktop application for quick text translation using OCR (Optical Character Recognition) and GPT API. It allows users to capture screen regions, extract text, and get instant translations via overlay interface, activated by global hotkeys.

## Development Commands

### Running the Application

**Qt-based UI (recommended):**
```bash
python scripts/run_qt_app.py
```

*(Legacy CustomTkinter UI has been removed — use the Qt launcher above.)*


**Code quality tools (from pyproject.toml):**
```bash
black src/  # Code formatting
isort src/  # Import sorting  
flake8 src/  # Linting
mypy src/   # Type checking
```

## Architecture

### UI System
The project uses the Qt (PySide6) UI backend exclusively:
- **Qt UI**: Located in `src/whisperbridge/ui_qt/` (use `UI_BACKEND=qt`)

### Core Components Structure
```
src/whisperbridge/
├── core/           # Core managers (API, OCR, keyboard, settings)
├── services/       # Business logic services (translation, screen capture, etc.)
├── ui_qt/          # Qt/PySide6 UI components
├── utils/          # Utility functions
└── models/         # Data models
```

### Key Services
- **OCR Service**: Text extraction using EasyOCR
- **Translation Service**: GPT API integration with caching
- **Screen Capture Service**: Cross-platform screen capture with MSS
- **Hotkey Service**: Global keyboard shortcuts via pynput
- **Overlay Service**: Result display overlays
- **Settings Manager**: Configuration via Pydantic settings

### Entry Points
- Qt Launcher: `scripts/run_qt_app.py` (Qt backend)
- Package entry: `whisperbridge.main:main` (from pyproject.toml)

## Configuration

### Settings Location
- Windows: `%USERPROFILE%\.whisperbridge\`
- macOS/Linux: `~/.whisperbridge/`

### API Configuration
The app requires OpenAI API key configuration. Settings are managed via Pydantic Settings with keyring integration for secure storage.

### Main Settings
- Global hotkeys (default: Ctrl+Shift+T)
- OCR engine selection (EasyOCR primary)
- Translation model (GPT-3.5-turbo default)
- UI themes and positioning

## Dependencies

### Core Libraries
- **UI**: PySide6 (Qt) 6.5+
- **OCR**: EasyOCR 1.7+
- **AI**: OpenAI 1.3+, httpx, tenacity
- **System**: pynput, pystray, mss, pillow
- **Config**: pydantic 2.4+, keyring, appdirs
- **Logging**: loguru

### Development Tools
- pytest, pytest-asyncio, pytest-cov
- black, isort, flake8, mypy
- sphinx for documentation

## Testing Strategy

Tests are located in `temp/tests/` directory:
- Unit tests for individual components
- Integration tests for service interactions
- OCR and translation pipeline tests
- UI component tests

Run the comprehensive test suite with `python temp/tests/test_suite.py` which discovers all test files.

## Key Workflows

### Main Translation Flow
1. User presses hotkey (Ctrl+Shift+T)
2. Screen selection overlay appears
3. User selects region to capture
4. OCR extracts text from captured image
5. Translation service processes text via GPT API
6. Results displayed in overlay window
7. User can copy results or paste directly

### Configuration Flow
- Settings dialog accessible via system tray
- Real-time validation of API keys
- Hotkey registration/unregistration
- Theme and language preference updates

## Architecture Patterns

### Async/Await Usage
The application uses asyncio for non-blocking operations, particularly for API calls and UI responsiveness.

### Service Layer Pattern
Business logic is encapsulated in service classes with clear interfaces and dependency injection.

### Settings Management
Centralized configuration using Pydantic Settings with environment variable support and secure credential storage.

### Error Handling
Comprehensive error handling with retry mechanisms for API calls, fallback strategies for OCR, and user-friendly error reporting.


Main files (key modules)

Core / Entry points
- [`scripts/run_qt_app.py`](scripts/run_qt_app.py:28) — Qt launcher; sets UI_BACKEND=qt and runs [`src/main.py:main()`](src/main.py:20).
- [`src/main.py`](src/main.py:20) — application entry point; async `main()` initializes logging and starts the Qt app via [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:994).

Core managers and configuration
- [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:18) — `Settings` Pydantic model, `load_settings()` / `save_settings()`, keyring API key handling; global `settings` instance (line ~252).
- [`src/whisperbridge/core/api_manager.py`](src/whisperbridge/core/api_manager.py:69) — `APIManager`, provider enum `APIProvider`, request retry and usage tracking, model listing and caching.
- [`src/whisperbridge/core/ocr_manager.py`](src/whisperbridge/core/ocr_manager.py:45) — `OCREngineManager`, `OCREngine`, `OCRResult` — manages EasyOCR engine lifecycle and stats.
- [`src/whisperbridge/core/keyboard_manager.py`](src/whisperbridge/core/keyboard_manager.py:1) — keyboard registration helper (hotkeys integration).
- [`src/whisperbridge/core/logger.py`](src/whisperbridge/core/logger.py:1) — logging setup used by `src/main.py` and services.

Services (business logic)
- [`src/whisperbridge/services/translation_service.py`](src/whisperbridge/services/translation_service.py:133) — `TranslationService`: GPT API integration, caching (`TranslationCache`), async/sync translate methods (`translate_text_async`, `translate_text_sync`).
- [`src/whisperbridge/services/ocr_service.py`](src/whisperbridge/services/ocr_service.py:139) — `OCRService`, `OCRRequest`, `OCRResponse` and OCR caching; background initialization and synchronous/async processing helpers.
- [`src/whisperbridge/services/screen_capture_service.py`](src/whisperbridge/services/screen_capture_service.py:1) — screen capture utilities and interactive capture (MSS wrapper).
- [`src/whisperbridge/services/hotkey_service.py`](src/whisperbridge/services/hotkey_service.py:1) — global hotkey registration (uses `pynput` and `KeyboardManager`).
- [`src/whisperbridge/services/overlay_service_qt.py`](src/whisperbridge/services/overlay_service_qt.py:1) — Qt overlay service integration.
- [`src/whisperbridge/services/tray_service.py`](src/whisperbridge/services/tray_service.py:1) — system tray integration/service.
- [`src/whisperbridge/services/clipboard_service.py`](src/whisperbridge/services/clipboard_service.py:1) — clipboard helper service.
- [`src/whisperbridge/services/paste_service.py`](src/whisperbridge/services/paste_service.py:1) — paste helper service.
- [`src/whisperbridge/services/config_service.py`](src/whisperbridge/services/config_service.py:1) — settings facade and observer pattern used throughout UI and services (`config_service.get_setting()`).

UI (Qt / PySide6)
- [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:171) — `QtApp` class: app lifecycle, initialization of windows/services, hotkey registration, tray manager, overlay windows; helpers `get_qt_app()` and `init_qt_app()` (lines ~986–999).
- [`src/whisperbridge/ui_qt/main_window.py`](src/whisperbridge/ui_qt/main_window.py:1) — main settings window used by `QtApp`.
- [`src/whisperbridge/ui_qt/overlay_window.py`](src/whisperbridge/ui_qt/overlay_window.py:15) — `OverlayWindow`: overlay UI for showing OCR and translation results (detailed UI logic, copy/translate actions, auto-swap checkbox).
- [`src/whisperbridge/ui_qt/selection_overlay.py`](src/whisperbridge/ui_qt/selection_overlay.py:1) — region selection overlay for interactive capture.
- [`src/whisperbridge/ui_qt/settings_dialog.py`](src/whisperbridge/ui_qt/settings_dialog.py:1) — settings dialog UI.
- [`src/whisperbridge/ui_qt/tray.py`](src/whisperbridge/ui_qt/tray.py:1) — `TrayManager`: system tray menu/actions and notifications.

Utilities
- [`src/whisperbridge/utils/api_utils.py`](src/whisperbridge/utils/api_utils.py:1) — prompt formatting, language detection helpers, response validation and key validation.
- [`src/whisperbridge/utils/image_utils.py`](src/whisperbridge/utils/image_utils.py:1) — image preprocessing helpers used by OCR service.
- [`src/whisperbridge/utils/screen_utils.py`](src/whisperbridge/utils/screen_utils.py:1) — `Rectangle` and DPI-related utilities (used in coordinate conversions).
- [`src/whisperbridge/utils/overlay_utils.py`](src/whisperbridge/utils/overlay_utils.py:1) — overlay positioning helpers.
- [`src/whisperbridge/utils/window_utils.py`](src/whisperbridge/utils/window_utils.py:1) — window focus/activation helpers.
- [`src/whisperbridge/utils/keyboard_utils.py`](src/whisperbridge/utils/keyboard_utils.py:1) — hotkey parsing/formatting helpers.
- [`src/whisperbridge/utils/icon_manager.py`](src/whisperbridge/utils/icon_manager.py:1) — icon/resource manager.

Packaging and config
- [`pyproject.toml`](pyproject.toml:33) — dependency list and package entry point (`whisperbridge = "whisperbridge.main:main"`); `qt` optional extra for PySide6 (lines ~51–53).
- [`requirements.txt`](requirements.txt:1) — (if maintained) pinned dependency file for environments.

Quick references (important code locations)
- Init Qt App: see [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:994) — `init_qt_app()`.
- Capture→OCR→Translate worker: [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:30) — class `CaptureOcrTranslateWorker`.
- Translation API flow: [`src/whisperbridge/services/translation_service.py`](src/whisperbridge/services/translation_service.py:175) — `translate_text_async`; [`src/whisperbridge/services/translation_service.py`](src/whisperbridge/services/translation_service.py:341) — `translate_text_sync`.
- Settings storage: [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:187, src/whisperbridge/core/config.py:218) — `load_settings()` / `save_settings()`.
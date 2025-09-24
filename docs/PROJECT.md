## Project Overview

WhisperBridge is a desktop application for quick text translation using OCR (Optical Character Recognition) and GPT API. It lets users capture a screen region, extract text, and translate it instantly in an overlay UI activated by global hotkeys.

## Development Commands

### Running the Application

Qt-based UI (recommended):
```bash
python scripts/run_qt_app.py
```
- The launcher sets UI_BACKEND=qt and starts the async entrypoint in [src/main.py](../src/main.py).

Code quality tools (configured in [pyproject.toml](../pyproject.toml)):
```bash
black src/      # Code formatting
isort src/      # Import sorting
flake8 src/     # Linting
mypy src/       # Type checking
```

## Architecture

### UI System
The project uses the Qt (PySide6) UI backend exclusively:
- Qt UI: [src/whisperbridge/ui_qt/](../src/whisperbridge/ui_qt/)

### Core Components Structure
```
src/whisperbridge/
├── core/           # Core managers (API, OCR, keyboard, settings)
├── services/       # Business logic services (translation, screen capture, etc.)
├── ui_qt/          # Qt/PySide6 UI components
├── utils/          # Utility functions
└── models/         # Data models (if present)
```

### Key Services
- Hotkey Translate Service: Instant translation of selected or clipboard text via [python.CopyTranslateService](../src/whisperbridge/services/copy_translate_service.py) with global shortcuts managed by [python.HotkeyService](../src/whisperbridge/services/hotkey_service.py). Results are displayed by [python.UIService](../src/whisperbridge/services/ui_service.py).
- OCR Service: Text extraction using EasyOCR via [python.OCREngineManager](../src/whisperbridge/core/ocr_manager.py)
- Translator Window (standard): Manual text translation in a dedicated translator window implemented by [python.OverlayWindow](../src/whisperbridge/ui_qt/overlay_window.py); toggled via tray menu ([python.TrayManager](../src/whisperbridge/ui_qt/tray.py)) or activation hotkey; uses [python.UIService.show_overlay_window()](../src/whisperbridge/services/ui_service.py) and [python.TranslationService](../src/whisperbridge/services/translation_service.py).
- Translation Service: GPT API integration with caching via [python.TranslationService](../src/whisperbridge/services/translation_service.py)
- Screen Capture Service: Region capture (current implementation uses Pillow ImageGrab)
- Hotkey Service: Global keyboard shortcuts via pynput
- UI Service: Central UI lifecycle orchestration (windows, overlays, tray)
- Theme Service: Light/Dark/System theme handling for Qt
- Clipboard and Paste Services: Copy/paste helpers and automation
- Settings Manager: JSON persistence and keyring integration

### Entry Points

- Qt Launcher: [scripts/run_qt_app.py](../scripts/run_qt_app.py)
- Application entry: [python.main()](../src/main.py) initializes logging and then [python.init_qt_app()](../src/whisperbridge/ui_qt/app.py) to start the Qt app runtime.
- Qt lifecycle: [python.QtApp](../src/whisperbridge/ui_qt/app.py) constructs services and UI, registers hotkeys, and runs the event loop via [python.QtApp.run()](../src/whisperbridge/ui_qt/app.py)

Note: [pyproject.toml](../pyproject.toml) declares a script entry whisperbridge = "whisperbridge.main:main", but the module whisperbridge/main.py is not present in this repository; use the launcher above.

## Configuration

### Settings Location
- Windows: %USERPROFILE%\.whisperbridge\

### API Configuration
OpenAI API key is required. Credentials are managed using keyring helpers in [python.load_api_key()](../src/whisperbridge/core/config.py) and [python.save_api_key()](../src/whisperbridge/core/config.py). Runtime settings access goes through [python.ConfigService](../src/whisperbridge/services/config_service.py); persistence uses [python.SettingsManager](../src/whisperbridge/core/settings_manager.py).

### Main Settings
Key fields in [python.Settings](../src/whisperbridge/core/config.py) include:
- API: openai_api_key (keyring), api_provider, model (default "gpt-5-nano"), api_timeout
- OCR: ocr_languages, ocr_confidence_threshold, ocr_timeout, initialize_ocr
- Hotkeys (defaults include "ctrl+shift+t" for translate)
- UI/Behavior: theme, window_geometry, auto_copy_translated, clipboard_poll_timeout_ms, system_prompt
- Caching and logging options

## Dependencies

### Core Libraries
- UI: PySide6 (Qt) ≥ 6.6.0
- OCR: EasyOCR ≥ 1.7
- AI: openai 1.x, httpx, tenacity
- System: pynput, pillow (ImageGrab), pyperclip
- Config: pydantic 2.x, keyring, appdirs
- Logging: loguru

Note: Screen capture currently uses Pillow’s ImageGrab rather than MSS; the mss library may be present but is not used in the current implementation.

### Development Tools
- pytest, pytest-asyncio, pytest-cov
- black, isort, flake8, mypy
- sphinx for documentation

## Testing Strategy

The repository currently does not include an active tests directory. pytest defaults are configured in [pyproject.toml](../pyproject.toml), typically expecting tests under "tests/". Adding a tests/ suite is recommended.

## Key Workflows

### Main Translation Flow (Capture → OCR → Translate → Overlay)
1. User presses translate hotkey (default: Ctrl+Shift+T).
2. Screen selection overlay appears via [python.SelectionOverlayQt](../src/whisperbridge/ui_qt/selection_overlay.py).
3. On completion, [python.QtApp._on_selection_completed()](../src/whisperbridge/ui_qt/app.py) creates a [python.CaptureOcrTranslateWorker](../src/whisperbridge/ui_qt/app.py) in a background thread.
4. The worker captures the region via [python.ScreenCaptureService.capture_area()](../src/whisperbridge/services/screen_capture_service.py) and runs OCR using [python.OCRService.process_image()](../src/whisperbridge/services/ocr_service.py).
5. If API key is configured, the text is translated using [python.TranslationService.translate_text_sync()](../src/whisperbridge/services/translation_service.py) with optional language auto-detect from [python.detect_language()](../src/whisperbridge/utils/language_utils.py).
6. Results are displayed using [python.UIService.show_overlay_window()](../src/whisperbridge/services/ui_service.py) → [python.OverlayWindow.show_overlay()](../src/whisperbridge/ui_qt/overlay_window.py). Completion is handled by [python.QtApp._handle_worker_finished()](../src/whisperbridge/ui_qt/app.py).

### Copy → Translate Flow
- Triggered by a dedicated hotkey; [python.CopyTranslateService.run()](../src/whisperbridge/services/copy_translate_service.py) simulates copy, polls clipboard, translates, and emits [python.CopyTranslateService.result_ready](../src/whisperbridge/services/copy_translate_service.py); handled by [python.QtApp._on_copy_translate_result](../src/whisperbridge/ui_qt/app.py).

### Standard Translator Window Flow
- Open the translator window via tray menu toggle or activation hotkey.
- In [python.OverlayWindow](../src/whisperbridge/ui_qt/overlay_window.py), enter or paste text and trigger translation; it calls [python.TranslationService.translate_text_sync()](../src/whisperbridge/services/translation_service.py) and displays the result.
- Optional: if auto-copy is enabled in Settings, the translated text is copied to the clipboard.


### Hotkey Registration
- Defaults are defined in [python.Settings](../src/whisperbridge/core/config.py).
- Registration occurs in [python.QtApp._register_default_hotkeys()](../src/whisperbridge/ui_qt/app.py) using [python.KeyboardManager](../src/whisperbridge/core/keyboard_manager.py) and [python.HotkeyService](../src/whisperbridge/services/hotkey_service.py).

## Architecture Patterns

### Async/Await Usage
Async operations are used for API calls and to keep the UI responsive.

### Service Layer Pattern
Business logic is encapsulated in services with clear interfaces; dependencies are injected at app startup.

### Settings Management
Runtime access via [python.ConfigService](../src/whisperbridge/services/config_service.py); persistence and keyring via [python.SettingsManager](../src/whisperbridge/core/settings_manager.py) and helpers in [src/whisperbridge/core/config.py](../src/whisperbridge/core/config.py).

### Error Handling
Retries and resilience for API calls via tenacity; OCR fallback strategies; user-friendly error reporting in UI.

## Main files (key modules)

Core / Entry points
- [scripts/run_qt_app.py](../scripts/run_qt_app.py) — Qt launcher; sets environment and runs [python.main()](../src/main.py).
- [src/main.py](../src/main.py) — async entry point; initializes logging and starts the Qt app via [python.init_qt_app()](../src/whisperbridge/ui_qt/app.py).

Core managers and configuration
- [src/whisperbridge/core/config.py](../src/whisperbridge/core/config.py) — [python.Settings](../src/whisperbridge/core/config.py), keyring helpers [python.load_api_key()](../src/whisperbridge/core/config.py) / [python.save_api_key()](../src/whisperbridge/core/config.py) / [python.validate_api_key_format()](../src/whisperbridge/core/config.py)
- [src/whisperbridge/core/settings_manager.py](../src/whisperbridge/core/settings_manager.py) — [python.SettingsManager](../src/whisperbridge/core/settings_manager.py) and singleton [python.settings_manager](../src/whisperbridge/core/settings_manager.py)
- [src/whisperbridge/core/api_manager.py](../src/whisperbridge/core/api_manager.py) — [python.APIManager](../src/whisperbridge/core/api_manager.py), [python.init_api_manager()](../src/whisperbridge/core/api_manager.py)
- [src/whisperbridge/core/ocr_manager.py](../src/whisperbridge/core/ocr_manager.py) — [python.OCREngineManager](../src/whisperbridge/core/ocr_manager.py)
- [src/whisperbridge/core/keyboard_manager.py](../src/whisperbridge/core/keyboard_manager.py) — [python.KeyboardManager](../src/whisperbridge/core/keyboard_manager.py)
- [src/whisperbridge/core/logger.py](../src/whisperbridge/core/logger.py)

Services (business logic)
- [src/whisperbridge/services/translation_service.py](../src/whisperbridge/services/translation_service.py) — [python.TranslationService](../src/whisperbridge/services/translation_service.py), [python.translate_text_sync()](../src/whisperbridge/services/translation_service.py)
- [src/whisperbridge/services/ocr_service.py](../src/whisperbridge/services/ocr_service.py) — [python.OCRService](../src/whisperbridge/services/ocr_service.py), [python.process_image()](../src/whisperbridge/services/ocr_service.py)
- [src/whisperbridge/services/screen_capture_service.py](../src/whisperbridge/services/screen_capture_service.py) — [python.ScreenCaptureService](../src/whisperbridge/services/screen_capture_service.py), [python._capture_screen_area()](../src/whisperbridge/services/screen_capture_service.py)
- [src/whisperbridge/services/hotkey_service.py](../src/whisperbridge/services/hotkey_service.py) — [python.HotkeyService](../src/whisperbridge/services/hotkey_service.py)
- [src/whisperbridge/services/clipboard_service.py](../src/whisperbridge/services/clipboard_service.py) — [python.get_clipboard_service()](../src/whisperbridge/services/clipboard_service.py)
- [src/whisperbridge/services/paste_service.py](../src/whisperbridge/services/paste_service.py)
- [src/whisperbridge/services/config_service.py](../src/whisperbridge/services/config_service.py) — [python.ConfigService](../src/whisperbridge/services/config_service.py), singleton [python.config_service](../src/whisperbridge/services/config_service.py)
- [src/whisperbridge/services/ui_service.py](../src/whisperbridge/services/ui_service.py) — [python.UIService](../src/whisperbridge/services/ui_service.py), [python.show_overlay_window()](../src/whisperbridge/services/ui_service.py), [python.handle_worker_finished()](../src/whisperbridge/services/ui_service.py)
- [src/whisperbridge/services/theme_service.py](../src/whisperbridge/services/theme_service.py) — [python.ThemeService](../src/whisperbridge/services/theme_service.py)
- [src/whisperbridge/services/copy_translate_service.py](../src/whisperbridge/services/copy_translate_service.py) — [python.CopyTranslateService](../src/whisperbridge/services/copy_translate_service.py), [python.run()](../src/whisperbridge/services/copy_translate_service.py), [python.result_ready](../src/whisperbridge/services/copy_translate_service.py)
- Auxiliary: [src/whisperbridge/services/overlay_service_qt.py](../src/whisperbridge/services/overlay_service_qt.py)

UI (Qt / PySide6)
- [src/whisperbridge/ui_qt/app.py](../src/whisperbridge/ui_qt/app.py) — [python.QtApp](../src/whisperbridge/ui_qt/app.py), [python._register_default_hotkeys()](../src/whisperbridge/ui_qt/app.py), [python._on_selection_completed()](../src/whisperbridge/ui_qt/app.py), [python._handle_worker_finished()](../src/whisperbridge/ui_qt/app.py), [python.save_settings_async()](../src/whisperbridge/ui_qt/app.py), [python.get_qt_app()](../src/whisperbridge/ui_qt/app.py), [python.init_qt_app()](../src/whisperbridge/ui_qt/app.py), [python.run()](../src/whisperbridge/ui_qt/app.py)
- [src/whisperbridge/ui_qt/main_window.py](../src/whisperbridge/ui_qt/main_window.py)
- [src/whisperbridge/ui_qt/overlay_window.py](../src/whisperbridge/ui_qt/overlay_window.py) — [python.OverlayWindow](../src/whisperbridge/ui_qt/overlay_window.py), [python.show_overlay()](../src/whisperbridge/ui_qt/overlay_window.py), [python.collapse_to_minibar()](../src/whisperbridge/ui_qt/overlay_window.py)
- [src/whisperbridge/ui_qt/minibar_overlay.py](../src/whisperbridge/ui_qt/minibar_overlay.py) — [python.MiniBarOverlay](../src/whisperbridge/ui_qt/minibar_overlay.py)
- [src/whisperbridge/ui_qt/selection_overlay.py](../src/whisperbridge/ui_qt/selection_overlay.py) — [python.SelectionOverlayQt](../src/whisperbridge/ui_qt/selection_overlay.py)
- [src/whisperbridge/ui_qt/settings_dialog.py](../src/whisperbridge/ui_qt/settings_dialog.py) — [python.SettingsDialog](../src/whisperbridge/ui_qt/settings_dialog.py)
- [src/whisperbridge/ui_qt/tray.py](../src/whisperbridge/ui_qt/tray.py) — [python.TrayManager](../src/whisperbridge/ui_qt/tray.py)

Utilities
- [src/whisperbridge/utils/translation_utils.py](../src/whisperbridge/utils/translation_utils.py) — [python.TranslationRequest](../src/whisperbridge/utils/translation_utils.py), [python.TranslationResponse](../src/whisperbridge/utils/translation_utils.py), [python.format_translation_prompt()](../src/whisperbridge/utils/translation_utils.py), [python.parse_gpt_response()](../src/whisperbridge/utils/translation_utils.py)
- [src/whisperbridge/utils/language_utils.py](../src/whisperbridge/utils/language_utils.py) — [python.detect_language()](../src/whisperbridge/utils/language_utils.py), [python.get_language_name()](../src/whisperbridge/utils/language_utils.py)
- [src/whisperbridge/utils/image_utils.py](../src/whisperbridge/utils/image_utils.py) — [python.preprocess_for_ocr()](../src/whisperbridge/utils/image_utils.py)
- [src/whisperbridge/utils/screen_utils.py](../src/whisperbridge/utils/screen_utils.py) — [python.Rectangle](../src/whisperbridge/utils/screen_utils.py)
- [src/whisperbridge/utils/window_utils.py](../src/whisperbridge/utils/window_utils.py)
- [src/whisperbridge/utils/keyboard_utils.py](../src/whisperbridge/utils/keyboard_utils.py)
- [src/whisperbridge/utils/overlay_utils.py](../src/whisperbridge/utils/overlay_utils.py)
- Archived/moved: [src/whisperbridge/utils/archive/api_utils.py](../src/whisperbridge/utils/archive/api_utils.py)

Packaging and config
- [pyproject.toml](../pyproject.toml) — dependencies and optional extras (e.g., "qt" with PySide6), tool configs for linting and tests
- [requirements.txt](../requirements.txt) — pinned base dependencies (if maintained)

Quick references
- Init Qt App: [python.init_qt_app()](../src/whisperbridge/ui_qt/app.py)
- Capture→OCR→Translate worker: [python.CaptureOcrTranslateWorker](../src/whisperbridge/ui_qt/app.py)
- Translation API call: [python.TranslationService.translate_text_sync()](../src/whisperbridge/services/translation_service.py)
- Settings storage: [python.SettingsManager](../src/whisperbridge/core/settings_manager.py); keyring helpers in [src/whisperbridge/core/config.py](../src/whisperbridge/core/config.py)
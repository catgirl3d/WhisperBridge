## Project Overview

WhisperBridge is a desktop application for fast on-screen text extraction and translation (OCR → AI translation). Users select a screen region, extract text via OCR, and translate it using a configured AI provider. The UI uses a Qt (PySide6) desktop interface with overlays, a system tray, and global hotkeys.

## Development

Run the Qt UI during development:
- Launcher script: [scripts/run_qt_app.py](scripts/run_qt_app.py)
  - This launcher prepares the environment (e.g., UI backend) and imports the runtime entry located at [src/main.py](src/main.py).
  - Command:
    - python scripts/run_qt_app.py

Runtime entrypoint used during development:
- Application entry module: [src/main.py](src/main.py)
  - Initializes logging, creates the Qt application, and starts the event loop.

Packaging and console script mapping:
- Declared console script in [pyproject.toml](pyproject.toml):
  - whisperbridge = "whisperbridge.main:main"
- Current code layout does not include a packaged module at src/whisperbridge/main.py. To make the console script work when packaging, either:
  - Add a small wrapper module in src/whisperbridge/ that imports and calls the actual entry in [src/main.py](src/main.py), or
  - Update the console script to point to a stable importable module placed under src/whisperbridge/.

## Architecture

High-level layout:
- Sources: [src/whisperbridge/](src/whisperbridge/)
- UI (Qt): [src/whisperbridge/ui_qt/](src/whisperbridge/ui_qt/)
- Core managers: [src/whisperbridge/core/](src/whisperbridge/core/)
- Services (business logic): [src/whisperbridge/services/](src/whisperbridge/services/)
- Providers: [src/whisperbridge/providers/](src/whisperbridge/providers/)
- Utilities: [src/whisperbridge/utils/](src/whisperbridge/utils/)

Primary design patterns:
- Service layer orchestrated by the Qt application. Business logic lives under [src/whisperbridge/services/](src/whisperbridge/services/).
- UI runs on the Qt main thread; heavy tasks run in QThreads using worker objects located in [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py).
- Settings and runtime configuration are provided by a Pydantic model at [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py) and managed at runtime via [src/whisperbridge/services/config_service.py](src/whisperbridge/services/config_service.py).

## UI Architecture and Lifecycle

Key UI modules:
- Qt app and lifecycle: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)
- Main window: [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py)
- Overlay window: [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py)
- Selection overlay: [src/whisperbridge/ui_qt/selection_overlay.py](src/whisperbridge/ui_qt/selection_overlay.py)
- System tray: [src/whisperbridge/ui_qt/tray.py](src/whisperbridge/ui_qt/tray.py)
- Settings dialog: [src/whisperbridge/ui_qt/settings_dialog.py](src/whisperbridge/ui_qt/settings_dialog.py)

Workers and threads:
- Background workers are implemented in [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py) and are moved into QThreads by logic in [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py).

UI lifecycle orchestration:
- A dedicated service handles creation and management of windows and overlays: [src/whisperbridge/services/ui_service.py](src/whisperbridge/services/ui_service.py).
- The Qt application module coordinates startup, hotkeys, worker wiring, and interactions with UI services: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py).

## Configuration

Canonical settings model:
- Defined in [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py).

Notable defaults (verify in source for your version):
- API provider and model names:
  - Default provider: openai (see [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py))
  - OpenAI model: gpt-5-nano (see [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py))
  - Google model: gemini-1.5-flash (see [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py))
- OCR initialization:
  - initialize_ocr default is False (see [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py))
- Hotkeys (defaults):
  - translate_hotkey: ctrl+shift+t
  - quick_translate_hotkey: ctrl+shift+q
  - activation_hotkey: ctrl+shift+a
  - copy_translate_hotkey: ctrl+shift+j
  - Source of defaults: [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py)
- Clipboard polling:
  - clipboard_poll_timeout_ms default is 2000 (see [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py))
- System prompt:
  - Default prompt string defined in [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py)
- Configuration directory:
  - get_config_path() resolves to a platform-specific user directory (default pattern: home/.whisperbridge). See [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py).
- Key handling and persistence helpers:
  - Implemented in [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py) with runtime persistence by [src/whisperbridge/core/settings_manager.py](src/whisperbridge/core/settings_manager.py) and [src/whisperbridge/services/config_service.py](src/whisperbridge/services/config_service.py).

## Dependencies and Tools

Runtime dependencies (see [pyproject.toml](pyproject.toml)):
- Core libraries include OCR, screen capture, AI clients, configuration, and desktop integration (pynput, pystray, pillow, mss, easyocr, openai, google-generativeai, httpx, tenacity, pydantic, pydantic-settings, keyring, appdirs, loguru, click, comtypes).
- Exact versions and full list are defined in [pyproject.toml](pyproject.toml).

Optional extras:
- Qt desktop UI extras (PySide6, qtawesome) are provided via the "qt" extra in [pyproject.toml](pyproject.toml).

Providers:
- Google adapter exists at [src/whisperbridge/providers/google_chat_adapter.py](src/whisperbridge/providers/google_chat_adapter.py).
- OpenAI usage is handled via the API manager and the upstream client; see [src/whisperbridge/core/api_manager.py](src/whisperbridge/core/api_manager.py).

Developer tooling:
- Black, isort, flake8, mypy, pytest, and other tools are configured in [pyproject.toml](pyproject.toml).

## Testing

- Pytest configuration is present in [pyproject.toml](pyproject.toml).
- A tests/ directory is not currently included; adding unit and integration tests is recommended, especially for services such as translation, OCR/processing, and API manager functionality.

## Key Workflows

Main translation pipeline (Capture → OCR → Translate → Display):
1) User triggers translation via hotkey or tray.
2) A selection overlay is shown: [src/whisperbridge/ui_qt/selection_overlay.py](src/whisperbridge/ui_qt/selection_overlay.py).
3) Upon selection completion, Qt-side code initializes a background worker and thread: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py) + [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py).
4) Worker steps:
   - Capture screen region via [src/whisperbridge/services/screen_capture_service.py](src/whisperbridge/services/screen_capture_service.py).
   - Perform OCR via [src/whisperbridge/services/ocr_service.py](src/whisperbridge/services/ocr_service.py).
   - Orchestrate translation via [src/whisperbridge/services/ocr_translation_service.py](src/whisperbridge/services/ocr_translation_service.py), which uses [src/whisperbridge/services/translation_service.py](src/whisperbridge/services/translation_service.py).
5) Results are emitted back to the UI thread and displayed by logic coordinated with [src/whisperbridge/services/ui_service.py](src/whisperbridge/services/ui_service.py) and UI modules such as [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py).

Copy → Translate flow:
- Triggered by a dedicated hotkey and implemented by [src/whisperbridge/services/copy_translate_service.py](src/whisperbridge/services/copy_translate_service.py) with integration points in [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py).

Manual translation windows:
- Translator overlay and main window live in [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py) and [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py). Settings UI is in [src/whisperbridge/ui_qt/settings_dialog.py](src/whisperbridge/ui_qt/settings_dialog.py).

## Hotkeys

Defaults:
- Stored in [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py) and registered during app startup.

Registration:
- Registration and lifecycle are handled by logic in [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py) using keyboard utilities from [src/whisperbridge/core/keyboard_manager.py](src/whisperbridge/core/keyboard_manager.py) and [src/whisperbridge/services/hotkey_service.py](src/whisperbridge/services/hotkey_service.py).

Conditional registration:
- OCR-dependent hotkeys are only registered when OCR is initialized or configured accordingly; the copy→translate hotkey is available independently based on current logic in [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py).

## Threads and Signals

Reference guidelines:
- See [THREADS_SIGNALS.md](THREADS_SIGNALS.md) for design guidance on signals, threads, and UI interactions.

Current implementation patterns:
- Workers are QObject-based and moved to QThreads via the app module: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py).
- Workers encapsulate long-running tasks (capture, OCR, translation) and emit signals back to the main thread: [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py).

## Practical Notes and Maintenance

- Provider defaults and model names are defined in [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py). If adding/removing providers, update both [pyproject.toml](pyproject.toml) dependencies and configuration defaults.
- OCR initialization is opt-in by default. If OCR-dependent hotkeys must always be available, enable initialization in settings or provide an explicit initialization action in UI logic: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py).
- Packaging: review the console script mapping in [pyproject.toml](pyproject.toml) to ensure it matches a packaged module under src/whisperbridge/.
- Tests: introduce a tests/ suite and cover services first (translation, API manager, OCR pipeline) using the configuration from [pyproject.toml](pyproject.toml).

## Quick References

Core / entry points:
- Launcher: [scripts/run_qt_app.py](scripts/run_qt_app.py)
- Development entry: [src/main.py](src/main.py)
- Qt app module: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)

Core managers and configuration:
- Settings model and keyring helpers: [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py)
- Settings manager: [src/whisperbridge/core/settings_manager.py](src/whisperbridge/core/settings_manager.py)
- API manager: [src/whisperbridge/core/api_manager.py](src/whisperbridge/core/api_manager.py)
- Keyboard manager: [src/whisperbridge/core/keyboard_manager.py](src/whisperbridge/core/keyboard_manager.py)
- Logger setup: [src/whisperbridge/core/logger.py](src/whisperbridge/core/logger.py)

Services:
- Translation: [src/whisperbridge/services/translation_service.py](src/whisperbridge/services/translation_service.py)
- OCR: [src/whisperbridge/services/ocr_service.py](src/whisperbridge/services/ocr_service.py)
- OCR+Translation coordinator: [src/whisperbridge/services/ocr_translation_service.py](src/whisperbridge/services/ocr_translation_service.py)
- Screen capture: [src/whisperbridge/services/screen_capture_service.py](src/whisperbridge/services/screen_capture_service.py)
- Hotkeys: [src/whisperbridge/services/hotkey_service.py](src/whisperbridge/services/hotkey_service.py)
- Clipboard: [src/whisperbridge/services/clipboard_service.py](src/whisperbridge/services/clipboard_service.py)
- UI service: [src/whisperbridge/services/ui_service.py](src/whisperbridge/services/ui_service.py)
- Copy → Translate: [src/whisperbridge/services/copy_translate_service.py](src/whisperbridge/services/copy_translate_service.py)
- Theme: [src/whisperbridge/services/theme_service.py](src/whisperbridge/services/theme_service.py)
- Paste: [src/whisperbridge/services/paste_service.py](src/whisperbridge/services/paste_service.py)
- Config runtime service: [src/whisperbridge/services/config_service.py](src/whisperbridge/services/config_service.py)

UI (Qt / PySide6):
- App/lifecycle: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)
- Main window: [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py)
- Overlay window: [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py)
- Selection overlay: [src/whisperbridge/ui_qt/selection_overlay.py](src/whisperbridge/ui_qt/selection_overlay.py)
- Settings dialog: [src/whisperbridge/ui_qt/settings_dialog.py](src/whisperbridge/ui_qt/settings_dialog.py)
- System tray: [src/whisperbridge/ui_qt/tray.py](src/whisperbridge/ui_qt/tray.py)
- Workers: [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py)

Utilities:
- Translation helpers: [src/whisperbridge/utils/translation_utils.py](src/whisperbridge/utils/translation_utils.py)
- Image preprocessing: [src/whisperbridge/utils/image_utils.py](src/whisperbridge/utils/image_utils.py)
- Screen utilities: [src/whisperbridge/utils/screen_utils.py](src/whisperbridge/utils/screen_utils.py)
- Keyboard utilities: [src/whisperbridge/utils/keyboard_utils.py](src/whisperbridge/utils/keyboard_utils.py)
- Overlay helpers: [src/whisperbridge/utils/overlay_utils.py](src/whisperbridge/utils/overlay_utils.py)
- Window helpers: [src/whisperbridge/utils/window_utils.py](src/whisperbridge/utils/window_utils.py)
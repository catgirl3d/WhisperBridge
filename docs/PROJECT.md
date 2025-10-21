## Project Overview

WhisperBridge is a desktop application for fast on-screen text extraction and translation (OCR → AI translation). Users select a screen region, extract text via OCR, and translate it using a configured AI provider. The UI uses a Qt (PySide6) desktop interface with overlays, a system tray, and global hotkeys.

## Development

Run the Qt UI during development:
- Development entrypoint: [src/main.py](src/main.py)
  - Initializes logging, creates the Qt application, and starts the event loop.
  - Command:
    - python src/main.py

Runtime entrypoint used during development:
- Application entry module: [src/main.py](src/main.py)
  - Initializes logging, creates the Qt application, and starts the event loop.

Packaging and console script mapping:
- Packaging console script: pyproject.toml currently defines whisperbridge = whisperbridge.main:main. Runtime entry (development) is now src/main.py. Consider updating the console script mapping to point to src.main:main if you want the package entry to match the in-repo runtime entry.

## Architecture

High-level layout:
- Sources: [src/whisperbridge/](src/whisperbridge/)
- UI (Qt): [src/whisperbridge/ui_qt/](src/whisperbridge/ui_qt/)
- Core infrastructure: [src/whisperbridge/core/](src/whisperbridge/core/)
- Services (business logic): [src/whisperbridge/services/](src/whisperbridge/services/)
- Providers: [src/whisperbridge/providers/](src/whisperbridge/providers/)
- Utilities: [src/whisperbridge/utils/](src/whisperbridge/utils/)
- Additional guidance: [docs/ARCHITECTURE_GUIDELINES.md](docs/ARCHITECTURE_GUIDELINES.md)

Primary design patterns:
- Service layer orchestrated by the Qt application; business logic lives under [src/whisperbridge/services/](src/whisperbridge/services/).
- UI runs on the Qt main thread; heavy tasks run in QThreads using QObject workers located in [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py).
- Settings and runtime configuration are provided by a Pydantic model at [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py) and managed at runtime via [src/whisperbridge/services/config_service.py](src/whisperbridge/services/config_service.py).

## Standardized Window Architecture

All overlay-style windows subclass the standardized base for consistent behavior:
- Base class: [python.StyledOverlayWindow](src/whisperbridge/ui_qt/styled_overlay_base.py:31)
  - Unified close/dismiss policy via [python.BaseWindow.dismiss](src/whisperbridge/ui_qt/base_window.py:7) and [python.BaseWindow.closeEvent](src/whisperbridge/ui_qt/base_window.py:14)
  - Frameless drag and edge-resize
  - Minibar collapse/restore via [python.StyledOverlayWindow.collapse_to_minibar](src/whisperbridge/ui_qt/styled_overlay_base.py:397) and [python.StyledOverlayWindow.restore_from_minibar](src/whisperbridge/ui_qt/styled_overlay_base.py:436)
  - Geometry persistence via [python.StyledOverlayWindow.restore_geometry](src/whisperbridge/ui_qt/styled_overlay_base.py:164) and [python.StyledOverlayWindow.capture_geometry](src/whisperbridge/ui_qt/styled_overlay_base.py:177)
  - Top-right control buttons (collapse/close) and optional settings button
- Companion minibar: [python.MiniBarOverlay](src/whisperbridge/ui_qt/minibar_overlay.py:13) with title sync from the owner
- Example consumer: translator overlay migrated to base: [python.OverlayWindow](src/whisperbridge/ui_qt/overlay_window.py:87)

UI lifecycle and orchestration:
- Qt app and lifecycle: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)
- Main window: [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py)
- Translator overlay: [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py)
- Selection overlay: [src/whisperbridge/ui_qt/selection_overlay.py](src/whisperbridge/ui_qt/selection_overlay.py)
- System tray: [src/whisperbridge/ui_qt/tray.py](src/whisperbridge/ui_qt/tray.py)
- Settings dialog: [src/whisperbridge/ui_qt/settings_dialog.py](src/whisperbridge/ui_qt/settings_dialog.py)
- UI service manages creation/show/hide/toggle of overlays: [src/whisperbridge/services/ui_service.py](src/whisperbridge/services/ui_service.py)

## Threading Model and Signals

- All Qt UI creation and mutation must occur on the Qt main thread.
- Long-running work runs in background threads using QThread and QObject workers:
  - Workers: [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py)
  - Wiring/threads created in: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)
  - Results/progress returned to the main thread via signals
- Reference guidelines: [docs/THREADS_SIGNALS.md](docs/THREADS_SIGNALS.md)

## Configuration

Canonical settings model:
- [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py)

Notable defaults (see source for exact values):
- Provider and models:
  - Default provider: openai
  - OpenAI model: gpt-5-nano
  - Google model: gemini-1.5-flash
- OCR initialization:
  - initialize_ocr default: False
- Hotkeys (defaults):
  - translate_hotkey: ctrl+shift+t
  - quick_translate_hotkey: ctrl+shift+q
  - activation_hotkey: ctrl+shift+a
  - copy_translate_hotkey: ctrl+shift+j
- Clipboard polling:
  - clipboard_poll_timeout_ms: 2000
- System prompt:
  - Defined in the settings model
- Configuration persistence and keys:
  - Settings manager: [src/whisperbridge/core/settings_manager.py](src/whisperbridge/core/settings_manager.py)
  - Runtime config service: [src/whisperbridge/services/config_service.py](src/whisperbridge/services/config_service.py)

## Dependencies and Tooling

- Project metadata and dependencies: [pyproject.toml](pyproject.toml)
- Core libraries include OCR, screen capture, AI clients, configuration, and desktop integration (e.g., easyocr, pillow, mss, openai, google-generativeai, httpx, tenacity, pydantic, pydantic-settings, keyring, appdirs, loguru, click, pynput, pystray, comtypes).
- Optional extras for Qt desktop UI (PySide6, qtawesome) via the "qt" extra in [pyproject.toml](pyproject.toml).
- Developer tooling (black, isort, flake8, mypy, pytest) configured in [pyproject.toml](pyproject.toml).

## Providers and API Manager

- Provider adapter(s): [src/whisperbridge/providers/google_chat_adapter.py](src/whisperbridge/providers/google_chat_adapter.py)
- API orchestration: [src/whisperbridge/core/api_manager.py](src/whisperbridge/core/api_manager.py)
- Translation service: [src/whisperbridge/services/translation_service.py](src/whisperbridge/services/translation_service.py)

## Testing

- Pytest configuration expects tests under a tests/ directory (see [pyproject.toml](pyproject.toml)).
- Repository currently has [test_workers.py](test_workers.py) at the project root.
- Recommended actions:
  - Create a tests/ directory and move root tests under tests/, or
  - Adjust pytest configuration to discover root-level tests
- Prioritize tests for services (translation, OCR/processing, API manager) and utilities.

## Key Workflows

Main translation pipeline (Capture → OCR → Translate → Display):
1) Trigger: user hotkey or tray
2) Region selection via overlay: [src/whisperbridge/ui_qt/selection_overlay.py](src/whisperbridge/ui_qt/selection_overlay.py)
3) Worker/thread initialization: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py) + [src/whisperbridge/ui_qt/workers.py](src/whisperbridge/ui_qt/workers.py)
4) Worker steps:
   - Capture screen region: [src/whisperbridge/services/screen_capture_service.py](src/whisperbridge/services/screen_capture_service.py)
   - Perform OCR: [src/whisperbridge/services/ocr_service.py](src/whisperbridge/services/ocr_service.py)
   - Orchestrate translation: [src/whisperbridge/services/ocr_translation_service.py](src/whisperbridge/services/ocr_translation_service.py), using [src/whisperbridge/services/translation_service.py](src/whisperbridge/services/translation_service.py)
5) Results are emitted back to the UI thread and displayed via UI service and windows:
   - [src/whisperbridge/services/ui_service.py](src/whisperbridge/services/ui_service.py)
   - [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py)

Copy → Translate flow:
- Hotkey-driven; implemented by [src/whisperbridge/services/copy_translate_service.py](src/whisperbridge/services/copy_translate_service.py) with orchestration in [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)

Manual translator UI:
- Translator overlay and main window:
  - [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py)
  - [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py)
- Settings UI:
  - [src/whisperbridge/ui_qt/settings_dialog.py](src/whisperbridge/ui_qt/settings_dialog.py)

## Hotkeys

Defaults:
- Stored in the settings model: [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py)

Registration and lifecycle:
- App wiring: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)
- Keyboard utilities and service:
  - [src/whisperbridge/core/keyboard_manager.py](src/whisperbridge/core/keyboard_manager.py)
  - [src/whisperbridge/services/hotkey_service.py](src/whisperbridge/services/hotkey_service.py)

Conditional registration:
- OCR-dependent hotkeys may be conditionally enabled based on OCR initialization (see UI wiring in [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py))

## Practical Notes and Maintenance

- Provider defaults and model names live in [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py). When adding/removing providers, update both [pyproject.toml](pyproject.toml) and configuration defaults.
- OCR initialization is opt-in by default. If OCR-dependent hotkeys must always be available, enable initialization in settings or provide an explicit initialization action in UI logic.
- Packaging alignment:
  - Packaging console script: pyproject.toml currently defines whisperbridge = whisperbridge.main:main. Runtime entry (development) is now src/main.py. Consider updating the console script mapping to point to src.main:main if you want the package entry to match the in-repo runtime entry.
- Documentation reference for threading and UI rules:
  - [docs/THREADS_SIGNALS.md](docs/THREADS_SIGNALS.md)

## Quick References

Core / entry points:
- Launcher: [src/main.py](src/main.py)
- Qt app module: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)

Core infrastructure and configuration:
- Settings model and key helpers: [src/whisperbridge/core/config.py](src/whisperbridge/core/config.py)
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
- Config runtime service: [src/whisperbridge/services/config_service.py](src/whisperbridge/services/config_service.py)

UI (Qt / PySide6):
- App/lifecycle: [src/whisperbridge/ui_qt/app.py](src/whisperbridge/ui_qt/app.py)
- Main window: [src/whisperbridge/ui_qt/main_window.py](src/whisperbridge/ui_qt/main_window.py)
- Translator overlay: [src/whisperbridge/ui_qt/overlay_window.py](src/whisperbridge/ui_qt/overlay_window.py)
- Selection overlay: [src/whisperbridge/ui_qt/selection_overlay.py](src/whisperbridge/ui_qt/selection_overlay.py)
- Settings dialog: [src/whisperbridge/ui_qt/settings_dialog.py](src/whisperbridge/ui_qt/settings_dialog.py)
- System tray: [src/whisperbridge/ui_qt/tray.py](src/whisperbridge/ui_qt/tray.py)
- Standardized window base: [python.StyledOverlayWindow](src/whisperbridge/ui_qt/styled_overlay_base.py:31), minibar: [python.MiniBarOverlay](src/whisperbridge/ui_qt/minibar_overlay.py:13)

Utilities:
- Translation helpers: [src/whisperbridge/utils/translation_utils.py](src/whisperbridge/utils/translation_utils.py)
- Image preprocessing: [src/whisperbridge/utils/image_utils.py](src/whisperbridge/utils/image_utils.py)
- Screen utilities: [src/whisperbridge/utils/screen_utils.py](src/whisperbridge/utils/screen_utils.py)
- Keyboard utilities: [src/whisperbridge/utils/keyboard_utils.py](src/whisperbridge/utils/keyboard_utils.py)
- Window helpers: [src/whisperbridge/utils/window_utils.py](src/whisperbridge/utils/window_utils.py)
- Language helpers: [src/whisperbridge/utils/language_utils.py](src/whisperbridge/utils/language_utils.py)
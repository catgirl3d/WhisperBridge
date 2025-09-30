## Project Overview

WhisperBridge is a desktop application for quick on-screen text extraction and translation (OCR → AI translation). Users capture a screen region, extract text via OCR and translate it using a configured AI provider. The UI is a Qt (PySide6) desktop interface with overlays, a system tray, and global hotkeys.

## Development Commands

Running the Qt UI (recommended)
- Launcher script: [`scripts/run_qt_app.py`](scripts/run_qt_app.py:1)
  - This launcher sets up the environment and imports the application entry from [`src/main.py`](src/main.py:1). Run it with:
    ```bash
    python scripts/run_qt_app.py
    ```

Application entrypoint
- The runtime entrypoint for development in this repository is [`src/main.py`](src/main.py:1), which initializes logging and starts the Qt application via [`src/whisperbridge/ui_qt/app.py::init_qt_app()`](src/whisperbridge/ui_qt/app.py:937).

Note about packaging / console script
- The project declares a console script in [`pyproject.toml`](pyproject.toml:88-90):
  - whisperbridge = "whisperbridge.main:main"
- In this repository the runtime entrypoint is implemented at [`src/main.py`](src/main.py:1), which is module `main`. There is no `src/whisperbridge/main.py`. If you intend to publish a console script, update the mapping in [`pyproject.toml`](pyproject.toml:88-90) to match the packaged module layout or move the entrypoint accordingly.

Code quality / developer tools (configured in [`pyproject.toml`](pyproject.toml:100))
```bash
black src/      # Code formatting
isort src/      # Import sorting
flake8 src/     # Linting
mypy src/       # Type checking
```

## Architecture

High-level layout
- Sources: [`src/whisperbridge/`](src/whisperbridge/:1)
- UI (Qt): [`src/whisperbridge/ui_qt/`](src/whisperbridge/ui_qt/:1)
- Core managers: [`src/whisperbridge/core/`](src/whisperbridge/core/:1)
- Services (business logic): [`src/whisperbridge/services/`](src/whisperbridge/services/:1)
- Utilities: [`src/whisperbridge/utils/`](src/whisperbridge/utils/:1)

Primary design patterns
- Service layer: business logic lives in services (translation, OCR, screen capture, hotkeys, etc.) and is orchestrated by the Qt application.
- Qt main thread / background workers: UI is handled in the Qt main thread while heavy tasks (capture → OCR → translate) run in QThreads; example worker is [`src/whisperbridge/ui_qt/app.py::CaptureOcrTranslateWorker`](src/whisperbridge/ui_qt/app.py:49).
- Settings and runtime configuration are provided by a Pydantic-based settings model in [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:19) and managed at runtime via `config_service` ([`src/whisperbridge/services/config_service.py`](src/whisperbridge/services/config_service.py:1)).

Key UI lifecycle
- The Qt application class is implemented at [`src/whisperbridge/ui_qt/app.py::QtApp`](src/whisperbridge/ui_qt/app.py:145). Use:
  - `get_qt_app()` / `init_qt_app()` in [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:929) to access or initialize the global app.
  - `QtApp.run()` starts the Qt event loop (see [`src/whisperbridge/ui_qt/app.py::run()`](src/whisperbridge/ui_qt/app.py:821)).

## Configuration

Settings model
- The canonical settings model is [`src/whisperbridge/core/config.py::Settings`](src/whisperbridge/core/config.py:19).
- Important default fields (verify source):
  - API provider and models:
    - `api_provider` (default `"openai"`) — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:29)
    - `openai_model` default `"gpt-5-nano"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:30)
    - `google_model` default `"gemini-1.5-flash"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:31)
  - OCR initialization:
    - `initialize_ocr` default `False` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:85)
  - Hotkeys (defaults are defined here and used during app startup):
    - `translate_hotkey` default `"ctrl+shift+t"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:60)
    - `quick_translate_hotkey` default `"ctrl+shift+q"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:61)
    - `activation_hotkey` default `"ctrl+shift+a"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:62)
    - `copy_translate_hotkey` default `"ctrl+shift+j"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:63)
  - Clipboard polling:
    - `clipboard_poll_timeout_ms` default `2000` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:69)
  - System prompt (GPT):
    - `system_prompt` default shown in the model — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:75)

Settings persistence and keyring
- Credentials and key handling: helpers are implemented in [`src/whisperbridge/core/config.py::load_api_key()` / `save_api_key()` / `delete_api_key()`](src/whisperbridge/core/config.py:179).
- Runtime access + persistence is managed via the runtime config service at [`src/whisperbridge/services/config_service.py`](src/whisperbridge/services/config_service.py:1) (singleton `config_service`).

Configuration path
- Default config directory: returned by `get_config_path()` → `Path.home() / ".whisperbridge"` — [`src/whisperbridge/core/config.py::get_config_path()`](src/whisperbridge/core/config.py:167).

## Dependencies and Tools

Declared dependencies (from [`pyproject.toml`](pyproject.toml:33))
- Core runtime dependencies (as declared):
  - pynput, pystray, pillow, mss, easyocr, openai, google-generativeai, httpx, tenacity, pydantic, pydantic-settings, keyring, appdirs, loguru, click, comtypes
  - See the exact list at [`pyproject.toml`](pyproject.toml:33-50).

Optional / extras
- Qt extras for desktop UI: [`pyproject.toml` optional-dependency "qt"](pyproject.toml:53-56) — PySide6 and qtawesome.

Notes about screen capture and OCR
- OCR: project depends on EasyOCR (declared in [`pyproject.toml`](pyproject.toml:38)) and the code references OCR services — check [`src/whisperbridge/services/ocr_service.py`](src/whisperbridge/services/ocr_service.py:1) for implementation.
- Screen capture libraries: both `pillow` and `mss` are included in declared dependencies; implementation details (which backend is used by default) live in [`src/whisperbridge/services/screen_capture_service.py`](src/whisperbridge/services/screen_capture_service.py:1). If you need a deterministic backend for all platforms, inspect that module and choose / pin the preferred library.

Dev tooling
- Development extras and testing tools are declared in [`pyproject.toml`](pyproject.toml:57-77) under `[project.optional-dependencies]` → `dev` and tooling sections (black, isort, flake8, mypy, pytest, sphinx, etc.).

## Testing

- Pytest configuration is present in [`pyproject.toml`](pyproject.toml:150-156); tests are expected under `tests/` by default.
- The repository currently does not include a `tests/` suite. Adding unit and integration tests (especially for non-UI services: translation, OCR/processing, API manager) is recommended.

## Key Workflows

Main translation flow (Capture → OCR → Translate → Overlay)
1. User triggers translation (hotkey or tray action).
2. Selection overlay is shown: [`src/whisperbridge/ui_qt/selection_overlay.py`](src/whisperbridge/ui_qt/selection_overlay.py:1).
3. After selection, [`src/whisperbridge/ui_qt/app.py::QtApp._on_selection_completed()`](src/whisperbridge/ui_qt/app.py:647) creates a background worker [`src/whisperbridge/ui_qt/app.py::CaptureOcrTranslateWorker`](src/whisperbridge/ui_qt/app.py:49) and runs it in a `QThread`.
4. Worker performs capture via [`src/whisperbridge/services/screen_capture_service.py`](src/whisperbridge/services/screen_capture_service.py:1) and OCR via [`src/whisperbridge/services/ocr_service.py`](src/whisperbridge/services/ocr_service.py:1).
5. If an API key is configured, translation calls are done by [`src/whisperbridge/services/translation_service.py`](src/whisperbridge/services/translation_service.py:1).
6. Results are shown via the UI service: [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:1) → overlay UI in [`src/whisperbridge/ui_qt/overlay_window.py`](src/whisperbridge/ui_qt/overlay_window.py:1).

Copy → Translate flow
- Triggered by `copy_translate_hotkey` (default `"ctrl+shift+j"`), implemented by [`src/whisperbridge/services/copy_translate_service.py`](src/whisperbridge/services/copy_translate_service.py:1) and integrated with the Qt app's copy-translate handling in [`src/whisperbridge/ui_qt/app.py::_on_copy_translate_hotkey()`](src/whisperbridge/ui_qt/app.py:592).

Standard translator window flow
- Manual translation via the overlay / main window is provided by [`src/whisperbridge/ui_qt/overlay_window.py`](src/whisperbridge/ui_qt/overlay_window.py:1) and the main window [`src/whisperbridge/ui_qt/main_window.py`](src/whisperbridge/ui_qt/main_window.py:1). Settings dialog is [`src/whisperbridge/ui_qt/settings_dialog.py`](src/whisperbridge/ui_qt/settings_dialog.py:1).

Hotkey registration
- Defaults are stored in [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:60).
- Registration is performed in [`src/whisperbridge/ui_qt/app.py::_register_default_hotkeys()`](src/whisperbridge/ui_qt/app.py:353) using the `KeyboardManager` (`src/whisperbridge/core/keyboard_manager.py`) and `HotkeyService` (`src/whisperbridge/services/hotkey_service.py`).

## Main files (quick references)

Core / entry points
- Launcher: [`scripts/run_qt_app.py`](scripts/run_qt_app.py:1)
- Application entry: [`src/main.py`](src/main.py:1)
- Qt initializer and main app class: [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:1)

Core managers and configuration
- Settings model and keyring helpers: [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:1)
- Settings manager: [`src/whisperbridge/core/settings_manager.py`](src/whisperbridge/core/settings_manager.py:1)
- API manager: [`src/whisperbridge/core/api_manager.py`](src/whisperbridge/core/api_manager.py:1)
- Keyboard manager: [`src/whisperbridge/core/keyboard_manager.py`](src/whisperbridge/core/keyboard_manager.py:1)
- Logger setup: [`src/whisperbridge/core/logger.py`](src/whisperbridge/core/logger.py:1)

Services
- Translation service: [`src/whisperbridge/services/translation_service.py`](src/whisperbridge/services/translation_service.py:1)
- OCR service: [`src/whisperbridge/services/ocr_service.py`](src/whisperbridge/services/ocr_service.py:1)
- Screen capture: [`src/whisperbridge/services/screen_capture_service.py`](src/whisperbridge/services/screen_capture_service.py:1)
- Hotkey service: [`src/whisperbridge/services/hotkey_service.py`](src/whisperbridge/services/hotkey_service.py:1)
- Clipboard service: [`src/whisperbridge/services/clipboard_service.py`](src/whisperbridge/services/clipboard_service.py:1)
- UI service: [`src/whisperbridge/services/ui_service.py`](src/whisperbridge/services/ui_service.py:1)
- Copy→Translate service: [`src/whisperbridge/services/copy_translate_service.py`](src/whisperbridge/services/copy_translate_service.py:1)

UI (Qt / PySide6)
- Qt app and lifecycle: [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:1)
- Main window: [`src/whisperbridge/ui_qt/main_window.py`](src/whisperbridge/ui_qt/main_window.py:1)
- Overlay window: [`src/whisperbridge/ui_qt/overlay_window.py`](src/whisperbridge/ui_qt/overlay_window.py:1)
- Selection overlay: [`src/whisperbridge/ui_qt/selection_overlay.py`](src/whisperbridge/ui_qt/selection_overlay.py:1)
- Settings dialog: [`src/whisperbridge/ui_qt/settings_dialog.py`](src/whisperbridge/ui_qt/settings_dialog.py:1)
- System tray manager: [`src/whisperbridge/ui_qt/tray.py`](src/whisperbridge/ui_qt/tray.py:1)
- Minibar overlay: [`src/whisperbridge/ui_qt/minibar_overlay.py`](src/whisperbridge/ui_qt/minibar_overlay.py:1)

Utilities
- Translation helpers: [`src/whisperbridge/utils/translation_utils.py`](src/whisperbridge/utils/translation_utils.py:1)
- Image preprocessing: [`src/whisperbridge/utils/image_utils.py`](src/whisperbridge/utils/image_utils.py:1)
- Screen utilities: [`src/whisperbridge/utils/screen_utils.py`](src/whisperbridge/utils/screen_utils.py:1)
- Keyboard utilities: [`src/whisperbridge/utils/keyboard_utils.py`](src/whisperbridge/utils/keyboard_utils.py:1)
- Archived/moved helper: [`src/whisperbridge/utils/archive/api_utils.py`](src/whisperbridge/utils/archive/api_utils.py:1)

## Practical notes and maintenance items

- Default AI model name(s) are available in the settings model:
  - `openai_model = "gpt-5-nano"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:30)
  - `google_model = "gemini-1.5-flash"` — [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:31)
  - If you add or remove providers, ensure `pyproject.toml` and `config` defaults are adjusted consistently.

- OCR initialization is opt-in by default (`initialize_ocr = False`). If OCR-dependent hotkeys must always be available, set that flag to `True` in settings or let the UI/Tray provide an on-demand initialization action (see [`src/whisperbridge/ui_qt/app.py::QtApp._initialize_ocr_service()`](src/whisperbridge/ui_qt/app.py:426)).

- Packaging: the console script declared in [`pyproject.toml`](pyproject.toml:88-90) needs review if you intend to build a wheel/installer. During local development prefer the launcher [`scripts/run_qt_app.py`](scripts/run_qt_app.py:1) which imports [`src/main.py`](src/main.py:1).

- Tests: add a `tests/` suite and target non-UI services first (translation, API manager, OCR request/response parsing) to improve coverage. Pytest configuration is present in [`pyproject.toml`](pyproject.toml:150-156).

## Where to look for common tasks

- Start app / debug UI initialization:
  - [`scripts/run_qt_app.py`](scripts/run_qt_app.py:1) → imports [`src/main.py`](src/main.py:1) → initializes [`src/whisperbridge/ui_qt/app.py`](src/whisperbridge/ui_qt/app.py:937).

- Change default hotkeys:
  - Edit the defaults or override via runtime settings managed by [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:60) and persisted via [`src/whisperbridge/core/settings_manager.py`](src/whisperbridge/core/settings_manager.py:1).

- Add or change AI provider:
  - Update `api_provider` / model defaults in [`src/whisperbridge/core/config.py`](src/whisperbridge/core/config.py:29-35) and ensure corresponding provider adapter exists under [`src/whisperbridge/providers/`](src/whisperbridge/providers/:1).

- Inspect OCR / capture backends:
  - OCR services: [`src/whisperbridge/services/ocr_service.py`](src/whisperbridge/services/ocr_service.py:1)
  - Screen capture: [`src/whisperbridge/services/screen_capture_service.py`](src/whisperbridge/services/screen_capture_service.py:1)
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


src/whisperbridge/ui_qt/app.py (OCR translation handling)
src/whisperbridge/ui_qt/settings_dialog.py (UI controls)
src/whisperbridge/ui_qt/overlay_window.py (checkbox persistence)
src/whisperbridge/services/translation_service.py (translation logic)
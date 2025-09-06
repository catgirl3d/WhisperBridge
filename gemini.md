## Project Overview
WhisperBridge is a desktop application designed for quick text translation using Optical Character Recognition (OCR) and the GPT API . Its main goal is to allow users to capture screen regions, extract text, and receive instant translations through an overlay interface, activated by global hotkeys . The target audience includes end-users who require on-demand translation of text appearing on their screen .

## Architecture & Structure
### High-level architecture overview
WhisperBridge follows a layered service-oriented architecture built on the Qt framework . The system is designed around a central orchestrator, `QtApp`, which coordinates multiple specialized services for screen capture, OCR, and AI-powered translation .

### Key directories and their purposes
The core components are structured within the `src/whisperbridge/` directory :
*   `core/`: Contains core managers for API, OCR, keyboard, and settings .
*   `services/`: Encapsulates business logic services such as translation and screen capture .
*   `ui_qt/`: Holds Qt/PySide6 UI components .
*   `utils/`: Provides utility functions .
*   `models/`: Stores data models .

### Main components and how they interact
The `QtApp` class acts as the central orchestrator, managing the lifecycle of UI components and coordinating core services . Key services include:
*   **OCR Service**: For text extraction using EasyOCR .
*   **Translation Service**: Integrates with the GPT API for translation and includes caching .
*   **Screen Capture Service**: Handles cross-platform screen capture using MSS .
*   **Hotkey Service**: Manages global keyboard shortcuts via `pynput` .
*   **Overlay Service**: Displays translation results in overlay windows .
*   **Settings Manager**: Manages configuration using Pydantic settings .

### Data flow and system design
The main workflow follows a capture-OCR-translate pipeline orchestrated by the `CaptureOcrTranslateWorker` class, which runs in separate threads to maintain UI responsiveness .
1.  **Hotkey Press**: User presses a global hotkey (e.g., `Ctrl+Shift+T`) .
2.  **Screen Capture**: The `ScreenCaptureService` interactively captures a user-selected screen region .
3.  **OCR Processing**: The captured image is passed to `CaptureOcrTranslateWorker`, which then uses `OCRService` to extract text .
4.  **Translation**: The extracted text is sent to `TranslationService` for translation via the GPT API .
5.  **Display Results**: The translated text is then displayed to the user via an `OverlayWindow` .

## Development Setup
### Prerequisites and dependencies
The project requires Python 3.8 or higher . Key dependencies are listed in `pyproject.toml`  and `requirements.txt` . These include `PySide6` for the UI, `easyocr` for OCR, `openai` for AI translation, `mss` for screen capture, `pydantic` for configuration, and `keyring` for secure storage .

### Installation steps
While not explicitly detailed as installation steps, the `pyproject.toml` indicates the project can be installed as a package . The `requirements.txt` lists the necessary packages .

### Environment configuration
The application's settings are managed via Pydantic Settings with `keyring` integration for secure storage of API keys . Configuration files are stored in `~/.whisperbridge/` on macOS/Linux and `%USERPROFILE%\.whisperbridge\` on Windows . The `UI_BACKEND` environment variable is set to `qt` when running the Qt application .

### How to run the project locally
The recommended way to run the Qt-based UI is by executing the script `scripts/run_qt_app.py` . This script sets the `UI_BACKEND` to `qt` and invokes the main application entry point `src.main.main` . The `main` function in `src/main.py` is an asynchronous function and is run using `asyncio.run()` .

## Code Organization
### Coding standards and conventions
The project uses `black` for code formatting , `isort` for import sorting , `flake8` for linting , and `mypy` for type checking . These tools are configured in `pyproject.toml` .

### File naming patterns
Not explicitly defined, but generally follows Python conventions.

### Import/export patterns
Imports are managed by `isort` . The `src` directory is added to the system path for imports .

### Component structure
The UI components are located in `src/whisperbridge/ui_qt/` . Core components are organized into `core/`, `services/`, `ui_qt/`, `utils/`, and `models/` within `src/whisperbridge/` .

## Key Features & Implementation
### Main features and how they're implemented
*   **Global Hotkey Activation**: Activated by `Ctrl+Shift+T` . Implemented via `HotkeyService` .
*   **Interactive Screen Region Selection**: Handled by `ScreenCaptureService` .
*   **Multi-language OCR Text Recognition**: Uses `EasyOCR` via `OCRService` .
*   **AI-powered Translation with Caching**: Utilizes OpenAI's GPT API and other services through `TranslationService` and `APIManager` .
*   **Overlay Windows for Displaying Results**: Managed by `OverlayServiceQt` .
*   **Secure API Key Storage**: Achieved using the system `keyring` .
*   **Configurable Translation Settings and Language Pairs**: Handled by the `ConfigService` and `Settings` Pydantic model .

### Important algorithms or business logic
*   **OCR Auto-Swap**: The `ocr_auto_swap_en_ru` setting, when enabled, automatically swaps translation languages between English and Russian based on the detected language of the OCR output . This logic is implemented in `CaptureOcrTranslateWorker` within `src/whisperbridge/ui_qt/app.py` .
*   **API Request Retry Logic**: The `APIManager` handles retry logic for API calls .
*   **Asynchronous Operations**: The application uses `asyncio` for non-blocking operations, especially for API calls and UI responsiveness .

### API endpoints (if applicable)
The application primarily interacts with OpenAI's GPT API . The `APIManager` in `src/whisperbridge/core/api_manager.py` abstracts the API interactions .

### Database schema (if applicable)
There is no explicit database schema; settings are stored in JSON files and API keys in the system keyring  .

## Testing Strategy
### Testing frameworks used
The project uses `pytest`, `pytest-asyncio`, `pytest-cov`, and `pytest-mock` for testing .

### Test file organization
Tests are located in the `temp/tests/` directory . They include unit tests, integration tests for service interactions, OCR and translation pipeline tests, and UI component tests .

### How to run tests
The comprehensive test suite can be run with `python temp/tests/test_suite.py` . `pytest` is configured to discover tests in `test_*.py` files, classes starting with `Test`, and functions starting with `test_` .

### Testing best practices in this codebase
Tests are marked with categories like `slow`, `integration`, and `unit` .

## Build & Deployment
### Build process and scripts
The project uses `setuptools` for building . Build-related dependencies include `build` and `twine` .

### Deployment configuration
Not explicitly detailed in the provided context.

### Environment-specific settings
Settings are loaded from `settings.json` in the configuration directory and can be overridden by environment variables . API keys are loaded from the system keyring .

### CI/CD pipeline (if exists)
Not explicitly detailed in the provided context.

## Git Workflow
Not explicitly detailed in the provided context.

# Development Partnership and How We Should Partner

We build production code together. I handle implementation details while you guide architecture and catch complexity early.

## Core Workflow: Research → Plan → Implement → Validate

**Start every feature with:** "Let me research the codebase and create a plan before implementing."

1. **Research** - Understand existing patterns and architecture
2. **Plan** - Propose approach and verify with you
3. **Implement** - Build with tests and error handling
4. **Validate** - ALWAYS run formatters, linters, and tests after implementation

## Code Organization

**Keep functions small and focused:**
- If you need comments to explain sections, split into functions
- Group related functionality into clear packages
- Prefer many small files over few large ones

## Architecture Principles

**This is always a feature branch:**
- Delete old code completely - no deprecation needed
- No "removed code" or "added this line" comments - just do it

**Prefer explicit over implicit:**
- Clear function names over clever abstractions
- Obvious data flow over hidden magic
- Direct dependencies over service locators

## Maximize Efficiency

**Parallel operations:** Run multiple searches, reads, and greps in single messages
**Multiple agents:** Split complex tasks - one for tests, one for implementation
**Batch similar work:** Group related file edits together

## Problem Solving

**When stuck:** Stop. The simple solution is usually correct.

**When uncertain:** "Let me ultrathink about this architecture."

**When choosing:** "I see approach A (simple) vs B (flexible). Which do you prefer?"

Your redirects prevent over-engineering. When uncertain about implementation, stop and ask for guidance.

## Testing Strategy

**Match testing approach to code complexity:**
- Complex business logic: Write tests first (TDD)
- Simple CRUD operations: Write code first, then tests
- Hot paths: Add benchmarks after implementation

**Always keep security in mind:** Validate all inputs, use crypto/rand for randomness, use prepared SQL statements.

**Performance rule:** Measure before optimizing. No guessing.

## Progress Tracking

- **Use Todo lists** for task management
- **Clear naming** in all code

Focus on maintainable solutions over clever abstractions.

---
Generated using [Sidekick Dev]({REPO_URL}), your coding agent sidekick.

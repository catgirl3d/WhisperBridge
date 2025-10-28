# WhisperBridge


### [DOWNLOAD](https://github.com/catgirl3d/WhisperBridge/releases) | [README Українською](README.UA.md)

![1](docs/img/_251020140250.png) 

Desktop application for instant on-screen text translation using OCR and GPT API. Capture a screen region, extract text, and show the translation in an overlay, triggered by a global hotkey.

## Features

- **Screen region capture + OCR** - uses EasyOCR or LLM-based OCR for text recognition
- **Fast translation via GPT API** - instant translation of extracted text
- **Overlay with actions** - convenient copy and paste functionality
- **Global hotkey** - Ctrl+Shift+T by default
- **System tray** - tray icon and Settings window (Qt / PySide6)

Features (highlights)

- Multi-provider translation and OCR: OpenAI, Google Generative AI, and DeepL adapters supported.
- Copy-Translate: copy text to clipboard and trigger translation via hotkey (configurable).

## Quick Start

**Requirements:** Python 3.8+ (Windows/macOS/Linux)

### Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

```
Install dependencies (recommended for development)
pip install -e .[qt,dev]

Notes:
- The project declares optional extras in pyproject.toml; use the `qt` extra to install PySide6 and UI dependencies, and `dev` for developer tooling.
- For a minimal runtime-only install you can still use: `pip install -r requirements.txt`, but the editable install with extras is recommended during development.
```

### Run
 
```bash
# Run application with Qt UI
python src/main.py
```

Packaging and console script

Development:
python src/main.py

Packaged install:
After building and installing the package (e.g. `python -m build` / `pip install dist/*.whl`), the console script `whisperbridge` is available:

whisperbridge

Note: The project defines a console script in pyproject.toml. Verify that the entry point aligns with your preferred layout (src.main:main). If you prefer a packaged module wrapper, add `src/whisperbridge/main.py` delegating to `src/main.py` or update pyproject.toml accordingly.

## Configuration

### Settings Location

- **Windows:** `%USERPROFILE%\.whisperbridge\`
- **macOS/Linux:** `~/.whisperbridge/`

### API Key Setup

1. Open the Settings dialog in the application
2. Provide your OpenAI API key
3. The key will be stored securely via keyring

### Additional Settings

In the Settings window you can configure:
- UI themes
- Hotkeys
- Translation languages
- OCR parameters

Settings UI: inline help

The settings dialog includes "?" help icons next to many fields. Detailed help texts are centralized in:
src/whisperbridge/utils/help_texts.py
Edit those strings to customize tooltip content shown in the UI.

LLM-based OCR configuration

The app supports an LLM-based OCR engine in addition to EasyOCR. Configuration keys:
- ocr_engine: "easyocr" or "llm" (default: "easyocr")
- ocr_llm_prompt: custom prompt for the vision model (example: "Extract plain text from the image in natural reading order. Output only the text.")
- openai_vision_model: model name for OpenAI vision requests (e.g., "gpt-4o-mini")
- google_vision_model: model name for Google vision requests (e.g., "gemini-1.5-flash")

Flow: Capture → LLM OCR (image encoded & resized) → extract text → translate. If LLM returns an empty or failed response and `ocr_enabled` is true, the service falls back to EasyOCR automatically.

## Project Structure

### Key Files

| File | Description |
|------|-------------|
| `src/main.py` | Application entry point |
| `src/whisperbridge/core/config.py` | Settings and configuration model |
| `src/whisperbridge/ui_qt/app.py` | Qt application and initialization |
| `requirements.txt` | Python dependencies list |
| `pyproject.toml` | Project configuration |

### Architecture

Project structure (high level)

WhisperBridge/
├── docs/              # documentation and guidelines
├── src/
│   └── whisperbridge/
│       ├── core/      # core logic: config, API manager, settings
│       ├── services/  # business services: OCR, translation, hotkeys
│       ├── providers/ # provider adapters: OpenAI, Google, DeepL
│       ├── ui_qt/     # Qt UI: app, windows, workers
│       ├── utils/     # stateless utilities: image, screen, language
│       └── models/    # pydantic models
├── tests/             # unit and integration tests
├── pyproject.toml
└── requirements.txt

Testing

Tests are in the `tests/` directory. Run the test suite with:
pytest tests/

For coverage:
pytest --cov=whisperbridge tests/

## Usage

1. **Launch application** - start WhisperBridge, icon will appear in system tray
2. **Configure API** - set up your OpenAI API key through Settings window
3. **Capture text** - press the hotkey (Ctrl+Shift+T by default)
4. **Select region** - select screen area containing text to translate
5. **Get translation** - translated text will appear in overlay

## Technical Details

- **OCR Engine:** EasyOCR or LLM-based OCR for text recognition in various formats
- **Translation API:** OpenAI GPT API for high-quality translation
- **UI Framework:** Qt/PySide6 for cross-platform interface
- **Security:** Keyring for secure API key storage

## Supported Platforms

- Windows 10/11
- macOS 10.15+
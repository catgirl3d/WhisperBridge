# WhisperBridge


### [DOWNLOAD](https://github.com/catgirl3d/WhisperBridge/releases/tag/WhisperBridge-v1.0.0-alpha) | [README Українською](README.UA.md)

![1](docs/img/_251020140250.png) 

Desktop application for instant on-screen text translation using OCR and GPT API. Capture a screen region, extract text, and show the translation in an overlay, triggered by a global hotkey.

## Features

- **Screen region capture + OCR** - uses EasyOCR for text recognition
- **Fast translation via GPT API** - instant translation of extracted text
- **Overlay with actions** - convenient copy and paste functionality
- **Global hotkey** - Ctrl+Shift+T by default
- **System tray** - tray icon and Settings window (Qt / PySide6)

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

### Run
 
```bash
# Run application with Qt UI
python src/main.py
```

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

```
WhisperBridge/
├── scripts/           # Launch scripts
├── src/
│   └── whisperbridge/
│       ├── core/      # Core logic
│       ├── ui_qt/     # Qt interface
│       └── utils/     # Utilities
├── requirements.txt   # Dependencies
└── pyproject.toml    # Project configuration
```

## Usage

1. **Launch application** - start WhisperBridge, icon will appear in system tray
2. **Configure API** - set up your OpenAI API key through Settings window
3. **Capture text** - press the hotkey (Ctrl+Shift+T by default)
4. **Select region** - select screen area containing text to translate
5. **Get translation** - translated text will appear in overlay

## Technical Details

- **OCR Engine:** EasyOCR for text recognition in various formats
- **Translation API:** OpenAI GPT API for high-quality translation
- **UI Framework:** Qt/PySide6 for cross-platform interface
- **Security:** Keyring for secure API key storage

## Supported Platforms

- Windows 10/11
- macOS 10.15+
# WhisperBridge

Desktop application for instant on-screen text translation using OCR and GPT API. Capture a screen region, extract text, and show the translation in an overlay, triggered by a global hotkey.

**Features**

- Screen region capture + OCR (EasyOCR)
- Fast translation via GPT API
- Overlay with copy/paste actions
- Global hotkey (Ctrl+Shift+T by default)
- System tray icon and Settings window (Qt / PySide6)

**Quick start**

Requirements: Python 3.8+ (Windows/macOS/Linux)

**Setup**

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
```

**Run (Qt UI)**

```bash
python scripts/run_qt_app.py
```

**Configuration**

- Settings location: Windows — %USERPROFILE%\.whisperbridge\, macOS/Linux — ~/.whisperbridge/
- Provide your OpenAI API key in the Settings dialog (stored securely via keyring).
- Themes, hotkeys, and languages are configurable in the Settings window.

*Key files**

- Launcher (Qt): scripts/run_qt_app.py
- App entry point: src/main.py
- Settings/config model: src/whisperbridge/core/config.py
- Qt app/initialization: src/whisperbridge/ui_qt/app.py
- Dependencies: requirements.txt, pyproject.toml

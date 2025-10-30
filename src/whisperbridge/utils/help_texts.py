"""
Help texts for WhisperBridge settings dialog.

Centralized dictionary of help texts for settings fields.
Each entry contains:
- 'tooltip': Short text shown on hover
- 'detailed': Rich HTML text shown on click (optional)
"""

HELP_TEXTS = {
    # API Tab
    "api.provider": {
        "tooltip": "Choose the AI provider for translations (OpenAI, Google, DeepL).",
        "detailed": "<b>AI Provider</b><br>Select the service to use for translations. Each provider has different models and pricing."
    },
    "api.key": {
        "tooltip": "Enter your API key for the selected provider.",
        "detailed": "<b>API Key</b><br>Securely store your API key. It will be encrypted and used for authentication with the provider."
    },
    "api.model": {
        "tooltip": "Select the AI model to use for translations.",
        "detailed": "<b>Model Selection</b><br>Choose the specific AI model. Newer models may provide better quality but cost more."
    },
    "api.timeout": {
        "tooltip": "Maximum time to wait for API responses (seconds).",
        "detailed": "<b>API Timeout</b><br>How long to wait for the provider to respond. Increase if you have slow internet."
    },
    "api.vision_model_openai": {
        "tooltip": "Model for OpenAI vision tasks (OCR with images).",
        "detailed": "<b>OpenAI Vision Model</b><br>Used for OCR when processing screenshots. Requires vision-capable model like gpt-4-vision."
    },
    "api.vision_model_google": {
        "tooltip": "Model for Google vision tasks (OCR with images).",
        "detailed": "<b>Google Vision Model</b><br>Used for OCR when processing screenshots. Requires vision-capable model like gemini-pro-vision."
    },
    "api.deepl_plan": {
        "tooltip": "Select your DeepL subscription plan (free or pro).",
        "detailed": "<b>DeepL Plan</b><br>Free plan has limits, Pro plan offers unlimited translations and better quality."
    },

    # Translation Tab
    "translation.auto_swap": {
        "tooltip": "Automatically swap English↔Russian for OCR translations.",
        "detailed": "<b>Auto-swap</b><br>When enabled, OCR translations will detect language and swap: English→Russian, Russian→English."
    },
    "translation.system_prompt": {
        "tooltip": "Custom instructions for the translation model.",
        "detailed": "<b>System Prompt</b><br>Instructions that guide how the AI translates."
    },

    # OCR Tab
    "ocr.initialize": {
        "tooltip": "Enable local OCR engine (EasyOCR) initialization on startup for fallback support.",
        "detailed": "<b>Initialize Local OCR</b><br>When enabled, the local EasyOCR engine will be loaded on startup. This provides fallback support when LLM OCR fails, but uses more memory and startup time."
    },
    "ocr.engine": {
        "tooltip": "Choose OCR method: easyocr (local) or llm (AI-powered).",
        "detailed": "<b>OCR Engine</b><br><b>easyocr:</b> Fast, local, works offline<br><b>llm:</b> Uses AI for better accuracy, requires API key"
    },
    "ocr.llm_prompt": {
        "tooltip": "Instructions for LLM-based OCR processing.",
        "detailed": "<b>LLM OCR Prompt</b><br>Tell the AI how to extract and format text from images."
    },
    "ocr.languages": {
        "tooltip": "Comma-separated list of languages for OCR (e.g., en,ru,es).",
        "detailed": "<b>OCR Languages</b><br>Languages to detect in images. Use ISO codes: en, ru, es, fr, de, etc. Multiple languages improve detection."
    },
    "ocr.confidence_threshold": {
        "tooltip": "Minimum confidence level for OCR text recognition (0.0-1.0).",
        "detailed": "<b>Confidence Threshold</b><br>Lower values accept more text but may include errors. Higher values are more accurate but may miss text."
    },
    "ocr.timeout": {
        "tooltip": "Maximum time to wait for OCR processing (seconds).",
        "detailed": "<b>OCR Timeout</b><br>How long to wait for OCR to complete. Increase for large images or slow hardware."
    },

    # Hotkeys Tab
    "hotkeys.show_translator": {
        "tooltip": "Hotkey to show the overlay translator window.",
        "detailed": "<b>Show Translator</b><br>Global hotkey to open the overlay translation interface. Format: ctrl+shift+t or alt+f1"
    },
    "hotkeys.capture_screen": {
        "tooltip": "Hotkey to capture screen region for OCR translation.",
        "detailed": "<b>Capture Screen</b><br>Select area of screen for OCR processing. Requires OCR to be enabled."
    },
    "hotkeys.translate": {
        "tooltip": "Hotkey to translate selected text.",
        "detailed": "<b>Translate</b><br>Translate currently selected text in any application."
    },
    "hotkeys.activate_app": {
        "tooltip": "Hotkey to show the main application window.",
        "detailed": "<b>Activate App</b><br>Global hotkey to bring up the main WhisperBridge window. Format: ctrl+shift+t or alt+f1"
    },
    "hotkeys.copy_translate": {
        "tooltip": "Hotkey to copy clipboard text and translate it.",
        "detailed": "<b>Copy→Translate</b><br>Copies text from clipboard and opens translator. Useful for text that can't be selected."
    },
    "hotkeys.auto_copy_hotkey": {
        "tooltip": "Automatically copy translated text\nto clipboard when using hotkeys.",
        "detailed": "<b>Auto-copy (Hotkey)</b><br>When enabled, translations via hotkeys are automatically copied to clipboard."
    },
    "hotkeys.auto_copy_main": {
        "tooltip": "Automatically copy translated text\nto clipboard (main translator window).",
        "detailed": "<b>Auto-copy (Main Window)</b><br>When enabled, translations in the main window are automatically copied to clipboard."
    },
    "hotkeys.clipboard_poll_timeout": {
        "tooltip": "How often to check clipboard for changes (milliseconds).",
        "detailed": "<b>Clipboard Polling</b><br>Lower values respond faster but use more CPU. Higher values save battery but may miss quick copies."
    },

    # General Tab
    "general.theme": {
        "tooltip": "Choose UI theme: dark, light, or system default.",
        "detailed": "<b>Theme</b><br><b>Dark:</b> Easy on eyes in low light<br><b>Light:</b> Classic bright interface<br><b>System:</b> Follows OS preference"
    },
    "general.log_level": {
        "tooltip": "Set logging verbosity for debugging and troubleshooting.",
        "detailed": "<b>Log Level</b><br><b>DEBUG:</b> Most verbose, for development<br><b>INFO:</b> Normal operation<br><b>WARNING/ERROR:</b> Only issues"
    },
    "general.show_notifications": {
        "tooltip": "Show system tray notifications for translation results.",
        "detailed": "<b>Notifications</b><br>When enabled, you'll see popups for completed translations and errors."
    },
    "general.stylist_cache": {
        "tooltip": "Cache Text Stylist results to avoid repeated API calls.",
        "detailed": "<b>Stylist Cache</b><br>Speeds up repeated stylizing of the same text. Uses disk space but saves API costs."
    },
    "general.translation_cache": {
        "tooltip": "Cache translation results to avoid repeated API calls.",
        "detailed": "<b>Translation Cache</b><br>Speeds up repeated translations of the same text. Uses disk space but saves API costs."
    },
}
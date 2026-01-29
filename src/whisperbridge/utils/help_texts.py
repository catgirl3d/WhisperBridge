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
    "api.temperature_translation": {
        "tooltip": "Temperature for translation (0.0-2.0). Lower = more deterministic, higher = more creative.",
        "detailed": "<b>Translation Temperature</b><br>Controls creativity and variability of translation.<br><br><b>Values:</b><br>• <b>0.0-0.3:</b> Most accurate, literal translation<br>• <b>0.4-0.7:</b> Balanced translation (technical texts)<br>• <b>0.8-1.2:</b> More natural, adaptive translation (default)<br>• <b>1.3-2.0:</b> Creative translation with interpretation<br><br><b>Recommendations:</b><br>• Documentation: 0.3-0.5<br>• Business: 0.5-0.8<br>• General text: 0.8-1.2<br>• Creative text: 1.0-1.5"
    },
    "api.temperature_vision": {
        "tooltip": "Temperature for OCR/vision (0.0-2.0). Lower = more accurate, higher = more interpretive.",
        "detailed": "<b>Vision/OCR Temperature</b><br>Controls text recognition behavior from images.<br><br><b>Values:</b><br>• <b>0.0:</b> Maximum accuracy (recommended)<br>• <b>0.1-0.3:</b> Minimal interpretation for unclear text<br>• <b>0.4-0.7:</b> Moderate interpretation (handwriting)<br>• <b>0.8+:</b> High interpretation (may be inaccurate)<br><br><b>Recommendations:</b><br>• Printed text: 0.0 (default)<br>• Screenshots: 0.0-0.1<br>• Handwriting: 0.2-0.5<br>• Blurry images: 0.3-0.7<br><br><b>Default:</b> 0.0 for maximum accuracy."
    },
    "api.temperature_stylist": {
        "tooltip": "Temperature for text stylist mode (0.0-2.0). Lower = more faithful, higher = more creative.",
        "detailed": "<b>Stylist Temperature</b><br>Controls creativity and variability in text rewriting.<br><br><b>Values:</b><br>• <b>0.0-0.3:</b> Most faithful to original meaning<br>• <b>0.4-0.7:</b> Balanced rewriting (recommended)<br>• <b>0.8-1.2:</b> More creative rewriting (default)<br>• <b>1.3-2.0:</b> Highly creative with interpretation<br><br><b>Recommendations:</b><br>• Technical documentation: 0.2-0.5<br>• Business correspondence: 0.4-0.8<br>• General content: 0.8-1.2<br>• Creative writing: 1.0-1.5<br><br><b>Default:</b> 1.2 for balanced creativity."
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
    "ocr.engine": {
        "tooltip": "OCR method (LLM-only).",
        "detailed": "<b>OCR Engine</b><br><b>llm:</b> Uses AI for text recognition."
    },
    "ocr.llm_prompt": {
        "tooltip": "Instructions for LLM-based OCR processing.",
        "detailed": "<b>LLM OCR Prompt</b><br>Tell the AI how to extract and format text from images."
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
    # "general.theme": {
    #     "tooltip": "Choose UI theme: dark, light, or system default.",
    #     "detailed": "<b>Theme</b><br><b>Dark:</b> Easy on eyes in low light<br><b>Light:</b> Classic bright interface<br><b>System:</b> Follows OS preference"
    # },
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
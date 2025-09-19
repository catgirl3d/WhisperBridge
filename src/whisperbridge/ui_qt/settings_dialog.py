"""
Settings Dialog for WhisperBridge Qt UI.

Provides a comprehensive settings interface with tabs for different configuration categories.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QFormLayout, QGroupBox, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

from ..core.settings_manager import settings_manager
from ..services.config_service import config_service, SettingsObserver
from ..core.config import Settings
from ..core.api_manager import get_api_manager, APIProvider
from loguru import logger


class ApiTestWorker(QObject):
    """Worker for testing API key asynchronously."""
    finished = Signal(bool, str)  # success, error_message

    def __init__(self, provider: str, api_key: str, model: str):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.model = model

    def run(self):
        """Test the API key for the specified provider."""
        try:
            if self.provider == "openai":
                self._test_openai()
            elif self.provider == "anthropic":
                self._test_anthropic()
            elif self.provider == "google":
                self._test_google()
            else:
                self.finished.emit(False, f"Unsupported provider: {self.provider}")

        except Exception as e:
            self.finished.emit(False, f"Ошибка подключения: {str(e)}")

    def _test_openai(self):
        """Test OpenAI API."""
        try:
            import openai

            # Create a temporary client for testing
            client = openai.OpenAI(api_key=self.api_key, timeout=10)

            # Make a simple test request
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )

            # If we get here, the API key is valid
            self.finished.emit(True, "")

        except openai.AuthenticationError:
            self.finished.emit(False, "Неверный API ключ")
        except openai.RateLimitError:
            self.finished.emit(False, "Превышен лимит запросов")
        except openai.APIError as e:
            self.finished.emit(False, f"Ошибка API: {str(e)}")
        except ImportError:
            self.finished.emit(False, "OpenAI library not installed")
        except Exception as e:
            self.finished.emit(False, f"Ошибка OpenAI: {str(e)}")

    def _test_anthropic(self):
        """Test Anthropic API."""
        try:
            import anthropic

            # Create a temporary client for testing
            client = anthropic.Anthropic(api_key=self.api_key, timeout=10)

            # Make a simple test request
            response = client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hello"}]
            )

            # If we get here, the API key is valid
            self.finished.emit(True, "")

        except Exception as e:
            if "authentication" in str(e).lower() or "api key" in str(e).lower():
                self.finished.emit(False, "Неверный API ключ")
            elif "rate" in str(e).lower():
                self.finished.emit(False, "Превышен лимит запросов")
            else:
                self.finished.emit(False, f"Ошибка Anthropic: {str(e)}")

    def _test_google(self):
        """Test Google API."""
        try:
            import google.generativeai as genai

            # Configure the API
            genai.configure(api_key=self.api_key)

            # Create a model instance
            model = genai.GenerativeModel(self.model)

            # Make a simple test request
            response = model.generate_content("Hello", generation_config={"max_output_tokens": 5})

            # If we get here, the API key is valid
            self.finished.emit(True, "")

        except Exception as e:
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                self.finished.emit(False, "Неверный API ключ")
            elif "quota" in str(e).lower() or "rate" in str(e).lower():
                self.finished.emit(False, "Превышен лимит запросов")
            else:
                self.finished.emit(False, f"Ошибка Google: {str(e)}")


class SettingsDialog(QDialog, SettingsObserver):
    """Settings dialog with tabbed interface for configuration."""

    def __init__(self, parent=None):
        """Initialize the settings dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("WhisperBridge Settings")
        self.setModal(False)  # Non-modal dialog
        self.resize(500, 600)

        # Initialize current settings first from config service
        self.current_settings = config_service.get_settings()

        # Apply proper color scheme for visibility
        self._apply_proper_colors()

        # Create main layout
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self._create_api_tab()
        self._create_translation_tab()
        self._create_ocr_tab()
        self._create_hotkeys_tab()
        self._create_general_tab()

        # Create buttons
        self._create_buttons(layout)

        # Register as config service observer
        config_service.add_observer(self)

        # Load current values
        self._load_settings()

    def _apply_proper_colors(self):
        """Apply proper color scheme to ensure text visibility."""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPalette, QColor
        from PySide6.QtCore import Qt

        # Create a palette that ensures good contrast
        palette = QPalette()

        # Check current theme setting from config service
        current_theme = config_service.get_setting("theme", use_cache=False).lower()

        if current_theme == "dark":
            # Dark theme - use dark colors but ensure good contrast
            palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))  # Dark gray background
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)  # White text
            palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))  # Dark input background
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)  # White text in inputs
            palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))  # Dark button background
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)  # White button text
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))  # Blue highlight
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)  # White text on highlight
        else:
            # Light theme (default) - use light colors
            palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))  # Light gray background
            palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)  # Black text
            palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)  # White for input fields
            palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)  # Black text in inputs
            palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))  # Light button background
            palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)  # Black button text
            palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))  # Blue highlight
            palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)  # White text on highlight

        # Apply the palette to this dialog
        self.setPalette(palette)

        # Also set auto-fill background to ensure consistency
        self.setAutoFillBackground(True)

    def _create_api_tab(self):
        """Create API settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # API Provider
        provider_group = QGroupBox("API Provider")
        provider_layout = QFormLayout(provider_group)

        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItems(["openai", "anthropic", "google"])
        self.api_provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addRow("Provider:", self.api_provider_combo)

        # API Key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        provider_layout.addRow("API Key:", self.api_key_edit)

        layout.addWidget(provider_group)

        # Model and Timeout
        model_group = QGroupBox("Model Settings")
        model_layout = QFormLayout(model_group)

        self.model_combo = QComboBox()
        # Allow custom model input
        self.model_combo.setEditable(True)
        # Add placeholder text while loading
        self.model_combo.addItem("Loading models...")
        model_layout.addRow("Model:", self.model_combo)

        # Don't load models here - they will be loaded in _load_settings
        logger.debug("Skipping model loading in _create_api_tab - will load in _load_settings")

        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(1, 300)
        self.api_timeout_spin.setSuffix(" seconds")
        model_layout.addRow("Timeout:", self.api_timeout_spin)

        layout.addWidget(model_group)

        # Test API button
        test_layout = QHBoxLayout()
        test_layout.addStretch()

        self.test_api_button = QPushButton("Test API")
        self.test_api_button.clicked.connect(self._on_test_api)
        test_layout.addWidget(self.test_api_button)

        layout.addLayout(test_layout)
        layout.addStretch()

        self.tab_widget.addTab(tab, "API")

    def _create_translation_tab(self):
        """Create translation settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Language settings
        lang_group = QGroupBox("Language Settings")
        lang_layout = QFormLayout(lang_group)

        # Source language
        self.source_lang_combo = QComboBox()
        source_items = ["auto"] + self.current_settings.supported_languages
        self.source_lang_combo.addItems(source_items)
        lang_layout.addRow("Source Language:", self.source_lang_combo)

        # Target language
        self.target_lang_combo = QComboBox()
        self.target_lang_combo.addItems(self.current_settings.supported_languages)
        lang_layout.addRow("Target Language:", self.target_lang_combo)

        layout.addWidget(lang_group)

        # Translation options: OCR auto-swap and System Prompt
        # OCR auto-swap checkbox (EN <-> RU)
        from PySide6.QtWidgets import QCheckBox
        self.ocr_auto_swap_checkbox = QCheckBox("OCR Auto-swap EN ↔ RU")
        self.ocr_auto_swap_checkbox.setToolTip("If enabled, OCR translations will auto-swap: English→Russian, Russian→English")
        layout.addWidget(self.ocr_auto_swap_checkbox)

        # System Prompt
        prompt_group = QGroupBox("System Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setAcceptRichText(False)
        self.system_prompt_edit.setPlaceholderText("Enter the system prompt for the translation model.")
        prompt_layout.addWidget(self.system_prompt_edit)
        layout.addWidget(prompt_group)
        layout.addStretch()

        self.tab_widget.addTab(tab, "Translation")

    def _create_ocr_tab(self):
        """Create OCR settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
 
        # OCR settings
        ocr_group = QGroupBox("OCR Configuration")
        ocr_layout = QFormLayout(ocr_group)
 
        # Initialize OCR on startup (enable/disable OCR features)
        self.initialize_ocr_check = QCheckBox("Initialize OCR service on startup")
        self.initialize_ocr_check.setToolTip("If enabled, the OCR service will be initialized and OCR actions (menu/hotkeys) will be available.")
        ocr_layout.addRow(self.initialize_ocr_check)
 
        # OCR Languages
        self.ocr_languages_edit = QLineEdit()
        self.ocr_languages_edit.setPlaceholderText("e.g., en,ru,es")
        ocr_layout.addRow("OCR Languages:", self.ocr_languages_edit)
 
        # Confidence threshold
        self.ocr_confidence_spin = QDoubleSpinBox()
        self.ocr_confidence_spin.setRange(0.0, 1.0)
        self.ocr_confidence_spin.setSingleStep(0.05)
        self.ocr_confidence_spin.setValue(0.7)
        ocr_layout.addRow("Confidence Threshold:", self.ocr_confidence_spin)
 
        layout.addWidget(ocr_group)
        layout.addStretch()
 
        self.tab_widget.addTab(tab, "OCR")

    def _create_hotkeys_tab(self):
        """Create hotkeys settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
    
        # Hotkey settings group
        hotkey_group = QGroupBox("Hotkey Configuration")
        hotkey_layout = QFormLayout(hotkey_group)
    
        self.translate_hotkey_edit = QLineEdit()
        hotkey_layout.addRow("Translate Hotkey:", self.translate_hotkey_edit)
    
        self.quick_translate_hotkey_edit = QLineEdit()
        hotkey_layout.addRow("Quick Translate Hotkey:", self.quick_translate_hotkey_edit)
    
        self.activation_hotkey_edit = QLineEdit()
        hotkey_layout.addRow("Activation Hotkey:", self.activation_hotkey_edit)
    
        self.copy_translate_hotkey_edit = QLineEdit()
        hotkey_layout.addRow("Copy→Translate Hotkey:", self.copy_translate_hotkey_edit)
    
        layout.addWidget(hotkey_group)

        # Help text
        help_label = QLabel("Use format like 'ctrl+shift+t' or 'alt+f1'")
        help_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(help_label)
    
        # Copy-translate options in a separate group box
        copy_group = QGroupBox("Copy-Translate Options")
        copy_layout = QFormLayout(copy_group)
    
        # Automatically copy translated text to clipboard
        self.auto_copy_translated_check = QCheckBox("Automatically copy translated text to clipboard")
        self.auto_copy_translated_check.setToolTip("If enabled, translated text will be copied to the clipboard automatically after translation.")
        copy_layout.addRow(self.auto_copy_translated_check)
    
        # Clipboard polling timeout (ms)
        self.clipboard_poll_timeout_spin = QSpinBox()
        self.clipboard_poll_timeout_spin.setRange(500, 10000)
        self.clipboard_poll_timeout_spin.setSingleStep(100)
        self.clipboard_poll_timeout_spin.setSuffix(" ms")
        copy_layout.addRow("Clipboard polling timeout (ms):", self.clipboard_poll_timeout_spin)
    
        layout.addWidget(copy_group)

    
        layout.addStretch()
    
        self.tab_widget.addTab(tab, "Hotkeys")

    def _create_general_tab(self):
        """Create general settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # UI settings
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout(ui_group)

        # Theme selection (support system option as well)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light", "system"])
        ui_layout.addRow("Theme:", self.theme_combo)

        # Log level selection (exposed to users so they can change verbosity)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        ui_layout.addRow("Log level:", self.log_level_combo)

        self.show_notifications_check = QCheckBox("Show notifications")
        ui_layout.addRow(self.show_notifications_check)

        layout.addWidget(ui_group)
        layout.addStretch()

        self.tab_widget.addTab(tab, "General")

    def _create_buttons(self, layout):
        """Create dialog buttons."""
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _load_settings(self):
        """Load current settings into the UI."""
        # Get fresh settings from config service
        settings = config_service.get_settings()

        logger.debug(f"Loading settings - theme: '{settings.theme}'")

        # API tab
        self.api_provider_combo.setCurrentText(settings.api_provider)
        if settings.openai_api_key:
            self.api_key_edit.setText(settings.openai_api_key)
        # Don't set model here - it will be set after loading models
        self.api_timeout_spin.setValue(settings.api_timeout)

        # Translation tab
        self.source_lang_combo.setCurrentText(settings.source_language)
        self.target_lang_combo.setCurrentText(settings.target_language)
        # OCR auto-swap checkbox (EN <-> RU)
        try:
            self.ocr_auto_swap_checkbox.setChecked(bool(getattr(settings, "ocr_auto_swap_en_ru", False)))
        except Exception:
            logger.debug("Failed to set ocr_auto_swap_checkbox state from settings")
        self.system_prompt_edit.setPlainText(settings.system_prompt)

        # OCR tab
        self.ocr_languages_edit.setText(",".join(settings.ocr_languages))
        self.ocr_confidence_spin.setValue(settings.ocr_confidence_threshold)
        # initialize_ocr checkbox (default False if missing)
        try:
            self.initialize_ocr_check.setChecked(bool(getattr(settings, "initialize_ocr", False)))
        except Exception:
            logger.debug("Failed to set initialize_ocr checkbox from settings; defaulting to False")
            self.initialize_ocr_check.setChecked(False)

        # Hotkeys tab
        self.translate_hotkey_edit.setText(settings.translate_hotkey)
        self.quick_translate_hotkey_edit.setText(settings.quick_translate_hotkey)
        self.activation_hotkey_edit.setText(settings.activation_hotkey)
        self.copy_translate_hotkey_edit.setText(settings.copy_translate_hotkey)
    
        # Copy-translate enhancements - load safely with defaults
        try:
            self.auto_copy_translated_check.setChecked(bool(getattr(settings, "auto_copy_translated", False)))
        except Exception:
            logger.debug("Failed to set auto_copy_translated state from settings")
        try:
            self.clipboard_poll_timeout_spin.setValue(int(getattr(settings, "clipboard_poll_timeout_ms", 2000)))
        except Exception:
            logger.debug("Failed to set clipboard_poll_timeout_ms from settings; defaulting to 2000")
            self.clipboard_poll_timeout_spin.setValue(2000)
    
        # General tab
        self.theme_combo.setCurrentText(settings.theme)
        # Load and set log level into UI safely
        try:
            self.log_level_combo.setCurrentText(getattr(settings, "log_level", "INFO"))
        except Exception:
            logger.debug("Failed to set log_level in UI; defaulting to INFO")
        self.show_notifications_check.setChecked(settings.show_notifications)

        # Reload models after loading settings to ensure dynamic loading
        logger.debug("About to call _load_models_synchronously from _load_settings")
        self._load_models_synchronously()

    def _on_save(self):
        """Handle save button click."""
        try:
            # Get current settings dict from config service to ensure we have the latest saved values
            current_settings = config_service.get_settings()
            current = current_settings.model_dump()

            # Update from UI
            current["api_provider"] = self.api_provider_combo.currentText()
            current["openai_api_key"] = self.api_key_edit.text().strip() or None
            current["model"] = self.model_combo.currentText().strip()
            current["api_timeout"] = self.api_timeout_spin.value()
            current["source_language"] = self.source_lang_combo.currentText()
            current["target_language"] = self.target_lang_combo.currentText()
            current["system_prompt"] = self.system_prompt_edit.toPlainText().strip()
            # OCR auto-swap flag
            current["ocr_auto_swap_en_ru"] = bool(self.ocr_auto_swap_checkbox.isChecked())
            current["ocr_languages"] = [lang.strip() for lang in self.ocr_languages_edit.text().split(",") if lang.strip()]
            current["ocr_confidence_threshold"] = self.ocr_confidence_spin.value()
            # Persist initialize_ocr flag
            try:
                current["initialize_ocr"] = bool(self.initialize_ocr_check.isChecked())
            except Exception:
                current["initialize_ocr"] = False
            current["translate_hotkey"] = self.translate_hotkey_edit.text().strip()
            current["quick_translate_hotkey"] = self.quick_translate_hotkey_edit.text().strip()
            current["activation_hotkey"] = self.activation_hotkey_edit.text().strip()
            current["copy_translate_hotkey"] = self.copy_translate_hotkey_edit.text().strip()

            # Copy-translate enhancements - persist UI values
            current["auto_copy_translated"] = bool(self.auto_copy_translated_check.isChecked())
            current["clipboard_poll_timeout_ms"] = int(self.clipboard_poll_timeout_spin.value())
    
            selected_theme = self.theme_combo.currentText()
            current["theme"] = selected_theme
            # Persist selected log level
            try:
                current["log_level"] = self.log_level_combo.currentText().strip()
            except Exception:
                current["log_level"] = "INFO"
            current["show_notifications"] = self.show_notifications_check.isChecked()

            logger.debug(f"Saving theme: '{selected_theme}'")
            logger.debug(f"Current settings before update: theme='{current.get('theme', 'NOT_FOUND')}'")
            logger.debug(f"Current dict keys: {list(current.keys())}")

            # Create new settings object for validation
            new_settings = Settings(**current)

            # Save via ConfigService
            if config_service.save_settings(new_settings):
                self.current_settings = new_settings
                self.accept()  # Close dialog
            else:
                QMessageBox.warning(
                    self,
                    "Save Failed",
                    "Failed to save settings. Please check your configuration and try again."
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"An error occurred while saving settings:\n\n{str(e)}"
            )

    def _on_test_api(self):
        """Handle test API button click."""
        # Get values from UI
        provider = self.api_provider_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()

        # Validate input
        if not api_key:
            QMessageBox.warning(self, "Validation Error", "Please enter an API key.")
            return

        # Provider-specific validation
        if provider == "openai" and not api_key.startswith("sk-"):
            QMessageBox.warning(self, "Validation Error", "OpenAI API key should start with 'sk-'.")
            return

        if not model:
            QMessageBox.warning(self, "Validation Error", "Please select a model.")
            return

        # Disable button and show testing state
        self.test_api_button.setEnabled(False)
        self.test_api_button.setText("Testing...")

        # Create and start worker thread
        self.test_worker = ApiTestWorker(provider, api_key, model)
        self.test_thread = QThread()

        self.test_worker.moveToThread(self.test_thread)
        self.test_worker.finished.connect(self._on_test_finished)
        self.test_thread.started.connect(self.test_worker.run)

        # Clean up thread when done
        self.test_worker.finished.connect(self.test_thread.quit)
        self.test_worker.finished.connect(self.test_worker.deleteLater)
        self.test_thread.finished.connect(self.test_thread.deleteLater)

        self.test_thread.start()

    def _on_test_finished(self, success: bool, error_msg: str):
        """Handle API test completion."""
        # Re-enable button
        self.test_api_button.setEnabled(True)
        self.test_api_button.setText("Test API")

        # Show result
        if success:
            QMessageBox.information(
                self,
                "Test Successful",
                "API key is working correctly!"
            )
        else:
            QMessageBox.warning(
                self,
                "Test Failed",
                f"API test failed: {error_msg}"
            )

    def _load_models_synchronously(self):
        """Load available models synchronously for immediate display."""
        provider_name = self.api_provider_combo.currentText()
        # Get the model from settings, not from current combo box (which might be empty)
        settings = config_service.get_settings()
        current_model = settings.model

        logger.debug(f"=== _load_models_synchronously called ===")
        logger.debug(f"Loading models for provider: {provider_name}")
        logger.debug(f"Current model from settings: '{current_model}'")

        # Clear current models
        self.model_combo.clear()

        try:
            api_manager = get_api_manager()
            logger.debug(f"API manager initialized: {api_manager.is_initialized()}")

            if provider_name == "openai":
                # Load models from API synchronously
                logger.debug("Fetching models from OpenAI API synchronously")
                models = api_manager.get_available_models_sync(APIProvider.OPENAI)
                logger.debug(f"Loaded {len(models)} models from API: {models[:5]}...")  # Log first 5 models
            else:
                # For other providers, use fallback list
                logger.debug("Using fallback models for non-OpenAI provider")
                models = [
                    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"
                ]

            self._apply_models_to_ui(models, current_model)

        except Exception as e:
            logger.error(f"Failed to load models synchronously: {e}")
            # Fallback to basic list
            fallback_models = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
            self._apply_models_to_ui(fallback_models, current_model)

    def _load_models_for_provider(self):
        """Load available models for the current provider asynchronously."""
        provider_name = self.api_provider_combo.currentText()
        current_model = self.model_combo.currentText()

        logger.debug(f"=== _load_models_for_provider called (async) ===")
        logger.debug(f"Loading models for provider: {provider_name}")
        logger.debug(f"Current model in combo: '{current_model}'")
        logger.debug(f"Combo box is visible: {self.model_combo.isVisible()}")
        logger.debug(f"Dialog is visible: {self.isVisible()}")

        # Clear current models
        self.model_combo.clear()

        try:
            api_manager = get_api_manager()
            logger.debug(f"API manager initialized: {api_manager.is_initialized()}")

            if provider_name == "openai":
                # Load models asynchronously using QThread
                logger.debug("Starting async model fetch from OpenAI API")
                self._start_model_fetch_thread(APIProvider.OPENAI, current_model)
                return  # Exit early, models will be loaded in thread
            else:
                # For other providers, use fallback list
                logger.debug("Using fallback models for non-OpenAI provider")
                models = [
                    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"
                ]
                self._apply_models_to_ui(models, current_model)

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            # Fallback to basic GPT list
            fallback_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
            self._apply_models_to_ui(fallback_models, current_model)

    def _start_model_fetch_thread(self, provider: APIProvider, current_model: str):
        """Start a thread to fetch models asynchronously."""
        from PySide6.QtCore import QThread, Signal, QObject

        # Don't start thread if dialog is being closed
        if not self.isVisible():
            logger.debug("Dialog is not visible, skipping model fetch thread")
            return

        class ModelFetchWorker(QObject):
            finished = Signal(list, str)  # models, current_model

            def __init__(self, provider, current_model):
                super().__init__()
                self.provider = provider
                self.current_model = current_model

            def run(self):
                try:
                    from ..core.api_manager import get_api_manager
                    api_manager = get_api_manager()
                    models = api_manager.get_available_models_sync(self.provider)
                    self.finished.emit(models, self.current_model)
                except Exception as e:
                    logger.error(f"Model fetch thread failed: {e}")
                    # Emit fallback models (GPT models only)
                    fallback_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
                    self.finished.emit(fallback_models, self.current_model)

        # Clean up any existing thread first
        if hasattr(self, 'model_thread') and self.model_thread.isRunning():
            logger.debug("Waiting for existing model fetch thread to finish...")
            self.model_thread.quit()
            if not self.model_thread.wait(2000):  # Wait up to 2 seconds
                logger.warning("Existing thread did not finish gracefully")

        # Create and start worker thread
        self.model_worker = ModelFetchWorker(provider, current_model)
        self.model_thread = QThread()

        self.model_worker.moveToThread(self.model_thread)
        self.model_worker.finished.connect(self._on_models_fetched)
        self.model_thread.started.connect(self.model_worker.run)

        # Clean up thread when done
        self.model_worker.finished.connect(self.model_thread.quit)
        self.model_worker.finished.connect(self.model_worker.deleteLater)
        self.model_thread.finished.connect(self.model_thread.deleteLater)

        self.model_thread.start()

    def _on_models_fetched(self, models: list, current_model: str):
        """Handle fetched models from thread."""
        logger.debug(f"Received {len(models)} models from thread: {models}")
        logger.debug(f"Current model before applying: '{current_model}'")

        # Ensure UI update happens on main thread
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._apply_models_to_ui(models, current_model))

    def _apply_models_to_ui(self, models: list, current_model: str):
        """Apply models to the UI combo box."""
        logger.debug(f"Applying {len(models)} models to UI: {models}")
        logger.debug(f"Combo box current count before clear: {self.model_combo.count()}")

        # Clear existing items
        self.model_combo.clear()

        # Add new models
        self.model_combo.addItems(models)
        logger.debug(f"Added {len(models)} models to combo box, new count: {self.model_combo.count()}")

        # Force UI update
        self.model_combo.update()
        self.model_combo.repaint()

        # Restore previously selected model if it exists in the new list
        if current_model and current_model in models:
            self.model_combo.setCurrentText(current_model)
            logger.debug(f"Restored current model: {current_model}")
        elif models:
            # Select first model as default
            self.model_combo.setCurrentText(models[0])
            logger.debug(f"Selected default model: {models[0]}")
            # Also update the settings to reflect the new default
            try:
                current_settings = config_service.get_settings()
                current_settings.model = models[0]
                config_service.save_settings(current_settings)
                logger.debug(f"Updated settings with default model: {models[0]}")
            except Exception as e:
                logger.error(f"Failed to update settings with default model: {e}")

        logger.debug(f"Final combo box current text: '{self.model_combo.currentText()}'")

        # Additional UI refresh
        self.update()
        self.repaint()

    def _on_provider_changed(self):
        """Handle provider change - reload models."""
        # Only reload if dialog is still open
        if not self.isVisible():
            return
        self._load_models_for_provider()

    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        if key == "theme":
            logger.debug(f"Theme setting changed from {old_value} to {new_value}")
            # Update current settings and reapply colors
            self.current_settings = config_service.get_settings()
            self._apply_proper_colors()
            # Update the theme combo box to reflect the change
            self.theme_combo.setCurrentText(new_value)

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        logger.debug("Settings loaded")
        self.current_settings = settings
        self._load_settings()
        self._apply_proper_colors()

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        logger.debug("Settings saved")
        self.current_settings = settings
        # Reapply colors in case theme changed
        self._apply_proper_colors()

    def closeEvent(self, event):
        """Handle dialog close event - clean up threads."""
        # Clean up model fetch thread if it's running
        if hasattr(self, 'model_thread') and self.model_thread.isRunning():
            logger.debug("Cleaning up model fetch thread on dialog close...")
            self.model_thread.quit()
            if not self.model_thread.wait(2000):  # Wait up to 2 seconds
                logger.warning("Model fetch thread did not finish gracefully")
                self.model_thread.terminate()

        super().closeEvent(event)
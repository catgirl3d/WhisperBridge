"""
Settings Dialog for WhisperBridge Qt UI.

Provides a comprehensive settings interface with tabs for different configuration categories.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QFormLayout,
    QGroupBox,
    QMessageBox,
    QTextEdit,
)
from PySide6.QtCore import QThread, Signal, QObject

from ..services.config_service import config_service, SettingsObserver
from ..core.api_manager import get_api_manager, APIProvider
from ..core.config import delete_api_key, validate_api_key_format
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
            elif self.provider == "google":
                self._test_google()
            else:
                self.finished.emit(False, f"Unsupported provider: {self.provider}")

        except Exception as e:
            self.finished.emit(False, f"Ошибка подключения: {str(e)}")

    def _test_openai(self):
        """Test OpenAI API by fetching available models."""
        try:
            import openai

            # Create a temporary client for testing
            client = openai.OpenAI(api_key=self.api_key, timeout=10)

            # Test API by fetching models list
            models_response = client.models.list()

            # If we get here, the API key is valid and we have models
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


    def _test_google(self):
        """Test Google API by fetching available models."""
        try:
            import google.generativeai as genai
            from google.api_core.exceptions import (
                Unauthenticated,
                ResourceExhausted,
                NotFound,
                PermissionDenied,
                InvalidArgument,
                FailedPrecondition,
            )

            # Configure the API
            genai.configure(api_key=self.api_key)

            # Test API by fetching models list
            models_response = genai.list_models()

            # If we get here, the API key is valid and we have models
            self.finished.emit(True, "")

        except Unauthenticated:
            self.finished.emit(False, "Неверный API ключ")
        except PermissionDenied:
            self.finished.emit(False, "Недостаточно прав доступа")
        except ResourceExhausted:
            self.finished.emit(False, "Превышен лимит запросов")
        except InvalidArgument as e:
            self.finished.emit(False, f"Неверные параметры запроса: {str(e)}")
        except FailedPrecondition as e:
            self.finished.emit(False, f"API не готово к использованию: {str(e)}")
        except NotFound as e:
            self.finished.emit(False, f"Ресурс не найден: {str(e)}")
        except ImportError:
            self.finished.emit(False, "Библиотека google-generativeai не установлена")
        except Exception as e:
            self.finished.emit(False, f"Неизвестная ошибка Google API: {str(e)}")


class SettingsDialog(QDialog, SettingsObserver):
    """Settings dialog with tabbed interface for configuration."""

    def __init__(self, app, parent=None):
        """Initialize the settings dialog.

        Args:
            app: The main QtApp instance.
            parent: Parent widget
        """
        super().__init__(parent)
        self.app = app
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
        self._provider_form_layout = provider_layout  # keep reference for label visibility

        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItems(["openai", "google"])
        self.api_provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addRow("Provider:", self.api_provider_combo)

        # API Key (dynamic based on provider)
        self.api_key_label = QLabel()  # Label will be updated dynamically
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.delete_api_key_button = QPushButton("Delete")
        self.delete_api_key_button.clicked.connect(self._on_delete_api_key)

        self.test_api_button = QPushButton("Test API")
        self.test_api_button.clicked.connect(self._on_test_api)

        key_layout = QHBoxLayout()
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.api_key_edit)
        key_layout.addWidget(self.delete_api_key_button)
        
        self.api_key_widget = QWidget()
        self.api_key_widget.setLayout(key_layout)

        provider_layout.addRow(self.api_key_label, self.api_key_widget)
        provider_layout.addRow(self.test_api_button)

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

        layout.addStretch()

        self.tab_widget.addTab(tab, "API")

    def _update_api_key_field(self):
        """Update the API key field label and content for the selected provider."""
        provider = self.api_provider_combo.currentText().strip().lower()
        settings = config_service.get_settings()

        if provider == "openai":
            self.api_key_label.setText("OpenAI API Key:")
            self.api_key_edit.setText(getattr(settings, "openai_api_key", "") or "")
        elif provider == "google":
            self.api_key_label.setText("Google API Key:")
            self.api_key_edit.setText(getattr(settings, "google_api_key", "") or "")

    def _create_translation_tab(self):
        """Create translation settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

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
        # This call will now correctly populate the unified API key field
        self._update_api_key_field()
        self.api_timeout_spin.setValue(settings.api_timeout)

        # Translation tab
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
            # Handle API keys based on provider
            provider = current["api_provider"].lower()
            api_key_text = self.api_key_edit.text().strip() or None

            if provider == "openai":
                current["openai_api_key"] = api_key_text
                # Ensure the other key is not lost if it was loaded
                if "google_api_key" not in current or current["google_api_key"] is None:
                    current["google_api_key"] = getattr(current_settings, "google_api_key", None)
            elif provider == "google":
                current["google_api_key"] = api_key_text
                if "openai_api_key" not in current or current["openai_api_key"] is None:
                    current["openai_api_key"] = getattr(current_settings, "openai_api_key", None)
            
            # Save the model based on the provider
            model_text = self.model_combo.currentText().strip()
            if provider == "openai":
                current["openai_model"] = model_text
                # Preserve Google model if it exists
                if "google_model" not in current or not current["google_model"]:
                    current["google_model"] = getattr(current_settings, "google_model", "gemini-1.5-flash")
            elif provider == "google":
                current["google_model"] = model_text
                # Preserve OpenAI model if it exists
                if "openai_model" not in current or not current["openai_model"]:
                    current["openai_model"] = getattr(current_settings, "openai_model", "gpt-5-nano")

            current["api_timeout"] = self.api_timeout_spin.value()
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

            # Save settings asynchronously
            self.app.save_settings_async(current)

            # Assume success and close the dialog immediately
            # The user will be notified of the result via a tray notification
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"An error occurred while saving settings:\n\n{str(e)}",
            )

    def _on_delete_api_key(self):
        """Handle delete API key button click."""
        provider = self.api_provider_combo.currentText().strip()

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to permanently delete the API key for {provider.capitalize()}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if delete_api_key(provider):
                    self.api_key_edit.setText("")  # Clear the unified input field
                    QMessageBox.information(
                        self,
                        "Success",
                        f"API key for {provider.capitalize()} has been deleted.",
                    )
                    # Force all services to re-read the configuration from its source
                    try:
                        # 1. Force config service to reload settings from disk/keyring
                        config_service.load_settings()
                        logger.info("Config service reloaded to reflect key deletion.")

                        # 2. Reinitialize the API manager with the now-updated config
                        get_api_manager().reinitialize()
                        logger.info(f"API manager reinitialized after deleting {provider} key.")

                        # 3. Reload models to update the UI, which will now show the unconfigured state
                        self._load_models_for_provider()
                    except Exception as e:
                        logger.error(f"Failed to update state after key deletion: {e}")
                else:
                    QMessageBox.warning(
                        self,
                        "Deletion Failed",
                        f"Failed to delete the API key for {provider.capitalize()}.",
                    )
            except Exception as e:
                logger.error(f"Error deleting API key for {provider}: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    f"An unexpected error occurred while deleting the key: {e}",
                )

    def _on_test_api(self):
        """Handle test API button click."""
        # Get values from UI
        provider = self.api_provider_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip()

        # Validate input
        if not api_key:
            QMessageBox.warning(self, "Validation Error", "Please enter an API key.")
            return

        # Delegate provider-specific validation to core to avoid duplication
        try:
            if not validate_api_key_format(api_key, provider):
                msg = "Invalid API key format."
                if provider == "openai":
                    msg = "Invalid API key format (expected OpenAI key with 'sk-' prefix and valid structure)."
                elif provider == "google":
                    msg = "Invalid API key format (expected Google key with 'AIza' prefix and valid structure)."
                QMessageBox.warning(self, "Validation Error", msg)
                return
        except Exception as e:
            logger.warning(f"API key validation failed: {e}")
            QMessageBox.warning(self, "Validation Error", "Invalid API key format.")
            return

        # Disable button and show testing state
        self.test_api_button.setEnabled(False)
        self.test_api_button.setText("Testing...")

        # Create and start worker thread (model parameter no longer needed)
        self.test_worker = ApiTestWorker(provider, api_key, "")
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
                self, "Test Successful", "API key is working correctly!"
            )
            # After a successful test, load models immediately using the tested key
            try:
                provider_name = self.api_provider_combo.currentText()
                api_key = self.api_key_edit.text().strip()
                provider_enum = APIProvider(provider_name)
                
                api_manager = get_api_manager()
                logger.info(f"Fetching models for {provider_name} with temporary key after successful test.")
                
                # Use the modified method to get models with the temporary key
                models, source = api_manager.get_available_models_sync(
                    provider=provider_enum, temp_api_key=api_key
                )

                if source == "error":
                    raise RuntimeError("Failed to fetch models with temporary key.")

                # Apply models to the UI
                current_model = self.model_combo.currentText().strip()
                self._apply_models_to_ui(models, current_model, source)
                logger.info(f"Successfully loaded {len(models)} models after API test.")

            except Exception as e:
                logger.error(f"Failed to load models after successful API test: {e}")
                QMessageBox.warning(self, "Model Load Failed", f"API key is valid, but could not fetch models: {e}")
        else:
            QMessageBox.warning(self, "Test Failed", f"API test failed: {error_msg}")

    def _load_models_synchronously(self):
        """Load available models synchronously for immediate display."""
        provider_name = self.api_provider_combo.currentText()
        # Get the model from settings based on the provider
        settings = config_service.get_settings()
        provider_name = self.api_provider_combo.currentText()
        
        if provider_name.lower() == "openai":
            current_model = settings.openai_model
        elif provider_name.lower() == "google":
            current_model = settings.google_model
        else:
            current_model = "gpt-5-nano" # Fallback

        logger.debug("=== _load_models_synchronously called ===")
        logger.debug("Loading models for provider: %s", provider_name)
        logger.debug("Current model from settings: '%s'", current_model)

        # Check if API key is configured for the current provider
        api_key_configured = self._is_api_key_configured(provider_name)

        if not api_key_configured:
            logger.debug("No API key configured for provider, showing empty model list")
            self.model_combo.clear()
            self.model_combo.addItem("No API key configured")
            return

        # Clear current models
        self.model_combo.clear()

        try:
            from ..core.api_manager import init_api_manager
            api_manager = init_api_manager()  # Ensure API manager is initialized
            logger.debug(f"API manager initialized: {api_manager.is_initialized()}")

            # Load models for all providers using centralized API manager
            logger.debug("Fetching models using centralized API manager")
            provider_enum = APIProvider(provider_name)
            models, source = api_manager.get_available_models_sync(provider_enum)
            logger.debug(f"Loaded {len(models)} models from {source}: {models[:5] if models else []}")  # Log first 5 models

            if source == "unconfigured":
                logger.debug(f"Provider {provider_enum.value} not configured, cannot load models")
                self.model_combo.clear()
                self.model_combo.addItem("No API key configured")
                return

            if models:
                self._apply_models_to_ui(models, current_model, source)
            else:
                self._apply_models_to_ui([], current_model, "error")

        except Exception as e:
            logger.error(f"Failed to load models synchronously: {e}")
            # Show empty model list when API fails - no fallback models
            self._apply_models_to_ui([], current_model, "error")

    def _is_api_key_configured(self, provider_name: str) -> bool:
        """Check if API key is configured for the given provider."""
        # Check both current input field and saved settings
        current_input = bool(self.api_key_edit.text().strip())

        # Also check if the key is saved in settings
        settings = config_service.get_settings()
        if provider_name.lower() == "openai":
            saved_key = bool(getattr(settings, "openai_api_key", None))
        elif provider_name.lower() == "google":
            saved_key = bool(getattr(settings, "google_api_key", None))
        else:
            saved_key = False

        return current_input or saved_key

    def _load_models_for_provider(self, model_to_restore: str = None):
        """Load available models for the current provider asynchronously."""
        provider_name = self.api_provider_combo.currentText()

        logger.debug(f"=== _load_models_for_provider called (async) ===")
        logger.debug(f"Loading models for provider: {provider_name}")
        logger.debug(f"Model to restore: '{model_to_restore}'")
        logger.debug(f"Combo box is visible: {self.model_combo.isVisible()}")
        logger.debug(f"Dialog is visible: {self.isVisible()}")

        # Check if API key is configured for the current provider
        api_key_configured = self._is_api_key_configured(provider_name)

        if not api_key_configured:
            logger.debug("No API key configured for provider, showing empty model list")
            self.model_combo.clear()
            self.model_combo.addItem("No API key configured")
            return

        # Clear current models
        self.model_combo.clear()

        try:
            from ..core.api_manager import init_api_manager
            api_manager = init_api_manager()  # Ensure API manager is initialized
            logger.debug(f"API manager initialized: {api_manager.is_initialized()}")

            # Unified synchronous fetch for all providers (simplified, with caching/fallback in APIManager)
            logger.debug("Fetching models synchronously via centralized API manager")
            provider_enum = APIProvider(provider_name)
            models, source = api_manager.get_available_models_sync(provider_enum)

            logger.debug(f"Loaded {len(models)} models from {source} for provider {provider_name}")

            if source == "unconfigured":
                logger.debug(f"Provider {provider_enum.value} not configured, cannot load models")
                self.model_combo.clear()
                self.model_combo.addItem("No API key configured")
                return

            if models:
                self._apply_models_to_ui(models, model_to_restore, source)
            else:
                logger.debug(f"No models returned from API manager for {provider_name}")
                # If no models from API but we have a model to restore, try to restore from cache
                if model_to_restore:
                    logger.debug(f"Attempting to restore model '{model_to_restore}' from cache")
                    # Try to get cached models for this provider
                    try:
                        # Check if API manager is properly initialized and has cache
                        if (api_manager.is_initialized() and
                            hasattr(api_manager, '_model_cache') and
                            hasattr(api_manager, '_lock')):
                            with api_manager._lock:
                                cached_models, _ = api_manager._model_cache.get(provider_enum, ([], 0))
                            if cached_models and model_to_restore in cached_models:
                                logger.debug(f"Found model '{model_to_restore}' in cache")
                                self._apply_models_to_ui(cached_models, model_to_restore, "cache")
                            else:
                                logger.debug(f"Model '{model_to_restore}' not found in cache")
                                self._apply_models_to_ui([], model_to_restore, "error")
                        else:
                            logger.debug("API manager not properly initialized or missing cache attributes")
                            self._apply_models_to_ui([], model_to_restore, "error")
                    except Exception as e:
                        logger.error(f"Failed to access model cache: {e}")
                        self._apply_models_to_ui([], model_to_restore, "error")
                else:
                    self._apply_models_to_ui([], model_to_restore, "error")

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            # Show empty model list when API fails - no fallback models
            self._apply_models_to_ui([], model_to_restore, "error")


    def _apply_models_to_ui(self, models: list, current_model: str, source: str = "unknown"):
        """Apply models to the UI combo box."""
        logger.debug(f"Applying {len(models)} models to UI: {models}")
        logger.debug(f"Combo box current count before clear: {self.model_combo.count()}")

        # Clear existing items
        self.model_combo.clear()

        # Add new models
        self.model_combo.addItems(models)
        logger.debug(f"Added {len(models)} models to combo box, new count: {self.model_combo.count()}")
        logger.info(f"Successfully loaded {len(models)} models from {source.upper()} for the model selection dropdown: {', '.join(models)}")

        # Force UI update
        self.model_combo.update()
        self.model_combo.repaint()

        # Restore previously selected model if it exists in the new list
        logger.debug(f"Attempting to restore model: '{current_model}'")
        logger.debug(f"Available models: {models}")

        # Find the best match for the current model
        # This handles cases where a model is saved (e.g. "gpt-4") but a more specific version is available ("gpt-4-turbo")
        best_match = None
        if current_model:
            # Exact match first
            if current_model in models:
                best_match = current_model
            else:
                # Partial match (e.g., "gpt-4" should match "gpt-4-turbo")
                for model in models:
                    if model.startswith(current_model):
                        best_match = model
                        break
        
        if best_match:
            self.model_combo.setCurrentText(best_match)
            logger.debug(f"✅ Restored current model: {best_match}")
        elif models:
            # Select first model as default
            self.model_combo.setCurrentText(models[0])
            logger.debug(f"✅ Selected default model: {models[0]}")
        else:
            # If no models are available, show a placeholder
            self.model_combo.clear()
            self.model_combo.addItem("No models available")
            logger.debug("❌ No models available to select")

        logger.debug(f"Final combo box current text: '{self.model_combo.currentText()}'")

        # Additional UI refresh
        self.update()
        self.repaint()

    def _on_provider_changed(self):
        """Handle provider change - update API key field and reload models."""
        if not self.isVisible():
            return

        new_provider_name = self.api_provider_combo.currentText().strip().lower()
        settings = config_service.get_settings()

        # Get the model that was saved for the new provider
        if new_provider_name == "openai":
            model_to_restore = settings.openai_model
        elif new_provider_name == "google":
            model_to_restore = settings.google_model
        else:
            model_to_restore = None

        logger.debug(f"🔄 Provider changed to {new_provider_name}, attempting to restore model: '{model_to_restore}'")

        self._update_api_key_field()
        self._load_models_for_provider(model_to_restore)

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
        elif key == "ocr_auto_swap_en_ru":
            logger.debug(f"OCR auto-swap setting changed from {old_value} to {new_value}")
            self.ocr_auto_swap_checkbox.setChecked(bool(new_value))

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        logger.debug("Settings loaded")
        self.current_settings = settings
        self._load_settings()
        self._apply_proper_colors()

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        logger.debug("Settings saved")

        # Reinitialize API manager if API keys or provider changed.
        # This must be done BEFORE self.current_settings is updated.
        try:
            old_settings = self.current_settings
            api_keys_changed = (
                (getattr(settings, 'openai_api_key', None) or "") != (getattr(old_settings, 'openai_api_key', None) or "") or
                (getattr(settings, 'google_api_key', None) or "") != (getattr(old_settings, 'google_api_key', None) or "") or
                settings.api_provider != old_settings.api_provider
            )

            if api_keys_changed:
                api_manager = get_api_manager()
                api_manager.reinitialize()
                logger.info("API manager reinitialized after settings save due to key/provider change.")
            else:
                logger.debug("API keys/provider unchanged, skipping reinitialization.")
        except Exception as e:
            logger.error(f"Failed to reinitialize API manager after settings save: {e}")

        # Now, update the dialog's state with the new settings
        self.current_settings = settings
        # Reapply colors in case theme changed
        self._apply_proper_colors()

    def closeEvent(self, event):
        """Handle dialog close event."""
        super().closeEvent(event)

"""
Settings Dialog for WhisperBridge Qt UI.

Provides a comprehensive settings interface with tabs for different configuration categories.
"""
 
from pathlib import Path
from textwrap import dedent
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

    def __init__(self, provider: str, api_key: str):
        super().__init__()
        self.provider = provider
        self.api_key = api_key

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
        # self._apply_proper_colors()  # Commented out to use stylesheet instead
        self._apply_stylesheet()

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


    def _apply_stylesheet(self):
        """Apply a custom stylesheet"""
        icon_base_path = (Path(__file__).resolve().parent.parent / "assets" / "icons").as_posix()
        stylesheet = dedent("""
            QDialog {
                background-color: #ffffff;
            }
            QTabWidget::pane {
                border-top: 0px solid #f0f0f0;
            }
            QTabBar::tab {
                background: #f0f0f0;
                color: #111111;
                padding: 6px 16px;
                border-radius: 2px;
                border-bottom: none;
                margin-bottom: 2px;
                border-left: 2px solid #fff;
            }
            QTabBar::tab:selected {
                background: #356bd0;
                border: 0px solid #d0d0d0;
                border-bottom: 0px solid #ffffff; /* Match pane background */
                color:white;
            }
            QTabBar::tab:!selected:hover {
                background: #e8e8e8;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 4px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
            }
            QLabel {
                color: #111111;
                border: none;
            }
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                color: #111111;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton#save_button {
                background-color: #356bd0;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#save_button:hover {
                background-color: #2f5db3;
            }
            QComboBox {
                border: 1px solid rgba(0,0,0,0.12);
                border-radius: 4px;
                padding: 6px 8px;
                background-color: #ffffff;
                color: #111111;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border-left: 1px solid rgba(0,0,0,0.08);
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
                background-color: transparent;
            }
            QComboBox::down-arrow {
                image: url("__ICON_PATH__/chevron-down-solid-full.svg");
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid rgba(0,0,0,0.12);
                background-color: #ffffff;
                color: #111111;
                selection-background-color: #0078d7;
            }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 22px;
                border-left: 1px solid rgba(0,0,0,0.08);
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 22px;
                border-left: 1px solid rgba(0,0,0,0.08);
            }
            QSpinBox::up-arrow {
                image: url("__ICON_PATH__/chevron-up-solid-full.svg");
                width: 12px;
                height: 12px;
            }
            QSpinBox::down-arrow {
                image: url("__ICON_PATH__/chevron-down-solid-full.svg");
                width: 12px;
                height: 12px;
            }
        """)
        self.setStyleSheet(stylesheet.replace("__ICON_PATH__", icon_base_path))

    def _create_api_tab(self):
        """Create API settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # API Provider
        provider_group = QGroupBox("API Provider")
        provider_layout = QFormLayout(provider_group)

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
        model_layout.addRow("Timeout (seconds):", self.api_timeout_spin)

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
 
        self.ocr_timeout_spin = QSpinBox()
        self.ocr_timeout_spin.setRange(1, 300)
        ocr_layout.addRow("OCR Timeout (seconds):", self.ocr_timeout_spin)

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
        self.save_button.setObjectName("save_button")  # Set object name for specific styling
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
        self.ocr_auto_swap_checkbox.setChecked(bool(getattr(settings, "ocr_auto_swap_en_ru", False)))
        self.system_prompt_edit.setPlainText(settings.system_prompt)

        # OCR tab
        self.ocr_languages_edit.setText(",".join(settings.ocr_languages))
        self.ocr_confidence_spin.setValue(settings.ocr_confidence_threshold)
        self.ocr_timeout_spin.setValue(settings.ocr_timeout)
        self.initialize_ocr_check.setChecked(bool(getattr(settings, "initialize_ocr", False)))

        # Hotkeys tab
        self.translate_hotkey_edit.setText(settings.translate_hotkey)
        self.quick_translate_hotkey_edit.setText(settings.quick_translate_hotkey)
        self.activation_hotkey_edit.setText(settings.activation_hotkey)
        self.copy_translate_hotkey_edit.setText(settings.copy_translate_hotkey)

        # Copy-translate enhancements
        self.auto_copy_translated_check.setChecked(bool(getattr(settings, "auto_copy_translated", False)))
        self.clipboard_poll_timeout_spin.setValue(int(getattr(settings, "clipboard_poll_timeout_ms", 2000)))

        # General tab
        self.theme_combo.setCurrentText(settings.theme)
        self.log_level_combo.setCurrentText(getattr(settings, "log_level", "INFO"))
        self.show_notifications_check.setChecked(settings.show_notifications)

        # Reload models after loading settings to ensure dynamic loading
        logger.debug("About to call _load_models from _load_settings")
        provider_name = self.api_provider_combo.currentText()
        if provider_name.lower() == "openai":
            model_to_select = settings.openai_model
        elif provider_name.lower() == "google":
            model_to_select = settings.google_model
        else:
            model_to_select = None  # Fallback
        self._load_models(provider_name=provider_name, model_to_select=model_to_select)

    def _on_save(self):
        """Handle save button click."""
        try:
            # Create a mutable copy of the current settings
            settings_to_save = config_service.get_settings().model_copy(deep=True)

            # API Tab
            provider = self.api_provider_combo.currentText().lower()
            api_key_text = self.api_key_edit.text().strip() or None
            model_text = self.model_combo.currentText().strip()

            settings_to_save.api_provider = provider
            if provider == "openai":
                settings_to_save.openai_api_key = api_key_text
                settings_to_save.openai_model = model_text
            elif provider == "google":
                settings_to_save.google_api_key = api_key_text
                settings_to_save.google_model = model_text
            settings_to_save.api_timeout = self.api_timeout_spin.value()

            # Translation Tab
            settings_to_save.system_prompt = self.system_prompt_edit.toPlainText().strip()
            settings_to_save.ocr_auto_swap_en_ru = self.ocr_auto_swap_checkbox.isChecked()

            # OCR Tab
            settings_to_save.initialize_ocr = self.initialize_ocr_check.isChecked()
            settings_to_save.ocr_languages = [lang.strip() for lang in self.ocr_languages_edit.text().split(",") if lang.strip()]
            settings_to_save.ocr_confidence_threshold = self.ocr_confidence_spin.value()
            settings_to_save.ocr_timeout = self.ocr_timeout_spin.value()

            # Hotkeys Tab
            settings_to_save.translate_hotkey = self.translate_hotkey_edit.text().strip()
            settings_to_save.quick_translate_hotkey = self.quick_translate_hotkey_edit.text().strip()
            settings_to_save.activation_hotkey = self.activation_hotkey_edit.text().strip()
            settings_to_save.copy_translate_hotkey = self.copy_translate_hotkey_edit.text().strip()
            settings_to_save.auto_copy_translated = self.auto_copy_translated_check.isChecked()
            settings_to_save.clipboard_poll_timeout_ms = self.clipboard_poll_timeout_spin.value()
    
            # General Tab
            settings_to_save.theme = self.theme_combo.currentText()
            settings_to_save.log_level = self.log_level_combo.currentText().strip()
            settings_to_save.show_notifications = self.show_notifications_check.isChecked()

            logger.debug(f"Saving settings with theme: '{settings_to_save.theme}'")

            # Save settings asynchronously by passing the dictionary representation
            self.app.save_settings_async(settings_to_save.model_dump())

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
                        provider = self.api_provider_combo.currentText().strip()
                        self._load_models(provider_name=provider)
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

        # Create and start worker thread
        self.test_worker = ApiTestWorker(provider, api_key)
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

    def _load_models(self, provider_name: str = None, model_to_select: str = None):
        """Load available models for the current provider."""
        if provider_name is None:
            provider_name = self.api_provider_combo.currentText()

        logger.debug("=== _load_models called ===")
        logger.debug(f"Loading models for provider: {provider_name}")
        logger.debug(f"Model to select: '{model_to_select}'")

        # Check if API key is configured for the current provider
        api_key_configured = self._is_api_key_configured(provider_name)

        if not api_key_configured:
            logger.debug("No API key configured for provider, showing empty model list")
            self.model_combo.clear()
            self.model_combo.addItem("No API key configured")
            return

        # Clear current models and show loading state
        self.model_combo.clear()
        self.model_combo.addItem("Loading models...")

        try:
            from ..core.api_manager import init_api_manager
            api_manager = init_api_manager()  # Ensure API manager is initialized
            logger.debug(f"API manager initialized: {api_manager.is_initialized()}")

            # Unified synchronous fetch for all providers
            logger.debug("Fetching models synchronously via centralized API manager")
            provider_enum = APIProvider(provider_name)
            models, source = api_manager.get_available_models_sync(provider_enum)

            logger.debug(f"Loaded {len(models)} models from {source} for provider {provider_name}")

            if source == "unconfigured":
                logger.debug(f"Provider {provider_enum.value} not configured, cannot load models")
                self.model_combo.clear()
                self.model_combo.addItem("No API key configured")
                return

            self._apply_models_to_ui(models, model_to_select, source)

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            self._apply_models_to_ui([], model_to_select, "error")

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



    def _apply_models_to_ui(self, models: list, current_model: str, source: str = "unknown"):
        """Apply models to the UI combo box."""
        logger.debug(f"Applying {len(models)} models to UI: {models}")
        
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            logger.info(f"Successfully loaded {len(models)} models from {source.upper()} for the model selection dropdown.")

            # Restore previously selected model if it exists in the new list
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
            else:
                # Select first model as default if no match found
                self.model_combo.setCurrentText(models[0])
                logger.debug(f"✅ Selected default model: {models[0]}")
        else:
            # If no models are available, show a placeholder
            self.model_combo.addItem("No models available")
            logger.debug("❌ No models available to select")

        logger.debug(f"Final combo box current text: '{self.model_combo.currentText()}'")

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
        self._load_models(provider_name=self.api_provider_combo.currentText(), model_to_select=model_to_restore)

    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        if key == "theme":
            logger.debug(f"Theme setting changed from {old_value} to {new_value}")
            # Update current settings
            self.current_settings = config_service.get_settings()
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

    def closeEvent(self, event):
        """Handle dialog close event."""
        super().closeEvent(event)

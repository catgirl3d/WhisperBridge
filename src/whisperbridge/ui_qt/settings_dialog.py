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
from .workers import ApiTestWorker


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

        # Initialize the settings map
        self._init_settings_map()

        # Register as config service observer
        config_service.add_observer(self)

        # Load current values
        self._load_settings()

    def _init_settings_map(self):
        """Initialize the map between settings and widgets."""
        self.settings_map = {
            "api_provider": (self.api_provider_combo, "currentText", "setCurrentText"),
            "api_timeout": (self.api_timeout_spin, "value", "setValue"),
            "ocr_auto_swap_en_ru": (self.ocr_auto_swap_checkbox, "isChecked", "setChecked"),
            "system_prompt": (self.system_prompt_edit, "toPlainText", "setPlainText"),
            "initialize_ocr": (self.initialize_ocr_check, "isChecked", "setChecked"),
            "ocr_languages": (
                self.ocr_languages_edit,
                lambda w: [lang.strip() for lang in w.text().split(",") if lang.strip()],
                lambda w, v: w.setText(",".join(v)),
            ),
            "ocr_confidence_threshold": (self.ocr_confidence_spin, "value", "setValue"),
            "ocr_timeout": (self.ocr_timeout_spin, "value", "setValue"),
            "translate_hotkey": (self.translate_hotkey_edit, "text", "setText"),
            "quick_translate_hotkey": (self.quick_translate_hotkey_edit, "text", "setText"),
            "activation_hotkey": (self.activation_hotkey_edit, "text", "setText"),
            "copy_translate_hotkey": (self.copy_translate_hotkey_edit, "text", "setText"),
            "auto_copy_translated": (self.auto_copy_translated_check, "isChecked", "setChecked"),
            "clipboard_poll_timeout_ms": (self.clipboard_poll_timeout_spin, "value", "setValue"),
            "theme": (self.theme_combo, "currentText", "setCurrentText"),
            "log_level": (self.log_level_combo, "currentText", "setCurrentText"),
            "show_notifications": (self.show_notifications_check, "isChecked", "setChecked"),
        }

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
        model_layout.addRow("Model:", self.model_combo)

        # Don't load models here - they will be loaded in _load_settings
        logger.debug("Skipping model loading in _create_api_tab - will load in _load_settings")

        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(1, 300)
        model_layout.addRow("Timeout (seconds):", self.api_timeout_spin)

        layout.addWidget(model_group)

        layout.addStretch()

        self.tab_widget.addTab(tab, "API")

    def _update_api_key_field(self, settings):
        """Update the API key field label and content for the selected provider."""
        provider = self._get_current_provider()

        self.api_key_label.setText(f"{provider.capitalize()} API Key:")
        api_key = getattr(settings, f"{provider}_api_key", "") or ""
        self.api_key_edit.setText(api_key)

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

    def _get_current_provider(self) -> str:
        """Gets the current provider name, normalized."""
        return self.api_provider_combo.currentText().strip().lower()

    def _load_settings(self, settings=None):
        """Load current settings into the UI."""
        if settings is None:
            settings = config_service.get_settings()
        self.current_settings = settings
        logger.debug(f"Loading settings - theme: '{settings.theme}'")

        for key, (widget, _, setter) in self.settings_map.items():
            value = getattr(settings, key, None)
            if value is not None:
                if callable(setter):
                    setter(widget, value)
                else:
                    getattr(widget, setter)(value)

        # Special handling for API key and models
        self._update_api_key_field(settings)

        provider_name = self.api_provider_combo.currentText()
        model_to_select = getattr(settings, f"{provider_name.lower()}_model", None)
        self._load_models(provider_name=provider_name, model_to_select=model_to_select)

    def _on_save(self):
        """Handle save button click."""
        try:
            settings_to_save = config_service.get_settings().model_copy(deep=True)

            for key, (widget, getter, _) in self.settings_map.items():
                if callable(getter):
                    value = getter(widget)
                else:
                    value = getattr(widget, getter)()
                if isinstance(value, str):
                    value = value.strip()

                setattr(settings_to_save, key, value)

            # Special handling for provider-specific fields
            provider = self._get_current_provider()
            api_key_text = self.api_key_edit.text().strip() or None
            model_text = self.model_combo.currentText().strip()

            setattr(settings_to_save, f"{provider}_api_key", api_key_text)
            setattr(settings_to_save, f"{provider}_model", model_text)

            logger.debug(f"Saving settings with theme: '{settings_to_save.theme}'")

            # Save settings asynchronously
            config_service.save_settings_async(settings_to_save)

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
        provider = self._get_current_provider()

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
                        self._load_models(provider_name=self._get_current_provider())
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
        provider = self._get_current_provider()
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

        # Create and start worker
        self.test_worker = ApiTestWorker(provider, api_key)
        self.app.create_and_run_worker(self.test_worker, self._on_test_finished, self._on_test_error)

    def _on_test_finished(self, success: bool, error_msg: str, models: list, source: str):
        """Handle API test completion (models already fetched in worker to avoid second network call)."""
        # Re-enable button
        self.test_api_button.setEnabled(True)
        self.test_api_button.setText("Test API")

        if success:
            QMessageBox.information(self, "Test Successful", "API key is working correctly!")
            try:
                current_model = self.model_combo.currentText().strip()
                self._apply_models_to_ui(models, current_model, source)
                logger.info(f"Successfully applied {len(models)} models from {source} after API test without extra fetch.")
            except Exception as e:
                logger.error(f"Failed applying models after API test: {e}")
                QMessageBox.warning(self, "Model Apply Failed", f"API key is valid, but could not apply models: {e}")
        else:
            QMessageBox.warning(self, "Test Failed", f"API test failed: {error_msg}")

    def _on_test_error(self, error_message: str):
        """Handle API test error."""
        # Re-enable button
        self.test_api_button.setEnabled(True)
        self.test_api_button.setText("Test API")
        QMessageBox.warning(self, "Test Failed", f"API test failed: {error_message}")

    def _load_models(self, provider_name: str = None, model_to_select: str = None):
        """Load available models for the current provider."""
        # Normalize provider name if passed, or get from UI
        provider = (provider_name.strip().lower() if provider_name else self._get_current_provider())

        logger.debug("=== _load_models called ===")
        logger.debug(f"Loading models for provider: {provider}")
        logger.debug(f"Model to select: '{model_to_select}'")

        # Clear current models
        self.model_combo.clear()

        try:
            api_manager = get_api_manager()
            if not api_manager.is_initialized():
                logger.debug("API manager not initialized; skipping model fetch in UI. It will be initialized at app startup.")
                self._apply_models_to_ui([], model_to_select, "unconfigured")
                return

            # Unified synchronous fetch for all providers (API manager is the single SoT)
            logger.debug("Fetching models synchronously via centralized API manager")
            provider_enum = APIProvider(provider)

            # Derive temp_api_key from typed value if it differs from saved and has valid format
            temp_key = None
            try:
                typed_key = self.api_key_edit.text().strip()
                saved_key = getattr(config_service.get_settings(), f"{provider}_api_key", None) or ""
                if typed_key and typed_key != saved_key and validate_api_key_format(typed_key, provider):
                    temp_key = typed_key
                    logger.debug("Using temporary API key from input for model fetch")
            except Exception as ve:
                logger.debug(f"Temp API key validation skipped or failed: {ve}")

            models, source = api_manager.get_available_models_sync(
                provider=provider_enum,
                temp_api_key=temp_key
            )

            self._apply_models_to_ui(models, model_to_select, source)

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            self._apply_models_to_ui([], model_to_select, "error")

    def _apply_models_to_ui(self, models: list, current_model: str, source: str = "unknown"):
        """Apply models to the UI combo box."""
        logger.debug(f"Applying {len(models)} models to UI from source '{source}': {models}")

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
            # If no models are available, show a placeholder based on the source
            if source == "unconfigured":
                self.model_combo.addItem("No API key configured")
                logger.debug("❌ No API key configured, cannot select models.")
            else:
                self.model_combo.addItem("No models available")
                logger.debug(f"❌ No models available to select (source: {source})")

        logger.debug(f"Final combo box current text: '{self.model_combo.currentText()}'")

    def _on_provider_changed(self):
        """Handle provider change - update API key field and reload models."""
        if not self.isVisible():
            return

        provider = self._get_current_provider()
        settings = config_service.get_settings()

        # Get the model that was saved for the new provider
        model_to_restore = getattr(settings, f"{provider}_model", None)

        logger.debug(f"🔄 Provider changed to {provider}, attempting to restore model: '{model_to_restore}'")

        self._update_api_key_field(settings)
        self._load_models(provider_name=provider, model_to_select=model_to_restore)

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
        self._load_settings(settings=settings)

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        logger.debug("Settings saved")

        # Reinitialize API manager if API keys or provider changed.
        # This must be done BEFORE self.current_settings is updated.
        try:
            old_settings = self.current_settings
            api_keys_changed = settings.api_provider != old_settings.api_provider

            if not api_keys_changed:
                providers = [self.api_provider_combo.itemText(i) for i in range(self.api_provider_combo.count())]
                for provider in providers:
                    p_lower = provider.lower()
                    old_key = getattr(old_settings, f"{p_lower}_api_key", None) or ""
                    new_key = getattr(settings, f"{p_lower}_api_key", None) or ""
                    if old_key != new_key:
                        api_keys_changed = True
                        break
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

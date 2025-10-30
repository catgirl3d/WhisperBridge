"""
Settings Dialog for WhisperBridge Qt UI.

Provides a comprehensive settings interface with tabs for different configuration categories.
"""
from pathlib import Path
from typing import Optional, Union
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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import QThread, Signal, QObject, QTimer

from ..services.config_service import config_service, SettingsObserver
from ..core.api_manager import get_api_manager, APIProvider
from ..core.config import delete_api_key, validate_api_key_format, requires_model_selection, supports_stylist, Settings as DefaultSettings
from loguru import logger
from ..core.version import get_version
from .workers import ApiTestWorker
from ..utils.help_texts import HELP_TEXTS


from .base_window import BaseWindow


class SettingsDialog(QDialog, BaseWindow, SettingsObserver):
    """Settings dialog with tabbed interface for configuration."""

    MODEL_PLACEHOLDERS = {
        "No API key configured",
        "No models available",
        "Translation Engine",
        "Invalid API key format",
        "Failed to retrieve models list"
    }

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
        self._create_general_tab()
        self._create_api_tab()
        self._create_translation_tab()
        self._create_ocr_tab()
        self._create_hotkeys_tab()
        self._create_stylist_tab()

        # Connect vision model visibility signals
        self.api_provider_combo.currentTextChanged.connect(self._update_vision_model_visibility)
        # Connect all API key fields to vision model visibility update
        for edit in self.api_key_edits.values():
            edit.textChanged.connect(self._update_vision_model_visibility)
        
        # Debounce API key input to auto-load models
        self.api_key_debounce_timer = QTimer(self)
        self.api_key_debounce_timer.setSingleShot(True)
        self.api_key_debounce_timer.setInterval(500)  # 500ms delay
        self.api_key_debounce_timer.timeout.connect(self._load_models_from_key_input)
        # Connect debounce timer to all API key fields
        for edit in self.api_key_edits.values():
            edit.textChanged.connect(self.api_key_debounce_timer.start)

        # Create buttons
        self._create_buttons(layout)

        # Initialize the settings map
        self._init_settings_map()

        # Register as config service observer
        config_service.add_observer(self)

        # Load current values
        self._load_settings()

        # Update Stylist tab visibility based on initial provider
        self._update_stylist_tab_visibility()

        # Update vision model visibility based on initial provider and API key
        self._update_vision_model_visibility()

    def dismiss(self):
        """Dismiss the settings dialog by hiding it."""
        self.hide()

    def _init_settings_map(self):
        """Initialize the map between settings and widgets."""
        self.settings_map = {
            "api_provider": (self.api_provider_combo, "currentText", "setCurrentText"),
            "api_timeout": (self.api_timeout_spin, "value", "setValue"),
            "deepl_plan": (self.deepl_plan_combo, "currentText", "setCurrentText"),
            "auto_swap_en_ru": (self.ocr_auto_swap_checkbox, "isChecked", "setChecked"),
            "system_prompt": (self.system_prompt_edit, "toPlainText", "setPlainText"),
            "initialize_ocr": (self.initialize_ocr_check, "isChecked", "setChecked"),
            "ocr_engine": (self.ocr_engine_combo, "currentText", "setCurrentText"),
            "ocr_llm_prompt": (self.ocr_llm_prompt_edit, "toPlainText", "setPlainText"),
            "ocr_languages": (
                self.ocr_languages_edit,
                lambda w: [lang.strip() for lang in w.text().split(",") if lang.strip()],
                lambda w, v: w.setText(",".join(v)),
            ),
            "ocr_confidence_threshold": (self.ocr_confidence_spin, "value", "setValue"),
            "ocr_timeout": (self.ocr_timeout_spin, "value", "setValue"),
            "openai_vision_model": (self.openai_vision_model_edit, "text", "setText"),
            "google_vision_model": (self.google_vision_model_edit, "text", "setText"),
            "translate_hotkey": (self.translate_hotkey_edit, "text", "setText"),
            "quick_translate_hotkey": (self.quick_translate_hotkey_edit, "text", "setText"),
            "activation_hotkey": (self.activation_hotkey_edit, "text", "setText"),
            "copy_translate_hotkey": (self.copy_translate_hotkey_edit, "text", "setText"),
            "auto_copy_translated": (self.auto_copy_translated_check, "isChecked", "setChecked"),
            "auto_copy_translated_main_window": (self.auto_copy_translated_main_window_check, "isChecked", "setChecked"),
            "clipboard_poll_timeout_ms": (self.clipboard_poll_timeout_spin, "value", "setValue"),
            "theme": (self.theme_combo, "currentText", "setCurrentText"),
            "log_level": (self.log_level_combo, "currentText", "setCurrentText"),
            "show_notifications": (self.show_notifications_check, "isChecked", "setChecked"),
            "stylist_cache_enabled": (self.stylist_cache_checkbox, "isChecked", "setChecked"),
            "translation_cache_enabled": (self.translation_cache_checkbox, "isChecked", "setChecked"),
        }

    def _apply_stylesheet(self):
        """Apply the main stylesheet"""
        # Load the main stylesheet
        style_path = Path(__file__).resolve().parent.parent / "assets" / "style.qss"
        with open(style_path, 'r', encoding='utf-8') as f:
            stylesheet = f.read()

        # Replace assets_path placeholder with actual path
        assets_path = (Path(__file__).resolve().parent.parent / "assets").as_posix()
        stylesheet = stylesheet.replace("{assets_path}", assets_path)

        self.setStyleSheet(stylesheet)

    def _create_hint_label(self, text_or_widget: Union[str, QLabel], help_key: str) -> QWidget:
        """Create a label widget with hint button for form rows.

        Args:
            text_or_widget: Either a string (creates new QLabel) or existing QLabel widget
            help_key: Key in HELP_TEXTS dictionary

        Returns:
            QWidget containing label and hint button
        """
        from PySide6.QtWidgets import QToolButton
        from PySide6.QtCore import QPoint

        container = QWidget(self)  # Properly parent to dialog
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        if isinstance(text_or_widget, str):
            label = QLabel(text_or_widget)
        else:
            label = text_or_widget

        layout.addWidget(label)

        hint_button = QToolButton()
        hint_button.setObjectName("hintButton")
        hint_button.setText("?")
        hint_button.setAutoRaise(True)
        hint_button.setToolTip(HELP_TEXTS.get(help_key, {}).get("tooltip", ""))

        def show_detailed_hint():
            detailed = HELP_TEXTS.get(help_key, {}).get("detailed", "")
            if detailed:
                from PySide6.QtWidgets import QToolTip
                pos = hint_button.mapToGlobal(QPoint(0, hint_button.height()))
                QToolTip.showText(pos, detailed, hint_button)

        hint_button.clicked.connect(show_detailed_hint)
        layout.addWidget(hint_button)

        return container


    def _create_api_tab(self):
        """Create API settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # API Provider
        provider_group = QGroupBox("API Provider")
        provider_layout = QFormLayout(provider_group)

        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItems(["openai", "google", "deepl"])
        self.api_provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addRow(self._create_hint_label("Provider:", "api.provider"), self.api_provider_combo)

        # API Key fields (one for each provider)
        self.api_key_label = QLabel()  # Label will be updated dynamically
        self.api_key_label_container = self._create_hint_label(self.api_key_label, "api.key")

        # Create separate QLineEdit for each provider
        self.api_key_edits = {}
        for provider in ["openai", "google", "deepl"]:
            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setVisible(False)  # Initially hidden, will be shown based on selected provider
            self.api_key_edits[provider] = edit

        self.delete_api_key_button = QPushButton("Delete")
        self.delete_api_key_button.clicked.connect(self._on_delete_api_key)

        self.test_api_button = QPushButton("Test API")
        self.test_api_button.clicked.connect(self._on_test_api)

        key_layout = QHBoxLayout()
        key_layout.setContentsMargins(0, 0, 0, 0)
        # Add all provider key fields to the layout
        for provider, edit in self.api_key_edits.items():
            key_layout.addWidget(edit)
        key_layout.addWidget(self.delete_api_key_button)
        self.api_key_widget = QWidget()
        self.api_key_widget.setLayout(key_layout)

        provider_layout.addRow(self.api_key_label_container, self.api_key_widget)
        provider_layout.addRow(self.test_api_button)

        layout.addWidget(provider_group)

        # Model and Timeout
        model_group = QGroupBox("Model Settings")
        model_layout = QFormLayout(model_group)

        self.model_label = QLabel("Model:")
        self.model_label_container = self._create_hint_label(self.model_label, "api.model")
        self.model_combo = QComboBox()
        # Allow custom model input
        self.model_combo.setEditable(True)
        model_layout.addRow(self.model_label_container, self.model_combo)

        # Don't load models here - they will be loaded in _load_settings
        logger.debug("Skipping model loading in _create_api_tab - will load in _load_settings")

        self.api_timeout_spin = QSpinBox()
        self.api_timeout_spin.setRange(1, 300)
        model_layout.addRow(self._create_hint_label("Timeout (seconds):", "api.timeout"), self.api_timeout_spin)

        # Vision model fields
        self.openai_vision_model_label = QLabel("OpenAI Vision Model:")
        self.openai_vision_model_label_container = self._create_hint_label(self.openai_vision_model_label, "api.vision_model_openai")
        self.openai_vision_model_edit = QLineEdit()
        self.openai_vision_model_edit.setPlaceholderText("e.g., gpt-4-vision-preview")
        model_layout.addRow(self.openai_vision_model_label_container, self.openai_vision_model_edit)

        self.google_vision_model_label = QLabel("Google Vision Model:")
        self.google_vision_model_label_container = self._create_hint_label(self.google_vision_model_label, "api.vision_model_google")
        self.google_vision_model_edit = QLineEdit()
        self.google_vision_model_edit.setPlaceholderText("e.g., gemini-pro-vision")
        model_layout.addRow(self.google_vision_model_label_container, self.google_vision_model_edit)

        # DeepL plan selection (controls endpoint free/pro) - visible only for DeepL
        self.deepl_plan_label = QLabel("DeepL Plan:")
        self.deepl_plan_label_container = self._create_hint_label(self.deepl_plan_label, "api.deepl_plan")
        self.deepl_plan_combo = QComboBox()
        self.deepl_plan_combo.addItems(["free", "pro"])
        self.deepl_plan_combo.setToolTip(HELP_TEXTS.get("api.deepl_plan", {}).get("tooltip", ""))
        self.deepl_plan_label_container.setVisible(False)
        self.deepl_plan_combo.setVisible(False)
        model_layout.addRow(self.deepl_plan_label_container, self.deepl_plan_combo)

        layout.addWidget(model_group)

        layout.addStretch()

        self.tab_widget.addTab(tab, "API")


    def _create_translation_tab(self):
        """Create translation settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Translation options: Auto-swap and System Prompt
        # Auto-swap checkbox (EN <-> RU)
        self.ocr_auto_swap_checkbox = QCheckBox("Auto-swap EN ↔ RU")
        self.ocr_auto_swap_checkbox.setToolTip(HELP_TEXTS.get("translation.auto_swap", {}).get("tooltip", ""))
        layout.addWidget(self.ocr_auto_swap_checkbox)

        # System Prompt
        prompt_group = QGroupBox("System Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setAcceptRichText(False)
        self.system_prompt_edit.setPlaceholderText("Enter the system prompt for the translation model.")
        prompt_layout.addWidget(self._create_hint_label("System Prompt:", "translation.system_prompt"))
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

        # Initialize OCR on startup (enable/disable local OCR features)
        self.initialize_ocr_check = QCheckBox("Initialize local OCR engine (EasyOCR) on startup")
        self.initialize_ocr_check.setToolTip(HELP_TEXTS.get("ocr.initialize", {}).get("tooltip", ""))
        self.initialize_ocr_check.stateChanged.connect(self._update_vision_model_visibility)
        ocr_layout.addRow(self.initialize_ocr_check)

        # OCR Engine selector
        self.ocr_engine_combo = QComboBox()
        self.ocr_engine_combo.addItems(["easyocr", "llm"])
        ocr_layout.addRow(self._create_hint_label("OCR Engine:", "ocr.engine"), self.ocr_engine_combo)

        # LLM OCR Prompt
        self.ocr_llm_prompt_edit = QTextEdit()
        self.ocr_llm_prompt_edit.setAcceptRichText(False)
        self.ocr_llm_prompt_edit.setPlaceholderText("Enter the prompt for LLM-based OCR.")
        ocr_layout.addRow(self._create_hint_label("LLM OCR Prompt:", "ocr.llm_prompt"), self.ocr_llm_prompt_edit)

        # OCR Languages
        self.ocr_languages_edit = QLineEdit()
        self.ocr_languages_edit.setPlaceholderText("e.g., en,ru,es")
        ocr_layout.addRow(self._create_hint_label("OCR Languages:", "ocr.languages"), self.ocr_languages_edit)

        # Confidence threshold
        self.ocr_confidence_spin = QDoubleSpinBox()
        self.ocr_confidence_spin.setRange(0.0, 1.0)
        self.ocr_confidence_spin.setSingleStep(0.05)
        self.ocr_confidence_spin.setValue(0.7)
        ocr_layout.addRow(self._create_hint_label("Confidence Threshold:", "ocr.confidence_threshold"), self.ocr_confidence_spin)
        self.ocr_timeout_spin = QSpinBox()
        self.ocr_timeout_spin.setRange(1, 300)
        ocr_layout.addRow(self._create_hint_label("OCR Timeout (seconds):", "ocr.timeout"), self.ocr_timeout_spin)

        layout.addWidget(ocr_group)
        layout.addStretch()

        self._ocr_tab = tab
        self.tab_widget.addTab(tab, "OCR")

    def _create_hotkeys_tab(self):
        """Create hotkeys settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Hotkey settings group
        hotkey_group = QGroupBox("Hotkey Configuration")
        hotkey_layout = QFormLayout(hotkey_group)

        self.quick_translate_hotkey_edit = QLineEdit()
        hotkey_layout.addRow(self._create_hint_label("Show Translator Window:", "hotkeys.show_translator"), self.quick_translate_hotkey_edit)
        self.activation_hotkey_edit = QLineEdit()
        hotkey_layout.addRow(self._create_hint_label("Translate:", "hotkeys.translate"), self.activation_hotkey_edit)

        self.translate_hotkey_edit = QLineEdit()
        hotkey_layout.addRow(self._create_hint_label("Capture screen region (OCR):", "hotkeys.capture_screen"), self.translate_hotkey_edit)

        self.copy_translate_hotkey_edit = QLineEdit()
        hotkey_layout.addRow(self._create_hint_label("Copy→Translate Hotkey:", "hotkeys.copy_translate"), self.copy_translate_hotkey_edit)

        layout.addWidget(hotkey_group)

        # Help text
        help_label = QLabel("Use format like 'ctrl+shift+t' or 'alt+f1'")
        help_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(help_label)

        # Copy-translate options in a separate group box
        copy_group = QGroupBox("Copy-Translate Options")
        copy_layout = QFormLayout(copy_group)

        # Automatically copy translated text to clipboard (hotkey mode)
        self.auto_copy_translated_check = QCheckBox("Automatically copy translated text to clipboard (hotkey mode)")
        self.auto_copy_translated_check.setToolTip(HELP_TEXTS.get("hotkeys.auto_copy_hotkey", {}).get("tooltip", ""))
        copy_layout.addRow(self.auto_copy_translated_check)

        # Automatically copy translated text to clipboard (main translator window)
        self.auto_copy_translated_main_window_check = QCheckBox("Automatically copy translated text to clipboard (main translator window)")
        self.auto_copy_translated_main_window_check.setToolTip(HELP_TEXTS.get("hotkeys.auto_copy_main", {}).get("tooltip", ""))
        copy_layout.addRow(self.auto_copy_translated_main_window_check)

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
        ui_layout.addRow(self._create_hint_label("Theme:", "general.theme"), self.theme_combo)

        # Log level selection (exposed to users so they can change verbosity)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        ui_layout.addRow(self._create_hint_label("Log level:", "general.log_level"), self.log_level_combo)

        self.show_notifications_check = QCheckBox("Show notifications")
        ui_layout.addRow(self.show_notifications_check)

        # Text Stylist caching
        self.stylist_cache_checkbox = QCheckBox("Enable caching for Text Stylist mode")
        self.stylist_cache_checkbox.setToolTip(HELP_TEXTS.get("general.stylist_cache", {}).get("tooltip", ""))
        ui_layout.addRow(self.stylist_cache_checkbox)

        # Translation caching
        self.translation_cache_checkbox = QCheckBox("Enable caching for translations")
        self.translation_cache_checkbox.setToolTip(HELP_TEXTS.get("general.translation_cache", {}).get("tooltip", ""))
        ui_layout.addRow(self.translation_cache_checkbox)

        # Application version (read from package metadata / setuptools-scm)
        version_value = QLabel(get_version())
        ui_layout.addRow("Version:", version_value)

        layout.addWidget(ui_group)
        layout.addStretch()

        self.tab_widget.addTab(tab, "General")

    def _create_stylist_tab(self):
        """Create Text Stylist presets management tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Text Stylist Presets")
        gl = QVBoxLayout(group)

        # Table with two columns: Name, Prompt
        self.styles_table = QTableWidget()
        self.styles_table.setColumnCount(2)
        self.styles_table.setHorizontalHeaderLabels(["Name", "Prompt"])
        header = self.styles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.styles_table.setWordWrap(True)
        self.styles_table.setSelectionBehavior(self.styles_table.SelectionBehavior.SelectRows)
        self.styles_table.setSelectionMode(self.styles_table.SelectionMode.ExtendedSelection)
        self.styles_table.setEditTriggers(self.styles_table.EditTrigger.AllEditTriggers)

        gl.addWidget(self.styles_table)

        # Buttons row
        btn_row = QHBoxLayout()
        self.add_style_btn = QPushButton("Add")
        self.del_style_btn = QPushButton("Delete Selected")
        self.reset_style_btn = QPushButton("Reset to Defaults")

        self.add_style_btn.clicked.connect(self._on_add_style)
        self.del_style_btn.clicked.connect(self._on_delete_selected_styles)
        self.reset_style_btn.clicked.connect(self._on_reset_styles_defaults)

        btn_row.addWidget(self.add_style_btn)
        btn_row.addWidget(self.del_style_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.reset_style_btn)

        gl.addLayout(btn_row)
        layout.addWidget(group)
        layout.addStretch()

        self.tab_widget.addTab(tab, "Stylist")
        self._stylist_tab = tab

    def _populate_styles_table(self, styles):
        """Populate styles_table with the given styles list."""
        try:
            self.styles_table.setRowCount(0)
            for s in styles:
                name = ""
                prompt = ""
                if isinstance(s, dict):
                    name = (s.get("name") or "").strip()
                    prompt = (s.get("prompt") or "").strip()
                else:
                    # Fallback if stored differently
                    name = str(s).strip()
                    prompt = ""
                row = self.styles_table.rowCount()
                self.styles_table.insertRow(row)
                self.styles_table.setItem(row, 0, QTableWidgetItem(name))
                self.styles_table.setItem(row, 1, QTableWidgetItem(prompt))
        except Exception as e:
            logger.error(f"Failed to populate styles table: {e}")

    def _load_text_styles(self, settings):
        """Populate styles_table from settings.text_styles."""
        if not hasattr(self, "styles_table"):
            return
        try:
            styles = getattr(settings, "text_styles", []) or []
            if not isinstance(styles, list):
                styles = []
            self._populate_styles_table(styles)
        except Exception as e:
            logger.error(f"Failed to load styles into table: {e}")

    def _collect_text_styles_from_ui(self) -> list:
        """Collect styles from the table as a list of dicts."""
        styles = []
        try:
            rows = self.styles_table.rowCount() if hasattr(self, "styles_table") else 0
            for r in range(rows):
                name_item = self.styles_table.item(r, 0)
                prompt_item = self.styles_table.item(r, 1)
                name = (name_item.text() if name_item else "").strip()
                prompt = (prompt_item.text() if prompt_item else "").strip()
                if name and prompt:
                    styles.append({"name": name, "prompt": prompt})
        except Exception as e:
            logger.error(f"Failed to collect styles from UI: {e}")
        return styles

    def _on_add_style(self):
        """Add an empty style row for inline editing."""
        try:
            row = self.styles_table.rowCount()
            self.styles_table.insertRow(row)
            self.styles_table.setItem(row, 0, QTableWidgetItem("New Style"))
            self.styles_table.setItem(row, 1, QTableWidgetItem("Describe how to rewrite the text. Only return the rewritten text."))
            # Focus first cell for convenience
            self.styles_table.setCurrentCell(row, 0)
            item = self.styles_table.item(row, 0)
            if item:
                self.styles_table.editItem(item)
        except Exception as e:
            logger.error(f"Failed to add style row: {e}")

    def _on_delete_selected_styles(self):
        """Delete selected style rows."""
        try:
            selected = sorted({idx.row() for idx in self.styles_table.selectedIndexes()}, reverse=True)
            if not selected:
                return
            for r in selected:
                self.styles_table.removeRow(r)
        except Exception as e:
            logger.error(f"Failed to delete selected styles: {e}")

    def _on_reset_styles_defaults(self):
        """Reset styles to application defaults."""
        try:
            default_styles = []
            try:
                default_styles = type(config_service.get_settings())().text_styles
            except Exception:
                from ..core.config import Settings as _S
                default_styles = _S().text_styles

            self._populate_styles_table(default_styles or [])
        except Exception as e:
            logger.error(f"Failed to reset styles to defaults: {e}")

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

    def _set_model_ui_visibility(self, visible: bool):
        """Set the visibility and enablement of model selection UI elements."""
        try:
            if hasattr(self, "model_label_container") and self.model_label_container:
                self.model_label_container.setVisible(visible)
            self.model_combo.setVisible(visible)
            self.model_combo.setEnabled(visible)
        except Exception as e:
            logger.debug(f"Failed to set model UI visibility: {e}")

    def _update_control_visibility(self, control_type: str):
        """Generic method to update visibility of provider-dependent controls."""
        provider = self._get_current_provider()

        if control_type == "stylist":
            stylist_tab_index = self.tab_widget.indexOf(self._stylist_tab) if hasattr(self, '_stylist_tab') else -1
            if stylist_tab_index == -1:
                # Find the Stylist tab by name
                for i in range(self.tab_widget.count()):
                    if self.tab_widget.tabText(i) == "Stylist":
                        stylist_tab_index = i
                        self._stylist_tab = self.tab_widget.widget(i)
                        break

            if stylist_tab_index != -1:
                is_visible = supports_stylist(provider)
                self.tab_widget.setTabVisible(stylist_tab_index, is_visible)
                logger.debug(f"Stylist tab visibility set to {is_visible} for provider {provider}")

            # Also update the stylist cache checkbox visibility
            if hasattr(self, 'stylist_cache_checkbox'):
                visible = supports_stylist(provider)
                self.stylist_cache_checkbox.setVisible(visible)
                logger.debug(f"Stylist cache checkbox visibility set to {visible} for provider {provider}")

        elif control_type == "vision_model":
            # For vision models, we only need API key presence and OCR build flag
            # The initialize_ocr setting doesn't affect LLM OCR availability
            ocr_build_enabled = getattr(self.current_settings, 'ocr_enabled', True)

            # Define vision model controls for each provider
            vision_controls = [
                ("openai", self.openai_vision_model_label_container, self.openai_vision_model_edit),
                ("google", self.google_vision_model_label_container, self.google_vision_model_edit),
            ]

            api_key_present = bool(self.api_key_edits[provider].text().strip())

            for provider_name, label_container, edit_field in vision_controls:
                show_field = (provider == provider_name) and ocr_build_enabled

                # Update visibility for label container
                label_container.setVisible(show_field)

                # Update visibility and enablement for edit field
                edit_field.setVisible(show_field)
                edit_field.setEnabled(show_field and api_key_present)

        elif control_type == "deepl_plan":
            is_deepl = provider == "deepl"

            if hasattr(self, "deepl_plan_label_container"):
                self.deepl_plan_label_container.setVisible(is_deepl)
            if hasattr(self, "deepl_plan_combo"):
                self.deepl_plan_combo.setVisible(is_deepl)
                if is_deepl:
                    # Initialize from settings with fallback
                    current_plan = getattr(self.current_settings, "deepl_plan", None) or config_service.get_setting("deepl_plan") or "free"
                    self.deepl_plan_combo.setCurrentText(current_plan)

    def _update_stylist_tab_visibility(self):
        """Update the visibility of the Stylist tab and related settings based on the current provider."""
        self._update_control_visibility("stylist")

    def _update_vision_model_visibility(self):
        """Update the visibility and enablement of vision model fields based on provider, API key presence, and OCR enabled status."""
        self._update_control_visibility("vision_model")

    def _update_deepl_plan_controls(self):
        """Update the visibility and value of DeepL plan controls based on the current provider."""
        self._update_control_visibility("deepl_plan")

    def _load_settings(self, settings=None):
        """Load current settings into the UI."""
        if settings is None:
            # Force reload from disk to avoid race conditions with async saves
            settings = config_service.load_settings()
        self.current_settings = settings
        logger.debug(f"Loading settings - theme: '{settings.theme}'")

        for key, (widget, _, setter) in self.settings_map.items():
            value = getattr(settings, key, None)
            if value is not None:
                if callable(setter):
                    setter(widget, value)
                else:
                    getattr(widget, setter)(value)

        # Load API keys into their respective fields
        for provider in self.api_key_edits.keys():
            api_key = getattr(settings, f"{provider}_api_key", "") or ""
            self.api_key_edits[provider].setText(api_key)

        # Set initial visibility based on current provider
        current_provider = self.api_provider_combo.currentText().lower()
        for provider, edit in self.api_key_edits.items():
            edit.setVisible(provider == current_provider)
        self.api_key_label.setText(f"{current_provider.capitalize()} API Key:")

        provider_name = self.api_provider_combo.currentText()
        model_to_select = getattr(settings, f"{provider_name.lower()}_model", None)
        self._load_models(provider_name=provider_name, model_to_select=model_to_select)

        # Load Text Stylist presets
        try:
            self._load_text_styles(settings)
        except Exception as e:
            logger.warning(f"Failed to load text styles into UI: {e}")

        # Update stylist cache checkbox visibility based on current provider
        provider = self._get_current_provider()
        if hasattr(self, 'stylist_cache_checkbox'):
            self.stylist_cache_checkbox.setVisible(supports_stylist(provider))

        # Update OCR tab visibility based on ocr_enabled build flag
        if hasattr(self, '_ocr_tab'):
            ocr_tab_index = self.tab_widget.indexOf(self._ocr_tab)
            if ocr_tab_index != -1:
                ocr_visible = getattr(settings, 'ocr_enabled', True)
                self.tab_widget.setTabVisible(ocr_tab_index, ocr_visible)
                logger.debug(f"OCR tab visibility set to {ocr_visible} based on ocr_enabled={ocr_visible}")

        # Update DeepL plan controls visibility and value
        self._update_deepl_plan_controls()

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

            # Save API keys from all provider fields
            for provider, edit in self.api_key_edits.items():
                api_key_text = edit.text().strip() or None
                setattr(settings_to_save, f"{provider}_api_key", api_key_text)
                logger.debug(f"Saved API key for {provider}: {'****' if api_key_text else 'None'}")

            # Special handling for provider-specific fields
            provider = self._get_current_provider()
            model_text = self.model_combo.currentText().strip()

            if requires_model_selection(provider):
                # Do not save placeholder text as a model name.
                if model_text not in self.MODEL_PLACEHOLDERS:
                    setattr(settings_to_save, f"{provider}_model", model_text)
                else:
                    # If a placeholder is selected, we don't save it.
                    # This preserves the last known valid model in the settings file.
                    logger.debug(f"Ignoring model placeholder '{model_text}' during save to prevent corrupting settings.")

            # Collect Text Stylist presets from UI
            try:
                styles = self._collect_text_styles_from_ui()
                setattr(settings_to_save, "text_styles", styles)
            except Exception as e:
                logger.warning(f"Failed to collect text styles from UI: {e}")

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
                    # Clear the field for the current provider
                    self.api_key_edits[provider].setText("")
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
        api_key = self.api_key_edits[provider].text().strip()

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
                elif provider == "deepl":
                    msg = "Invalid API key format (expected DeepL key like UUID; free keys may end with ':fx')."
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

    def _reset_test_button(self):
        """Reset the test API button to its default state."""
        self.test_api_button.setEnabled(True)
        self.test_api_button.setText("Test API")

    def _on_test_finished(self, success: bool, error_msg: str, models: list, source: str):
        """Handle API test completion (models already fetched in worker to avoid second network call)."""
        # Re-enable button
        self._reset_test_button()

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
        self._reset_test_button()
        QMessageBox.warning(self, "Test Failed", f"API test failed: {error_message}")

    def _load_models(self, provider_name: Optional[str] = None, model_to_select: Optional[str] = None):
        """Load available models for the current provider."""
        # Normalize provider name if passed, or get from UI
        provider = (provider_name.strip().lower() if provider_name else self._get_current_provider())

        logger.debug("=== _load_models called ===")
        logger.debug(f"Loading models for provider: {provider}")
        logger.debug(f"Model to select: '{model_to_select}'")

        # Set model UI visibility based on provider requirements
        requires_model = requires_model_selection(provider)
        self._set_model_ui_visibility(requires_model)
        if not requires_model:
            self.model_combo.clear()
            self.model_combo.addItem("Translation Engine")
            logger.debug("Provider without model selection - model selection hidden/disabled")
            return

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
                typed_key = self.api_key_edits[provider].text().strip()
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

    def _apply_models_to_ui(self, models: list, current_model: Optional[str], source: str = "unknown"):
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
            elif source == "error":
                self.model_combo.addItem("Failed to retrieve models list")
                logger.debug(f"❌ Failed to get models list (source: {source})")
            else:
                self.model_combo.addItem("No models available")
                logger.debug(f"❌ No models available to select (source: {source})")

        logger.debug(f"Final combo box current text: '{self.model_combo.currentText()}'")

    def _on_provider_changed(self):
        """Handle provider change - update API key field visibility and reload models."""
        if not self.isVisible():
            return

        provider = self._get_current_provider()
        settings = config_service.get_settings()

        # Update API key field visibility - show only the field for the current provider
        for p, edit in self.api_key_edits.items():
            edit.setVisible(p == provider)

        # Update label
        self.api_key_label.setText(f"{provider.capitalize()} API Key:")

        # Get the model that was saved for the new provider (only when needed)
        model_to_restore = getattr(settings, f"{provider}_model", None) if requires_model_selection(provider) else None

        logger.debug(f"🔄 Provider changed to {provider}, attempting to restore model: '{model_to_restore}'")

        self._load_models(provider_name=provider, model_to_select=model_to_restore)
        self._update_stylist_tab_visibility()

        # Update DeepL plan controls visibility and value
        self._update_deepl_plan_controls()

    # SettingsObserver methods
    def on_settings_changed(self, key: str, old_value, new_value):
        """Called when a setting value changes."""
        if key == "theme":
            logger.debug(f"Theme setting changed from {old_value} to {new_value}")
            # Update current settings
            self.current_settings = config_service.get_settings()
            # Update the theme combo box to reflect the change
            self.theme_combo.setCurrentText(new_value)
        elif key == "auto_swap_en_ru":
            logger.debug(f"Auto-swap setting changed from {old_value} to {new_value}")
            self.ocr_auto_swap_checkbox.setChecked(bool(new_value))

    def on_settings_loaded(self, settings):
        """Called when settings are loaded."""
        logger.debug("Settings loaded")
        self.current_settings = settings
        self._load_settings(settings=settings)

    def on_settings_saved(self, settings):
        """Called when settings are saved."""
        logger.debug("Settings saved")
        # API manager reinitialization is now handled by ConfigService
        # Now, update the dialog's state with the new settings
        self.current_settings = settings

    def closeEvent(self, event):
        """Handle dialog close event."""
        super().closeEvent(event)

    def _load_models_from_key_input(self):
        """Slot for the debounce timer to reload models based on API key input."""
        provider = self._get_current_provider()
        api_key = self.api_key_edits[provider].text().strip()

        # Check if there's any key entered
        if not api_key:
            logger.debug("API key is empty, skipping model load.")
            return

        # Validate key format first
        if not validate_api_key_format(api_key, provider):
            logger.debug(f"API key format is invalid for {provider}. Showing format error.")
            # Show format error directly in the model combo
            self.model_combo.clear()
            self.model_combo.addItem("Invalid API key format")
            self.model_combo.setCurrentText("Invalid API key format")
            return

        # Key format is valid, proceed with loading models
        logger.debug(f"API key changed and format is valid for {provider}. Reloading models.")
        # Pass the currently selected model to preserve it if it's still valid
        current_model = self.model_combo.currentText().strip()
        if current_model in self.MODEL_PLACEHOLDERS:
            current_model = None # Don't try to re-select a placeholder
        self._load_models(provider_name=provider, model_to_select=current_model)


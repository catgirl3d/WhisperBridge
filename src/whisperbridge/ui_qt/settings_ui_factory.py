"""
Settings UI Factory module for creating settings dialog widgets.

Provides a centralized factory for creating and configuring widgets used in settings dialogs,
following the UI configuration guidelines.
"""

from PySide6.QtWidgets import QComboBox, QLineEdit, QSpinBox, QPushButton, QCheckBox, QTextEdit, QDoubleSpinBox, QTableWidget, QLabel, QToolButton, QGroupBox, QWidget, QTabWidget


class SettingsUIFactory:
    """Factory class for creating settings dialog widgets with centralized configuration."""

    # Configuration for settings widgets
    SETTINGS_WIDGET_CONFIG = {
        'apiProviderCombo': {
            'object_name': 'apiProviderCombo',
            'items': ['openai', 'google', 'deepl']
        },
        'openaiApiKeyEdit': {
            'object_name': 'openaiApiKeyEdit',
            'placeholder': '',
            'echo_mode': 'password',
            'visible': False
        },
        'googleApiKeyEdit': {
            'object_name': 'googleApiKeyEdit',
            'placeholder': '',
            'echo_mode': 'password',
            'visible': False
        },
        'deeplApiKeyEdit': {
            'object_name': 'deeplApiKeyEdit',
            'placeholder': '',
            'echo_mode': 'password',
            'visible': False
        },
        'apiDeleteButton': {
            'object_name': 'apiDeleteButton',
            'text': 'Delete'
        },
        'apiTestButton': {
            'object_name': 'apiTestButton',
            'text': 'Test API'
        },
        'modelCombo': {
            'object_name': 'modelCombo',
            'editable': True
        },
        'apiTimeoutSpin': {
            'object_name': 'apiTimeoutSpin',
            'range': (1, 300)
        },
        'openaiVisionModelEdit': {
            'object_name': 'openaiVisionModelEdit',
            'placeholder': 'e.g., gpt-4-vision-preview'
        },
        'googleVisionModelEdit': {
            'object_name': 'googleVisionModelEdit',
            'placeholder': 'e.g., gemini-pro-vision'
        },
        'deeplPlanCombo': {
            'object_name': 'deeplPlanCombo',
            'items': ['free', 'pro'],
            'visible': False
        },
        'autoSwapCheck': {
            'object_name': 'autoSwapCheck',
            'text': 'Auto-swap EN ↔ RU'
        },
        'systemPromptEdit': {
            'object_name': 'systemPromptEdit',
            'placeholder': 'Enter the system prompt for the translation model.'
        },
        'ocrLlmPromptEdit': {
            'object_name': 'ocrLlmPromptEdit',
            'placeholder': 'Enter the prompt for LLM-based OCR.'
        },
        'quickTranslateHotkeyEdit': {
            'object_name': 'quickTranslateHotkeyEdit'
        },
        'activationHotkeyEdit': {
            'object_name': 'activationHotkeyEdit'
        },
        'translateHotkeyEdit': {
            'object_name': 'translateHotkeyEdit'
        },
        'copyTranslateHotkeyEdit': {
            'object_name': 'copyTranslateHotkeyEdit'
        },
        'autoCopyTranslatedCheck': {
            'object_name': 'autoCopyTranslatedCheck',
            'text': 'Automatically copy translated text to clipboard (hotkey mode)'
        },
        'autoCopyTranslatedMainCheck': {
            'object_name': 'autoCopyTranslatedMainCheck',
            'text': 'Automatically copy translated text to clipboard (main translator window)'
        },
        'clipboardPollTimeoutSpin': {
            'object_name': 'clipboardPollTimeoutSpin',
            'range': (500, 10000),
            'single_step': 100
        },
        # 'themeCombo': {
        #     'object_name': 'themeCombo',
        #     'items': ['dark', 'light', 'system']
        # },
        'logLevelCombo': {
            'object_name': 'logLevelCombo',
            'items': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        },
        'showNotificationsCheck': {
            'object_name': 'showNotificationsCheck',
            'text': 'Show notifications'
        },
        'stylistCacheCheck': {
            'object_name': 'stylistCacheCheck',
            'text': 'Enable caching for Text Stylist mode'
        },
        'translationCacheCheck': {
            'object_name': 'translationCacheCheck',
            'text': 'Enable caching for translations'
        },
        'textStylistTable': {
            'object_name': 'textStylistTable',
            'columns': 2,
            'headers': ['Name', 'Prompt']
        },
        'addStyleButton': {
            'object_name': 'addStyleButton',
            'text': 'Add'
        },
        'deleteStyleButton': {
            'object_name': 'deleteStyleButton',
            'text': 'Delete Selected'
        },
        'resetStyleButton': {
            'object_name': 'resetStyleButton',
            'text': 'Reset to Defaults'
        },
        'versionLabel': {
            'object_name': 'versionLabel'
        },
        'hotkeysHelpLabel': {
            'object_name': 'hotkeysHelpLabel',
            'text': 'Use format like \'ctrl+shift+t\' or \'alt+f1\''
        },
        'saveButton': {
            'object_name': 'save_button',
            'text': 'Save'
        },
        'cancelButton': {
            'object_name': 'cancelButton',
            'text': 'Cancel'
        },
        'hintLabel': {
            'object_name': 'hintLabel'
        },
        'hintButton': {
            'object_name': 'hintButton'
        },
        'tabWidget': {
            'object_name': 'tabWidget'
        },
        'containerWidget': {
            'object_name': 'containerWidget'
        },
        'apiProviderGroup': {
            'object_name': 'apiProviderGroup',
            'title': 'API Provider'
        },
        'apiKeyWidget': {
            'object_name': 'apiKeyWidget'
        },
        'modelSettingsGroup': {
            'object_name': 'modelSettingsGroup',
            'title': 'Model Settings'
        },
        'systemPromptGroup': {
            'object_name': 'systemPromptGroup',
            'title': 'System Prompt'
        },
        'ocrConfigGroup': {
            'object_name': 'ocrConfigGroup',
            'title': 'OCR Configuration'
        },
        'hotkeyConfigGroup': {
            'object_name': 'hotkeyConfigGroup',
            'title': 'Hotkey Configuration'
        },
        'copyTranslateOptionsGroup': {
            'object_name': 'copyTranslateOptionsGroup',
            'title': 'Copy-Translate Options'
        },
        'uiGroup': {
            'object_name': 'uiGroup',
            'title': 'User Interface'
        },
        'textStylistPresetsGroup': {
            'object_name': 'textStylistPresetsGroup',
            'title': 'Text Stylist Presets'
        },
        'apiTab': {
            'object_name': 'apiTab'
        },
        'translationTab': {
            'object_name': 'translationTab'
        },
        'ocrTab': {
            'object_name': 'ocrTab'
        },
        'hotkeysTab': {
            'object_name': 'hotkeysTab'
        },
        'generalTab': {
            'object_name': 'generalTab'
        },
        'stylistTab': {
            'object_name': 'stylistTab'
        }
    }

    def create_combo(self, key: str) -> QComboBox:
        """Create a QComboBox widget using configuration."""
        config = self.get_config(key)
        combo = QComboBox()
        self.set_properties(combo, config)
        return combo

    def create_line_edit(self, key: str) -> QLineEdit:
        """Create a QLineEdit widget using configuration."""
        config = self.get_config(key)
        edit = QLineEdit()
        self.set_properties(edit, config)
        return edit

    def create_spin(self, key: str) -> QSpinBox:
        """Create a QSpinBox widget using configuration."""
        config = self.get_config(key)
        spin = QSpinBox()
        self.set_properties(spin, config)
        return spin

    def create_button(self, key: str) -> QPushButton:
        """Create a QPushButton widget using configuration."""
        config = self.get_config(key)
        button = QPushButton()
        self.set_properties(button, config)
        return button

    def create_check(self, key: str) -> QCheckBox:
        """Create a QCheckBox widget using configuration."""
        config = self.get_config(key)
        check = QCheckBox()
        self.set_properties(check, config)
        return check

    def create_text_edit(self, key: str) -> QTextEdit:
        """Create a QTextEdit widget using configuration."""
        config = self.get_config(key)
        text_edit = QTextEdit()
        self.set_properties(text_edit, config)
        return text_edit

    def create_double_spin(self, key: str) -> QDoubleSpinBox:
        """Create a QDoubleSpinBox widget using configuration."""
        config = self.get_config(key)
        spin = QDoubleSpinBox()
        self.set_properties(spin, config)
        return spin

    def create_table(self, key: str) -> QTableWidget:
        """Create a QTableWidget widget using configuration."""
        config = self.get_config(key)
        table = QTableWidget()
        self.set_properties(table, config)
        return table

    def create_label(self, key: str) -> QLabel:
        """Create a QLabel widget using configuration."""
        config = self.get_config(key)
        label = QLabel()
        self.set_properties(label, config)
        return label

    def create_tool_button(self, key: str) -> QToolButton:
        """Create a QToolButton widget using configuration."""
        config = self.get_config(key)
        button = QToolButton()
        self.set_properties(button, config)
        return button

    def create_group_box(self, key: str) -> QGroupBox:
        """Create a QGroupBox widget using configuration."""
        config = self.get_config(key)
        group = QGroupBox()
        self.set_properties(group, config)
        return group

    def create_widget(self, key: str) -> QWidget:
        """Create a QWidget widget using configuration."""
        config = self.get_config(key)
        widget = QWidget()
        self.set_properties(widget, config)
        return widget

    def create_tab_widget(self, key: str) -> QTabWidget:
        """Create a QTabWidget widget using configuration."""
        config = self.get_config(key)
        tab_widget = QTabWidget()
        self.set_properties(tab_widget, config)
        return tab_widget

    def set_properties(self, widget, cfg: dict) -> None:
        """Apply standard properties from config to widget."""
        if 'object_name' in cfg:
            widget.setObjectName(cfg['object_name'])
        if 'text' in cfg:
            widget.setText(cfg['text'])
        if 'placeholder' in cfg:
            widget.setPlaceholderText(cfg['placeholder'])
        if 'tooltip' in cfg and hasattr(widget, 'setToolTip'):
            widget.setToolTip(cfg['tooltip'])
        if 'visible' in cfg:
            widget.setVisible(cfg['visible'])
        if 'editable' in cfg and hasattr(widget, 'setEditable'):
            widget.setEditable(cfg['editable'])
        if 'items' in cfg and hasattr(widget, 'addItems'):
            widget.addItems(cfg['items'])
        if 'range' in cfg and hasattr(widget, 'setRange'):
            widget.setRange(*cfg['range'])
        if 'single_step' in cfg and hasattr(widget, 'setSingleStep'):
            widget.setSingleStep(cfg['single_step'])
        if 'echo_mode' in cfg and cfg['echo_mode'] == 'password' and hasattr(widget, 'setEchoMode'):
            widget.setEchoMode(QLineEdit.EchoMode.Password)
        if 'columns' in cfg and hasattr(widget, 'setColumnCount'):
            widget.setColumnCount(cfg['columns'])
        if 'headers' in cfg and hasattr(widget, 'setHorizontalHeaderLabels'):
            widget.setHorizontalHeaderLabels(cfg['headers'])
        if 'title' in cfg and hasattr(widget, 'setTitle'):
            widget.setTitle(cfg['title'])

    def get_config(self, key: str) -> dict:
        """Retrieve configuration for a given key."""
        return self.SETTINGS_WIDGET_CONFIG.get(key, {})
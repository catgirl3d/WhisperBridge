"""
Reader window implementation for Qt-based UI.

Configuration Guidelines:
- All widget styles should be centralized in CONFIG dictionaries
- Use consistent naming: {COMPONENT_TYPE}_CONFIG
- Include size, style, and any widget-specific properties
- Add objectName for widgets that need styling/testing
- Follow DRY principle - avoid hardcoded values

Key Principles:
1. Centralized Configuration: All styles in CONFIG dictionaries at class level
2. Explicit Mapping: Use explicit button-to-style mappings, not dynamic key generation
3. Unified Factory: Single _create_widget_from_config method for all widgets
4. ObjectName Usage: Set objectName for all testable/stylable widgets
5. Separation of Concerns: Python handles logic, QSS handles appearance
"""

from pathlib import Path

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QSizePolicy,
)

from .styled_overlay_base import StyledOverlayWindow

# Configuration dictionaries for UI components
READER_WINDOW_CONFIG = {
    'minimum_size': (500, 400),
    'default_font_size': 14,
    'font_family': "Arial",
    'font_size_min': 8,
    'font_size_max': 32,
    'font_size_step': 2,
    'text_display_padding': "10px",
}

READER_BUTTON_CONFIG = {
    'font_controls': {
        'size': (32, 32),
        'icon_size': (16, 16),
        'icon_color': "black",
    },
    'decrease': {
        'icon': "fa5s.minus",
        'tooltip': "Decrease font size",
        'object_name': "decreaseFontBtn",
    },
    'increase': {
        'icon': "fa5s.plus",
        'tooltip': "Increase font size",
        'object_name': "increaseFontBtn",
    },
}

# Configuration for label widgets
READER_LABEL_CONFIG = {
    'text_display': {
        'object_name': 'readerTextDisplay',
        'placeholder': "Translated text will appear here...",
    }
}


class ReaderWindow(StyledOverlayWindow):
    """Reader window for displaying translated text in a comfortable reading format."""

    def __init__(self):
        """Initialize the reader window."""
        super().__init__(title="Reader")
        self._current_font_size = READER_WINDOW_CONFIG['default_font_size']
        self._init_ui()
        logger.debug("ReaderWindow initialized")

    def _create_widget_from_config(self, widget_type: str, config_key: str, widget_class, **kwargs):
        """Generic factory method to create widgets from configuration dictionaries."""
        config_maps = {
            'button': READER_BUTTON_CONFIG,
            'label': READER_LABEL_CONFIG
        }
        
        config = config_maps[widget_type][config_key]
        widget = widget_class(**kwargs)
        
        # Apply common configuration properties
        if 'object_name' in config:
            widget.setObjectName(config['object_name'])
        if 'size' in config:
            widget.setFixedSize(*config['size'])
        if 'icon_size' in config:
            widget.setIconSize(QSize(*config['icon_size']))
        if 'icon_color' in config:
            # Will be applied by specific button methods
            pass
        if 'placeholder' in config:
            widget.setPlaceholderText(config['placeholder'])
            
        return widget, config

    def _init_ui(self):
        """Initialize the main UI widgets."""
        # Text display area
        self.text_display, _ = self._create_widget_from_config('label', 'text_display', QTextEdit)
        self.text_display.setReadOnly(True)
        self.text_display.setAcceptRichText(False)
        self.text_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.text_display.setFont(QFont(READER_WINDOW_CONFIG['font_family'], self._current_font_size))

        # Font size control buttons
        self.decrease_font_btn = self._create_decrease_button()
        self.increase_font_btn = self._create_increase_button()

        # Connect button signals
        self.decrease_font_btn.clicked.connect(self._decrease_font_size)
        self.increase_font_btn.clicked.connect(self._increase_font_size)

        # Layout for font controls
        font_controls_layout = QHBoxLayout()
        font_controls_layout.addStretch()
        font_controls_layout.addWidget(self.decrease_font_btn)
        font_controls_layout.addWidget(self.increase_font_btn)
        font_controls_layout.addStretch()

        # Assemble layout
        self.content_layout.addWidget(self.text_display, 1)
        self.content_layout.addLayout(font_controls_layout)

        # Set minimum size for comfortable reading
        self.setMinimumSize(*READER_WINDOW_CONFIG['minimum_size'])

    def _create_decrease_button(self) -> QPushButton:
        """Create the decrease font size button using configuration."""
        btn, config = self._create_widget_from_config('button', 'decrease', QPushButton)
        btn_config = READER_BUTTON_CONFIG['font_controls']
        
        # Apply button-specific configuration
        btn.setIcon(qta.icon(config['icon'], color=btn_config['icon_color']))
        btn.setToolTip(config['tooltip'])
        return btn

    def _create_increase_button(self) -> QPushButton:
        """Create the increase font size button using configuration."""
        btn, config = self._create_widget_from_config('button', 'increase', QPushButton)
        btn_config = READER_BUTTON_CONFIG['font_controls']
        
        # Apply button-specific configuration
        btn.setIcon(qta.icon(config['icon'], color=btn_config['icon_color']))
        btn.setToolTip(config['tooltip'])
        return btn

    def _decrease_font_size(self):
        """Decrease the font size of the text display."""
        if self._current_font_size > READER_WINDOW_CONFIG['font_size_min']:
            self._current_font_size -= READER_WINDOW_CONFIG['font_size_step']
            self._update_font_size()
            logger.debug(f"Font size decreased to {self._current_font_size}")

    def _increase_font_size(self):
        """Increase the font size of the text display."""
        if self._current_font_size < READER_WINDOW_CONFIG['font_size_max']:
            self._current_font_size += READER_WINDOW_CONFIG['font_size_step']
            self._update_font_size()
            logger.debug(f"Font size increased to {self._current_font_size}")

    def _update_font_size(self):
        """Update the font size of the text display."""
        font = self.text_display.font()
        font.setPointSize(self._current_font_size)
        self.text_display.setFont(font)

    def show_text(self, text: str):
        """Display the provided text in the reader window."""
        self.text_display.setPlainText(text)
        self.show_window()
        logger.debug("Reader window shown with text")

    def dismiss(self) -> None:
        """Dismiss the reader window."""
        logger.info("Dismissing reader window")
        super().dismiss()
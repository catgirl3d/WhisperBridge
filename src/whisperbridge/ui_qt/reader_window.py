"""
Reader window implementation for Qt-based UI.
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


class ReaderWindow(StyledOverlayWindow):
    """Reader window for displaying translated text in a comfortable reading format."""

    def __init__(self):
        """Initialize the reader window."""
        super().__init__(title="Reader")
        self._current_font_size = 14
        self._init_ui()
        logger.debug("ReaderWindow initialized")

    def _init_ui(self):
        """Initialize the main UI widgets."""
        # Text display area
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setAcceptRichText(False)
        self.text_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.text_display.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; border: none; padding: 10px; }")
        self.text_display.setFont(QFont("Arial", self._current_font_size))
        self.text_display.setPlaceholderText("Translated text will appear here...")

        # Font size control buttons
        self.decrease_font_btn = self._create_button(
            text="", icon=qta.icon("fa5s.minus", color="black"), size=(32, 32), tooltip="Decrease font size"
        )
        self.increase_font_btn = self._create_button(
            text="", icon=qta.icon("fa5s.plus", color="black"), size=(32, 32), tooltip="Increase font size"
        )

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
        self.setMinimumSize(500, 400)

    def _create_button(self, parent=None, text=None, icon=None, size=(32, 32), tooltip=None):
        """Generic button factory."""
        if parent is None:
            parent = self
        btn = QPushButton(parent)
        if text:
            btn.setText(text)
        if icon:
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(*size)
        if tooltip:
            btn.setToolTip(tooltip)
        return btn

    def _decrease_font_size(self):
        """Decrease the font size of the text display."""
        if self._current_font_size > 8:
            self._current_font_size -= 2
            self._update_font_size()
            logger.debug(f"Font size decreased to {self._current_font_size}")

    def _increase_font_size(self):
        """Increase the font size of the text display."""
        if self._current_font_size < 32:
            self._current_font_size += 2
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
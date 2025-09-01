"""
Overlay window implementation for Qt-based UI.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont


class OverlayWindow(QWidget):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__()

        # Configure window properties
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Set window size
        self.setFixedSize(400, 200)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Original text label
        self.original_label = QLabel("Original Text:")
        self.original_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self.original_label)

        # Original text display
        self.original_text = QTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setMaximumHeight(60)
        layout.addWidget(self.original_text)

        # Translated text label
        self.translated_label = QLabel("Translated Text:")
        self.translated_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self.translated_label)

        # Translated text display
        self.translated_text = QTextEdit()
        self.translated_text.setReadOnly(True)
        self.translated_text.setMaximumHeight(60)
        layout.addWidget(self.translated_text)

        # Set background color and opacity
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 180);
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 5px;
            }
            QLabel {
                color: white;
            }
            QTextEdit {
                background-color: rgba(255, 255, 255, 20);
                color: white;
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 3px;
            }
        """)

    def show_overlay(self, original_text: str, translated_text: str, position: tuple = None):
        """Show the overlay with specified content.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) position for the window
        """
        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

        if position:
            self.move(QPoint(position[0], position[1]))

        self.show()
        self.raise_()

    def hide_overlay(self):
        """Hide the overlay window."""
        self.hide()
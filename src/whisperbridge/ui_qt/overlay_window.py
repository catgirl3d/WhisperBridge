"""
Overlay window implementation for Qt-based UI.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QApplication
from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QFont, QKeyEvent

from loguru import logger


class OverlayWindow(QWidget):
    """Overlay window for displaying translation results."""

    def __init__(self):
        """Initialize the overlay window."""
        super().__init__()

        # Configure window properties — ordinary window with title and close button
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("WhisperBridge — Переводчик")
        # Default size (width x height). Height set to 430px as requested.
        self.resize(480, 430)
        self.setMinimumSize(320, 160)

        logger.debug("Overlay window configured as regular translator window")

        # Main vertical layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header: title and close button
        header_layout = QVBoxLayout()
        # Use a horizontal layout-like composition (keep simple)
        title_label = QLabel("Переводчик")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title_label)

        # Original text label and widget
        self.original_label = QLabel("Оригинал:")
        self.original_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self.original_label)

        self.original_text = QTextEdit()
        # Make the field interactive (editable) so user can select/modify text
        self.original_text.setReadOnly(False)
        self.original_text.setAcceptRichText(False)
        # Use a fixed comfortable height so buttons appear below
        self.original_text.setFixedHeight(100)
        # Make the text area expand horizontally
        from PySide6.QtWidgets import QSizePolicy
        self.original_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Placeholder test text for manual verification and visibility
        self.original_text.setPlainText("Тестовый оригинал: Здесь будет распознанный текст (заглушка).")
        self.original_text.setPlaceholderText("Здесь появится распознанный текст...")
        # Ensure explicit black text color and white background on the widget (override app palette)
        try:
            self.original_text.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        except Exception:
            logger.debug("Unable to apply style to original_text")
        layout.addWidget(self.original_text)

        # Small spacing before buttons
        layout.addSpacing(6)

        # Buttons row for original text (positioned under the field)
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSpacerItem, QSizePolicy
        btn_row_orig = QHBoxLayout()
        btn_row_orig.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.copy_original_btn = QPushButton("Копировать оригинал")
        # Ensure button size
        self.copy_original_btn.setFixedHeight(28)
        self.copy_original_btn.setFixedWidth(160)
        self.copy_original_btn.clicked.connect(self._copy_original_to_clipboard)
        btn_row_orig.addWidget(self.copy_original_btn)
        layout.addLayout(btn_row_orig)

        # Translated text label and widget
        self.translated_label = QLabel("Перевод:")
        self.translated_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(self.translated_label)

        self.translated_text = QTextEdit()
        # Make the field interactive (editable) so user can copy/modify text before copying out
        self.translated_text.setReadOnly(False)
        self.translated_text.setAcceptRichText(False)
        # Fixed height to avoid overlap with buttons
        self.translated_text.setFixedHeight(100)
        from PySide6.QtWidgets import QSizePolicy
        self.translated_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Placeholder test text for manual verification
        self.translated_text.setPlainText("Тестовый перевод: Здесь будет переведённый текст (заглушка).")
        self.translated_text.setPlaceholderText("Здесь появится перевод...")
        try:
            self.translated_text.setStyleSheet("QTextEdit { color: #111111; background-color: #ffffff; }")
        except Exception:
            logger.debug("Unable to apply style to translated_text")
        layout.addWidget(self.translated_text)

        # Small spacing before buttons
        layout.addSpacing(6)

        # Buttons row for translated text (positioned under the field)
        btn_row_tr = QHBoxLayout()
        btn_row_tr.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.copy_translated_btn = QPushButton("Копировать перевод")
        self.copy_translated_btn.setFixedHeight(28)
        self.copy_translated_btn.setFixedWidth(160)
        self.copy_translated_btn.clicked.connect(self._copy_translated_to_clipboard)
        btn_row_tr.addWidget(self.copy_translated_btn)
        layout.addLayout(btn_row_tr)

        # Footer row with Close button
        footer_row = QHBoxLayout()
        footer_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.hide_overlay)
        footer_row.addWidget(self.close_btn)
        layout.addLayout(footer_row)

        # Set background and styling — solid card with readable text
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 6px;
            }
            QLabel {
                color: #111111;
                border: none;
            }
            QTextEdit {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid rgba(0,0,0,0.08);
                border-radius: 4px;
            }
            QPushButton {
                color: #111111;
                padding: 6px 10px;
                border: none;
                border-radius: 4px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
        """)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("Escape key pressed, hiding overlay")
            self.hide_overlay()
        else:
            super().keyPressEvent(event)

    def _copy_original_to_clipboard(self):
        """Copy original text to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.original_text.toPlainText())
            logger.info("Original text copied to clipboard")
            # Simple user feedback via title change (transient)
            self.copy_original_btn.setText("Скопировано")
            QTimer.singleShot(1200, lambda: self.copy_original_btn.setText("Копировать оригинал"))
        except Exception as e:
            logger.error(f"Failed to copy original text: {e}")

    def _copy_translated_to_clipboard(self):
        """Copy translated text to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.translated_text.toPlainText())
            logger.info("Translated text copied to clipboard")
            self.copy_translated_btn.setText("Скопировано")
            QTimer.singleShot(1200, lambda: self.copy_translated_btn.setText("Копировать перевод"))
        except Exception as e:
            logger.error(f"Failed to copy translated text: {e}")

    def show_overlay(self, original_text: str = "", translated_text: str = "", position: tuple = None):
        """Show the overlay with specified content.

        Args:
            original_text: Original text to display
            translated_text: Translated text to display
            position: (x, y) position for the window (ignored for fullscreen)
        """
        logger.info("Showing overlay window")
        self.original_text.setPlainText(original_text)
        self.translated_text.setPlainText(translated_text)

        # For fullscreen overlay, position is ignored
        self.show()
        self.raise_()
        self.activateWindow()
        logger.debug("Overlay window shown and activated")

    def show_result(self, original_text: str, translated_text: str | None = None):
        """Show the overlay with OCR result.

        Args:
            original_text: OCR text to display
            translated_text: Translated text to display (optional)
        """
        self.show_overlay(original_text, translated_text or "")

    def hide_overlay(self):
        """Hide the overlay window."""
        logger.info("Hiding overlay window")
        self.hide()
        logger.debug("Overlay window hidden")

    def closeEvent(self, event):
        """Intercept window close (X) and hide the overlay instead of exiting the app."""
        try:
            logger.info("Overlay closeEvent triggered — hiding overlay instead of closing application")
            # Hide the overlay and ignore the close so application keeps running
            self.hide_overlay()
            event.ignore()
        except Exception as e:
            logger.error(f"Error handling closeEvent on overlay: {e}")
            # As a fallback, accept the event to avoid leaving the app in inconsistent state
            event.accept()

    def is_overlay_visible(self) -> bool:
        """Check if overlay is currently visible.

        Returns:
            bool: True if overlay is visible
        """
        return self.isVisible()
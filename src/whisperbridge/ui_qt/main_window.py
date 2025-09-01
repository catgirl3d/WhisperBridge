"""
Main window implementation for Qt-based UI.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class MainWindow(QMainWindow):
    """Main application window for Qt UI."""

    def __init__(self, on_save_callback=None):
        """Initialize the main window.

        Args:
            on_save_callback: Callback function for settings save events
        """
        super().__init__()

        self.on_save_callback = on_save_callback

        # Configure window
        self.setWindowTitle("WhisperBridge")
        self.setGeometry(100, 100, 800, 600)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create layout
        layout = QVBoxLayout(central_widget)

        # Add placeholder content
        title_label = QLabel("WhisperBridge Qt UI")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title_label)

        self.status_label = QLabel("Qt-based interface is under development")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Add interactive button to demonstrate responsiveness
        self.test_button = QPushButton("Click me to test!")
        self.test_button.setFont(QFont("Arial", 12))
        self.test_button.clicked.connect(self._on_button_clicked)
        layout.addWidget(self.test_button)

        # Connect close event
        self.closeEvent = self._on_close

    def _on_close(self, event):
        """Handle window close event."""
        # For now, just accept the close
        event.accept()

    def _on_button_clicked(self):
        """Handle button click to demonstrate responsiveness."""
        current_text = self.test_button.text()
        if current_text == "Click me to test!":
            self.test_button.setText("Button clicked! ✅")
            self.status_label.setText("Qt interface is working correctly!")
        else:
            self.test_button.setText("Click me to test!")
            self.status_label.setText("Qt-based interface is under development")

    def showEvent(self, event):
        """Handle window show event."""
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
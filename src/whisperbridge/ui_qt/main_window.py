"""
Main window implementation for Qt-based UI.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QFont

from ..core.settings_manager import settings_manager
from loguru import logger


class MainWindow(QMainWindow):
    """Main application window for Qt UI."""

    # Signal emitted when window should be closed to tray instead of exiting
    closeToTrayRequested = Signal()

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

        # Restore geometry on initialization
        self.restore_geometry()

    def _on_close(self, event):
        """Handle window close event."""
        logger.info("Main window close event triggered")
        # Save geometry before closing
        self.capture_geometry()
        # Emit signal to hide to tray instead of closing
        self.closeToTrayRequested.emit()
        event.ignore()
        self.hide()
        logger.debug("Main window hidden to tray")

    def restore_geometry(self):
        """Restore window geometry from settings."""
        try:
            settings = settings_manager.get_settings()
            if settings.window_geometry and len(settings.window_geometry) == 4:
                geometry = QRect(*settings.window_geometry)
                self.setGeometry(geometry)
                logger.debug(f"Window geometry restored: {geometry}")
            else:
                logger.debug("No saved geometry found, using defaults")
        except Exception as e:
            logger.error(f"Failed to restore window geometry: {e}")

    def capture_geometry(self):
        """Capture and save current window geometry."""
        try:
            geometry = self.geometry()
            geometry_data = [geometry.x(), geometry.y(), geometry.width(), geometry.height()]
    
            # Update settings only if geometry changed to avoid unnecessary full writes
            try:
                current = settings_manager.get_settings()
                current_geometry = getattr(current, "window_geometry", None)
            except Exception:
                current_geometry = None
    
            if current_geometry != geometry_data:
                # Use update_settings to change a single field (validates and saves safely)
                settings_manager.update_settings({"window_geometry": geometry_data})
                logger.debug(f"Window geometry captured and saved: {geometry_data}")
            else:
                logger.debug("Window geometry unchanged; skipping save.")
        except Exception as e:
            logger.error(f"Failed to capture window geometry: {e}")

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
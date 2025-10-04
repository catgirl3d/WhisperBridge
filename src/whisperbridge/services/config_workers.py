"""
Workers for configuration-related background tasks.
"""

from loguru import logger
from PySide6.QtCore import QObject, Signal

from ..core.config import Settings
from ..core.settings_manager import settings_manager


class SettingsSaveWorker(QObject):
    """Worker for saving settings asynchronously."""

    finished = Signal(bool, str)  # success, error_message
    error = Signal(str)

    def __init__(self, settings_to_save: Settings):
        super().__init__()
        self.settings_to_save = settings_to_save

    def run(self):
        """Save settings using the low-level settings manager."""
        try:
            if settings_manager.save_settings(self.settings_to_save):
                self.finished.emit(True, "Settings saved successfully.")
            else:
                self.error.emit("Failed to save settings.")
        except Exception as e:
            logger.error(f"Error in SettingsSaveWorker: {e}", exc_info=True)
            self.error.emit(f"An error occurred: {e}")
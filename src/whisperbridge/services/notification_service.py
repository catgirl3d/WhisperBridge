"""
Notification Service for WhisperBridge.

Centralized service for managing system tray notifications with different types
(INFO, WARNING, ERROR, SUCCESS) and thread-safe operations.
"""

from enum import Enum
from typing import Optional
from loguru import logger
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QSystemTrayIcon, QApplication

# Lazy import to avoid circular dependencies


class NotificationType(Enum):
    """Enumeration of notification types."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class NotificationService:
    """Centralized service for managing system tray notifications."""

    def __init__(self, tray_manager=None):
        """
        Initialize the notification service.

        Args:
            tray_manager: Optional tray manager instance
        """
        self.tray_manager = tray_manager
        self._enabled = True
        self._logger = logger

    def set_tray_manager(self, tray_manager):
        """
        Set the tray manager after initialization.

        Args:
            tray_manager: Tray manager instance
        """
        self.tray_manager = tray_manager

    def enable(self):
        """Enable notifications."""
        self._enabled = True
        self._logger.debug("Notification service enabled")

    def disable(self):
        """Disable notifications."""
        self._enabled = False
        self._logger.debug("Notification service disabled")

    def show(self, message: str, title: str = "WhisperBridge",
             notification_type: NotificationType = NotificationType.INFO,
             duration: int = 3000):
        """
        Show a notification through the system tray.

        Args:
            message: Notification message
            title: Notification title
            notification_type: Type of notification
            duration: Duration in milliseconds
        """
        if not self._enabled:
            self._logger.debug(f"Notification suppressed (disabled): {title} - {message}")
            return

        # Ensure execution on the main Qt thread
        try:
            app = QApplication.instance()
            if app and QThread.currentThread() != app.thread():
                QTimer.singleShot(0, lambda: self.show(message, title, notification_type, duration))
                self._logger.debug("Notification marshalled to main thread")
                return
        except Exception as e:
            self._logger.debug(f"Main-thread dispatch check failed: {e}")

        try:
            if self.tray_manager and hasattr(self.tray_manager, 'is_available') and self.tray_manager.is_available():
                # Map notification type to QSystemTrayIcon.MessageIcon
                icon_map = {
                    NotificationType.INFO: QSystemTrayIcon.MessageIcon.Information,
                    NotificationType.WARNING: QSystemTrayIcon.MessageIcon.Warning,
                    NotificationType.ERROR: QSystemTrayIcon.MessageIcon.Critical,
                    NotificationType.SUCCESS: QSystemTrayIcon.MessageIcon.Information,
                }

                icon = icon_map.get(notification_type, QSystemTrayIcon.MessageIcon.Information)

                # Show the notification
                if hasattr(self.tray_manager, 'tray_icon') and self.tray_manager.tray_icon:
                    self.tray_manager.tray_icon.showMessage(title, message, icon, duration)
                    self._logger.debug(f"Notification shown: {title} - {message} ({notification_type.value})")
                else:
                    self._logger.debug(f"Tray icon not available, notification not shown: {title} - {message}")
            else:
                self._logger.debug(f"Tray manager not available, notification not shown: {title} - {message}")
        except Exception as e:
            self._logger.error(f"Failed to show notification: {e}")

    def info(self, message: str, title: str = "WhisperBridge"):
        """
        Show an info notification.

        Args:
            message: Notification message
            title: Notification title
        """
        self.show(message, title, NotificationType.INFO)

    def success(self, message: str, title: str = "WhisperBridge"):
        """
        Show a success notification.

        Args:
            message: Notification message
            title: Notification title
        """
        self.show(message, title, NotificationType.SUCCESS)

    def warning(self, message: str, title: str = "WhisperBridge"):
        """
        Show a warning notification.

        Args:
            message: Notification message
            title: Notification title
        """
        self.show(message, title, NotificationType.WARNING)

    def error(self, message: str, title: str = "WhisperBridge"):
        """
        Show an error notification.

        Args:
            message: Notification message
            title: Notification title
        """
        self.show(message, title, NotificationType.ERROR)


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """
    Get the global notification service instance.

    Returns:
        NotificationService: Global notification service instance
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
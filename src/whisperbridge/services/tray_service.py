"""
System Tray Service for WhisperBridge.

This module provides system tray functionality including icon management,
context menu, notifications, and window visibility control.
"""

import threading
import time
from typing import Optional, Callable, Any
import pystray
from PIL import Image

from loguru import logger
from ..utils.icon_manager import icon_manager
from ..core.config import settings


class TrayService:
    """Service for managing system tray functionality."""

    def __init__(self, app_instance: Any):
        """
        Initialize the tray service.

        Args:
            app_instance: Reference to the main application instance
        """
        self.app = app_instance
        self.tray_icon: Optional[pystray.Icon] = None
        self._is_running = False
        self._status_callbacks: dict = {}
        self._menu_items: dict = {}

        # Threading
        self._tray_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def initialize(self) -> bool:
        """
        Initialize the system tray.

        Returns:
            bool: True if initialization successful
        """
        try:
            logger.info("Initializing system tray service...")

            # Create tray icon
            self._create_tray_icon()

            # Start tray in separate thread
            self._tray_thread = threading.Thread(
                target=self._run_tray,
                daemon=True,
                name="TrayService"
            )
            self._tray_thread.start()

            self._is_running = True
            logger.info("System tray service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize system tray: {e}")
            return False

    def _create_tray_icon(self):
        """Create the system tray icon with menu."""
        try:
            # Get main icon
            icon_data = icon_manager.get_icon('main', (32, 32))
            if icon_data:
                icon = Image.open(io.BytesIO(icon_data))
            else:
                # Fallback to simple icon
                icon = Image.new('RGB', (32, 32), color='blue')

            # Create menu
            menu = self._create_context_menu()

            # Create tray icon
            self.tray_icon = pystray.Icon(
                "WhisperBridge",
                icon,
                "WhisperBridge",
                menu
            )

            # Bind events
            self.tray_icon.on_left_click = self._on_left_click
            self.tray_icon.on_double_click = self._on_double_click

        except Exception as e:
            logger.error(f"Failed to create tray icon: {e}")
            raise

    def _create_context_menu(self) -> pystray.Menu:
        """Create the context menu for the tray icon."""
        try:
            menu_items = [
                pystray.MenuItem(
                    "Открыть настройки",
                    self._on_show_settings,
                    default=True
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Активировать перевод",
                    self._on_activate_translation
                ),
                pystray.MenuItem(
                    "Показать статус",
                    self._on_show_status
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "О программе",
                    self._on_show_about
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Выход",
                    self._on_exit
                )
            ]

            return pystray.Menu(*menu_items)

        except Exception as e:
            logger.error(f"Failed to create context menu: {e}")
            # Return minimal menu
            return pystray.Menu(
                pystray.MenuItem("Выход", self._on_exit)
            )

    def _run_tray(self):
        """Run the tray icon in a separate thread."""
        try:
            logger.debug("Starting tray icon loop...")
            self.tray_icon.run()
        except Exception as e:
            logger.error(f"Tray icon loop error: {e}")
        finally:
            logger.debug("Tray icon loop stopped")

    def _on_left_click(self, icon: pystray.Icon):
        """Handle left click on tray icon."""
        logger.debug("Tray icon left clicked")
        self.show_main_window()

    def _on_double_click(self, icon: pystray.Icon):
        """Handle double click on tray icon."""
        logger.debug("Tray icon double clicked")
        self.show_main_window()

    def _on_show_settings(self):
        """Handle show settings menu item."""
        logger.info("Tray: Show settings requested")
        self.show_main_window()

    def _on_activate_translation(self):
        """Handle activate translation menu item."""
        logger.info("Tray: Activate translation requested")
        # Trigger the same translation workflow as the hotkey
        if hasattr(self.app, '_on_translate_hotkey'):
            try:
                # Schedule the translation on the main GUI thread
                self.app.root.after(0, self.app._on_translate_hotkey)
                logger.info("Translation workflow triggered from tray")
            except Exception as e:
                logger.error(f"Failed to trigger translation from tray: {e}")
                self.show_notification(
                    "WhisperBridge",
                    "Ошибка запуска перевода"
                )
        else:
            logger.error("Translation method not available in app")
            self.show_notification(
                "WhisperBridge",
                "Функция перевода недоступна"
            )

    def _on_show_status(self):
        """Handle show status menu item."""
        logger.info("Tray: Show status requested")
        status = self._get_app_status()
        self.show_notification("Статус WhisperBridge", status)

    def _on_show_about(self):
        """Handle show about menu item."""
        logger.info("Tray: Show about requested")
        about_text = (
            "WhisperBridge v1.0.0\n"
            "Приложение для перевода текста с экрана\n"
            "Использует OCR и ИИ для точного перевода"
        )
        self.show_notification("О программе", about_text)

    def _on_exit(self):
        """Handle exit menu item."""
        logger.info("Tray: Exit requested. Scheduling app shutdown.")
        if hasattr(self.app, 'root') and hasattr(self.app, 'shutdown'):
            try:
                # Schedule the main application to shut down.
                # This must be done on the main GUI thread.
                self.app.root.after(50, self.app.shutdown)
            except Exception as e:
                logger.error(f"Failed to schedule app shutdown from tray: {e}")
                # As a fallback, try to stop the tray directly
                self.shutdown()

    def _get_app_status(self) -> str:
        """Get current application status."""
        try:
            if hasattr(self.app, 'is_app_running') and self.app.is_app_running():
                return "Приложение запущено и работает"
            else:
                return "Приложение остановлено"
        except Exception as e:
            logger.error(f"Failed to get app status: {e}")
            return "Статус неизвестен"

    def show_main_window(self):
        """
        Show the main application window in a thread-safe way.
        Schedules the window to be shown on the main GUI thread.
        """
        try:
            if hasattr(self.app, 'root') and self.app.root:
                self.app.root.after(0, self.app.show_main_window)
                logger.debug("Scheduled main window to be shown from tray")
        except Exception as e:
            logger.error(f"Failed to schedule showing main window: {e}")

    def hide_main_window(self):
        """
        Hide the main application window in a thread-safe way.
        Schedules the window to be hidden on the main GUI thread.
        """
        try:
            if hasattr(self.app, 'root') and self.app.root:
                self.app.root.after(0, self.app.hide_main_window)
                logger.debug("Scheduled main window to be hidden from tray")
        except Exception as e:
            logger.error(f"Failed to schedule hiding main window: {e}")

    def show_notification(self, title: str, message: str):
        """
        Show a system notification.

        Args:
            title: Notification title
            message: Notification message
        """
        try:
            if self.tray_icon:
                self.tray_icon.notify(message, title)
                logger.debug(f"Notification shown: {title}")
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def update_status_icon(self, is_active: bool = False, has_error: bool = False, is_loading: bool = False):
        """
        Update the tray icon based on application status.

        Args:
            is_active: Whether the app is actively processing
            has_error: Whether there's an error state
            is_loading: Whether the app is loading resources
        """
        try:
            if not self.tray_icon:
                return

            # Get appropriate icon
            icon_data = icon_manager.get_status_icon(is_active, has_error, is_loading)
            if icon_data:
                icon = Image.open(io.BytesIO(icon_data))
                self.tray_icon.icon = icon
                logger.debug(f"Tray icon updated: active={is_active}, error={has_error}, loading={is_loading}")

        except Exception as e:
            logger.error(f"Failed to update status icon: {e}")

    def shutdown(self):
        """
        Shutdown the tray service gracefully.
        This method should be called from the main thread as part of the
        application's shutdown sequence.
        """
        logger.info("Shutting down tray service...")
        self._is_running = False
    
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception as e:
                logger.error(f"Error stopping tray icon: {e}")
    
        # The thread is a daemon, so it will exit with the main application.
        # No need to join it here, especially since this can be called from the
        # tray thread itself.
        self.tray_icon = None
        logger.info("Tray service shutdown complete.")

    def is_running(self) -> bool:
        """Check if the tray service is running."""
        return self._is_running and self.tray_icon is not None

    def register_status_callback(self, name: str, callback: Callable):
        """
        Register a callback for status updates.

        Args:
            name: Callback name
            callback: Function to call on status change
        """
        self._status_callbacks[name] = callback
        logger.debug(f"Status callback registered: {name}")

    def unregister_status_callback(self, name: str):
        """
        Unregister a status callback.

        Args:
            name: Callback name to remove
        """
        if name in self._status_callbacks:
            del self._status_callbacks[name]
            logger.debug(f"Status callback unregistered: {name}")


# Import here to avoid circular imports
import io
"""
Tray Manager for Qt-based UI.
Provides system tray functionality with icon, menu, and event handling.
"""

import os
from typing import Optional, Callable
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction, QFont
from PySide6.QtCore import QObject, Signal

from loguru import logger


class TrayManager(QObject):
    """Manager for system tray functionality."""

    def __init__(self, on_show_main_window: Callable, on_toggle_overlay: Callable,
                 on_open_settings: Callable, on_exit_app: Callable, on_activate_ocr: Callable):
        """
        Initialize the tray manager.

        Args:
            on_show_main_window: Callback for showing main window
            on_toggle_overlay: Callback for toggling overlay
            on_open_settings: Callback for opening settings
            on_exit_app: Callback for exiting application
            on_activate_ocr: Callback for activating OCR
        """
        super().__init__()

        self.on_show_main_window = on_show_main_window
        self.on_toggle_overlay = on_toggle_overlay
        self.on_open_settings = on_open_settings
        self.on_exit_app = on_exit_app
        self.on_activate_ocr = on_activate_ocr

        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.tray_menu: Optional[QMenu] = None

        logger.info("TrayManager initialized")

    def create(self) -> bool:
        """
        Create and show the system tray icon.

        Returns:
            bool: True if successful
        """
        try:
            logger.info("Creating system tray icon...")

            # Create tray icon
            self.tray_icon = QSystemTrayIcon(self)

            # Try to load custom icon
            icon_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'assets', 'icons', 'app_tray.png')
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
                logger.debug(f"Loaded custom tray icon from: {icon_path}")
            else:
                # Use system default icon
                self.tray_icon.setIcon(QApplication.style().standardIcon(QApplication.style().StandardPixmap.SP_ComputerIcon))
                logger.debug("Using system default tray icon")

            # Create context menu
            self._create_context_menu()

            # Set menu
            self.tray_icon.setContextMenu(self.tray_menu)

            # Connect signals
            self.tray_icon.activated.connect(self._on_tray_activated)

            # Show tray icon
            self.tray_icon.show()

            logger.info("System tray icon created and shown successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to create system tray icon: {e}")
            return False

    def dispose(self):
        """Clean up tray resources."""
        try:
            logger.info("Disposing tray manager...")

            if self.tray_icon:
                self.tray_icon.hide()
                self.tray_icon.setParent(None)
                self.tray_icon = None

            if self.tray_menu:
                self.tray_menu.setParent(None)
                self.tray_menu = None

            logger.info("Tray manager disposed successfully")

        except Exception as e:
            logger.error(f"Error disposing tray manager: {e}")

    def _create_context_menu(self):
        """Create the context menu for the tray icon."""
        try:
            self.tray_menu = QMenu()

            # Ensure menu text is readable: prefer black text on light backgrounds
            try:
                # This stylesheet forces menu text color to black and gives a light background.
                # Platforms that ignore menu stylesheet will fall back to native look.
                self.tray_menu.setStyleSheet(
                    "QMenu { background-color: rgba(255,255,255,240); color: #111111; }"
                    "QMenu::item { color: #111111; }"
                    "QMenu::separator { height: 1px; background: rgba(0,0,0,0.08); margin: 6px 0; }"
                )
            except Exception:
                logger.debug("Unable to apply tray menu stylesheet on this platform")

            # Show Main Window action
            show_action = QAction("Показать окно", self)
            # Make the main/primary action visually stand out (bold)
            try:
                bold_font = QFont()
                bold_font.setBold(True)
                show_action.setFont(bold_font)
                # Mark as default action so some platforms show it highlighted
                self.tray_menu.setDefaultAction(show_action)
            except Exception:
                # Non-fatal if styling not supported on a platform
                logger.debug("Unable to style tray menu action (font/default) on this platform")
            show_action.triggered.connect(self._on_show_main_window)
            self.tray_menu.addAction(show_action)

            # Toggle Overlay action
            toggle_action = QAction("Переключить оверлей", self)
            toggle_action.triggered.connect(self._on_toggle_overlay)
            self.tray_menu.addAction(toggle_action)

            # Settings action
            settings_action = QAction("Настройки", self)
            settings_action.triggered.connect(self._on_open_settings)
            self.tray_menu.addAction(settings_action)

            # Activate OCR action
            activate_ocr_action = QAction("Активировать OCR", self)
            activate_ocr_action.triggered.connect(self._on_activate_ocr)
            self.tray_menu.addAction(activate_ocr_action)

            self.tray_menu.addSeparator()

            # Exit action
            exit_action = QAction("Выйти", self)
            exit_action.triggered.connect(self._on_exit_app)
            self.tray_menu.addAction(exit_action)

            logger.debug("Context menu created")

        except Exception as e:
            logger.error(f"Failed to create context menu: {e}")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle tray icon activation."""
        try:
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                logger.info("Tray icon double-clicked")
                self._on_show_main_window()
            elif reason == QSystemTrayIcon.ActivationReason.Trigger:
                logger.debug("Tray icon single-clicked")
        except Exception as e:
            logger.error(f"Error handling tray activation: {e}")

    def _on_show_main_window(self):
        """Handle show main window action."""
        try:
            logger.info("Tray: Show main window requested")
            if self.on_show_main_window:
                self.on_show_main_window()
        except Exception as e:
            logger.error(f"Error showing main window from tray: {e}")

    def _on_toggle_overlay(self):
        """Handle toggle overlay action."""
        try:
            logger.info("Tray: Toggle overlay requested")
            if self.on_toggle_overlay:
                self.on_toggle_overlay()
        except Exception as e:
            logger.error(f"Error toggling overlay from tray: {e}")

    def _on_open_settings(self):
        """Handle open settings action."""
        try:
            logger.info("Tray: Open settings requested")
            if self.on_open_settings:
                self.on_open_settings()
        except Exception as e:
            logger.error(f"Error opening settings from tray: {e}")

    def _on_activate_ocr(self):
        """Handle activate OCR action."""
        try:
            logger.info("Tray: Activate OCR requested")
            if self.on_activate_ocr:
                self.on_activate_ocr()
        except Exception as e:
            logger.error(f"Error activating OCR from tray: {e}")

    def _on_exit_app(self):
        """Handle exit application action."""
        try:
            logger.info("Tray: Exit application requested")
            if self.on_exit_app:
                self.on_exit_app()
        except Exception as e:
            logger.error(f"Error exiting application from tray: {e}")

    def show_notification(self, title: str, message: str):
        """
        Show a system notification.

        Args:
            title: Notification title
            message: Notification message
        """
        try:
            if self.tray_icon:
                self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
                logger.debug(f"Notification shown: {title}")
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")

    def is_available(self) -> bool:
        """
        Check if system tray is available.

        Returns:
            bool: True if available
        """
        return QSystemTrayIcon.isSystemTrayAvailable()
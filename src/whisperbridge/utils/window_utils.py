"""
Window utilities for WhisperBridge.

This module provides utilities for working with windows across different platforms.
Handles window detection, focus management, and input field identification.
"""

import time
from typing import Any, Dict, Optional

from loguru import logger

try:
    import pygetwindow as gw

    PYGETWINDOW_AVAILABLE = True
except ImportError:
    logger.warning("pygetwindow not available. Window utilities will be limited.")
    PYGETWINDOW_AVAILABLE = False
    gw = None

# Common application classes that typically have input fields
INPUT_FIELD_CLASSES = {
    "windows": [
        "edit",
        "richedit",
        "text",
        "combobox",
        "listbox",
        "chrome",
        "firefox",
        "edge",
        "opera",  # Browsers
        "notepad",
        "wordpad",
        "winword",
        "excel",  # Office apps
        "discord",
        "telegram",
        "skype",
        "teams",  # Messengers
        "slack",
        "whatsapp",
        "outlook",  # Communication
    ],
    "linux": [
        "gtkentry",
        "gtktextview",
        "qlineedit",
        "qtextedit",
        "qplaintextedit",
        "chromium",
        "firefox",
        "opera",
        "vivaldi",  # Browsers
        "gedit",
        "libreoffice",
        "soffice",  # Office
        "discord",
        "telegram",
        "skype",
        "teams",  # Messengers
        "slack",
        "thunderbird",  # Communication
    ],
    "darwin": [
        "nstextfield",
        "nstextview",
        "nsscrollview",
        "safari",
        "firefox",
        "chrome",
        "opera",  # Browsers
        "textedit",
        "pages",
        "numbers",
        "keynote",  # Office
        "messages",
        "discord",
        "telegram",
        "skype",
        "teams",  # Messengers
        "slack",
        "mail",  # Communication
    ],
}

# Window titles that indicate input fields
INPUT_FIELD_TITLES = [
    "new message",
    "compose",
    "reply",
    "comment",
    "search",
    "find",
    "type here",
    "enter text",
    "input",
    "chat",
    "message",
    "browser",
    "editor",
    "document",
    "spreadsheet",
]


class WindowUtils:
    """Utility class for window operations."""

    @staticmethod
    def get_platform() -> str:
        """Get the current platform."""
        import platform

        system = platform.system().lower()
        if system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        elif system == "darwin":
            return "darwin"
        else:
            return "unknown"

    @staticmethod
    def get_active_window() -> Optional[Any]:
        """Get the currently active window.

        Returns:
            Optional[Any]: Active window object or None if not found
        """
        if not PYGETWINDOW_AVAILABLE:
            logger.warning("pygetwindow not available")
            return None

        try:
            active = gw.getActiveWindow()
            return active
        except Exception as e:
            logger.error(f"Failed to get active window: {e}")
            return None

    @staticmethod
    def get_window_info(window: Any) -> Optional[Dict[str, Any]]:
        """Get detailed information about a window.

        Args:
            window: Window object

        Returns:
            Optional[Dict[str, Any]]: Window information or None if error
        """
        if not window:
            return None

        try:
            info = {}

            # Get title
            try:
                info["title"] = window.title
            except AttributeError:
                info["title"] = None

            # Get class
            try:
                info["class"] = getattr(window, "_class", None)
            except AttributeError:
                info["class"] = None

            # Get size
            try:
                info["size"] = window.size
            except AttributeError:
                info["size"] = None

            # Get position
            try:
                info["position"] = window.position
            except AttributeError:
                info["position"] = None

            # Get active state
            try:
                info["is_active"] = window.isActive
            except AttributeError:
                info["is_active"] = None

            # Get minimized state
            try:
                info["is_minimized"] = window.isMinimized
            except AttributeError:
                info["is_minimized"] = None

            # Get maximized state
            try:
                info["is_maximized"] = window.isMaximized
            except AttributeError:
                info["is_maximized"] = None

            return info
        except Exception as e:
            logger.error(f"Failed to get window info: {e}")
            return None

    @staticmethod
    def focus_window(window: Any) -> bool:
        """Focus/activate a window.

        Args:
            window: Window object to focus

        Returns:
            bool: True if successful, False otherwise
        """
        if not window:
            return False

        try:
            if not window.isActive:
                window.activate()
                # Small delay to ensure focus
                time.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"Failed to focus window: {e}")
            return False

    @staticmethod
    def is_input_field(window: Any) -> bool:
        """Determine if a window likely contains input fields.

        Args:
            window: Window object to check

        Returns:
            bool: True if likely has input fields, False otherwise
        """
        if not window:
            return False

        try:
            title = window.title.lower() if window.title else ""
            window_class = (
                getattr(window, "_class", "").lower()
                if hasattr(window, "_class")
                else ""
            )

            platform = WindowUtils.get_platform()
            platform_classes = INPUT_FIELD_CLASSES.get(platform, [])

            # Check window class
            for cls in platform_classes:
                if cls.lower() in window_class:
                    return True

            # Check window title
            for keyword in INPUT_FIELD_TITLES:
                if keyword in title:
                    return True

            # Additional heuristics
            if len(title) > 0 and not any(word in title for word in ['settings', 'preferences', 'about', 'help']):
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to check if window has input fields: {e}")
            return False

